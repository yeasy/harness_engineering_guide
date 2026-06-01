"""Command guardrails for dangerous command detection."""

import shlex
from typing import Dict, List, Optional, Set


class DangerousCommandDetector:
    """Detects and blocks dangerous commands in shell execution."""

    # Static blacklist of dangerous commands
    DANGEROUS_COMMANDS: Set[str] = {
        "rm", "dd", "mkfs", "reboot", "shutdown", "chmod",
        "sudo", "passwd", "useradd", "cryptsetup",
        "fdisk", "parted", "format", "diskpart"
    }

    # Commands allowed only with specific subcommands
    RESTRICTED_COMMANDS: Dict[str, Set[str]] = {
        "apt": {"list", "search", "show"},
        "yum": {"list", "search"},
        "pip": {"list", "show"},
    }

    SHELL_CONTROL_OPERATORS: Dict[str, str] = {
        "&&": "command chaining with &&",
        "||": "command chaining with ||",
        ";": "command sequencing with ;",
        "\n": "multi-line shell input",
        "\r": "multi-line shell input",
        "$(": "command substitution with $(",
        "`": "command substitution with backticks",
    }

    INLINE_EXEC_FLAGS: Dict[str, Set[str]] = {
        "bash": {"-c"},
        "sh": {"-c"},
        "zsh": {"-c"},
        "python": {"-c"},
        "python3": {"-c"},
        "node": {"-e", "--eval"},
    }

    def __init__(self, custom_dangerous: Optional[List[str]] = None):
        """Initialize the dangerous command detector.

        Args:
            custom_dangerous: Optional list of additional dangerous commands to block
        """
        self.dangerous_commands = self.DANGEROUS_COMMANDS.copy()
        if custom_dangerous:
            self.dangerous_commands.update(custom_dangerous)

    def detect(self, command: str) -> bool:
        """Detect if command contains dangerous operations.

        Args:
            command: Shell command to analyze

        Returns:
            True if command is dangerous, False otherwise
        """
        try:
            tokens = shlex.split(command)
        except ValueError:
            # If command can't be parsed, consider it suspicious
            return True

        if not tokens:
            return False

        if self._shell_control_reason(command) is not None:
            return True

        # Check main command (remove path prefix)
        main_cmd = tokens[0].split('/')[-1]

        # Layer 1: Check main command against blacklist
        if main_cmd in self.dangerous_commands:
            return True

        if self._inline_exec_reason(main_cmd, tokens) is not None:
            return True

        # Layer 2: Check restricted commands with allowed subcommands
        if main_cmd in self.RESTRICTED_COMMANDS:
            if len(tokens) < 2:
                return True  # No subcommand provided
            subcommand = tokens[1]
            if subcommand not in self.RESTRICTED_COMMANDS[main_cmd]:
                return True

        # Layer 3: Check piped commands
        for piped_cmd in self._extract_piped_commands(command):
            if piped_cmd in self.dangerous_commands:
                return True

        return False

    def _extract_piped_commands(self, command: str) -> List[str]:
        """Extract all commands in a piped sequence.

        Args:
            command: Shell command potentially with pipes

        Returns:
            List of command names (main executables) in pipe sequence
        """
        piped_commands = []

        # Split by pipe
        pipe_segments = command.split('|')

        for segment in pipe_segments:
            try:
                tokens = shlex.split(segment.strip())
                if tokens:
                    cmd = tokens[0].split('/')[-1]
                    piped_commands.append(cmd)
            except ValueError:
                # Skip segments that can't be parsed
                continue

        return piped_commands

    def get_reason(self, command: str) -> Optional[str]:
        """Get the reason why a command is considered dangerous.

        Args:
            command: Shell command to analyze

        Returns:
            Reason string if dangerous, None otherwise
        """
        try:
            tokens = shlex.split(command)
        except ValueError:
            return "Command cannot be safely parsed"

        if not tokens:
            return None

        shell_control_reason = self._shell_control_reason(command)
        if shell_control_reason is not None:
            return shell_control_reason

        main_cmd = tokens[0].split('/')[-1]

        # Check main command
        if main_cmd in self.dangerous_commands:
            return f"Command '{main_cmd}' is in the dangerous commands blacklist"

        inline_exec_reason = self._inline_exec_reason(main_cmd, tokens)
        if inline_exec_reason is not None:
            return inline_exec_reason

        # Check restricted commands
        if main_cmd in self.RESTRICTED_COMMANDS:
            if len(tokens) < 2:
                return f"Command '{main_cmd}' requires explicit subcommand"
            subcommand = tokens[1]
            if subcommand not in self.RESTRICTED_COMMANDS[main_cmd]:
                allowed = ", ".join(self.RESTRICTED_COMMANDS[main_cmd])
                return f"Command '{main_cmd} {subcommand}' not allowed. Only: {allowed}"

        # Check piped commands
        for piped_cmd in self._extract_piped_commands(command):
            if piped_cmd in self.dangerous_commands:
                return f"Piped command '{piped_cmd}' is dangerous"

        return None

    def add_dangerous_command(self, cmd: str) -> None:
        """Add a command to the dangerous blacklist.

        Args:
            cmd: Command name to add
        """
        self.dangerous_commands.add(cmd)

    def remove_dangerous_command(self, cmd: str) -> None:
        """Remove a command from the dangerous blacklist.

        Args:
            cmd: Command name to remove
        """
        self.dangerous_commands.discard(cmd)

    def set_restricted_command(self, cmd: str, allowed_subcommands: Set[str]) -> None:
        """Configure a command as restricted with allowed subcommands.

        Args:
            cmd: Command name
            allowed_subcommands: Set of allowed subcommands
        """
        self.RESTRICTED_COMMANDS[cmd] = allowed_subcommands

    def _inline_exec_reason(self, main_cmd: str, tokens: List[str]) -> Optional[str]:
        flags = self.INLINE_EXEC_FLAGS.get(main_cmd)
        if not flags:
            return None

        for token in tokens[1:]:
            if token in flags or any(token.startswith(f"{flag}=") for flag in flags):
                return (
                    f"Inline interpreter execution via '{main_cmd} {token}' is blocked "
                    "by the command allowlist"
                )
        return None

    def _shell_control_reason(self, command: str) -> Optional[str]:
        """Return why shell control syntax is blocked, if present.

        MiniHarness allows pipes so benign inspection pipelines remain usable,
        but rejects shell control syntax that can hide a second command from
        the first-token blacklist.
        """
        for operator, reason in self.SHELL_CONTROL_OPERATORS.items():
            if operator in command:
                return f"Shell control operator blocked: {reason}"
        return None
