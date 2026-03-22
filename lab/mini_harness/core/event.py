"""事件类型和定义"""

from dataclasses import dataclass, field
from typing import Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class EventType(str, Enum):
    """事件类型"""
    # 任务事件
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # 步骤事件
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"

    # 工具事件
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_EXECUTION_COMPLETED = "tool_execution_completed"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"

    # 权限事件
    PERMISSION_CHECK = "permission_check"
    APPROVAL_REQUESTED = "approval_requested"


@dataclass
class Event:
    """事件类"""
    event_type: EventType
    source: str  # 事件来源
    data: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat()
        }
