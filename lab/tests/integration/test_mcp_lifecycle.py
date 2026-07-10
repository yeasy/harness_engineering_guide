"""Lifecycle tests against real stdio and loopback Streamable HTTP servers."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

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

    with pytest.raises(MCPConnectionError, match="401"):
        await client.initialize()
    await client.close()


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
