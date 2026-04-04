"""
Integration tests for mini_harness.runtime module:
- runtime/engine.py: RuntimeEngine (async generator event stream)
- runtime/models.py: Message, AgentState, TextBlock, ToolUseBlock, ToolResultBlock
- runtime/events.py: Event types
"""

import pytest
import asyncio

from mini_harness.runtime.models import (
    Message, AgentState, TextBlock, ToolUseBlock, ToolResultBlock,
    MessageRole, ContentBlockType
)
from mini_harness.runtime.events import (
    Event, EventType,
    AgentStartEvent, TurnStartEvent, ErrorEvent,
    TextResponseEvent, ToolExecuteEvent, ToolResultEvent,
    TurnEndEvent, AgentEndEvent
)
from mini_harness.runtime.engine import RuntimeEngine


# ============ Runtime Models Tests ============

class TestRuntimeTextBlock:
    def test_defaults(self):
        block = TextBlock()
        assert block.type == "text"
        assert block.text == ""

    def test_to_dict(self):
        block = TextBlock(text="Hello")
        d = block.to_dict()
        assert d == {"type": "text", "text": "Hello"}


class TestRuntimeToolUseBlock:
    def test_auto_id(self):
        block = ToolUseBlock(name="bash_exec", input={"command": "ls"})
        assert block.id.startswith("tooluse_")
        assert block.name == "bash_exec"

    def test_to_dict(self):
        block = ToolUseBlock(name="test", input={"key": "val"})
        d = block.to_dict()
        assert d["type"] == "tool_use"
        assert d["name"] == "test"
        assert d["input"] == {"key": "val"}


class TestRuntimeToolResultBlock:
    def test_creation(self):
        block = ToolResultBlock(
            tool_use_id="tu_123",
            content="result output",
            is_error=False
        )
        assert block.tool_use_id == "tu_123"
        assert block.is_error is False

    def test_error_result(self):
        block = ToolResultBlock(
            tool_use_id="tu_456",
            content="error msg",
            is_error=True,
            error_type="TimeoutError"
        )
        assert block.is_error is True
        assert block.error_type == "TimeoutError"


class TestRuntimeMessage:
    def test_user_message(self):
        msg = Message.user("Hello")
        assert msg.role == "user"
        assert msg.get_text() == "Hello"
        assert msg.has_tool_calls() is False

    def test_assistant_text_message(self):
        msg = Message.assistant([TextBlock(text="Hi there")])
        assert msg.role == "assistant"
        assert msg.get_text() == "Hi there"

    def test_assistant_with_tool_call(self):
        msg = Message.assistant([
            TextBlock(text="Let me run a command."),
            ToolUseBlock(name="bash_exec", input={"command": "ls"})
        ])
        assert msg.has_tool_calls() is True
        calls = msg.get_tool_calls()
        assert len(calls) == 1
        assert calls[0].name == "bash_exec"

    def test_multiple_text_blocks(self):
        msg = Message.assistant([
            TextBlock(text="Part 1 "),
            TextBlock(text="Part 2")
        ])
        assert msg.get_text() == "Part 1 Part 2"

    def test_to_dict(self):
        msg = Message.user("Test")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert len(d["content"]) == 1
        assert "timestamp" in d
        assert "message_id" in d

    def test_unique_ids(self):
        m1 = Message.user("a")
        m2 = Message.user("b")
        assert m1.message_id != m2.message_id


class TestRuntimeAgentState:
    def test_creation(self):
        state = AgentState(session_id="sess-001")
        assert state.session_id == "sess-001"
        assert state.current_turn == 0
        assert len(state.messages) == 0

    def test_add_message(self):
        state = AgentState(session_id="sess-001")
        state.add_message(Message.user("Hello"))
        assert len(state.messages) == 1
        assert state.current_turn == 1

    def test_get_total_text_length(self):
        state = AgentState(session_id="sess-001")
        state.add_message(Message.user("Hello"))  # 5 chars
        state.add_message(Message.assistant([TextBlock(text="World")]))  # 5 chars
        assert state.get_total_text_length() == 10


# ============ Runtime Events Tests ============

class TestRuntimeEvents:
    def test_event_types(self):
        assert EventType.AGENT_START.value == "agent_start"
        assert EventType.TURN_START.value == "turn_start"
        assert EventType.ERROR.value == "error"

    def test_event_to_json(self):
        event = Event(event_type=EventType.AGENT_START, metadata={"key": "val"})
        j = event.to_json()
        assert "agent_start" in j
        assert "key" in j

    def test_specialized_events(self):
        assert AgentStartEvent().event_type == EventType.AGENT_START
        assert TurnStartEvent().event_type == EventType.TURN_START
        assert ErrorEvent().event_type == EventType.ERROR
        assert TextResponseEvent().event_type == EventType.TEXT_RESPONSE
        assert ToolExecuteEvent().event_type == EventType.TOOL_EXECUTE
        assert ToolResultEvent().event_type == EventType.TOOL_RESULT
        assert TurnEndEvent().event_type == EventType.TURN_END
        assert AgentEndEvent().event_type == EventType.AGENT_END


# ============ RuntimeEngine Integration Tests ============

class TestRuntimeEngine:
    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """Test that a simple query produces text response without tool calls."""
        engine = RuntimeEngine()
        events = []
        async for event in engine.run("Hello, how are you?"):
            events.append(event)

        # Should have: AgentStart, TurnStart, TextResponse, AgentEnd
        event_types = [e.event_type for e in events]
        assert EventType.AGENT_START in event_types
        assert EventType.TEXT_RESPONSE in event_types
        assert EventType.AGENT_END in event_types

    @pytest.mark.asyncio
    async def test_tool_call_response(self):
        """Test that a bash-related query triggers tool calls."""
        engine = RuntimeEngine()
        events = []
        async for event in engine.run("Run a bash command please"):
            events.append(event)

        event_types = [e.event_type for e in events]
        assert EventType.AGENT_START in event_types
        assert EventType.TOOL_EXECUTE in event_types
        # Tool result should indicate registry error (no registry configured)
        assert EventType.TOOL_RESULT in event_types

    @pytest.mark.asyncio
    async def test_event_stream_order(self):
        """Test that events are emitted in the correct order."""
        engine = RuntimeEngine()
        events = []
        async for event in engine.run("Hello"):
            events.append(event)

        # First event should be AgentStart
        assert events[0].event_type == EventType.AGENT_START
        # Last event should be AgentEnd
        assert events[-1].event_type == EventType.AGENT_END

    @pytest.mark.asyncio
    async def test_agent_end_metadata(self):
        """Test that AgentEnd event contains useful metadata."""
        engine = RuntimeEngine()
        last_event = None
        async for event in engine.run("Hello"):
            last_event = event

        assert last_event.event_type == EventType.AGENT_END
        assert "session_id" in last_event.metadata
        assert "turn_count" in last_event.metadata
        assert "final_response" in last_event.metadata

    @pytest.mark.asyncio
    async def test_max_turns_respected(self):
        """Test that the engine doesn't exceed max_turns."""
        engine = RuntimeEngine()
        engine.max_turns = 2

        turn_count = 0
        async for event in engine.run("Run a bash command"):
            if event.event_type == EventType.TURN_START:
                turn_count += 1

        assert turn_count <= 2

    @pytest.mark.asyncio
    async def test_no_tool_registry(self):
        """Test graceful handling when tool registry is None."""
        engine = RuntimeEngine(tool_registry=None)
        events = []
        async for event in engine.run("Execute bash command"):
            events.append(event)

        # Should still complete without crashing
        assert any(e.event_type == EventType.AGENT_END for e in events)

        # Tool result should indicate error
        tool_results = [e for e in events if e.event_type == EventType.TOOL_RESULT]
        if tool_results:
            assert tool_results[0].metadata.get("is_error") is True
