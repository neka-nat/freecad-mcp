"""Persistence of MCP RPC server settings under FreeCAD's user app data dir."""

import json
import os

import FreeCAD


_SETTINGS_FILENAME = "freecad_mcp_settings.json"

# Environment override for auto-start. FreeCAD launched from a container
# entrypoint or a provisioning script has no one to click the toolbar, so the
# addon reads this variable before the saved setting.
AUTO_START_ENV_VAR = "FREECAD_MCP_AUTO_START"

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})

_DEFAULT_SETTINGS = {
    "remote_enabled": False,
    "allowed_ips": "127.0.0.1",
    "auto_start_rpc": False,
    "auth_token": "",  # empty = authentication disabled
}


def auto_start_requested(settings):
    """Whether the RPC server should start automatically at launch.

    ``FREECAD_MCP_AUTO_START`` overrides the saved ``auto_start_rpc`` setting so
    a container or script can start the server without opening the workbench
    menu. It accepts ``1``/``true``/``yes``/``on`` to enable and
    ``0``/``false``/``no``/``off`` to disable, case-insensitively and ignoring
    surrounding whitespace. An unset or blank variable falls back to the saved
    setting. An unrecognised value also falls back, but is reported, so a typo
    does not look like a request that was quietly dropped.
    """
    override = os.environ.get(AUTO_START_ENV_VAR, "").strip().lower()
    if override in _TRUE_VALUES:
        return True
    if override in _FALSE_VALUES:
        return False
    if override:
        FreeCAD.Console.PrintWarning(
            f"MCP: ignoring unrecognised {AUTO_START_ENV_VAR}={override!r}; "
            "use 1/true/yes/on to enable or 0/false/no/off to disable.\n"
        )
    return bool(settings.get("auto_start_rpc", False))


def _get_settings_path():
    return os.path.join(FreeCAD.getUserAppDataDir(), _SETTINGS_FILENAME)


def load_settings():
    path = _get_settings_path()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                settings = json.load(f)
            for key, value in _DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"Failed to load MCP settings: {e}\n")
    return dict(_DEFAULT_SETTINGS)


def save_settings(settings):
    path = _get_settings_path()
    try:
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        FreeCAD.Console.PrintError(f"Failed to save MCP settings: {e}\n")
