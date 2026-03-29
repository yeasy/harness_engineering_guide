"""
mini_harness/tools/builtin.py - Built-in tools and execution pipeline
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
import subprocess
import time
import os


# ============ Tool Base Class and Results ============

@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    content: str
    execution_time: float
    error_type: Optional[str] = None


class Tool(ABC):
    """工具基类"""

    @abstractmethod
    async def call(self, params: Dict[str, Any]) -> ToolResult:
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


# ============ Built-in Tools ============

class BashTool(Tool):
    """Bash 命令执行工具"""

    async def call(self, params: Dict[str, Any]) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 30)

        start = time.time()

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                text=True
            )

            output = f"stdout: {result.stdout}\nstderr: {result.stderr}\nreturncode: {result.returncode}"

            return ToolResult(
                success=result.returncode == 0,
                content=output,
                execution_time=time.time() - start
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                content=f"Command timeout after {timeout}s",
                execution_time=time.time() - start,
                error_type="TimeoutError"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=str(e),
                execution_time=time.time() - start,
                error_type=type(e).__name__
            )

    def name(self) -> str:
        return "bash_exec"

    def description(self) -> str:
        return "Execute bash commands"

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30}
            },
            "required": ["command"]
        }


class FileReadTool(Tool):
    """文件读取工具"""

    async def call(self, params: Dict[str, Any]) -> ToolResult:
        filepath = params.get("path", "")
        max_bytes = params.get("max_bytes", 1024 * 1024)  # 1MB default

        start = time.time()

        try:
            with open(filepath, 'r') as f:
                content = f.read(max_bytes)

            if len(content) >= max_bytes:
                content += f"\n... [File truncated at {max_bytes} bytes]"

            return ToolResult(
                success=True,
                content=content,
                execution_time=time.time() - start
            )

        except FileNotFoundError:
            return ToolResult(
                success=False,
                content=f"File not found: {filepath}",
                execution_time=time.time() - start,
                error_type="FileNotFoundError"
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=str(e),
                execution_time=time.time() - start,
                error_type=type(e).__name__
            )

    def name(self) -> str:
        return "file_read"

    def description(self) -> str:
        return "Read file contents"

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "max_bytes": {"type": "integer", "description": "Max bytes to read"}
            },
            "required": ["path"]
        }


class FileWriteTool(Tool):
    """文件写入工具"""

    async def call(self, params: Dict[str, Any]) -> ToolResult:
        filepath = params.get("path", "")
        content = params.get("content", "")
        append = params.get("append", False)

        start = time.time()

        try:
            mode = 'a' if append else 'w'

            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(filepath, mode) as f:
                f.write(content)

            return ToolResult(
                success=True,
                content=f"Successfully wrote {len(content)} bytes to {filepath}",
                execution_time=time.time() - start
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=str(e),
                execution_time=time.time() - start,
                error_type=type(e).__name__
            )

    def name(self) -> str:
        return "file_write"

    def description(self) -> str:
        return "Write or append to file"

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content to write"},
                "append": {"type": "boolean", "description": "Append instead of write", "default": False}
            },
            "required": ["path", "content"]
        }


# ============ Execution Pipeline ============

@dataclass
class ToolResultBlock:
    """工具结果块"""
    tool_name: str
    success: bool
    content: str
    execution_time: float = 0.0
    error_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "content": self.content,
            "execution_time": self.execution_time,
            "error_type": self.error_type
        }


class ExecutionPipeline:
    """工具执行流水线"""

    def __init__(self, tool_registry: 'ToolRegistry'):
        self.tool_registry = tool_registry
        self.execution_history = []

    async def execute(self, tool_name: str,
                     input_params: Dict[str, Any]) -> ToolResultBlock:
        """执行工具的完整流水线"""

        # 1. 工具发现
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return ToolResultBlock(
                tool_name=tool_name,
                success=False,
                content=f"Tool not found: {tool_name}"
            )

        # 2. 权限检查
        if not tool.check_permissions({}):
            return ToolResultBlock(
                tool_name=tool_name,
                success=False,
                content=f"Permission denied for tool: {tool_name}"
            )

        # 3. 执行工具
        try:
            result = await tool.call(input_params)

            return ToolResultBlock(
                tool_name=tool_name,
                success=result.success,
                content=result.content,
                execution_time=result.execution_time,
                error_type=result.error_type
            )

        except Exception as e:
            return ToolResultBlock(
                tool_name=tool_name,
                success=False,
                content=str(e),
                error_type=type(e).__name__
            )
