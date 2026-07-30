"""Official MCP SDK transport adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from mini_harness.mcp.auth import BearerTokenAuth


class MCPTransport(Protocol):
    """Transport boundary required by :class:`MCPClient`."""

    def connect(self):
        """Return an async context manager yielding SDK read/write streams."""


@dataclass(frozen=True)
class StdioTransport:
    """Launch a local MCP server through the SDK stdio adapter."""

    command: str
    args: tuple[str, ...] = ()
    env: Mapping[str, str] | None = None
    cwd: str | None = None

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[tuple[Any, Any]]:
        parameters = StdioServerParameters(
            command=self.command,
            args=list(self.args),
            env=dict(self.env) if self.env is not None else None,
            cwd=self.cwd,
        )
        async with stdio_client(parameters) as streams:
            yield streams


@dataclass(frozen=True)
class StreamableHTTPTransport:
    """Connect to a remote MCP server through Streamable HTTP."""

    url: str
    auth: BearerTokenAuth | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    verify_ssl: bool = True

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[tuple[Any, Any]]:
        headers = dict(self.headers)
        if self.auth is not None:
            headers.update(self.auth.as_headers())

        async with httpx.AsyncClient(headers=headers, verify=self.verify_ssl) as http_client:
            async with streamable_http_client(
                self.url,
                http_client=http_client,
                terminate_on_close=True,
            ) as (read_stream, write_stream):
                # mcp 2.0 起该上下文只产出两个流：协议级会话已从
                # Streamable HTTP 中移除，不再有 get_session_id 回调。
                yield read_stream, write_stream
