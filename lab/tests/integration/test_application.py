"""Integration coverage for the application composition root."""

from __future__ import annotations

from typing import Any

import pytest

from mini_harness.application import HarnessApplication
from mini_harness.core.tool import Tool, ToolResult
from mini_harness.reliability.resilience import RetryConfig
from mini_harness.runtime.checkpoint import JSONCheckpointStore
from mini_harness.security.permissions import PermissionDecisionEngine, PermissionLevel
from mini_harness.security.secure_executor import SecureToolExecutor
from mini_harness.tools.registry import ToolRegistry


class CountingTool(Tool):
    def __init__(self, tool_name: str = "count", failures_before_success: int = 0):
        self.tool_name = tool_name
        self.failures_before_success = failures_before_success
        self.attempts = 0
        self.side_effects = 0

    async def call(self, params: dict[str, Any]) -> ToolResult:
        self.attempts += 1
        if self.attempts <= self.failures_before_success:
            raise ConnectionError("temporary transport failure")
        self.side_effects += 1
        return ToolResult(
            success=True,
            content=f"counted:{params['value']}",
            execution_time=0,
        )

    def name(self) -> str:
        return self.tool_name

    def description(self) -> str:
        return "Count a visible side effect"

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }


class StaticContextAssembler:
    async def assemble(self, user_message: str) -> str:
        return "## Project Context\nrelease branch"


class FakeMCPRegistry:
    def __init__(self):
        self.tool_to_servers = {"remote_write": ["fixture"]}
        self.calls = 0

    async def call_tool(self, tool_name, arguments, agent_id=None):
        self.calls += 1
        return True, f"remote:{arguments['value']}", ""


def secure_executor(tool_name: str, level: PermissionLevel) -> SecureToolExecutor:
    permissions = PermissionDecisionEngine()
    permissions.register_policy(tool_name, level)
    return SecureToolExecutor(permission_engine=permissions)


def local_application(
    tool: CountingTool,
    *,
    level: PermissionLevel = PermissionLevel.OVERRIDE,
    context_assembler=None,
    checkpoint_store=None,
    retry_config=None,
) -> HarnessApplication:
    registry = ToolRegistry()
    registry.register(tool)
    return HarnessApplication(
        tool_registry=registry,
        secure_executor=secure_executor(tool.name(), level),
        context_assembler=context_assembler,
        checkpoint_store=checkpoint_store,
        retry_config=retry_config,
    )


@pytest.mark.asyncio
async def test_context_is_composed_before_the_current_request():
    app = local_application(CountingTool(), context_assembler=StaticContextAssembler())

    prompt = await app.prepare_context("ship it")

    assert prompt == "## Project Context\nrelease branch\n\n## Current Request\nship it"
    assert app.event_trace[-1].event_type == "context.assembled"
    assert "release branch" not in str(app.event_trace[-1].metadata)


@pytest.mark.asyncio
async def test_deny_happens_before_local_tool_side_effect():
    tool = CountingTool("dangerous_write")
    app = local_application(tool, level=PermissionLevel.DENY)

    with pytest.raises(PermissionError, match="denied by policy"):
        await app.execute_tool(
            "dangerous_write",
            {"value": "blocked"},
            user_id="user-1",
            session_id="session-deny",
            call_id="call-deny",
        )

    assert tool.attempts == 0
    assert tool.side_effects == 0
    assert app.event_trace[-1].event_type == "tool.denied"


@pytest.mark.asyncio
async def test_retry_attempts_share_one_trace_and_emit_retry_event():
    tool = CountingTool(failures_before_success=1)
    app = local_application(
        tool,
        retry_config=RetryConfig(
            max_attempts=2,
            initial_delay=0,
            max_delay=0,
            jitter=False,
            retryable_exceptions={ConnectionError},
        ),
    )

    result = await app.execute_tool(
        "count",
        {"value": "once"},
        user_id="user-1",
        session_id="session-retry",
        call_id="call-retry",
        trace_id="a" * 32,
    )

    assert result.success is True
    assert result.content == "counted:once"
    assert tool.attempts == 2
    assert tool.side_effects == 1
    assert [event.event_type for event in app.event_trace] == [
        "tool.requested",
        "tool.attempt",
        "tool.retry",
        "tool.attempt",
        "tool.completed",
    ]
    assert {event.trace_id for event in app.event_trace} == {"a" * 32}


@pytest.mark.asyncio
async def test_checkpoint_recovery_reuses_result_without_duplicate_side_effect(tmp_path):
    checkpoint_path = tmp_path / "runtime-checkpoints.json"
    tool = CountingTool()
    first = local_application(tool, checkpoint_store=JSONCheckpointStore(checkpoint_path))

    initial = await first.execute_tool(
        "count",
        {"value": "durable"},
        user_id="user-1",
        session_id="session-resume",
        call_id="call-stable",
    )
    assert initial.content == "counted:durable"
    assert tool.side_effects == 1

    resumed = local_application(tool, checkpoint_store=JSONCheckpointStore(checkpoint_path))
    replayed = await resumed.execute_tool(
        "count",
        {"value": "durable"},
        user_id="user-1",
        session_id="session-resume",
        call_id="call-stable",
    )

    assert replayed == initial
    assert tool.side_effects == 1
    assert resumed.event_trace[-1].event_type == "tool.checkpoint_replay"


@pytest.mark.asyncio
async def test_mcp_tool_uses_the_same_secure_executor():
    mcp = FakeMCPRegistry()
    denied = HarnessApplication(
        secure_executor=secure_executor("remote_write", PermissionLevel.DENY),
        mcp_registry=mcp,
    )

    with pytest.raises(PermissionError):
        await denied.execute_tool(
            "remote_write",
            {"value": "blocked"},
            user_id="user-1",
            session_id="session-mcp-deny",
            call_id="call-mcp-deny",
        )
    assert mcp.calls == 0

    allowed = HarnessApplication(
        secure_executor=secure_executor("remote_write", PermissionLevel.OVERRIDE),
        mcp_registry=mcp,
    )
    result = await allowed.execute_tool(
        "remote_write",
        {"value": "allowed"},
        user_id="user-1",
        session_id="session-mcp-allow",
        call_id="call-mcp-allow",
    )
    assert result.success is True
    assert result.content == "remote:allowed"
    assert result.source == "mcp"
    assert mcp.calls == 1
