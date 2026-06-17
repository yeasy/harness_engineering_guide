"""
mini_harness/tools/builtin.py - Built-in tools and execution pipeline
"""

import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from mini_harness.core.tool import Tool, ToolResult
from mini_harness.security.guardrails import DangerousCommandDetector
from mini_harness.security.path_validator import PathValidator

# ============ Built-in Tools ============


class BashTool(Tool):
    """受限命令执行工具。

    默认只允许少量无副作用命令，并使用 shell=False 执行。需要完整 shell
    能力时应显式设置 allow_shell=True，并继续接受危险命令检测。
    """

    SAFE_COMMANDS = frozenset({"echo", "pwd", "true", "false", "sleep"})

    def __init__(
        self,
        allow_shell: bool = False,
        allowed_commands: Optional[set[str]] = None,
        command_detector: Optional[DangerousCommandDetector] = None,
    ):
        self.allow_shell = allow_shell
        self.allowed_commands = allowed_commands or set(self.SAFE_COMMANDS)
        self.command_detector = command_detector or DangerousCommandDetector()

    async def call(self, params: Dict[str, Any]) -> ToolResult:
        command = params.get("command", "")
        timeout = params.get("timeout", 30)

        start = time.time()

        try:
            if self.command_detector.detect(command):
                reason = self.command_detector.get_reason(command)
                return ToolResult(
                    success=False,
                    content=f"Dangerous command blocked: {reason}",
                    execution_time=time.time() - start,
                    error_type="PermissionError",
                )

            run_args: Any = command
            use_shell = self.allow_shell
            if not self.allow_shell:
                run_args = self._parse_safe_command(command)

            result = subprocess.run(
                run_args, shell=use_shell, capture_output=True, timeout=timeout, text=True
            )

            output = (
                f"stdout: {result.stdout}\nstderr: {result.stderr}\nreturncode: {result.returncode}"
            )

            return ToolResult(
                success=result.returncode == 0, content=output, execution_time=time.time() - start
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                content=f"Command timeout after {timeout}s",
                execution_time=time.time() - start,
                error_type="TimeoutError",
            )

        except ValueError as e:
            return ToolResult(
                success=False,
                content=str(e),
                execution_time=time.time() - start,
                error_type="PermissionError",
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=str(e),
                execution_time=time.time() - start,
                error_type=type(e).__name__,
            )

    def _parse_safe_command(self, command: str) -> list[str]:
        tokens = shlex.split(command)
        if not tokens:
            raise ValueError("Empty command")

        executable = os.path.basename(tokens[0])
        if executable not in self.allowed_commands:
            allowed = ", ".join(sorted(self.allowed_commands))
            raise ValueError(
                f"Command '{executable}' is not in the safe allowlist. Allowed: {allowed}"
            )

        return tokens

    def name(self) -> str:
        return "bash_exec"

    def description(self) -> str:
        return "Execute allowlisted Bash commands without shell expansion"

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Allowlisted command"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["command"],
        }


class FileReadTool(Tool):
    """文件读取工具"""

    SENSITIVE_FILENAMES = frozenset(
        {
            ".env",
            ".netrc",
            "credentials.json",
            "service-account.json",
            "id_rsa",
            "id_dsa",
            "id_ecdsa",
            "id_ed25519",
        }
    )
    SENSITIVE_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".kubeconfig")

    def __init__(
        self,
        base_path: Optional[str] = None,
        allow_unsafe_paths: bool = False,
        allow_sensitive_paths: bool = False,
    ):
        self.allow_unsafe_paths = allow_unsafe_paths
        self.allow_sensitive_paths = allow_sensitive_paths
        self.path_validator = None if allow_unsafe_paths else PathValidator(base_path)

    async def call(self, params: Dict[str, Any]) -> ToolResult:
        filepath = params.get("path", "")
        max_bytes = params.get("max_bytes", 1024 * 1024)  # 1MB default

        start = time.time()

        try:
            if self.path_validator is not None:
                filepath = self.path_validator.validate(filepath)
            if not self.allow_sensitive_paths:
                self._check_sensitive_path(filepath)

            with open(filepath, "r") as f:
                content = f.read(max_bytes)

            if len(content) >= max_bytes:
                content += f"\n... [File truncated at {max_bytes} bytes]"

            return ToolResult(success=True, content=content, execution_time=time.time() - start)

        except FileNotFoundError:
            return ToolResult(
                success=False,
                content=f"File not found: {filepath}",
                execution_time=time.time() - start,
                error_type="FileNotFoundError",
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=str(e),
                execution_time=time.time() - start,
                error_type="PermissionError" if isinstance(e, PermissionError) else type(e).__name__,
            )

    def _check_sensitive_path(self, filepath: str) -> None:
        parts = [part.lower() for part in os.path.normpath(filepath).split(os.sep) if part]
        basename = parts[-1] if parts else ""

        if basename.startswith(".") or basename in self.SENSITIVE_FILENAMES:
            raise PermissionError(f"Sensitive file reads are blocked by default: {basename}")

        if basename.startswith(".env.") or basename.endswith(self.SENSITIVE_SUFFIXES):
            raise PermissionError(f"Sensitive file reads are blocked by default: {basename}")

    def name(self) -> str:
        return "file_read"

    def description(self) -> str:
        return "Read file contents"

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "max_bytes": {"type": "integer", "description": "Max bytes to read"},
            },
            "required": ["path"],
        }


class FileWriteTool(Tool):
    """文件写入工具"""

    def __init__(self, base_path: Optional[str] = None, allow_unsafe_paths: bool = False):
        self.allow_unsafe_paths = allow_unsafe_paths
        self.path_validator = None if allow_unsafe_paths else PathValidator(base_path)

    async def call(self, params: Dict[str, Any]) -> ToolResult:
        filepath = params.get("path", "")
        content = params.get("content", "")
        append = params.get("append", False)

        start = time.time()

        try:
            mode = "a" if append else "w"

            if self.path_validator is not None:
                filepath = self.path_validator.validate(filepath)

            dirname = os.path.dirname(filepath)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

            with open(filepath, mode) as f:
                f.write(content)

            return ToolResult(
                success=True,
                content=f"Successfully wrote {len(content)} bytes to {filepath}",
                execution_time=time.time() - start,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content=str(e),
                execution_time=time.time() - start,
                error_type=type(e).__name__,
            )

    def name(self) -> str:
        return "file_write"

    def description(self) -> str:
        return "Write or append to a file within the configured workspace"

    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "content": {"type": "string", "description": "Content to write"},
                "append": {
                    "type": "boolean",
                    "description": "Append instead of write",
                    "default": False,
                },
            },
            "required": ["path", "content"],
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
            "error_type": self.error_type,
        }


class ExecutionPipeline:
    """工具执行流水线"""

    def __init__(self, tool_registry: "ToolRegistry"):
        self.tool_registry = tool_registry
        self.execution_history = []

    async def execute(self, tool_name: str, input_params: Dict[str, Any]) -> ToolResultBlock:
        """执行工具的完整流水线"""

        # 1. 工具发现
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return ToolResultBlock(
                tool_name=tool_name, success=False, content=f"Tool not found: {tool_name}"
            )

        # 2. 权限检查
        if not tool.check_permissions({}):
            return ToolResultBlock(
                tool_name=tool_name,
                success=False,
                content=f"Permission denied for tool: {tool_name}",
            )

        # 3. 执行工具
        try:
            result = await tool.call(input_params)

            return ToolResultBlock(
                tool_name=tool_name,
                success=result.success,
                content=result.content,
                execution_time=result.execution_time,
                error_type=result.error_type,
            )

        except Exception as e:
            return ToolResultBlock(
                tool_name=tool_name, success=False, content=str(e), error_type=type(e).__name__
            )
