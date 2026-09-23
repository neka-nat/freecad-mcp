"""Version handshake between the MCP server and the FreeCAD addon.

The two ship separately (pip/uvx vs. a manual copy into FreeCAD's Mod
directory), so either side can be older. The addon reports its versions via
get_rpc_status; this module turns that report into a warning the user sees.
"""

from importlib.metadata import PackageNotFoundError, version
from typing import Any

# Must match PROTOCOL_VERSION in addon/FreeCADMCP/rpc_server/version.py.
PROTOCOL_VERSION = 1

try:
    __version__ = version("freecad-mcp")
except PackageNotFoundError:
    __version__ = "unknown"

_UPDATE_ADDON = (
    "Update the addon: copy addon/FreeCADMCP from the matching freecad-mcp "
    "release into FreeCAD's Mod directory and restart FreeCAD."
)
_UPDATE_SERVER = "Update the MCP server: run `uvx freecad-mcp@latest` or upgrade the package."


def addon_version_warning(status: dict[str, Any] | None) -> str | None:
    """Return a warning when the addon does not match this server, else None.

    ``status`` is the addon's get_rpc_status reply, or None when the addon is
    too old to have that method.
    """
    server = f"freecad-mcp {__version__} (protocol {PROTOCOL_VERSION})"
    if status is None:
        return (
            f"The FreeCAD addon is older than {server}: it has no get_rpc_status. "
            f"{_UPDATE_ADDON}"
        )

    addon_protocol = status.get("protocol_version")
    if not isinstance(addon_protocol, int) or isinstance(addon_protocol, bool):
        return (
            f"The FreeCAD addon does not report a version, so it is older than "
            f"{server}. {_UPDATE_ADDON}"
        )
    if addon_protocol == PROTOCOL_VERSION:
        return None

    addon = f"FreeCAD addon {status.get('addon_version', 'unknown')} (protocol {addon_protocol})"
    fix = _UPDATE_ADDON if addon_protocol < PROTOCOL_VERSION else _UPDATE_SERVER
    return f"{addon} does not match {server}. {fix}"
