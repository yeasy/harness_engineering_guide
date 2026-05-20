"""
Tests for mini_harness.security module:
- permissions.py: PermissionLevel, PermissionDecisionEngine, Decision
- path_validator.py: PathValidator
- guardrails.py: DangerousCommandDetector
- secure_executor.py: SecureToolExecutor, ToolCall
"""

import os
import tempfile
import pytest

from mini_harness.security.permissions import (
    PermissionLevel,
    Decision,
    PermissionDecisionEngine,
)
from mini_harness.security.path_validator import PathValidator
from mini_harness.security.guardrails import DangerousCommandDetector
from mini_harness.security.secure_executor import (
    SecureToolExecutor,
    ToolCall,
)


# ============ PermissionLevel Tests ============


class TestPermissionLevel:
    def test_permission_level_values(self):
        assert PermissionLevel.DENY.value == 0
        assert PermissionLevel.ASK.value == 1
        assert PermissionLevel.AUTO.value == 2
        assert PermissionLevel.OVERRIDE.value == 3

    def test_permission_level_ordering(self):
        # Test that we can compare permission levels
        assert PermissionLevel.DENY.value < PermissionLevel.ASK.value
        assert PermissionLevel.AUTO.value < PermissionLevel.OVERRIDE.value


# ============ PermissionDecisionEngine Tests ============


class TestPermissionDecisionEngine:
    def test_engine_creation(self):
        engine = PermissionDecisionEngine()
        assert len(engine.policies) == 0
        assert len(engine.user_approvals) == 0
        assert len(engine.audit_logs) == 0

    def test_register_policy(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("bash_exec", PermissionLevel.DENY, "Bash is dangerous")
        engine.register_policy("read_file", PermissionLevel.AUTO, "Safe for reading")

        assert engine.policies["bash_exec"] == PermissionLevel.DENY
        assert engine.policies["read_file"] == PermissionLevel.AUTO

    def test_decision_deny_policy(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("dangerous_tool", PermissionLevel.DENY)

        decision = engine.decide("dangerous_tool", "user_123")
        assert decision == Decision.DENY

    def test_decision_ask_policy(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("ask_tool", PermissionLevel.ASK)

        decision = engine.decide("ask_tool", "user_123")
        assert decision == Decision.ASK_USER

    def test_decision_auto_policy_first_use(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("auto_tool", PermissionLevel.AUTO)

        decision = engine.decide("auto_tool", "user_123")
        assert decision == Decision.ASK_USER  # First use requires approval

    def test_decision_auto_policy_cached_approval(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("auto_tool", PermissionLevel.AUTO)

        # Record approval
        engine.record_approval("user_123", "auto_tool")

        # Subsequent decision should allow
        decision = engine.decide("auto_tool", "user_123")
        assert decision == Decision.ALLOW

    def test_decision_auto_policy_cached_approval_can_be_scoped(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("auto_tool", PermissionLevel.AUTO)

        engine.record_approval("user_123", "auto_tool", approval_scope="args:a")

        assert engine.decide("auto_tool", "user_123", approval_scope="args:a") == Decision.ALLOW
        assert engine.decide("auto_tool", "user_123", approval_scope="args:b") == Decision.ASK_USER

    def test_decision_override_policy(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("admin_tool", PermissionLevel.OVERRIDE)

        decision = engine.decide("admin_tool", "user_123")
        assert decision == Decision.ALLOW

    def test_decision_default_policy(self):
        engine = PermissionDecisionEngine()
        # No policy registered for this tool

        decision = engine.decide("unknown_tool", "user_123")
        assert decision == Decision.ASK_USER  # Default is ASK

    def test_record_approval(self):
        engine = PermissionDecisionEngine()
        engine.record_approval("user_123", "tool_a")
        engine.record_approval("user_456", "tool_a")

        assert ("user_123", "tool_a", "__tool__") in engine.user_approvals
        assert ("user_456", "tool_a", "__tool__") in engine.user_approvals

    def test_approval_per_user(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("auto_tool", PermissionLevel.AUTO)

        # User 1 approves
        engine.record_approval("user_1", "auto_tool")

        # User 1 gets access
        assert engine.decide("auto_tool", "user_1") == Decision.ALLOW

        # User 2 needs approval again
        assert engine.decide("auto_tool", "user_2") == Decision.ASK_USER

    def test_audit_log_creation(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("tool_a", PermissionLevel.DENY)

        engine.decide("tool_a", "user_123")

        logs = engine.get_audit_logs()
        assert len(logs) == 1
        assert logs[0].user_id == "user_123"
        assert logs[0].tool_name == "tool_a"
        assert logs[0].decision == Decision.DENY

    def test_clear_audit_logs(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("tool_a", PermissionLevel.DENY)
        engine.decide("tool_a", "user_123")

        assert len(engine.get_audit_logs()) == 1
        engine.clear_audit_logs()
        assert len(engine.get_audit_logs()) == 0


# ============ PathValidator Tests ============


class TestPathValidator:
    def test_path_validator_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = PathValidator(base_path=tmpdir)
            assert validator.base_path == os.path.realpath(tmpdir)

    def test_valid_path_in_base(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = PathValidator(base_path=tmpdir)
            test_file = os.path.join(tmpdir, "test.txt")

            resolved = validator.validate("test.txt")
            assert resolved == os.path.realpath(test_file)

    def test_path_with_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)

            validator = PathValidator(base_path=tmpdir)
            resolved = validator.validate("subdir/file.txt")

            assert tmpdir in resolved
            assert "subdir" in resolved

    def test_path_segment_starting_with_two_dots_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = PathValidator(base_path=tmpdir)

            resolved = validator.validate("..notes/file.txt")

            assert resolved == os.path.realpath(os.path.join(tmpdir, "..notes", "file.txt"))

    def test_backslashes_are_normalized_as_path_separators(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = PathValidator(base_path=tmpdir)

            resolved = validator.validate(r"subdir\file.txt")

            assert resolved == os.path.realpath(os.path.join(tmpdir, "subdir", "file.txt"))

    def test_backslash_directory_traversal_attack_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = PathValidator(base_path=tmpdir)

            with pytest.raises(ValueError, match="Path traversal"):
                validator.validate(r"..\escape.txt")

    def test_directory_traversal_attack_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a parent directory outside the base
            parent_dir = os.path.dirname(tmpdir)

            validator = PathValidator(base_path=tmpdir)

            with pytest.raises(ValueError, match="Path traversal"):
                validator.validate("../escape.txt")

    def test_path_length_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = PathValidator(base_path=tmpdir)

            long_path = "a" * 5000
            with pytest.raises(ValueError, match="Path too long"):
                validator.validate(long_path)

    def test_url_encoded_path_attack(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = PathValidator(base_path=tmpdir)

            # %2e%2e = ..
            with pytest.raises(ValueError, match="Path traversal"):
                validator.validate("%2e%2e/escape.txt")

    def test_double_encoded_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = PathValidator(base_path=tmpdir)

            # Double encoded: %252e%252e
            with pytest.raises(ValueError, match="Path traversal"):
                validator.validate("%252e%252e/escape.txt")

    def test_set_base_path(self):
        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                validator = PathValidator(base_path=tmpdir1)
                assert tmpdir1 in validator.base_path

                validator.set_base_path(tmpdir2)
                assert os.path.realpath(tmpdir2) == validator.base_path


# ============ DangerousCommandDetector Tests ============


class TestDangerousCommandDetector:
    def test_detector_creation(self):
        detector = DangerousCommandDetector()
        assert "rm" in detector.dangerous_commands
        assert "dd" in detector.dangerous_commands

    def test_dangerous_command_detected(self):
        detector = DangerousCommandDetector()

        assert detector.detect("rm -rf /") is True
        assert detector.detect("dd if=/dev/zero of=/dev/sda") is True
        assert detector.detect("sudo rm /tmp/file") is True

    def test_safe_command_allowed(self):
        detector = DangerousCommandDetector()

        assert detector.detect("echo hello") is False
        assert detector.detect("ls -la") is False
        assert detector.detect("cat /etc/hosts") is False

    def test_command_with_path_prefix(self):
        detector = DangerousCommandDetector()

        # /bin/rm should still be detected
        assert detector.detect("/bin/rm file.txt") is True
        assert detector.detect("/usr/bin/rm file.txt") is True

    def test_restricted_command_allowed_subcommand(self):
        detector = DangerousCommandDetector()

        # pip with allowed subcommand
        assert detector.detect("pip list") is False
        assert detector.detect("pip show package") is False

    def test_restricted_command_denied_subcommand(self):
        detector = DangerousCommandDetector()

        # pip with dangerous subcommand
        assert detector.detect("pip install package") is True
        assert detector.detect("pip uninstall package") is True

    def test_restricted_command_without_subcommand(self):
        detector = DangerousCommandDetector()

        # apt without subcommand
        assert detector.detect("apt") is True

    def test_piped_commands(self):
        detector = DangerousCommandDetector()

        # Dangerous command in pipe
        assert detector.detect("cat file.txt | rm file.txt") is True
        assert detector.detect("grep -r . | sudo chmod 777 /") is True

    def test_safe_piped_commands(self):
        detector = DangerousCommandDetector()

        # All safe commands
        assert detector.detect("cat file.txt | grep pattern | wc -l") is False

    def test_shell_control_operators_are_blocked(self):
        detector = DangerousCommandDetector()

        assert detector.detect("echo ok && rm -rf /") is True
        assert detector.detect("echo ok; rm -rf /") is True
        assert detector.detect("echo $(rm -rf /)") is True
        assert detector.detect("echo `rm -rf /`") is True

    def test_get_reason_dangerous(self):
        detector = DangerousCommandDetector()

        reason = detector.get_reason("rm -rf /")
        assert reason is not None
        assert "rm" in reason

    def test_get_reason_safe(self):
        detector = DangerousCommandDetector()

        reason = detector.get_reason("echo hello")
        assert reason is None

    def test_custom_dangerous_command(self):
        detector = DangerousCommandDetector(custom_dangerous=["custom_bad"])

        assert detector.detect("custom_bad arg") is True

    def test_add_dangerous_command(self):
        detector = DangerousCommandDetector()
        detector.add_dangerous_command("dangerous_new")

        assert detector.detect("dangerous_new arg") is True

    def test_remove_dangerous_command(self):
        detector = DangerousCommandDetector()
        detector.remove_dangerous_command("rm")

        # rm should no longer be detected
        assert detector.detect("rm file.txt") is False


# ============ SecureToolExecutor Tests ============


class TestSecureToolExecutor:
    def test_executor_creation(self):
        engine = PermissionDecisionEngine()
        executor = SecureToolExecutor(permission_engine=engine)

        assert executor.permission_engine == engine
        assert executor.path_validator is not None
        assert executor.command_detector is not None

    def test_sync_execute_allowed_tool(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("safe_tool", PermissionLevel.OVERRIDE)

        executor = SecureToolExecutor(permission_engine=engine)

        def execute_func(call):
            return "executed"

        tool_call = ToolCall(tool_name="safe_tool", args={}, user_id="user_1")
        result = executor.sync_execute(tool_call, execute_func)

        assert result == "executed"

    def test_sync_execute_denied_tool(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("denied_tool", PermissionLevel.DENY)

        executor = SecureToolExecutor(permission_engine=engine)

        def execute_func(call):
            return "executed"

        tool_call = ToolCall(tool_name="denied_tool", args={}, user_id="user_1")

        with pytest.raises(PermissionError, match="denied by policy"):
            executor.sync_execute(tool_call, execute_func)

    def test_sync_execute_dangerous_bash_command(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("bash", PermissionLevel.OVERRIDE)

        executor = SecureToolExecutor(permission_engine=engine)

        def execute_func(call):
            return "executed"

        tool_call = ToolCall(
            tool_name="bash",
            args={"command": "rm -rf /"},
            user_id="user_1"
        )

        with pytest.raises(PermissionError, match="Dangerous command blocked"):
            executor.sync_execute(tool_call, execute_func)

    def test_sync_execute_dangerous_builtin_bash_command(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("bash_exec", PermissionLevel.OVERRIDE)

        executor = SecureToolExecutor(permission_engine=engine)

        def execute_func(call):
            return "executed"

        tool_call = ToolCall(
            tool_name="bash_exec",
            args={"command": "rm -rf /"},
            user_id="user_1"
        )

        with pytest.raises(PermissionError, match="Dangerous command blocked"):
            executor.sync_execute(tool_call, execute_func)

    def test_sync_execute_builtin_file_read_validates_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = PermissionDecisionEngine()
            engine.register_policy("file_read", PermissionLevel.OVERRIDE)

            executor = SecureToolExecutor(
                permission_engine=engine,
                path_validator=PathValidator(base_path=tmpdir)
            )

            def execute_func(call):
                return "executed"

            tool_call = ToolCall(
                tool_name="file_read",
                args={"path": "../escape.txt"},
                user_id="user_1"
            )

            with pytest.raises(PermissionError, match="Path validation failed"):
                executor.sync_execute(tool_call, execute_func)

    def test_sync_execute_safe_bash_command(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("bash", PermissionLevel.OVERRIDE)

        executor = SecureToolExecutor(permission_engine=engine)

        def execute_func(call):
            return "executed"

        tool_call = ToolCall(
            tool_name="bash",
            args={"command": "echo hello"},
            user_id="user_1"
        )

        result = executor.sync_execute(tool_call, execute_func)
        assert result == "executed"

    def test_sync_execute_with_user_approval_callback(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("ask_tool", PermissionLevel.ASK)

        def approval_callback(user_id, tool_call):
            # Simulate user approval
            return True

        executor = SecureToolExecutor(
            permission_engine=engine,
            user_approval_callback=approval_callback
        )

        def execute_func(call):
            return "executed"

        tool_call = ToolCall(tool_name="ask_tool", args={}, user_id="user_1")
        result = executor.sync_execute(tool_call, execute_func)

        assert result == "executed"

    def test_sync_execute_approval_denied(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("ask_tool", PermissionLevel.ASK)

        def approval_callback(user_id, tool_call):
            return False  # User denies

        executor = SecureToolExecutor(
            permission_engine=engine,
            user_approval_callback=approval_callback
        )

        def execute_func(call):
            return "executed"

        tool_call = ToolCall(tool_name="ask_tool", args={}, user_id="user_1")

        with pytest.raises(PermissionError, match="rejected"):
            executor.sync_execute(tool_call, execute_func)

    def test_sync_execute_approval_caching(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("auto_tool", PermissionLevel.AUTO)

        call_count = 0

        def approval_callback(user_id, tool_call):
            nonlocal call_count
            call_count += 1
            return True

        executor = SecureToolExecutor(
            permission_engine=engine,
            user_approval_callback=approval_callback
        )

        def execute_func(call):
            return "executed"

        # First call asks for approval
        tool_call = ToolCall(tool_name="auto_tool", args={}, user_id="user_1")
        executor.sync_execute(tool_call, execute_func)
        assert call_count == 1

        # Second call uses cache
        executor.sync_execute(tool_call, execute_func)
        assert call_count == 1  # No additional approval needed

    def test_sync_execute_auto_approval_cache_is_scoped_to_args(self):
        engine = PermissionDecisionEngine()
        engine.register_policy("safe_tool", PermissionLevel.AUTO)
        approvals = []

        def approval_callback(user_id, tool_call):
            approvals.append((user_id, dict(tool_call.args)))
            return True

        executor = SecureToolExecutor(
            permission_engine=engine,
            user_approval_callback=approval_callback
        )

        def execute_func(call):
            return "executed"

        first_call = ToolCall(tool_name="safe_tool", args={"target": "a"}, user_id="user_1")
        second_call = ToolCall(tool_name="safe_tool", args={"target": "a"}, user_id="user_1")
        changed_args_call = ToolCall(tool_name="safe_tool", args={"target": "b"}, user_id="user_1")

        assert executor.sync_execute(first_call, execute_func) == "executed"
        assert executor.sync_execute(second_call, execute_func) == "executed"
        assert executor.sync_execute(changed_args_call, execute_func) == "executed"

        assert approvals == [
            ("user_1", {"target": "a"}),
            ("user_1", {"target": "b"}),
        ]

    def test_path_validation_in_file_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = PermissionDecisionEngine()
            engine.register_policy("read_file", PermissionLevel.OVERRIDE)

            validator = PathValidator(base_path=tmpdir)
            executor = SecureToolExecutor(
                permission_engine=engine,
                path_validator=validator
            )

            def execute_func(call):
                return call.args["path"]

            # Valid path
            tool_call = ToolCall(
                tool_name="read_file",
                args={"path": "test.txt"},
                user_id="user_1"
            )
            result = executor.sync_execute(tool_call, execute_func)
            assert "test.txt" in result

            # Invalid path (traversal)
            tool_call = ToolCall(
                tool_name="read_file",
                args={"path": "../../etc/passwd"},
                user_id="user_1"
            )
            with pytest.raises(PermissionError, match="Path validation failed"):
                executor.sync_execute(tool_call, execute_func)
