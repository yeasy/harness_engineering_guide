"""Application composition root for context, security, retries, and tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, cast

from mini_harness.reliability.resilience import RetryConfig
from mini_harness.runtime.checkpoint import (
    CheckpointConflictError,
    CheckpointStore,
    InMemoryCheckpointStore,
    IncompleteCheckpointError,
)
from mini_harness.security.permissions import PermissionDecisionEngine
from mini_harness.security.secure_executor import SecureToolExecutor, ToolCall


class ToolNotFoundError(LookupError):
    """Raised when neither the local nor MCP registry exposes a tool."""


@dataclass(frozen=True)
class ApplicationToolResult:
    """Normalized result shared by local and MCP tools."""

    success: bool
    content: Any
    error_type: str | None = None
    source: str = "local"

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any]) -> "ApplicationToolResult":
        return cls(**data)


@dataclass(frozen=True)
class ApplicationEvent:
    """Sanitized event emitted by the composition root."""

    event_type: str
    trace_id: str
    metadata: dict[str, Any]


class HarnessApplication:
    """Route every tool through one security, retry, and checkpoint pipeline."""

    def __init__(
        self,
        *,
        tool_registry=None,
        secure_executor: SecureToolExecutor | None = None,
        mcp_registry=None,
        context_assembler=None,
        checkpoint_store: CheckpointStore | None = None,
        retry_config: RetryConfig | None = None,
        event_sink: Callable[[ApplicationEvent], None] | None = None,
    ):
        self.tool_registry = tool_registry
        self.mcp_registry = mcp_registry
        self.context_assembler = context_assembler
        self.secure_executor = secure_executor or SecureToolExecutor(
            PermissionDecisionEngine()
        )
        self.checkpoint_store = checkpoint_store or InMemoryCheckpointStore()
        self.retry_config = retry_config or RetryConfig()
        self.event_sink = event_sink
        self.event_trace: list[ApplicationEvent] = []

    async def prepare_context(self, user_input: str) -> str:
        """Assemble optional memory context without exposing it in event metadata."""
        context = ""
        if self.context_assembler is not None:
            context = await self.context_assembler.assemble(user_input)
        trace_id = secrets.token_hex(16)
        self._emit(
            "context.assembled",
            trace_id,
            context_chars=len(context),
            request_chars=len(user_input),
        )
        if not context:
            return user_input
        return f"{context}\n\n## Current Request\n{user_input}"

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        user_id: str,
        session_id: str,
        call_id: str,
        trace_id: str | None = None,
    ) -> ApplicationToolResult:
        """Execute one local or MCP tool with recovery-safe ordering."""
        current_trace = trace_id or secrets.token_hex(16)
        fingerprint = self._fingerprint(tool_name, arguments)
        self._emit(
            "tool.requested",
            current_trace,
            tool_name=tool_name,
            call_id=call_id,
        )

        checkpoint = await self.checkpoint_store.get(session_id, call_id)
        if checkpoint is not None:
            if checkpoint.fingerprint != fingerprint:
                raise CheckpointConflictError(
                    f"Checkpoint {session_id}/{call_id} was reused with different input"
                )
            if checkpoint.status == "completed" and checkpoint.result is not None:
                result = ApplicationToolResult.from_checkpoint(checkpoint.result)
                self._emit(
                    "tool.checkpoint_replay",
                    current_trace,
                    tool_name=tool_name,
                    call_id=call_id,
                )
                return result
            raise IncompleteCheckpointError(
                f"Tool call {session_id}/{call_id} may already have executed; refusing replay"
            )

        tool_call = ToolCall(tool_name=tool_name, args=dict(arguments), user_id=user_id)

        async def guarded_execution(approved_call: ToolCall) -> ApplicationToolResult:
            await self.checkpoint_store.begin(
                session_id,
                call_id,
                tool_name,
                fingerprint,
            )
            result = await self._execute_with_retry(approved_call, current_trace, call_id)
            await self.checkpoint_store.complete(
                session_id,
                call_id,
                fingerprint,
                asdict(result),
            )
            return result

        try:
            result = cast(
                ApplicationToolResult,
                await self.secure_executor.execute(tool_call, guarded_execution),
            )
        except PermissionError:
            self._emit(
                "tool.denied",
                current_trace,
                tool_name=tool_name,
                call_id=call_id,
            )
            raise

        self._emit(
            "tool.completed",
            current_trace,
            tool_name=tool_name,
            call_id=call_id,
            success=result.success,
            source=result.source,
        )
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        """List local tool schemas for model adapters and examples."""
        if self.tool_registry is None:
            return []
        return cast(list[dict[str, Any]], self.tool_registry.list_tools())

    async def _execute_with_retry(
        self,
        tool_call: ToolCall,
        trace_id: str,
        call_id: str,
    ) -> ApplicationToolResult:
        for attempt in range(1, self.retry_config.max_attempts + 1):
            self._emit(
                "tool.attempt",
                trace_id,
                tool_name=tool_call.tool_name,
                call_id=call_id,
                attempt=attempt,
            )
            try:
                return await self._invoke(tool_call)
            except Exception as error:
                if (
                    attempt >= self.retry_config.max_attempts
                    or not self.retry_config.should_retry(error)
                ):
                    raise
                self._emit(
                    "tool.retry",
                    trace_id,
                    tool_name=tool_call.tool_name,
                    call_id=call_id,
                    attempt=attempt,
                    error_type=type(error).__name__,
                )
                delay = self.retry_config.calculate_delay(attempt)
                if delay > 0:
                    await asyncio.sleep(delay)
        raise RuntimeError("unreachable retry state")

    async def _invoke(self, tool_call: ToolCall) -> ApplicationToolResult:
        if self.tool_registry is not None:
            tool = self.tool_registry.get(tool_call.tool_name)
            if tool is not None:
                result = await tool.call(tool_call.args)
                return ApplicationToolResult(
                    success=bool(result.success),
                    content=result.content,
                    error_type=result.error_type,
                    source="local",
                )

        if self.mcp_registry is not None:
            success, content, error = await self.mcp_registry.call_tool(
                tool_call.tool_name,
                tool_call.args,
                tool_call.user_id,
            )
            return ApplicationToolResult(
                success=success,
                content=content if success else error,
                error_type=None if success else "MCPToolError",
                source="mcp",
            )

        raise ToolNotFoundError(f"Tool '{tool_call.tool_name}' not found")

    def _emit(self, event_type: str, trace_id: str, **metadata: Any) -> None:
        event = ApplicationEvent(event_type=event_type, trace_id=trace_id, metadata=metadata)
        self.event_trace.append(event)
        if self.event_sink is not None:
            self.event_sink(event)

    @staticmethod
    def _fingerprint(tool_name: str, arguments: dict[str, Any]) -> str:
        encoded = json.dumps(
            {"tool_name": tool_name, "arguments": arguments},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
