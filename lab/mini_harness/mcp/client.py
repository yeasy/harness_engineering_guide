"""Lifecycle-safe client built on the official MCP Python SDK."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any, Protocol

from mcp import ClientSession
from mcp.types import Implementation, TextContent

from mini_harness.mcp.transports import MCPTransport


class MCPClientError(RuntimeError):
    """Base error for MCP client lifecycle and request failures."""


class MCPNotInitializedError(MCPClientError):
    """Raised when a request is attempted before initialize completes."""


class MCPClientClosedError(MCPClientError):
    """Raised when a closed client is reused."""


class MCPConnectionError(MCPClientError):
    """Raised when a transport cannot connect or initialize."""


class MCPRequestTimeout(MCPClientError, TimeoutError):
    """Raised after cancelling a request that exceeded its deadline."""


class MCPToolError(MCPClientError):
    """Raised when the remote tool reports an MCP error result."""


@dataclass(frozen=True)
class InitializationMetadata:
    """Negotiated lifecycle values retained after initialization."""

    protocol_version: str
    capabilities: dict[str, Any]
    server_name: str
    server_version: str


class MCPClientProtocol(Protocol):
    """Small client interface used by the registry and test fakes."""

    initialized: bool
    closed: bool

    async def initialize(self) -> InitializationMetadata:
        """Open the transport and negotiate protocol capabilities."""

    async def ensure_initialized(self) -> None:
        """Initialize once if necessary."""

    async def list_tools(self) -> list[dict[str, Any]]:
        """List remote tool schemas."""

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        """Invoke a remote tool."""

    async def close(self) -> None:
        """Close the session and transport."""


def _exception_details(error: BaseException) -> str:
    """Flatten exception groups so HTTP status details remain actionable."""
    messages: list[str] = []
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        message = str(current).strip()
        if message and message not in messages:
            messages.append(message)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        elif current.__context__ is not None:
            pending.append(current.__context__)
    return "; ".join(messages) or type(error).__name__


class MCPClient:
    """Own an official SDK session and enforce its lifecycle explicitly."""

    def __init__(self, transport: MCPTransport, timeout_seconds: float = 30.0):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.initialized = False
        self.closed = False
        self.metadata: InitializationMetadata | None = None
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def initialize(self) -> InitializationMetadata:
        """Connect and retain the negotiated version and capabilities."""
        self._ensure_open()
        if self.metadata is not None:
            return self.metadata

        stack = AsyncExitStack()
        self._stack = stack
        try:
            async with asyncio.timeout(self.timeout_seconds):
                read_stream, write_stream = await stack.enter_async_context(
                    self.transport.connect()
                )
                session = ClientSession(
                    read_stream,
                    write_stream,
                    client_info=Implementation(name="MiniHarness", version="0.1.0"),
                )
                self._session = await stack.enter_async_context(session)
                result = await self._session.initialize()
        except TimeoutError as error:
            await self._abort_stack()
            raise MCPRequestTimeout("MCP initialize timed out") from error
        except BaseException as error:
            cleanup_error = await self._abort_stack()
            details = _exception_details(error)
            if cleanup_error is not None:
                details = f"{details}; {_exception_details(cleanup_error)}"
            raise MCPConnectionError(
                f"MCP initialize failed: {details}"
            ) from error

        self.metadata = InitializationMetadata(
            protocol_version=str(result.protocolVersion),
            capabilities=result.capabilities.model_dump(by_alias=True, exclude_none=True),
            server_name=result.serverInfo.name,
            server_version=result.serverInfo.version,
        )
        self.initialized = True
        return self.metadata

    async def ensure_initialized(self) -> None:
        """Initialize once for registry-managed clients."""
        if not self.initialized:
            await self.initialize()

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return JSON-compatible tool definitions from the negotiated session."""
        session = self._require_session()
        result = await self._request(session.list_tools(), "tools/list", self.timeout_seconds)
        return [tool.model_dump(by_alias=True, exclude_none=True) for tool in result.tools]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> Any:
        """Call a tool and normalize common text or structured results."""
        session = self._require_session()
        deadline = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        if deadline <= 0:
            raise ValueError("timeout_seconds must be positive")
        result = await self._request(
            session.call_tool(name, arguments),
            f"tools/call:{name}",
            deadline,
        )
        if result.isError:
            raise MCPToolError(self._content_text(result.content) or f"Tool '{name}' failed")
        text = self._content_text(result.content)
        if text is not None:
            return text
        if result.structuredContent is not None:
            return result.structuredContent
        return [block.model_dump(by_alias=True, exclude_none=True) for block in result.content]

    async def close(self) -> None:
        """Close the SDK session and transport; repeated calls are harmless."""
        if self.closed:
            return
        self.closed = True
        self.initialized = False
        self.metadata = None
        await self._abort_stack(suppress_errors=False)

    async def __aenter__(self) -> "MCPClient":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()

    async def _request(self, awaitable, operation: str, timeout_seconds: float):
        try:
            async with asyncio.timeout(timeout_seconds):
                return await awaitable
        except TimeoutError as error:
            raise MCPRequestTimeout(f"MCP {operation} timed out") from error

    def _ensure_open(self) -> None:
        if self.closed:
            raise MCPClientClosedError("MCP client is closed")

    def _require_session(self) -> ClientSession:
        self._ensure_open()
        if not self.initialized or self._session is None:
            raise MCPNotInitializedError("MCP initialize must complete before tool use")
        return self._session

    async def _abort_stack(self, suppress_errors: bool = True) -> BaseException | None:
        stack, self._stack = self._stack, None
        self._session = None
        self.initialized = False
        if stack is None:
            return None
        if suppress_errors:
            try:
                await stack.aclose()
            except BaseException as error:
                return error
            return None
        await stack.aclose()
        return None

    @staticmethod
    def _content_text(content: list[Any]) -> str | None:
        texts = [block.text for block in content if isinstance(block, TextContent)]
        if not texts:
            return None
        return "\n".join(texts)
