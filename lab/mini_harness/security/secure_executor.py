"""Secure tool executor integrating all security layers."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Optional

from mini_harness.security.guardrails import DangerousCommandDetector
from mini_harness.security.path_validator import PathValidator
from mini_harness.security.permissions import Decision, PermissionDecisionEngine


BASH_TOOL_NAMES = {"bash", "bash_exec"}
FILE_TOOL_NAMES = {"read_file", "write_file", "file_read", "file_write"}


def approval_scope_for_args(args: dict[str, Any]) -> str:
    """Create a stable approval scope from tool arguments."""
    encoded = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class ToolCall:
    """Represents a tool call to be executed."""
    tool_name: str
    args: dict[str, Any]
    user_id: Optional[str] = None


class SecureToolExecutor:
    """Secure executor integrating permission engine, guardrails, and user approval."""

    def __init__(
        self,
        permission_engine: PermissionDecisionEngine,
        path_validator: Optional[PathValidator] = None,
        command_detector: Optional[DangerousCommandDetector] = None,
        user_approval_callback: Optional[Callable[[str, ToolCall], bool]] = None,
    ):
        """Initialize the secure tool executor.

        Args:
            permission_engine: Permission decision engine
            path_validator: Optional path validator for file operations
            command_detector: Optional dangerous command detector for bash operations
            user_approval_callback: Optional callback to ask user for approval
        """
        self.permission_engine = permission_engine
        self.path_validator = path_validator or PathValidator()
        self.command_detector = command_detector or DangerousCommandDetector()
        self.user_approval_callback = user_approval_callback

    async def execute(self, tool_call: ToolCall, executor: Callable) -> Any:
        """Execute a tool call with security checks.

        Four-layer security flow:
        1. Permission decision
        2. Guardrail checks
        3. User approval (if needed)
        4. Execute

        Args:
            tool_call: Tool call to execute
            executor: Async callable that performs the actual execution

        Returns:
            Result from executor

        Raises:
            PermissionError: If any security layer rejects the call
        """
        user_id = tool_call.user_id or "unknown"
        approval_scope = approval_scope_for_args(tool_call.args)

        # Layer 1: Permission decision
        decision = self.permission_engine.decide(
            tool_call.tool_name, user_id, approval_scope=approval_scope
        )
        if decision == Decision.DENY:
            raise PermissionError(f"Tool '{tool_call.tool_name}' is denied by policy")

        # Layer 2: Guardrail checks
        if tool_call.tool_name in BASH_TOOL_NAMES and "command" in tool_call.args:
            command = tool_call.args["command"]
            if self.command_detector.detect(command):
                reason = self.command_detector.get_reason(command)
                raise PermissionError(f"Dangerous command blocked: {reason}")

        # Layer 2b: Path validation for file operations
        if tool_call.tool_name in FILE_TOOL_NAMES and "path" in tool_call.args:
            try:
                validated_path = self.path_validator.validate(tool_call.args["path"])
                tool_call.args["path"] = validated_path
            except ValueError as e:
                raise PermissionError(f"Path validation failed: {str(e)}")

        # Layer 3: User approval (if needed)
        if decision == Decision.ASK_USER:
            if self.user_approval_callback is None:
                raise PermissionError(
                    f"Tool '{tool_call.tool_name}' requires user approval but no approval callback provided"
                )

            approved = self.user_approval_callback(user_id, tool_call)
            if not approved:
                raise PermissionError(f"User rejected tool '{tool_call.tool_name}'")

            self.permission_engine.record_approval(
                user_id, tool_call.tool_name, approval_scope=approval_scope
            )

        # Layer 4: Execute
        return await executor(tool_call)

    def sync_execute(self, tool_call: ToolCall, executor: Callable) -> Any:
        """Execute a tool call synchronously (for non-async executors).

        Args:
            tool_call: Tool call to execute
            executor: Callable that performs the actual execution

        Returns:
            Result from executor

        Raises:
            PermissionError: If any security layer rejects the call
        """
        user_id = tool_call.user_id or "unknown"
        approval_scope = approval_scope_for_args(tool_call.args)

        # Layer 1: Permission decision
        decision = self.permission_engine.decide(
            tool_call.tool_name, user_id, approval_scope=approval_scope
        )
        if decision == Decision.DENY:
            raise PermissionError(f"Tool '{tool_call.tool_name}' is denied by policy")

        # Layer 2: Guardrail checks
        if tool_call.tool_name in BASH_TOOL_NAMES and "command" in tool_call.args:
            command = tool_call.args["command"]
            if self.command_detector.detect(command):
                reason = self.command_detector.get_reason(command)
                raise PermissionError(f"Dangerous command blocked: {reason}")

        # Layer 2b: Path validation for file operations
        if tool_call.tool_name in FILE_TOOL_NAMES and "path" in tool_call.args:
            try:
                validated_path = self.path_validator.validate(tool_call.args["path"])
                tool_call.args["path"] = validated_path
            except ValueError as e:
                raise PermissionError(f"Path validation failed: {str(e)}")

        # Layer 3: User approval (if needed)
        if decision == Decision.ASK_USER:
            if self.user_approval_callback is None:
                raise PermissionError(
                    f"Tool '{tool_call.tool_name}' requires user approval but no approval callback provided"
                )

            approved = self.user_approval_callback(user_id, tool_call)
            if not approved:
                raise PermissionError(f"User rejected tool '{tool_call.tool_name}'")

            self.permission_engine.record_approval(
                user_id, tool_call.tool_name, approval_scope=approval_scope
            )

        # Layer 4: Execute
        return executor(tool_call)
