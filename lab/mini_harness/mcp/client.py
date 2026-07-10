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


@dataclass
class _ConnectionOwner:
    """State shared by callers and the task that owns SDK contexts."""

    ready: asyncio.Future[InitializationMetadata]
    close_event: asyncio.Event
    started: asyncio.Event
    cancel_requested: asyncio.Event
    task: asyncio.Task[None] | None = None
    waiters: int = 0
    delivered: bool = False


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
        self._session: ClientSession | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._owner: _ConnectionOwner | None = None
        self._close_task: asyncio.Task[None] | None = None

    async def initialize(self) -> InitializationMetadata:
        """Connect and retain the negotiated version and capabilities."""
        self._ensure_open()
        async with self._lifecycle_lock:
            self._ensure_open()
            if self.metadata is not None:
                return self.metadata

            owner = self._owner
            if owner is None or owner.task is None or owner.task.done():
                loop = asyncio.get_running_loop()
                owner = _ConnectionOwner(
                    ready=loop.create_future(),
                    close_event=asyncio.Event(),
                    started=asyncio.Event(),
                    cancel_requested=asyncio.Event(),
                )
                owner.task = asyncio.create_task(
                    self._run_connection_owner(owner),
                    name="mini-harness-mcp-connection-owner",
                )
                self._owner = owner
            owner.waiters += 1

        released = False
        observed = False
        try:
            result = await asyncio.shield(owner.ready)
            observed = True
            return result
        except asyncio.CancelledError:
            cancel_owner = self._release_initialize_waiter(owner, cancelled=True)
            released = True
            if cancel_owner:
                await self._cancel_and_wait_for_owner(owner)
            raise
        finally:
            if not released:
                self._release_initialize_waiter(
                    owner,
                    cancelled=False,
                    observed=observed,
                )

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
        async with self._lifecycle_lock:
            was_initialized = self.initialized
            self.closed = True
            self.initialized = False
            self.metadata = None
            owner = self._owner
            owner_task = owner.task if owner is not None else None
            if owner is not None:
                owner.close_event.set()
            close_task = self._close_task
            if close_task is None and owner is not None and owner_task is not None:
                close_task = asyncio.create_task(
                    self._finish_close(owner, cancel_owner=not was_initialized),
                    name="mini-harness-mcp-close",
                )
                self._close_task = close_task

        if close_task is not None:
            await asyncio.shield(close_task)

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

    async def _run_connection_owner(self, owner: _ConnectionOwner) -> None:
        """Enter and exit all SDK contexts in one dedicated task."""
        owner.started.set()
        stack = AsyncExitStack()
        initialization_error: MCPClientError | None = None
        cancelled_error: asyncio.CancelledError | None = None

        try:
            session, metadata = await self._open_sdk_session(stack, owner)
            if await self._publish_connection(session, metadata):
                owner.ready.set_result(metadata)
                await owner.close_event.wait()
            else:
                initialization_error = MCPClientClosedError("MCP client is closed")
        except MCPClientError as error:
            initialization_error = error
        except asyncio.CancelledError as error:
            cancelled_error = error
        finally:
            cleanup_error = await self._close_owner_stack(stack)
            await self._clear_connection_owner(owner)
            self._complete_owner_ready(
                owner,
                initialization_error,
                cancelled_error,
                cleanup_error,
            )

        if cancelled_error is not None:
            raise cancelled_error
        if (
            cleanup_error is not None
            and initialization_error is None
            and owner.ready.done()
            and not owner.ready.cancelled()
            and owner.ready.exception() is None
        ):
            raise cleanup_error

    async def _open_sdk_session(
        self,
        stack: AsyncExitStack,
        owner: _ConnectionOwner,
    ) -> tuple[ClientSession, InitializationMetadata]:
        """Open and initialize the official SDK session for the owner task."""
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
                session = await stack.enter_async_context(session)
                result = await session.initialize()
        except TimeoutError as error:
            raise MCPRequestTimeout("MCP initialize timed out") from error
        except asyncio.CancelledError as error:
            if owner.cancel_requested.is_set():
                raise
            raise MCPConnectionError(
                f"MCP initialize failed: {_exception_details(error)}"
            ) from error
        except Exception as error:  # pylint: disable=broad-exception-caught
            raise MCPConnectionError(
                f"MCP initialize failed: {_exception_details(error)}"
            ) from error

        metadata = InitializationMetadata(
            protocol_version=str(result.protocolVersion),
            capabilities=result.capabilities.model_dump(
                by_alias=True,
                exclude_none=True,
            ),
            server_name=result.serverInfo.name,
            server_version=result.serverInfo.version,
        )
        return session, metadata

    async def _publish_connection(
        self,
        session: ClientSession,
        metadata: InitializationMetadata,
    ) -> bool:
        """Publish an initialized session unless close already won the race."""
        async with self._lifecycle_lock:
            if self.closed:
                return False
            self._session = session
            self.metadata = metadata
            self.initialized = True
            return True

    @staticmethod
    async def _close_owner_stack(stack: AsyncExitStack) -> BaseException | None:
        """Close SDK contexts and retain cleanup failures for the caller."""
        try:
            await stack.aclose()
        except BaseException as error:  # pylint: disable=broad-exception-caught
            return error
        return None

    async def _clear_connection_owner(self, owner: _ConnectionOwner) -> None:
        """Remove public connection state after same-task context cleanup."""
        async with self._lifecycle_lock:
            if self._owner is owner:
                self._owner = None
                self._session = None
                self.initialized = False
                self.metadata = None

    async def _finish_close(self, owner: _ConnectionOwner, *, cancel_owner: bool) -> None:
        """Complete one shared teardown that every close caller joins."""
        owner_task = owner.task
        if owner_task is None:
            return
        if cancel_owner and not owner_task.done():
            await self._cancel_and_wait_for_owner(owner)
        else:
            await self._wait_for_owner(owner_task)

    def _complete_owner_ready(
        self,
        owner: _ConnectionOwner,
        initialization_error: MCPClientError | None,
        cancelled_error: asyncio.CancelledError | None,
        cleanup_error: BaseException | None,
    ) -> None:
        """Resolve initialization waiters only after owner cleanup finishes."""
        if owner.ready.done():
            return
        if initialization_error is not None:
            if cleanup_error is not None:
                details = _exception_details(cleanup_error)
                message = f"{initialization_error}; cleanup failed: {details}"
                initialization_error = type(initialization_error)(message)
            owner.ready.set_exception(initialization_error)
        elif cancelled_error is not None:
            if self.closed:
                owner.ready.set_exception(MCPClientClosedError("MCP client is closed"))
            else:
                owner.ready.cancel()
        elif cleanup_error is not None:
            owner.ready.set_exception(
                MCPConnectionError(
                    f"MCP initialize cleanup failed: {_exception_details(cleanup_error)}"
                )
            )

    def _release_initialize_waiter(
        self,
        owner: _ConnectionOwner,
        *,
        cancelled: bool,
        observed: bool = False,
    ) -> bool:
        """Drop one initialize waiter and stop abandoned connection attempts."""
        owner.waiters -= 1
        owner.delivered = owner.delivered or observed
        return bool(
            cancelled
            and owner.waiters == 0
            and not owner.delivered
            and self._owner is owner
            and owner.task is not None
            and not owner.task.done()
        )

    @classmethod
    async def _cancel_and_wait_for_owner(cls, owner: _ConnectionOwner) -> None:
        """Let the owner start so its cleanup finally block always executes."""
        await owner.started.wait()
        owner_task = owner.task
        if owner_task is None:
            return
        if not owner_task.done():
            owner.cancel_requested.set()
            owner_task.cancel()
        await cls._wait_for_owner(owner_task)

    @staticmethod
    async def _wait_for_owner(owner_task: asyncio.Task[None]) -> None:
        """Wait for owner cleanup without cancelling it from another task."""
        try:
            await asyncio.shield(owner_task)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            if not owner_task.cancelled():
                raise

    @staticmethod
    def _content_text(content: list[Any]) -> str | None:
        texts = [block.text for block in content if isinstance(block, TextContent)]
        if not texts:
            return None
        return "\n".join(texts)
