"""Real MCP protocol fixture used by lifecycle integration tests."""

from __future__ import annotations

import argparse
import asyncio

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.responses import PlainTextResponse


def build_server(host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """Build a small server that exercises tools and cancellation."""
    server = FastMCP(
        "mini-harness-lifecycle-fixture",
        host=host,
        port=port,
        json_response=True,
        stateless_http=True,
    )

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


def authenticated_app(server: FastMCP, bearer_token: str):
    """Wrap the fixture ASGI app with deterministic bearer authentication."""
    app = server.streamable_http_app()
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
