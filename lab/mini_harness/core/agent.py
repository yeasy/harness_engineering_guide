"""智能体接口定义"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class AgentState(str, Enum):
    """智能体状态"""

    IDLE = "idle"
    INITIALIZING = "initializing"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExecutionResult:
    """执行结果"""

    status: str  # "success", "error", "timeout"
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class Agent:
    """Agent定义"""

    agent_id: str
    name: str
    description: str
    system_prompt: str
    model_name: str = "claude-sonnet-4-6"
    max_steps: int = 10
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
