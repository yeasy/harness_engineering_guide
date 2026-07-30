"""Lifecycle tests against real stdio and loopback Streamable HTTP servers."""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_harness.mcp import client as client_module
from mini_harness.mcp.auth import BearerTokenAuth
from mini_harness.mcp.client import (
    MCPClient,
    MCPClientClosedError,
    MCPConnectionError,
    MCPNotInitializedError,
    MCPRequestTimeout,
)
from mini_harness.mcp.transports import StdioTransport, StreamableHTTPTransport

FIXTURE_SERVER = Path(__file__).parents[1] / "fakes" / "mcp_server.py"


class TrackingTransport:
    """Observe real transport entry/exit without replacing the SDK adapter."""

    def __init__(
        self,
        delegate,
        *,
        pause_before_yield: bool = False,
        pause_before_exit: bool = False,
    ):
        self.delegate = delegate
        self.pause_before_yield = pause_before_yield
        self.pause_before_exit = pause_before_exit
        self.entries = 0
        self.entered = asyncio.Event()
        self.exiting = asyncio.Event()
        self.exited = asyncio.Event()
        self.release = asyncio.Event()
        self.release_exit = asyncio.Event()

    @asynccontextmanager
    async def connect(self):
        self.entries += 1
        async with self.delegate.connect() as streams:
            self.entered.set()
            try:
                if self.pause_before_yield:
                    await self.release.wait()
                yield streams
            finally:
                self.exiting.set()
                if self.pause_before_exit:
                    await self.release_exit.wait()
                self.exited.set()


def _free_loopback_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_listener(port: int, process: subprocess.Popen, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"fixture server exited early: {stderr}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.02)
    raise TimeoutError(f"fixture server did not listen on port {port}")


@pytest.fixture
def loopback_mcp_server():
    port = _free_loopback_port()
    token = "loopback-test-token"
    process = subprocess.Popen(
        [
            sys.executable,
            str(FIXTURE_SERVER),
            "http",
            "--port",
            str(port),
            "--token",
            token,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for_listener(port, process)
        yield f"http://127.0.0.1:{port}/mcp", token
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def stdio_client(timeout_seconds: float = 1.0) -> MCPClient:
    transport = StdioTransport(
        command=sys.executable,
        args=(str(FIXTURE_SERVER), "stdio"),
    )
    return MCPClient(transport, timeout_seconds=timeout_seconds)


@pytest.mark.asyncio
async def test_stdio_requires_initialize_before_tool_use_and_negotiates_metadata():
    client = stdio_client()
    try:
        with pytest.raises(MCPNotInitializedError):
            await client.list_tools()

        initialized = await client.initialize()
        assert initialized.protocol_version
        assert initialized.server_name == "mini-harness-lifecycle-fixture"
        assert initialized.capabilities.get("tools") is not None

        tools = await client.list_tools()
        assert {tool["name"] for tool in tools} == {"echo", "slow"}
        assert await client.call_tool("echo", {"text": "over-stdio"}) == "over-stdio"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_streamable_http_sends_auth_and_closes(loopback_mcp_server):
    endpoint, token = loopback_mcp_server
    client = MCPClient(
        StreamableHTTPTransport(endpoint, auth=BearerTokenAuth(token)),
        timeout_seconds=1,
    )

    try:
        initialized = await client.initialize()
        assert initialized.protocol_version
        assert await client.call_tool("echo", {"text": "over-http"}) == "over-http"
    finally:
        await client.close()
    assert client.closed is True
    with pytest.raises(MCPClientClosedError):
        await client.list_tools()


@pytest.mark.asyncio
async def test_streamable_http_rejects_missing_auth(loopback_mcp_server):
    endpoint, _ = loopback_mcp_server
    client = MCPClient(StreamableHTTPTransport(endpoint), timeout_seconds=1)

    # mcp 2.0 不再把 HTTP 状态码写进异常消息（1.x 会带 "401"），
    # 所以这里断言的是意图本身：未携带凭据就无法完成初始化。
    with pytest.raises(MCPConnectionError):
        await client.initialize()
    await client.close()
    assert client.closed is True


@pytest.mark.asyncio
async def test_real_request_timeout_cancels_wait_and_client_still_closes():
    client = stdio_client(timeout_seconds=1)
    await client.initialize()

    started = time.monotonic()
    with pytest.raises(MCPRequestTimeout):
        await client.call_tool("slow", {"delay_seconds": 1.0}, timeout_seconds=0.05)
    assert time.monotonic() - started < 0.5

    await client.close()
    assert client.closed is True


@pytest.mark.asyncio
async def test_cancelled_initialize_stays_cancelled_and_cleans_real_stdio():
    transport = TrackingTransport(
        StdioTransport(
            command=sys.executable,
            args=(str(FIXTURE_SERVER), "stdio"),
        ),
        pause_before_yield=True,
    )
    client = MCPClient(transport, timeout_seconds=1)
    initialize_task = asyncio.create_task(client.initialize())
    await asyncio.wait_for(transport.entered.wait(), timeout=1)

    initialize_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await initialize_task

    assert initialize_task.cancelled() is True
    await asyncio.wait_for(transport.exited.wait(), timeout=1)
    await client.close()


@pytest.mark.asyncio
async def test_real_stdio_can_initialize_and_close_from_different_tasks():
    transport = TrackingTransport(
        StdioTransport(
            command=sys.executable,
            args=(str(FIXTURE_SERVER), "stdio"),
        )
    )
    client = MCPClient(transport, timeout_seconds=1)

    metadata = await asyncio.create_task(client.initialize())
    assert metadata.server_name == "mini-harness-lifecycle-fixture"
    await asyncio.create_task(client.close())

    assert client.closed is True
    assert transport.exited.is_set()


@pytest.mark.asyncio
async def test_real_http_can_initialize_and_close_from_different_tasks(loopback_mcp_server):
    endpoint, token = loopback_mcp_server
    transport = TrackingTransport(StreamableHTTPTransport(endpoint, auth=BearerTokenAuth(token)))
    client = MCPClient(transport, timeout_seconds=1)

    metadata = await asyncio.create_task(client.initialize())
    assert metadata.server_name == "mini-harness-lifecycle-fixture"
    await asyncio.create_task(client.close())

    assert client.closed is True
    assert transport.exited.is_set()


@pytest.mark.asyncio
async def test_concurrent_initialize_opens_one_real_http_connection(loopback_mcp_server):
    endpoint, token = loopback_mcp_server
    transport = TrackingTransport(StreamableHTTPTransport(endpoint, auth=BearerTokenAuth(token)))
    client = MCPClient(transport, timeout_seconds=1)

    try:
        results = await asyncio.gather(*(client.initialize() for _ in range(8)))
        assert {result.server_name for result in results} == {"mini-harness-lifecycle-fixture"}
        assert transport.entries == 1
    finally:
        await asyncio.create_task(client.close())

    assert transport.exited.is_set()


@pytest.mark.asyncio
async def test_cancelled_real_request_stays_cancelled_and_connection_closes():
    client = stdio_client(timeout_seconds=1)
    await asyncio.create_task(client.initialize())
    request_task = asyncio.create_task(client.call_tool("slow", {"delay_seconds": 1.0}))
    await asyncio.sleep(0.05)

    request_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request_task
    assert request_task.cancelled() is True

    await asyncio.create_task(client.close())
    assert client.closed is True


@pytest.mark.asyncio
async def test_concurrent_stdio_close_and_cancelled_first_waiter_share_cleanup():
    transport = TrackingTransport(
        StdioTransport(
            command=sys.executable,
            args=(str(FIXTURE_SERVER), "stdio"),
        ),
        pause_before_exit=True,
    )
    client = MCPClient(transport, timeout_seconds=1)
    await asyncio.create_task(client.initialize())

    close_task = asyncio.create_task(client.close())
    await asyncio.wait_for(transport.exiting.wait(), timeout=1)
    joining_close = asyncio.create_task(client.close())
    await asyncio.sleep(0)
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task
    assert close_task.cancelled() is True
    assert transport.exited.is_set() is False

    transport.release_exit.set()
    await joining_close
    assert transport.exited.is_set()


@pytest.mark.asyncio
async def test_concurrent_http_close_and_cancelled_first_waiter_share_cleanup(
    loopback_mcp_server,
):
    endpoint, token = loopback_mcp_server
    transport = TrackingTransport(
        StreamableHTTPTransport(endpoint, auth=BearerTokenAuth(token)),
        pause_before_exit=True,
    )
    client = MCPClient(transport, timeout_seconds=1)
    await asyncio.create_task(client.initialize())

    close_task = asyncio.create_task(client.close())
    await asyncio.wait_for(transport.exiting.wait(), timeout=1)
    joining_close = asyncio.create_task(client.close())
    await asyncio.sleep(0)
    close_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await close_task
    assert close_task.cancelled() is True
    assert transport.exited.is_set() is False

    transport.release_exit.set()
    await joining_close
    assert transport.exited.is_set()


@pytest.mark.asyncio
async def test_concurrent_initialize_is_single_flight(monkeypatch):
    release_initialize = asyncio.Event()
    initialize_started = asyncio.Event()

    class CountingTransport:
        def __init__(self):
            self.entries = 0

        @asynccontextmanager
        async def connect(self):
            self.entries += 1
            yield object(), object()

    class FakeCapabilities:
        @staticmethod
        def model_dump(**_kwargs):
            return {"tools": {}}

    class BlockingClientSession:
        initialize_calls = 0

        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            type(self).initialize_calls += 1
            initialize_started.set()
            await release_initialize.wait()
            return SimpleNamespace(
                protocol_version="test",
                capabilities=FakeCapabilities(),
                server_info=SimpleNamespace(name="single-flight", version="1"),
            )

    monkeypatch.setattr(client_module, "ClientSession", BlockingClientSession)
    transport = CountingTransport()
    client = MCPClient(transport, timeout_seconds=1)
    tasks = [asyncio.create_task(client.initialize()) for _ in range(4)]
    await asyncio.wait_for(initialize_started.wait(), timeout=1)
    await asyncio.sleep(0.05)
    release_initialize.set()

    try:
        results = await asyncio.gather(*tasks)
        assert {result.server_name for result in results} == {"single-flight"}
        assert transport.entries == 1
        assert BlockingClientSession.initialize_calls == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_close_before_owner_starts_unblocks_initialize_waiter():
    transport = TrackingTransport(
        StdioTransport(
            command=sys.executable,
            args=(str(FIXTURE_SERVER), "stdio"),
        )
    )
    client = MCPClient(transport, timeout_seconds=1)
    initialize_task = asyncio.create_task(client.initialize())
    await asyncio.sleep(0)

    await asyncio.wait_for(client.close(), timeout=1)

    with pytest.raises(MCPClientClosedError):
        await asyncio.wait_for(initialize_task, timeout=1)
    assert transport.entries <= 1


@pytest.mark.asyncio
async def test_cancel_race_cleans_connection_when_no_initializer_observed_result(monkeypatch):
    transport_exited = asyncio.Event()
    initialize_task = None

    class RaceTransport:
        @asynccontextmanager
        async def connect(self):
            try:
                yield object(), object()
            finally:
                transport_exited.set()

    class FakeCapabilities:
        @staticmethod
        def model_dump(**_kwargs):
            return {"tools": {}}

    class RaceClientSession:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def initialize(self):
            assert initialize_task is not None
            asyncio.get_running_loop().call_soon(initialize_task.cancel)
            return SimpleNamespace(
                protocol_version="test",
                capabilities=FakeCapabilities(),
                server_info=SimpleNamespace(name="cancel-race", version="1"),
            )

    monkeypatch.setattr(client_module, "ClientSession", RaceClientSession)
    client = MCPClient(RaceTransport(), timeout_seconds=1)
    initialize_task = asyncio.create_task(client.initialize())

    try:
        with pytest.raises(asyncio.CancelledError):
            await initialize_task
        await asyncio.wait_for(transport_exited.wait(), timeout=0.2)
        assert client.initialized is False
    finally:
        await client.close()
