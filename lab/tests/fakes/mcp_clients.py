"""Test-only MCP clients for registry and adapter unit tests."""

from __future__ import annotations

from typing import Any

from mini_harness.mcp.client import (
    InitializationMetadata,
    MCPClientClosedError,
    MCPNotInitializedError,
)


class FakeMCPClient:
    """Deterministic client fake that enforces the public lifecycle contract."""

    def __init__(self, tools: list[dict[str, Any]], results: dict[str, Any]):
        self.tools = tools
        self.results = results
        self.initialized = False
        self.closed = False
        self.metadata = InitializationMetadata(
            protocol_version="2025-11-25",
            capabilities={"tools": {}},
            server_name="test-fake",
            server_version="1.0",
        )

    async def initialize(self) -> InitializationMetadata:
        if self.closed:
            raise MCPClientClosedError("MCP client is closed")
        self.initialized = True
        return self.metadata

    async def ensure_initialized(self) -> None:
        if not self.initialized:
            await self.initialize()

    async def list_tools(self) -> list[dict[str, Any]]:
        if not self.initialized:
            raise MCPNotInitializedError("initialize first")
        return self.tools

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        if not self.initialized:
            raise MCPNotInitializedError("initialize first")
        return self.results[name]

    async def close(self) -> None:
        self.closed = True
        self.initialized = False


class FakeMCPClientFactory:
    """Create test clients based on transport without touching real I/O."""

    def __init__(self):
        self.clients: dict[str, FakeMCPClient] = {}

    def __call__(self, config) -> FakeMCPClient:
        if config.transport_type == "stdio":
            tools = [
                {
                    "name": "read_file",
                    "description": "Read file contents",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
                {
                    "name": "write_file",
                    "description": "Write file contents",
                    "inputSchema": {"type": "object"},
                },
            ]
            results = {"read_file": "fake file", "write_file": "written"}
        else:
            tools = [
                {
                    "name": "web_search",
                    "description": "Search the web",
                    "inputSchema": {"type": "object"},
                }
            ]
            results = {"web_search": "fake search"}
        client = FakeMCPClient(tools, results)
        self.clients[config.server_id] = client
        return client
