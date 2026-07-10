"""MCP tool schema cache, registry, and LLM-facing adapter."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from mini_harness.mcp.auth import BearerTokenAuth
from mini_harness.mcp.client import MCPClient, MCPClientProtocol
from mini_harness.mcp.transports import MCPTransport, StdioTransport, StreamableHTTPTransport

logger = logging.getLogger(__name__)


@dataclass
class CachedToolSchema:
    """Cached representation of one remote MCP tool schema."""

    server_id: str
    tool_name: str
    description: str
    input_schema: dict[str, Any]
    cached_at: datetime
    schema_hash: str

    @classmethod
    def from_mcp_tool(cls, server_id: str, tool_dict: Mapping[str, Any]) -> "CachedToolSchema":
        input_schema = dict(tool_dict.get("inputSchema", {}))
        schema_hash = hashlib.sha256(
            json.dumps(input_schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return cls(
            server_id=server_id,
            tool_name=str(tool_dict["name"]),
            description=str(tool_dict.get("description", "")),
            input_schema=input_schema,
            cached_at=datetime.now(timezone.utc),
            schema_hash=schema_hash,
        )


class ToolSchemaCache:
    """Memory-and-disk cache for remote tool schemas."""

    def __init__(self, cache_dir: str = "./mcp_cache", ttl_seconds: int = 3600):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_seconds
        self.memory_cache: dict[str, CachedToolSchema] = {}
        os.makedirs(cache_dir, exist_ok=True)

    async def get(self, server_id: str, tool_name: str) -> CachedToolSchema | None:
        cache_key = f"{server_id}#{tool_name}"
        cached = self.memory_cache.get(cache_key)
        if cached is not None:
            if self._is_fresh(cached):
                return cached
            self.memory_cache.pop(cache_key, None)

        disk_path = self._get_disk_path(server_id, tool_name)
        if not os.path.exists(disk_path):
            return None
        try:
            with open(disk_path, "r", encoding="utf-8") as cache_file:
                data = json.load(cache_file)
            disk_cached = CachedToolSchema(
                **{**data, "cached_at": datetime.fromisoformat(data["cached_at"])}
            )
            if not self._is_fresh(disk_cached):
                return None
            self.memory_cache[cache_key] = disk_cached
            return disk_cached
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            logger.warning("Failed to load cached schema from %s: %s", disk_path, error)
            return None

    async def put(self, schema: CachedToolSchema) -> None:
        cache_key = f"{schema.server_id}#{schema.tool_name}"
        self.memory_cache[cache_key] = schema
        disk_path = self._get_disk_path(schema.server_id, schema.tool_name)
        try:
            os.makedirs(os.path.dirname(disk_path), exist_ok=True)
            with open(disk_path, "w", encoding="utf-8") as cache_file:
                data = asdict(schema)
                data["cached_at"] = schema.cached_at.isoformat()
                json.dump(data, cache_file, indent=2)
        except OSError as error:
            logger.warning("Failed to write cached schema to %s: %s", disk_path, error)

    def _get_disk_path(self, server_id: str, tool_name: str) -> str:
        filename = f"{server_id}_{tool_name.replace('/', '_')}.json"
        return os.path.join(self.cache_dir, filename)

    def _is_fresh(self, schema: CachedToolSchema) -> bool:
        cached_at = schema.cached_at
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=timezone.utc)
            schema.cached_at = cached_at
        return datetime.now(timezone.utc) - cached_at < timedelta(seconds=self.ttl_seconds)

    def get_stats(self) -> dict[str, Any]:
        disk_items = len([name for name in os.listdir(self.cache_dir) if name.endswith(".json")])
        return {
            "memory_items": len(self.memory_cache),
            "disk_items": disk_items,
            "cache_dir": self.cache_dir,
        }


@dataclass
class MCPServerConfig:
    """Connection and lifecycle configuration for one MCP server."""

    server_id: str
    server_name: str
    transport_type: str
    endpoint: str
    enabled: bool = True
    priority: int = 0
    timeout_seconds: float = 30
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    cwd: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    auth: BearerTokenAuth | None = None
    verify_ssl: bool = True


ClientFactory = Callable[[MCPServerConfig], MCPClientProtocol]


def create_mcp_client(config: MCPServerConfig) -> MCPClient:
    """Build a production client using only official SDK transport adapters."""
    transport: MCPTransport
    if config.transport_type == "stdio":
        transport = StdioTransport(
            command=config.endpoint,
            args=config.args,
            env=config.env,
            cwd=config.cwd,
        )
    elif config.transport_type in {"streamable_http", "http"}:
        transport = StreamableHTTPTransport(
            url=config.endpoint,
            auth=config.auth,
            headers=config.headers,
            verify_ssl=config.verify_ssl,
        )
    else:
        raise ValueError(f"Unknown MCP transport type: {config.transport_type}")
    return MCPClient(transport, timeout_seconds=config.timeout_seconds)


class MCPToolRegistry:
    """Discover and invoke tools from configured MCP servers."""

    def __init__(
        self,
        schema_cache: ToolSchemaCache | None = None,
        client_factory: ClientFactory | None = None,
    ):
        self.servers: dict[str, MCPServerConfig] = {}
        self.schema_cache = schema_cache or ToolSchemaCache()
        self.client_factory = client_factory or create_mcp_client
        self.clients: dict[str, MCPClientProtocol] = {}
        self.tool_to_servers: dict[str, list[str]] = {}
        self.lock = asyncio.Lock()
        self.last_discovery_time = 0.0
        self.discovery_interval = 300

    async def add_server(self, config: MCPServerConfig) -> None:
        async with self.lock:
            self.servers[config.server_id] = config

    async def discover_tools(self, force: bool = False) -> dict[str, list[str]]:
        async with self.lock:
            now = datetime.now().timestamp()
            if not force and (now - self.last_discovery_time) < self.discovery_interval:
                return self.tool_to_servers

            discovered: dict[str, list[str]] = {}
            for server_id, config in sorted(
                self.servers.items(), key=lambda item: item[1].priority, reverse=True
            ):
                if not config.enabled:
                    continue
                try:
                    client = await self._get_client(server_id, config)
                    await client.ensure_initialized()
                    tools = await client.list_tools()
                    for tool in tools:
                        discovered.setdefault(str(tool["name"]), []).append(server_id)
                except Exception as error:
                    logger.warning("MCP discovery failed for %s: %s", server_id, error)

            self.tool_to_servers = discovered
            self.last_discovery_time = now
            return self.tool_to_servers

    async def get_tool_schema(self, tool_name: str) -> CachedToolSchema | None:
        for server_id in self.tool_to_servers.get(tool_name, []):
            cached = await self.schema_cache.get(server_id, tool_name)
            if cached is not None:
                return cached
            try:
                config = self.servers[server_id]
                client = await self._get_client(server_id, config)
                await client.ensure_initialized()
                for tool in await client.list_tools():
                    if tool["name"] == tool_name:
                        schema = CachedToolSchema.from_mcp_tool(server_id, tool)
                        await self.schema_cache.put(schema)
                        return schema
            except Exception as error:
                logger.warning("MCP schema lookup failed for %s: %s", server_id, error)
        return None

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        agent_id: str | None = None,
    ) -> tuple[bool, Any, str]:
        del agent_id
        server_ids = self.tool_to_servers.get(tool_name, [])
        if not server_ids:
            return False, None, f"Tool {tool_name} not found"

        server_id = server_ids[0]
        try:
            config = self.servers[server_id]
            client = await self._get_client(server_id, config)
            await client.ensure_initialized()
            result = await client.call_tool(
                tool_name,
                arguments,
                timeout_seconds=config.timeout_seconds,
            )
            return True, result, ""
        except Exception as error:
            return False, None, str(error)

    async def close(self) -> None:
        """Close every client owned by the registry."""
        clients = tuple(self.clients.values())
        self.clients.clear()
        if clients:
            await asyncio.gather(*(client.close() for client in clients))

    async def _get_client(
        self,
        server_id: str,
        config: MCPServerConfig,
    ) -> MCPClientProtocol:
        if server_id not in self.clients:
            self.clients[server_id] = self.client_factory(config)
        return self.clients[server_id]


class MCPToolAdapter:
    """Translate discovered MCP tools into LLM-facing definitions."""

    def __init__(self, registry: MCPToolRegistry):
        self.registry = registry

    async def get_available_tools(self) -> list[dict[str, Any]]:
        await self.registry.discover_tools()
        tools: list[dict[str, Any]] = []
        for tool_name in self.registry.tool_to_servers:
            schema = await self.registry.get_tool_schema(tool_name)
            if schema is not None:
                tools.append(self._schema_to_llm_format(schema))
        return tools

    async def call_tool_from_llm(
        self,
        tool_name: str,
        tool_input: str | dict[str, Any],
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            arguments = json.loads(tool_input) if isinstance(tool_input, str) else tool_input
            success, result, error = await self.registry.call_tool(
                tool_name,
                arguments,
                agent_id,
            )
            return {"success": success, "result": result, "error": error}
        except json.JSONDecodeError as error:
            return {"success": False, "result": None, "error": f"Invalid JSON input: {error}"}
        except Exception as error:
            return {"success": False, "result": None, "error": str(error)}

    @staticmethod
    def _schema_to_llm_format(schema: CachedToolSchema) -> dict[str, Any]:
        return {
            "name": schema.tool_name,
            "description": schema.description,
            "input_schema": schema.input_schema,
        }


class MiniHarnessWithMCP:
    """Small composition wrapper for an explicitly configured MCP registry."""

    def __init__(
        self,
        server_configs: Sequence[MCPServerConfig] = (),
        schema_cache: ToolSchemaCache | None = None,
        client_factory: ClientFactory | None = None,
    ):
        self.server_configs = tuple(server_configs)
        self.schema_cache = schema_cache or ToolSchemaCache()
        self.registry = MCPToolRegistry(self.schema_cache, client_factory=client_factory)
        self.adapter = MCPToolAdapter(self.registry)

    async def initialize(self) -> None:
        for config in self.server_configs:
            await self.registry.add_server(config)
        await self.registry.discover_tools(force=True)

    async def close(self) -> None:
        await self.registry.close()

    async def get_tools_for_agent(self) -> list[dict[str, Any]]:
        return await self.adapter.get_available_tools()

    async def process_tool_call(
        self,
        tool_name: str,
        tool_input: str | dict[str, Any],
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.adapter.call_tool_from_llm(tool_name, tool_input, agent_id)

    def get_stats(self) -> dict[str, Any]:
        return {
            "servers_enabled": sum(1 for server in self.registry.servers.values() if server.enabled),
            "tools_discovered": len(self.registry.tool_to_servers),
            "schema_cache": self.schema_cache.get_stats(),
        }
