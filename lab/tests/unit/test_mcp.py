"""
Tests for mini_harness.mcp module:
- integration.py: ToolSchemaCache, CachedToolSchema, MCPToolRegistry, MCPToolAdapter, MiniHarnessWithMCP
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from mini_harness.mcp.integration import (
    BaseMCPClient,
    CachedToolSchema,
    MCPServerConfig,
    MCPToolAdapter,
    MCPToolRegistry,
    MiniHarnessWithMCP,
    MockHttpMCPClient,
    MockStdioMCPClient,
    ToolSchemaCache,
)

# ============ CachedToolSchema Tests ============


class TestCachedToolSchema:
    def test_creation(self):
        schema = CachedToolSchema(
            server_id="test-server",
            tool_name="read_file",
            description="Read a file",
            input_schema={"type": "object"},
            cached_at=datetime.now(timezone.utc),
            schema_hash="abc123",
        )
        assert schema.server_id == "test-server"
        assert schema.tool_name == "read_file"

    def test_from_mcp_tool(self):
        tool_dict = {
            "name": "web_search",
            "description": "Search the web",
            "inputSchema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
        schema = CachedToolSchema.from_mcp_tool("web-server", tool_dict)
        assert schema.server_id == "web-server"
        assert schema.tool_name == "web_search"
        assert schema.description == "Search the web"
        assert schema.schema_hash is not None
        assert len(schema.schema_hash) > 0

    def test_schema_hash_deterministic(self):
        tool_dict = {
            "name": "test",
            "inputSchema": {"type": "object", "properties": {"a": {"type": "string"}}},
        }
        s1 = CachedToolSchema.from_mcp_tool("server", tool_dict)
        s2 = CachedToolSchema.from_mcp_tool("server", tool_dict)
        assert s1.schema_hash == s2.schema_hash


# ============ ToolSchemaCache Tests ============


class TestToolSchemaCache:
    @pytest.mark.asyncio
    async def test_put_and_get_memory(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        schema = CachedToolSchema(
            server_id="srv",
            tool_name="tool1",
            description="A tool",
            input_schema={"type": "object"},
            cached_at=datetime.now(timezone.utc),
            schema_hash="hash1",
        )
        await cache.put(schema)

        retrieved = await cache.get("srv", "tool1")
        assert retrieved is not None
        assert retrieved.tool_name == "tool1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        result = await cache.get("no-server", "no-tool")
        assert result is None

    @pytest.mark.asyncio
    async def test_disk_persistence(self, tmp_dir):
        # Write with one cache instance
        cache1 = ToolSchemaCache(cache_dir=tmp_dir, ttl_seconds=3600)
        schema = CachedToolSchema(
            server_id="srv",
            tool_name="persistent",
            description="Persistent tool",
            input_schema={"type": "object"},
            cached_at=datetime.now(timezone.utc),
            schema_hash="hash_p",
        )
        await cache1.put(schema)

        # Read with another cache instance (simulating restart)
        cache2 = ToolSchemaCache(cache_dir=tmp_dir, ttl_seconds=3600)
        retrieved = await cache2.get("srv", "persistent")
        assert retrieved is not None
        assert retrieved.description == "Persistent tool"

    @pytest.mark.asyncio
    async def test_ttl_expiry(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir, ttl_seconds=1)
        schema = CachedToolSchema(
            server_id="srv",
            tool_name="expiring",
            description="Will expire",
            input_schema={},
            cached_at=datetime.now(timezone.utc) - timedelta(seconds=10),  # Already old
            schema_hash="h",
        )
        # Put directly in memory cache (bypassing normal put which sets fresh cached_at)
        cache.memory_cache["srv#expiring"] = schema

        # Memory cache should return None due to TTL
        result = await cache.get("srv", "expiring")
        # The memory cache entry is expired, but it will try disk
        # Disk won't have it since we didn't write, so None
        # Actually, let me just verify the memory path: cached_at is 10s ago, ttl is 1s
        # So memory cache returns None, disk won't have it
        assert result is None

    @pytest.mark.asyncio
    async def test_disk_cache_respects_ttl(self, tmp_dir):
        cache1 = ToolSchemaCache(cache_dir=tmp_dir, ttl_seconds=1)
        schema = CachedToolSchema(
            server_id="srv",
            tool_name="expired_on_disk",
            description="Expired disk tool",
            input_schema={},
            cached_at=datetime.now(timezone.utc) - timedelta(seconds=10),
            schema_hash="h",
        )
        await cache1.put(schema)

        cache2 = ToolSchemaCache(cache_dir=tmp_dir, ttl_seconds=1)
        result = await cache2.get("srv", "expired_on_disk")
        assert result is None

    def test_get_stats(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        stats = cache.get_stats()
        assert "memory_items" in stats
        assert "disk_items" in stats
        assert stats["memory_items"] == 0


# ============ MCPServerConfig Tests ============


class TestMCPServerConfig:
    def test_defaults(self):
        config = MCPServerConfig(
            server_id="test",
            server_name="Test Server",
            transport_type="stdio",
            endpoint="./server.py",
        )
        assert config.enabled is True
        assert config.priority == 0
        assert config.timeout_seconds == 30


# ============ MockClient Tests ============


class TestMockClients:
    @pytest.mark.asyncio
    async def test_base_initialize_marks_client_initialized(self):
        class PlainMCPClient(BaseMCPClient):
            def __init__(self):
                super().__init__()
                self.methods = []

            async def send_request(
                self, method: str, params: dict = None, expect_response: bool = True
            ) -> dict:
                self.methods.append(method)
                if method == "initialize":
                    return {"result": {"protocolVersion": self.protocol_version}}
                if method == "notifications/initialized":
                    return {}
                raise AssertionError(method)

        client = PlainMCPClient()
        await client.initialize()
        assert client.initialized is True
        assert client.methods == ["initialize", "notifications/initialized"]

        await client.ensure_initialized()
        assert client.methods == ["initialize", "notifications/initialized"]

    @pytest.mark.asyncio
    async def test_request_before_initialize_rejected(self):
        client = MockStdioMCPClient("./server.py")
        response = await client.send_request("tools/list")
        assert "error" in response
        assert "initialize" in response["error"]["message"]

    @pytest.mark.asyncio
    async def test_stdio_client_list_tools(self):
        client = MockStdioMCPClient("./server.py")
        await client.initialize()
        response = await client.send_request("tools/list")
        tools = response["result"]["tools"]
        assert len(tools) > 0
        names = [t["name"] for t in tools]
        assert "read_file" in names

    @pytest.mark.asyncio
    async def test_stdio_client_call_tool(self):
        client = MockStdioMCPClient("./server.py")
        await client.initialize()
        response = await client.send_request("tools/call", {"name": "read_file"})
        content = response["result"]["content"]
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_http_client_list_tools(self):
        client = MockHttpMCPClient("http://localhost:8001")
        await client.initialize()
        response = await client.send_request("tools/list")
        tools = response["result"]["tools"]
        names = [t["name"] for t in tools]
        assert "web_search" in names

    @pytest.mark.asyncio
    async def test_http_client_call_tool(self):
        client = MockHttpMCPClient("http://localhost:8001")
        await client.initialize()
        response = await client.send_request("tools/call", {"name": "web_search"})
        assert "result" in response


# ============ MCPToolRegistry Tests ============


class TestMCPToolRegistry:
    @pytest.mark.asyncio
    async def test_add_server(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(
            MCPServerConfig(
                server_id="fs",
                server_name="Filesystem",
                transport_type="stdio",
                endpoint="./fs_server.py",
            )
        )
        assert "fs" in registry.servers

    @pytest.mark.asyncio
    async def test_discover_tools(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(
            MCPServerConfig(
                server_id="fs",
                server_name="Filesystem",
                transport_type="stdio",
                endpoint="./fs_server.py",
            )
        )

        tools = await registry.discover_tools(force=True)
        assert len(tools) > 0
        assert "read_file" in tools
        assert registry.clients["fs"].initialized is True

    @pytest.mark.asyncio
    async def test_discover_multiple_servers(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(MCPServerConfig("fs", "FS", "stdio", "./fs.py"))
        await registry.add_server(MCPServerConfig("web", "Web", "streamable_http", "http://localhost"))

        tools = await registry.discover_tools(force=True)
        assert "read_file" in tools
        assert "web_search" in tools

    @pytest.mark.asyncio
    async def test_legacy_http_transport_alias(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(MCPServerConfig("web", "Web", "http", "http://localhost"))
        tools = await registry.discover_tools(force=True)
        assert "web_search" in tools

    @pytest.mark.asyncio
    async def test_disabled_server_skipped(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(
            MCPServerConfig("disabled", "Disabled", "stdio", "./d.py", enabled=False)
        )

        tools = await registry.discover_tools(force=True)
        assert len(tools) == 0

    @pytest.mark.asyncio
    async def test_call_tool(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(MCPServerConfig("fs", "FS", "stdio", "./fs.py"))
        await registry.discover_tools(force=True)

        success, result, error = await registry.call_tool("read_file", {"path": "/tmp/test"})
        assert success is True
        assert result is not None

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        success, result, error = await registry.call_tool("ghost", {})
        assert success is False
        assert "not found" in error.lower()


# ============ MCPToolAdapter Tests ============


class TestMCPToolAdapter:
    @pytest.mark.asyncio
    async def test_get_available_tools(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(MCPServerConfig("fs", "FS", "stdio", "./fs.py"))

        adapter = MCPToolAdapter(registry)
        tools = await adapter.get_available_tools()
        assert len(tools) > 0
        assert all("name" in t for t in tools)
        assert all("description" in t for t in tools)

    @pytest.mark.asyncio
    async def test_call_tool_from_llm(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(MCPServerConfig("fs", "FS", "stdio", "./fs.py"))
        await registry.discover_tools(force=True)

        adapter = MCPToolAdapter(registry)
        result = await adapter.call_tool_from_llm(
            "read_file", json.dumps({"path": "/tmp/test.txt"})
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_call_tool_invalid_json(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)
        adapter = MCPToolAdapter(registry)

        result = await adapter.call_tool_from_llm("test", "not json{")
        assert result["success"] is False
        assert "JSON" in result["error"]

    @pytest.mark.asyncio
    async def test_call_tool_with_dict_input(self, tmp_dir):
        cache = ToolSchemaCache(cache_dir=tmp_dir)
        registry = MCPToolRegistry(schema_cache=cache)

        await registry.add_server(MCPServerConfig("fs", "FS", "stdio", "./fs.py"))
        await registry.discover_tools(force=True)

        adapter = MCPToolAdapter(registry)
        result = await adapter.call_tool_from_llm(
            "read_file", {"path": "/tmp/test.txt"}  # Dict, not string
        )
        assert result["success"] is True


# ============ MiniHarnessWithMCP Tests ============


class TestMiniHarnessWithMCP:
    @pytest.mark.asyncio
    async def test_initialize(self):
        harness = MiniHarnessWithMCP()
        await harness.initialize()
        assert len(harness.registry.servers) == 2

    @pytest.mark.asyncio
    async def test_get_tools_for_agent(self):
        harness = MiniHarnessWithMCP()
        await harness.initialize()
        tools = await harness.get_tools_for_agent()
        assert len(tools) > 0

    @pytest.mark.asyncio
    async def test_process_tool_call(self):
        harness = MiniHarnessWithMCP()
        await harness.initialize()
        result = await harness.process_tool_call("read_file", json.dumps({"path": "/tmp/test.txt"}))
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_get_stats(self):
        harness = MiniHarnessWithMCP()
        await harness.initialize()
        stats = harness.get_stats()
        assert stats["servers_enabled"] == 2
        assert stats["tools_discovered"] > 0
        assert "schema_cache" in stats
