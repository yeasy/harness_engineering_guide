"""消息类型和接口定义"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class MessageRole(str, Enum):
    """消息角色"""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


class MessageType(str, Enum):
    """消息类型"""

    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    EVENT = "event"


@dataclass
class Message:
    """通用消息类"""

    role: MessageRole
    type: MessageType
    content: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "message_id": self.message_id,
            "role": self.role.value,
            "type": self.type.value,
            "content": self.content,
            "parent_id": self.parent_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从字典创建"""
        return cls(
            role=MessageRole(data["role"]),
            type=MessageType(data["type"]),
            content=data["content"],
            message_id=data.get("message_id", str(uuid.uuid4())),
            parent_id=data.get("parent_id"),
            metadata=data.get("metadata", {}),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
        )


@dataclass
class ToolCallMessage(Message):
    """工具调用消息"""

    @property
    def tool_name(self) -> str:
        return self.metadata.get("tool_name")

    @property
    def tool_params(self) -> Dict[str, Any]:
        return self.metadata.get("tool_params", {})


@dataclass
class ToolResultMessage(Message):
    """工具结果消息"""

    @property
    def status(self) -> str:
        return self.metadata.get("status", "unknown")

    @property
    def is_success(self) -> bool:
        return self.status == "success"
