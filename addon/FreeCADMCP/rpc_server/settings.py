"""Persistence of MCP RPC server settings under FreeCAD's user app data dir."""

import json
import os

import FreeCAD


_SETTINGS_FILENAME = "freecad_mcp_settings.json"

_DEFAULT_SETTINGS = {
    "remote_enabled": False,
    "allowed_ips": "127.0.0.1",
    "auto_start_rpc": False,
}


def _get_settings_path():
    return os.path.join(FreeCAD.getUserAppDataDir(), _SETTINGS_FILENAME)


def load_settings():
    # FIX-5: _get_settings_path() call is inside the try block so that
    # exceptions from getUserAppDataDir() are caught and fall back to defaults.
    try:
        path = _get_settings_path()
        if os.path.exists(path):
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
    # FIX-7: _get_settings_path() inside try; atomic write via .tmp + os.replace.
    try:
        path = _get_settings_path()
        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(settings, f, indent=2)
        os.replace(tmp_path, path)
    except Exception as e:
        FreeCAD.Console.PrintError(f"Failed to save MCP settings: {e}\n")
