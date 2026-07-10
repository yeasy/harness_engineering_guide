"""MiniHarness MCP integration."""

from .client import MCPClient
from .integration import MCPToolRegistry, MiniHarnessWithMCP

__all__ = [
    "MCPClient",
    "MCPToolRegistry",
    "MiniHarnessWithMCP",
]
