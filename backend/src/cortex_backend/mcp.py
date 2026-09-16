"""FastMCP registry composition."""

from fastmcp import FastMCP


def create_mcp_server(name: str = "Cortex") -> FastMCP:
    """Create the empty MCP registry used by the application composition root."""

    return FastMCP(name)
