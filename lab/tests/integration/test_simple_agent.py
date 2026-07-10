"""The runnable example must use the application security pipeline."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from mini_harness.application import HarnessApplication
from mini_harness.core.tool import Tool, ToolResult
from mini_harness.security.permissions import PermissionDecisionEngine, PermissionLevel
from mini_harness.security.secure_executor import SecureToolExecutor
from mini_harness.tools.registry import ToolRegistry


EXAMPLE_PATH = Path(__file__).parents[2] / "examples" / "simple_agent.py"


def load_example_module():
    spec = importlib.util.spec_from_file_location("simple_agent_example", EXAMPLE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VisibleTool(Tool):
    def __init__(self):
        self.calls = 0

    async def call(self, params):
        self.calls += 1
        return ToolResult(True, f"visible:{params['value']}", 0)

    def name(self):
        return "visible_tool"

    def description(self):
        return "Expose one test result"

    def input_schema(self):
        return {"type": "object"}


class TwoTurnLLM:
    model = "fixture-model"

    def __init__(self):
        self.calls = 0

    async def chat_completion(self, messages, tools=None, stream=False):
        self.calls += 1
        if self.calls == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "stable-tool-call",
                                    "type": "function",
                                    "function": {
                                        "name": "visible_tool",
                                        "arguments": '{"value":"through-app"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "done"},
                    "finish_reason": "stop",
                }
            ]
        }


@pytest.mark.asyncio
async def test_simple_agent_routes_tools_through_harness_application():
    module = load_example_module()
    tool = VisibleTool()
    registry = ToolRegistry()
    registry.register(tool)
    permissions = PermissionDecisionEngine()
    permissions.register_policy("visible_tool", PermissionLevel.OVERRIDE)
    application = HarnessApplication(
        tool_registry=registry,
        secure_executor=SecureToolExecutor(permissions),
    )

    agent = module.SimpleAgent(llm=TwoTurnLLM(), application=application)
    response = await agent.run("use the visible tool")

    assert response == "done"
    assert tool.calls == 1
    assert "tool.completed" in [event.event_type for event in application.event_trace]
