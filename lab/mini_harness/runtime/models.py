"""
mini_harness/runtime/models.py
基础数据模型定义
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ContentBlockType(Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


@dataclass
class TextBlock:
    type: str = "text"
    text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "text": self.text}


@dataclass
class ToolUseBlock:
    type: str = "tool_use"
    id: str = field(default_factory=lambda: f"tooluse_{uuid.uuid4().hex[:12]}")
    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "id": self.id, "name": self.name, "input": self.input}


@dataclass
class ToolResultBlock:
    type: str = "tool_result"
    tool_use_id: str = ""
    content: str = ""
    is_error: bool = False
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "tool_use_id": self.tool_use_id,
            "content": self.content,
            "is_error": self.is_error,
            "error_type": self.error_type,
        }


@dataclass
class Message:
    role: str
    content: List[Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls(role="user", content=[TextBlock(text=text)])

    @classmethod
    def assistant(cls, content: List[Any]) -> "Message":
        return cls(role="assistant", content=content)

    def has_tool_calls(self) -> bool:
        return any(isinstance(block, ToolUseBlock) for block in self.content)

    def get_tool_calls(self) -> List[ToolUseBlock]:
        return [block for block in self.content if isinstance(block, ToolUseBlock)]

    def get_text(self) -> str:
        texts = [block.text for block in self.content if isinstance(block, TextBlock)]
        return "".join(texts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": [block.to_dict() for block in self.content],
            "timestamp": self.timestamp.isoformat(),
            "message_id": self.message_id,
        }


@dataclass
class AgentState:
    """Agent 会话状态"""

    session_id: str
    messages: List[Message] = field(default_factory=list)
    current_turn: int = 0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_message(self, message: Message):
        self.messages.append(message)
        self.current_turn += 1

    def get_total_text_length(self) -> int:
        return sum(len(msg.get_text()) for msg in self.messages)
