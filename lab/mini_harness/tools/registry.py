"""
mini_harness/tools/registry.py - Tool Registry
"""

from typing import Any, Dict, List, Optional


class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self.tools: Dict[str, "Tool"] = {}
        self.schema_cache: Dict[str, Dict] = {}

    def register(self, tool: "Tool"):
        """注册工具"""
        name = tool.name()
        self.tools[name] = tool

        # 缓存 Schema
        self.schema_cache[name] = {
            "name": name,
            "description": tool.description(),
            "input_schema": tool.input_schema(),
        }

    def get(self, name: str) -> Optional["Tool"]:
        """获取工具"""
        return self.tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具 Schema"""
        return list(self.schema_cache.values())

    def get_schema(self, name: str) -> Optional[Dict]:
        """获取工具 Schema"""
        return self.schema_cache.get(name)
