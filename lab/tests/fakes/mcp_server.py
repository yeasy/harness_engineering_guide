"""Real MCP protocol fixture used by lifecycle integration tests."""

from __future__ import annotations

import argparse
import asyncio

import uvicorn
from mcp.server import MCPServer
from starlette.responses import PlainTextResponse


def build_server(host: str = "127.0.0.1", port: int = 8000) -> MCPServer:
    """Build a small server that exercises tools and cancellation.

    mcp 2.0 起，host/port/json_response/stateless_http 不再是构造器参数，
    改由 streamable_http_app() 与 uvicorn 承担，因此这里只保留服务端身份；
    host 与 port 由调用方在建 ASGI app / 起 uvicorn 时传入。
    """
    del host, port  # 保留签名以兼容既有调用方
    server = MCPServer(name="mini-harness-lifecycle-fixture")

    @server.tool()
    async def echo(text: str) -> str:
        """Return the supplied text."""
        return text

    @server.tool()
    async def slow(delay_seconds: float) -> str:
        """Wait before returning so clients can test timeout cancellation."""
        await asyncio.sleep(delay_seconds)
        return "finished"

    return server


def authenticated_app(server: MCPServer, bearer_token: str):
    """Wrap the fixture ASGI app with deterministic bearer authentication."""
    # mcp 2.0：json_response/stateless_http 从构造器移到了这里。
    # 注意不要开 stateless_http——握手时代（2025-11-25 及更早）的客户端需要
    # 服务端签发 Mcp-Session-Id，开了就握不上手；2026-07-28 的客户端本身
    # 不依赖会话，不受此设置影响。
    app = server.streamable_http_app(json_response=True)
    expected = f"Bearer {bearer_token}".encode("utf-8")

    async def wrapped(scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            if headers.get(b"authorization") != expected:
                response = PlainTextResponse("Unauthorized", status_code=401)
                await response(scope, receive, send)
                return
        await app(scope, receive, send)

    return wrapped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transport", choices=("stdio", "http"))
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--token", default="test-token")
    args = parser.parse_args()

    server = build_server(port=args.port)
    if args.transport == "stdio":
        server.run(transport="stdio")
        return

    uvicorn.run(
        authenticated_app(server, args.token),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
