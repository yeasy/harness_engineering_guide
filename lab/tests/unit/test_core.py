"""
Tests for mini_harness.core module:
- message.py: Message, MessageRole, MessageType, ToolCallMessage, ToolResultMessage
- tool.py: ToolInputSchema, ToolDefinition, Tool
- agent.py: AgentState, ExecutionResult, Agent
- event.py: EventType, Event
"""

import json
from datetime import datetime

import pytest

from mini_harness.core.agent import Agent, AgentState, ExecutionResult
from mini_harness.core.event import Event, EventType
from mini_harness.core.message import (
    Message,
    MessageRole,
    MessageType,
    ToolCallMessage,
    ToolResultMessage,
)
from mini_harness.core.tool import Tool, ToolDefinition, ToolInputSchema

# ============ Message Tests ============


class TestMessageRole:
    def test_role_values(self):
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.TOOL.value == "tool"
        assert MessageRole.SYSTEM.value == "system"

    def test_role_is_string(self):
        assert isinstance(MessageRole.USER, str)
        assert MessageRole.USER == "user"


class TestMessageType:
    def test_type_values(self):
        assert MessageType.TEXT.value == "text"
        assert MessageType.TOOL_CALL.value == "tool_call"
        assert MessageType.TOOL_RESULT.value == "tool_result"
        assert MessageType.EVENT.value == "event"


class TestMessage:
    def test_create_message(self):
        msg = Message(role=MessageRole.USER, type=MessageType.TEXT, content="Hello, world!")
        assert msg.role == MessageRole.USER
        assert msg.type == MessageType.TEXT
        assert msg.content == "Hello, world!"
        assert msg.message_id is not None
        assert msg.parent_id is None
        assert msg.metadata == {}
        assert isinstance(msg.timestamp, datetime)

    def test_message_auto_id(self):
        msg1 = Message(role=MessageRole.USER, type=MessageType.TEXT, content="a")
        msg2 = Message(role=MessageRole.USER, type=MessageType.TEXT, content="b")
        assert msg1.message_id != msg2.message_id

    def test_message_with_metadata(self):
        msg = Message(
            role=MessageRole.ASSISTANT,
            type=MessageType.TEXT,
            content="Hi",
            metadata={"model": "claude-sonnet"},
        )
        assert msg.metadata["model"] == "claude-sonnet"

    def test_to_dict(self):
        msg = Message(
            role=MessageRole.USER, type=MessageType.TEXT, content="Test", message_id="test-id-123"
        )
        d = msg.to_dict()
        assert d["message_id"] == "test-id-123"
        assert d["role"] == "user"
        assert d["type"] == "text"
        assert d["content"] == "Test"
        assert d["parent_id"] is None
        assert "timestamp" in d

    def test_to_json(self):
        msg = Message(role=MessageRole.USER, type=MessageType.TEXT, content="Test")
        j = msg.to_json()
        data = json.loads(j)
        assert data["role"] == "user"
        assert data["content"] == "Test"

    def test_from_dict(self):
        data = {
            "role": "assistant",
            "type": "text",
            "content": "Hello!",
            "message_id": "msg-001",
            "metadata": {"key": "value"},
        }
        msg = Message.from_dict(data)
        assert msg.role == MessageRole.ASSISTANT
        assert msg.type == MessageType.TEXT
        assert msg.content == "Hello!"
        assert msg.message_id == "msg-001"
        assert msg.metadata["key"] == "value"

    def test_roundtrip_dict(self):
        original = Message(
            role=MessageRole.TOOL,
            type=MessageType.TOOL_RESULT,
            content="result data",
            metadata={"status": "ok"},
        )
        d = original.to_dict()
        restored = Message.from_dict(d)
        assert restored.role == original.role
        assert restored.type == original.type
        assert restored.content == original.content

    def test_parent_id(self):
        parent = Message(role=MessageRole.USER, type=MessageType.TEXT, content="parent")
        child = Message(
            role=MessageRole.ASSISTANT,
            type=MessageType.TEXT,
            content="child",
            parent_id=parent.message_id,
        )
        assert child.parent_id == parent.message_id


class TestToolCallMessage:
    def test_tool_call_properties(self):
        msg = ToolCallMessage(
            role=MessageRole.ASSISTANT,
            type=MessageType.TOOL_CALL,
            content="",
            metadata={"tool_name": "bash_exec", "tool_params": {"command": "ls -la"}},
        )
        assert msg.tool_name == "bash_exec"
        assert msg.tool_params == {"command": "ls -la"}

    def test_tool_call_no_params(self):
        msg = ToolCallMessage(
            role=MessageRole.ASSISTANT,
            type=MessageType.TOOL_CALL,
            content="",
            metadata={"tool_name": "list_tools"},
        )
        assert msg.tool_name == "list_tools"
        assert msg.tool_params == {}


class TestToolResultMessage:
    def test_success_status(self):
        msg = ToolResultMessage(
            role=MessageRole.TOOL,
            type=MessageType.TOOL_RESULT,
            content="output",
            metadata={"status": "success"},
        )
        assert msg.status == "success"
        assert msg.is_success is True

    def test_failure_status(self):
        msg = ToolResultMessage(
            role=MessageRole.TOOL,
            type=MessageType.TOOL_RESULT,
            content="error",
            metadata={"status": "error"},
        )
        assert msg.status == "error"
        assert msg.is_success is False

    def test_default_status(self):
        msg = ToolResultMessage(role=MessageRole.TOOL, type=MessageType.TOOL_RESULT, content="")
        assert msg.status == "unknown"
        assert msg.is_success is False


# ============ Tool Tests ============


class TestToolInputSchema:
    def test_defaults(self):
        schema = ToolInputSchema()
        assert schema.type == "object"
        assert schema.properties == {}
        assert schema.required == []

    def test_with_properties(self):
        schema = ToolInputSchema(properties={"name": {"type": "string"}}, required=["name"])
        assert "name" in schema.properties
        assert "name" in schema.required


class TestToolDefinition:
    def test_creation(self):
        schema = ToolInputSchema(properties={"cmd": {"type": "string"}}, required=["cmd"])
        defn = ToolDefinition(
            name="bash_exec",
            description="Execute bash commands",
            input_schema=schema,
            timeout_seconds=60,
        )
        assert defn.name == "bash_exec"
        assert defn.timeout_seconds == 60
        assert defn.permissions_required == []
        assert defn.tags == []

    def test_with_tags_and_permissions(self):
        defn = ToolDefinition(
            name="file_write",
            description="Write files",
            input_schema=ToolInputSchema(),
            permissions_required=["write"],
            tags=["filesystem"],
        )
        assert "write" in defn.permissions_required
        assert "filesystem" in defn.tags


class TestToolABC:
    def test_concrete_tool(self):
        """Test that a concrete tool implementation works."""

        class EchoTool(Tool):
            def name(self) -> str:
                return "echo"

            def description(self) -> str:
                return "Echo input"

            def input_schema(self) -> dict:
                return {"properties": {}, "required": []}

            async def call(self, params):
                return params.get("text", "")

        tool = EchoTool()
        assert tool.name() == "echo"
        assert tool.description() == "Echo input"

    def test_get_definition_dict(self):
        class DummyTool(Tool):
            def name(self) -> str:
                return "dummy"

            def description(self) -> str:
                return "A dummy tool"

            def input_schema(self) -> dict:
                return {"properties": {"x": {"type": "integer"}}, "required": ["x"]}

            async def call(self, params):
                return None

        tool = DummyTool()
        d = tool.get_definition_dict()
        assert d["name"] == "dummy"
        assert d["description"] == "A dummy tool"
        assert "x" in d["input_schema"]["properties"]
        assert "x" in d["input_schema"]["required"]


# ============ Agent Tests ============


class TestAgentState:
    def test_values(self):
        assert AgentState.IDLE.value == "idle"
        assert AgentState.EXECUTING.value == "executing"
        assert AgentState.COMPLETED.value == "completed"
        assert AgentState.FAILED.value == "failed"

    def test_is_string(self):
        assert isinstance(AgentState.IDLE, str)


class TestExecutionResult:
    def test_success(self):
        result = ExecutionResult(status="success", output="done")
        assert result.status == "success"
        assert result.output == "done"
        assert result.error is None
        assert result.metadata == {}

    def test_error(self):
        result = ExecutionResult(
            status="error", error="Something went wrong", metadata={"retry_count": 3}
        )
        assert result.status == "error"
        assert result.error == "Something went wrong"
        assert result.metadata["retry_count"] == 3


class TestAgent:
    def test_creation(self):
        agent = Agent(
            agent_id="agent-001",
            name="TestAgent",
            description="A test agent",
            system_prompt="You are helpful.",
        )
        assert agent.agent_id == "agent-001"
        assert agent.name == "TestAgent"
        assert agent.model_name == "claude-sonnet-4-20250514"
        assert agent.max_steps == 10
        assert agent.metadata == {}

    def test_custom_config(self):
        agent = Agent(
            agent_id="agent-002",
            name="CustomAgent",
            description="Custom",
            system_prompt="Custom prompt",
            model_name="claude-opus-4-20250514",
            max_steps=50,
            metadata={"role": "researcher"},
        )
        assert agent.model_name == "claude-opus-4-20250514"
        assert agent.max_steps == 50
        assert agent.metadata["role"] == "researcher"


# ============ Event Tests ============


class TestEventType:
    def test_task_events(self):
        assert EventType.TASK_STARTED.value == "task_started"
        assert EventType.TASK_COMPLETED.value == "task_completed"
        assert EventType.TASK_FAILED.value == "task_failed"

    def test_tool_events(self):
        assert EventType.TOOL_CALL_REQUESTED.value == "tool_call_requested"
        assert EventType.TOOL_EXECUTION_STARTED.value == "tool_execution_started"
        assert EventType.TOOL_EXECUTION_COMPLETED.value == "tool_execution_completed"


class TestEvent:
    def test_creation(self):
        event = Event(
            event_type=EventType.TASK_STARTED, source="runtime", data={"task_id": "task-001"}
        )
        assert event.event_type == EventType.TASK_STARTED
        assert event.source == "runtime"
        assert event.data["task_id"] == "task-001"
        assert event.event_id is not None
        assert isinstance(event.timestamp, datetime)

    def test_auto_id(self):
        e1 = Event(event_type=EventType.TASK_STARTED, source="a", data={})
        e2 = Event(event_type=EventType.TASK_STARTED, source="a", data={})
        assert e1.event_id != e2.event_id

    def test_to_dict(self):
        event = Event(
            event_type=EventType.TOOL_EXECUTION_COMPLETED,
            source="tool_layer",
            data={"result": "ok"},
            event_id="evt-001",
        )
        d = event.to_dict()
        assert d["event_id"] == "evt-001"
        assert d["event_type"] == "tool_execution_completed"
        assert d["source"] == "tool_layer"
        assert d["data"]["result"] == "ok"
        assert "timestamp" in d
