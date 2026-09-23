"""Addon version reported to the MCP server through get_rpc_status."""

# Keep in step with the freecad-mcp package version in pyproject.toml.
__version__ = "0.1.24"

# Bump when the RPC contract changes in a way the MCP server must know about:
# a method or parameter is added or removed, or a response shape changes.
# Must match PROTOCOL_VERSION in src/freecad_mcp/version.py.
PROTOCOL_VERSION = 1
