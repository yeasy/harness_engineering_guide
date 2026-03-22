"""工具接口定义"""

from typing import Protocol, Optional, Any, Dict, List
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class ToolInputSchema:
    """工具输入schema"""
    type: str = "object"
    properties: Dict[str, Dict[str, Any]] = None
    required: List[str] = None

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
    permissions_required: List[str] = None
    timeout_seconds: int = 30
    tags: List[str] = None

    def __post_init__(self):
        if self.permissions_required is None:
            self.permissions_required = []
        if self.tags is None:
            self.tags = []


class Tool(ABC):
    """工具的抽象基类"""

    def __init__(self, definition: ToolDefinition):
        self.definition = definition

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def description(self) -> str:
        return self.definition.description

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """执行工具"""
        pass

    def get_definition_dict(self) -> Dict[str, Any]:
        """获取工具定义的字典格式"""
        return {
            "name": self.definition.name,
            "description": self.definition.description,
            "input_schema": {
                "type": self.definition.input_schema.type,
                "properties": self.definition.input_schema.properties,
                "required": self.definition.input_schema.required
            }
        }
