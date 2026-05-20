"""Permission system for MiniHarness security module."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set, Tuple


class PermissionLevel(Enum):
    """Permission level enumeration for tools and operations."""
    DENY = 0  # Never allow
    ASK = 1  # Ask user each time
    AUTO = 2  # Auto-approve (can cache previous approvals)
    OVERRIDE = 3  # Admin override


class Decision(Enum):
    """Permission decision result."""
    ALLOW = "allow"
    DENY = "deny"
    ASK_USER = "ask_user"


@dataclass
class PermissionPolicy:
    """Policy record for a tool."""
    tool_name: str
    level: PermissionLevel
    description: str = ""


@dataclass
class AuditLog:
    """Audit log entry for permission decisions."""
    user_id: str
    tool_name: str
    decision: Decision
    timestamp: str = ""
    reason: str = ""


class PermissionDecisionEngine:
    """Permission decision engine with policy-driven approach."""

    DEFAULT_APPROVAL_SCOPE = "__tool__"

    def __init__(self):
        """Initialize the permission decision engine."""
        self.policies: dict[str, PermissionLevel] = {}
        self.user_approvals: Set[Tuple[str, str, str]] = set()
        self.audit_logs: list[AuditLog] = []

    def register_policy(self, tool_name: str, level: PermissionLevel, description: str = "") -> None:
        """Register a permission policy for a tool.

        Args:
            tool_name: Name of the tool
            level: Permission level for the tool
            description: Optional description of the policy
        """
        self.policies[tool_name] = level

    def decide(
        self,
        tool_name: str,
        user_id: str,
        approval_scope: Optional[str] = None,
    ) -> Decision:
        """Make a permission decision for a tool.

        Args:
            tool_name: Name of the tool
            user_id: ID of the user requesting access
            approval_scope: Optional operation scope, such as an argument fingerprint

        Returns:
            Decision enum (ALLOW, DENY, or ASK_USER)
        """
        level = self.policies.get(tool_name, PermissionLevel.ASK)

        if level == PermissionLevel.DENY:
            self._log_decision(user_id, tool_name, Decision.DENY, "Policy: DENY")
            return Decision.DENY

        elif level == PermissionLevel.AUTO:
            # Check if user has approved this before
            if self._was_approved_before(user_id, tool_name, approval_scope):
                self._log_decision(user_id, tool_name, Decision.ALLOW, "Cached approval")
                return Decision.ALLOW
            else:
                self._log_decision(user_id, tool_name, Decision.ASK_USER, "First use, need approval")
                return Decision.ASK_USER

        elif level == PermissionLevel.ASK:
            self._log_decision(user_id, tool_name, Decision.ASK_USER, "Policy: ASK")
            return Decision.ASK_USER

        else:  # OVERRIDE
            self._log_decision(user_id, tool_name, Decision.ALLOW, "Policy: OVERRIDE")
            return Decision.ALLOW

    def _approval_key(
        self,
        user_id: str,
        tool_name: str,
        approval_scope: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        scope = approval_scope or self.DEFAULT_APPROVAL_SCOPE
        return (user_id, tool_name, scope)

    def _was_approved_before(
        self,
        user_id: str,
        tool_name: str,
        approval_scope: Optional[str] = None,
    ) -> bool:
        """Check if user has previously approved this tool."""
        return self._approval_key(user_id, tool_name, approval_scope) in self.user_approvals

    def record_approval(
        self,
        user_id: str,
        tool_name: str,
        approval_scope: Optional[str] = None,
    ) -> None:
        """Record user approval for a tool.

        Args:
            user_id: ID of the user
            tool_name: Name of the tool
            approval_scope: Optional operation scope, such as an argument fingerprint
        """
        self.user_approvals.add(self._approval_key(user_id, tool_name, approval_scope))
        self._log_decision(user_id, tool_name, Decision.ALLOW, "User approved")

    def _log_decision(self, user_id: str, tool_name: str, decision: Decision, reason: str = "") -> None:
        """Log a permission decision to audit log.

        Args:
            user_id: ID of the user
            tool_name: Name of the tool
            decision: The decision made
            reason: Reason for the decision
        """
        log_entry = AuditLog(
            user_id=user_id,
            tool_name=tool_name,
            decision=decision,
            reason=reason
        )
        self.audit_logs.append(log_entry)

    def get_audit_logs(self) -> list[AuditLog]:
        """Get all audit logs.

        Returns:
            List of audit log entries
        """
        return self.audit_logs.copy()

    def clear_audit_logs(self) -> None:
        """Clear all audit logs."""
        self.audit_logs.clear()
