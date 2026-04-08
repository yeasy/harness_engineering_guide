"""工具接口定义"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    """工具执行结果"""

    success: bool
    content: str
    execution_time: float
    error_type: Optional[str] = None


@dataclass
class ToolInputSchema:
    """工具输入schema"""

    type: str = "object"
    properties: Optional[Dict[str, Dict[str, Any]]] = None
    required: Optional[List[str]] = None

    def __post_init__(self):
        if self.properties is None:
            self.properties = {}
        if self.required is None:
            self.required = []


@dataclass
class ToolDefinition:
    """工具定义"""

    name: str
    description: str
    input_schema: ToolInputSchema
    permissions_required: Optional[List[str]] = None
    timeout_seconds: int = 30
    tags: Optional[List[str]] = None

    def __post_init__(self):
        if self.permissions_required is None:
            self.permissions_required = []
        if self.tags is None:
            self.tags = []


class Tool(ABC):
    """工具的抽象基类"""

    @abstractmethod
    async def call(self, params: Dict[str, Any]) -> "ToolResult":
        """执行工具"""
        pass

    @abstractmethod
    def name(self) -> str:
        """工具名称"""
        pass

    @abstractmethod
    def description(self) -> str:
        """工具描述"""
        pass

    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        """输入 Schema"""
        pass

    def check_permissions(self, context: Any) -> bool:
        """权限检查"""
        return True

    def get_definition_dict(self) -> Dict[str, Any]:
        """获取工具定义的字典格式"""
        return {
            "name": self.name(),
            "description": self.description(),
            "input_schema": self.input_schema(),
        }
