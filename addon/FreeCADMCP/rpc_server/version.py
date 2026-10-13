"""Addon version reported to the MCP server through get_rpc_status."""

from pathlib import Path
import xml.etree.ElementTree as ET


def _read_version() -> str:
    """Read the metadata shipped with the independently installed addon."""
    metadata = Path(__file__).resolve().parents[1] / "package.xml"
    value = ET.parse(metadata).getroot().findtext(
        "{https://wiki.freecad.org/Package_Metadata}version"
    )
    if not value or not value.strip():
        raise ValueError(f"Missing addon version in {metadata}")
    return value.strip()


__version__ = _read_version()

# Bump when the RPC contract changes in a way the MCP server must know about:
# a method or parameter is added or removed, or a response shape changes.
# Must match PROTOCOL_VERSION in src/freecad_mcp/version.py.
PROTOCOL_VERSION = 1
