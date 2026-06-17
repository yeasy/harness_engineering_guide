"""
Tests for mini_harness.tools module:
- builtin.py: ToolResult, Tool, BashTool, FileReadTool, FileWriteTool, ExecutionPipeline, ToolResultBlock
- registry.py: ToolRegistry
"""

import os

import pytest

from mini_harness.tools.builtin import (
    BashTool,
    ExecutionPipeline,
    FileReadTool,
    FileWriteTool,
    Tool,
    ToolResult,
    ToolResultBlock,
)
from mini_harness.tools.registry import ToolRegistry

# ============ ToolResult Tests ============


class TestToolResult:
    def test_success_result(self):
        result = ToolResult(success=True, content="output", execution_time=0.5)
        assert result.success is True
        assert result.content == "output"
        assert result.execution_time == 0.5
        assert result.error_type is None

    def test_error_result(self):
        result = ToolResult(
            success=False,
            content="file not found",
            execution_time=0.01,
            error_type="FileNotFoundError",
        )
        assert result.success is False
        assert result.error_type == "FileNotFoundError"


# ============ ToolResultBlock Tests ============


class TestToolResultBlock:
    def test_to_dict(self):
        block = ToolResultBlock(
            tool_name="bash_exec", success=True, content="hello", execution_time=0.1
        )
        d = block.to_dict()
        assert d["tool_name"] == "bash_exec"
        assert d["success"] is True
        assert d["content"] == "hello"
        assert d["execution_time"] == 0.1
        assert d["error_type"] is None

    def test_error_block(self):
        block = ToolResultBlock(
            tool_name="unknown_tool",
            success=False,
            content="Tool not found",
            error_type="NotFoundError",
        )
        assert block.success is False
        assert block.error_type == "NotFoundError"


# ============ BashTool Tests ============


class TestBashTool:
    def test_name_and_description(self):
        tool = BashTool()
        assert tool.name() == "bash_exec"
        assert "bash" in tool.description().lower() or "Bash" in tool.description()

    def test_input_schema(self):
        tool = BashTool()
        schema = tool.input_schema()
        assert schema["type"] == "object"
        assert "command" in schema["properties"]
        assert "command" in schema["required"]

    @pytest.mark.asyncio
    async def test_echo_command(self):
        tool = BashTool()
        result = await tool.call({"command": "echo hello"})
        assert result.success is True
        assert "hello" in result.content
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_failing_command(self):
        tool = BashTool()
        result = await tool.call({"command": "false"})
        assert result.success is False
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_timeout(self):
        tool = BashTool()
        result = await tool.call({"command": "sleep 10", "timeout": 1})
        assert result.success is False
        assert result.error_type == "TimeoutError"

    @pytest.mark.asyncio
    async def test_return_code_in_output(self):
        tool = BashTool()
        result = await tool.call({"command": "echo test"})
        assert "returncode: 0" in result.content

    @pytest.mark.asyncio
    async def test_blocks_unlisted_command_by_default(self):
        tool = BashTool()
        result = await tool.call({"command": "uname -a"})
        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "allowlist" in result.content

    @pytest.mark.asyncio
    async def test_blocks_python_by_default(self):
        tool = BashTool()
        result = await tool.call({"command": "python3 -c 'print(1)'"})
        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "allowlist" in result.content

    @pytest.mark.asyncio
    async def test_blocks_dangerous_command(self):
        tool = BashTool()
        result = await tool.call({"command": "rm -rf /tmp/example"})
        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "Dangerous command blocked" in result.content

    def test_check_permissions(self):
        tool = BashTool()
        assert tool.check_permissions({}) is True


# ============ FileReadTool Tests ============


class TestFileReadTool:
    def test_name_and_schema(self):
        tool = FileReadTool()
        assert tool.name() == "file_read"
        schema = tool.input_schema()
        assert "path" in schema["required"]

    @pytest.mark.asyncio
    async def test_read_existing_file(self, tmp_dir):
        filepath = os.path.join(tmp_dir, "test.txt")
        with open(filepath, "w") as f:
            f.write("Hello MiniHarness")

        tool = FileReadTool(base_path=tmp_dir)
        result = await tool.call({"path": filepath})
        assert result.success is True
        assert "Hello MiniHarness" in result.content

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, tmp_dir):
        tool = FileReadTool(base_path=tmp_dir)
        result = await tool.call({"path": "missing.txt"})
        assert result.success is False
        assert result.error_type == "FileNotFoundError"

    @pytest.mark.asyncio
    async def test_read_with_max_bytes(self, tmp_dir):
        filepath = os.path.join(tmp_dir, "large.txt")
        with open(filepath, "w") as f:
            f.write("A" * 1000)

        tool = FileReadTool(base_path=tmp_dir)
        result = await tool.call({"path": filepath, "max_bytes": 100})
        assert result.success is True
        assert len(result.content) <= 200  # 100 bytes + truncation notice

    @pytest.mark.asyncio
    async def test_blocks_path_traversal(self, tmp_dir):
        tool = FileReadTool(base_path=tmp_dir)
        result = await tool.call({"path": "../secret.txt"})
        assert result.success is False
        assert result.error_type == "ValueError"

    @pytest.mark.asyncio
    async def test_blocks_sensitive_files_by_default(self, tmp_dir):
        filepath = os.path.join(tmp_dir, ".env")
        with open(filepath, "w") as f:
            f.write("LLM_API_KEY=fixture-secret")

        tool = FileReadTool(base_path=tmp_dir)
        result = await tool.call({"path": ".env"})
        assert result.success is False
        assert result.error_type == "PermissionError"
        assert "Sensitive file reads" in result.content


# ============ FileWriteTool Tests ============


class TestFileWriteTool:
    def test_name_and_schema(self):
        tool = FileWriteTool()
        assert tool.name() == "file_write"
        schema = tool.input_schema()
        assert "path" in schema["required"]
        assert "content" in schema["required"]

    @pytest.mark.asyncio
    async def test_write_file(self, tmp_dir):
        filepath = os.path.join(tmp_dir, "output.txt")
        tool = FileWriteTool(base_path=tmp_dir)
        result = await tool.call({"path": filepath, "content": "Test content"})
        assert result.success is True

        with open(filepath, "r") as f:
            assert f.read() == "Test content"

    @pytest.mark.asyncio
    async def test_write_file_in_current_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        tool = FileWriteTool()
        result = await tool.call({"path": "output.txt", "content": "local"})
        assert result.success is True
        assert (tmp_path / "output.txt").read_text() == "local"

    @pytest.mark.asyncio
    async def test_write_creates_directories(self, tmp_dir):
        filepath = os.path.join(tmp_dir, "sub", "dir", "file.txt")
        tool = FileWriteTool(base_path=tmp_dir)
        result = await tool.call({"path": filepath, "content": "nested"})
        assert result.success is True
        assert os.path.exists(filepath)

    @pytest.mark.asyncio
    async def test_append_mode(self, tmp_dir):
        filepath = os.path.join(tmp_dir, "append.txt")
        tool = FileWriteTool(base_path=tmp_dir)

        await tool.call({"path": filepath, "content": "Line 1\n"})
        await tool.call({"path": filepath, "content": "Line 2\n", "append": True})

        with open(filepath, "r") as f:
            content = f.read()
        assert "Line 1" in content
        assert "Line 2" in content

    @pytest.mark.asyncio
    async def test_overwrite_mode(self, tmp_dir):
        filepath = os.path.join(tmp_dir, "overwrite.txt")
        tool = FileWriteTool(base_path=tmp_dir)

        await tool.call({"path": filepath, "content": "Original"})
        await tool.call({"path": filepath, "content": "Replaced"})

        with open(filepath, "r") as f:
            content = f.read()
        assert content == "Replaced"

    @pytest.mark.asyncio
    async def test_write_blocks_path_traversal(self, tmp_dir):
        tool = FileWriteTool(base_path=tmp_dir)
        result = await tool.call({"path": "../escape.txt", "content": "blocked"})
        assert result.success is False
        assert result.error_type == "ValueError"


# ============ ToolRegistry Tests ============


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = BashTool()
        registry.register(tool)

        retrieved = registry.get("bash_exec")
        assert retrieved is tool

    def test_get_nonexistent(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(BashTool())
        registry.register(FileReadTool())
        registry.register(FileWriteTool())

        tools = registry.list_tools()
        assert len(tools) == 3
        names = [t["name"] for t in tools]
        assert "bash_exec" in names
        assert "file_read" in names
        assert "file_write" in names

    def test_get_schema(self):
        registry = ToolRegistry()
        registry.register(BashTool())

        schema = registry.get_schema("bash_exec")
        assert schema is not None
        assert schema["name"] == "bash_exec"
        assert "input_schema" in schema

    def test_get_schema_nonexistent(self):
        registry = ToolRegistry()
        assert registry.get_schema("ghost") is None

    def test_schema_cache(self):
        registry = ToolRegistry()
        tool = BashTool()
        registry.register(tool)

        # Schema should be cached at registration time
        assert "bash_exec" in registry.schema_cache
        schema = registry.schema_cache["bash_exec"]
        assert schema["name"] == "bash_exec"
        assert schema["description"] == tool.description()


# ============ ExecutionPipeline Tests ============


class TestExecutionPipeline:
    def _make_pipeline(self, base_path=None):
        registry = ToolRegistry()
        registry.register(BashTool())
        registry.register(FileReadTool(base_path=base_path))
        registry.register(FileWriteTool(base_path=base_path))
        return ExecutionPipeline(registry)

    @pytest.mark.asyncio
    async def test_execute_existing_tool(self):
        pipeline = self._make_pipeline()
        result = await pipeline.execute("bash_exec", {"command": "echo pipeline_test"})
        assert result.success is True
        assert "pipeline_test" in result.content
        assert result.tool_name == "bash_exec"

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        pipeline = self._make_pipeline()
        result = await pipeline.execute("ghost_tool", {})
        assert result.success is False
        assert "not found" in result.content.lower()

    @pytest.mark.asyncio
    async def test_pipeline_permission_denied(self):
        """Test that permission denied is handled."""

        class RestrictedTool(Tool):
            async def call(self, params):
                return ToolResult(success=True, content="ok", execution_time=0)

            def name(self):
                return "restricted"

            def description(self):
                return "Restricted tool"

            def input_schema(self):
                return {"type": "object", "properties": {}}

            def check_permissions(self, context):
                return False

        registry = ToolRegistry()
        registry.register(RestrictedTool())
        pipeline = ExecutionPipeline(registry)

        result = await pipeline.execute("restricted", {})
        assert result.success is False
        assert "permission" in result.content.lower()

    @pytest.mark.asyncio
    async def test_pipeline_file_operations(self, tmp_dir):
        pipeline = self._make_pipeline(base_path=tmp_dir)

        # Write
        filepath = os.path.join(tmp_dir, "pipeline_test.txt")
        result = await pipeline.execute(
            "file_write", {"path": filepath, "content": "Pipeline wrote this"}
        )
        assert result.success is True

        # Read
        result = await pipeline.execute("file_read", {"path": filepath})
        assert result.success is True
        assert "Pipeline wrote this" in result.content
