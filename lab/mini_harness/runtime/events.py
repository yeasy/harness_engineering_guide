"""
mini_harness/runtime/events.py
事件定义和流处理
"""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from typing import AsyncIterator, Any, Dict
import json


class EventType(Enum):
    AGENT_START = "agent_start"
    TURN_START = "turn_start"
    TOOL_EXECUTE = "tool_execute"
    TOOL_RESULT = "tool_result"
    TEXT_RESPONSE = "text_response"
    TURN_END = "turn_end"
    AGENT_END = "agent_end"
    ERROR = "error"


@dataclass
class Event:
    event_type: EventType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        })


# 特化的事件类
@dataclass
class AgentStartEvent(Event):
    event_type: EventType = EventType.AGENT_START


@dataclass
class TurnStartEvent(Event):
    event_type: EventType = EventType.TURN_START


@dataclass
class ToolExecuteEvent(Event):
    event_type: EventType = EventType.TOOL_EXECUTE


@dataclass
class ToolResultEvent(Event):
    event_type: EventType = EventType.TOOL_RESULT


@dataclass
class TextResponseEvent(Event):
    event_type: EventType = EventType.TEXT_RESPONSE


@dataclass
class TurnEndEvent(Event):
    event_type: EventType = EventType.TURN_END


@dataclass
class AgentEndEvent(Event):
    event_type: EventType = EventType.AGENT_END


@dataclass
class ErrorEvent(Event):
    event_type: EventType = EventType.ERROR
