"""Qt Command classes for the MCP Addon workbench menu.

Defines the five toolbar/menu entries (Start, Stop, Toggle Auto-Start,
Toggle Remote, Configure Allowed IPs).

``register_commands()`` and ``schedule_toggle_sync()`` are invoked from
``rpc_server.py`` at import time to preserve current side-effect behavior.
"""

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

from rpc_server.ip_filter import validate_allowed_ips
from rpc_server.settings import load_settings, save_settings


# FIX-6: module-level cache so toggle state survives workbench switches
_cached_settings = None


def _get_cached_settings():
    """Return settings from cache, loading from disk the first time.

    Never raises; returns defaults on any error.
    """
    global _cached_settings
    if _cached_settings is None:
        try:
            _cached_settings = load_settings()
        except Exception:
            _cached_settings = {
                "remote_enabled": False,
                "allowed_ips": "127.0.0.1",
                "auto_start_rpc": False,
            }
    return _cached_settings


class StartRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Start RPC Server", "ToolTip": "Start RPC Server"}

    def Activated(self):
        from . import rpc_server  # late import: avoids circular at module load
        msg = rpc_server.start_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


class StopRPCServerCommand:
    def GetResources(self):
        return {"MenuText": "Stop RPC Server", "ToolTip": "Stop RPC Server"}

    def Activated(self):
        from . import rpc_server
        msg = rpc_server.stop_rpc_server()
        FreeCAD.Console.PrintMessage(msg + "\n")

    def IsActive(self):
        return True


class ToggleRemoteConnectionsCommand:
    def GetResources(self):
        # FIX-1: always include Checkable; wrap in try/except, never raise
        try:
            settings = _get_cached_settings()
            return {
                "MenuText": "Remote Connections",
                "ToolTip": "Enable or disable remote connections for the RPC server.",
                "Checkable": bool(settings.get("remote_enabled", False)),
            }
        except Exception:
            return {
                "MenuText": "Remote Connections",
                "ToolTip": "Enable or disable remote connections for the RPC server.",
                "Checkable": False,
            }

    def Activated(self, checked=0):
        # FIX-6: update module-level cache after saving
        global _cached_settings
        from . import rpc_server
        settings = load_settings()
        settings["remote_enabled"] = bool(checked)
        save_settings(settings)
        _cached_settings = settings

        if settings["remote_enabled"]:
            allowed_ips = settings.get("allowed_ips", "127.0.0.1")
            FreeCAD.Console.PrintMessage(
                f"Remote connections enabled. Allowed IPs: {allowed_ips}\n"
            )
        else:
            FreeCAD.Console.PrintMessage("Remote connections disabled.\n")

        if rpc_server.rpc_server_instance:
            FreeCAD.Console.PrintMessage(
                "Restart the RPC server for changes to take effect.\n"
            )

    def IsActive(self):
        return True


class ConfigureAllowedIPsCommand:
    def GetResources(self):
        return {
            "MenuText": "Configure Allowed IPs",
            "ToolTip": "Set which IP addresses or subnets are allowed to connect to the RPC server.",
        }

    def Activated(self):
        from . import rpc_server
        settings = load_settings()
        current_ips = settings.get("allowed_ips", "127.0.0.1")
        text, ok = QtWidgets.QInputDialog.getText(
            None,
            "Allowed IP Addresses",
            "Enter allowed IP addresses or subnets (comma-separated):\n"
            "Examples: 127.0.0.1, 192.168.1.0/24, 10.0.0.5",
            QtWidgets.QLineEdit.Normal,
            current_ips,
        )
        if ok and text.strip():
            valid, errors = validate_allowed_ips(text.strip())
            if errors:
                QtWidgets.QMessageBox.warning(
                    None,
                    "Invalid IP Configuration",
                    "The following errors were found:\n\n"
                    + "\n".join(f"• {e}" for e in errors)
                    + ("\n\nOnly valid entries will be saved."
                       if valid else "\n\nNo valid entries found. Settings not changed."),
                )
            if not valid:
                FreeCAD.Console.PrintWarning("Allowed IPs not changed — no valid entries.\n")
                return
            normalised = ", ".join(valid)
            settings["allowed_ips"] = normalised
            save_settings(settings)
            FreeCAD.Console.PrintMessage(
                f"Allowed IPs updated to: {normalised}\n"
            )
            if rpc_server.rpc_server_instance:
                FreeCAD.Console.PrintMessage(
                    "Restart the RPC server for changes to take effect.\n"
                )
        else:
            FreeCAD.Console.PrintMessage("Allowed IPs not changed.\n")

    def IsActive(self):
        return True


class ToggleAutoStartCommand:
    def GetResources(self):
        # FIX-1: always include Checkable; wrap in try/except, never raise
        try:
            settings = _get_cached_settings()
            return {
                "MenuText": "Auto-Start Server",
                "ToolTip": "Automatically start the RPC server when FreeCAD launches.",
                "Checkable": bool(settings.get("auto_start_rpc", False)),
            }
        except Exception:
            return {
                "MenuText": "Auto-Start Server",
                "ToolTip": "Automatically start the RPC server when FreeCAD launches.",
                "Checkable": False,
            }

    def Activated(self, checked=0):
        # FIX-6: update module-level cache after saving
        global _cached_settings
        settings = load_settings()
        settings["auto_start_rpc"] = bool(checked)
        save_settings(settings)
        _cached_settings = settings

        if settings["auto_start_rpc"]:
            FreeCAD.Console.PrintMessage(
                "MCP RPC server will start automatically on next FreeCAD launch.\n"
            )
        else:
            FreeCAD.Console.PrintMessage(
                "MCP RPC server auto-start disabled.\n"
            )

    def IsActive(self):
        return True


def register_commands() -> None:
    FreeCADGui.addCommand("Start_RPC_Server", StartRPCServerCommand())
    FreeCADGui.addCommand("Stop_RPC_Server", StopRPCServerCommand())
    FreeCADGui.addCommand("Toggle_Auto_Start", ToggleAutoStartCommand())
    FreeCADGui.addCommand("Toggle_Remote_Connections", ToggleRemoteConnectionsCommand())
    FreeCADGui.addCommand("Configure_Allowed_IPs", ConfigureAllowedIPsCommand())


def _apply_toggle_states():
    """Apply saved checked states to the two checkable QActions.

    Called 2 s after startup once the GUI is fully initialised.
    """
    try:
        settings = _get_cached_settings()
        mw = FreeCADGui.getMainWindow()
        actions = mw.findChildren(QtWidgets.QAction)
        for action in actions:
            name = action.objectName()
            if name == "Toggle_Remote_Connections":
                action.setChecked(bool(settings.get("remote_enabled", False)))
            elif name == "Toggle_Auto_Start":
                action.setChecked(bool(settings.get("auto_start_rpc", False)))
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"MCP: failed to sync toggle states: {e}\n")


def schedule_toggle_sync() -> None:
    """Schedule a deferred sync of the two checkable toggle action states.

    Uses ``QtCore.QTimer.singleShot(2000, ...)`` so the call fires after
    FreeCAD's GUI is fully initialised and ``findChildren(QAction)`` can
    locate both named actions.  Fires unconditionally — no workbench guard
    is needed because QTimer delivers the callback regardless of which
    workbench is active at the time.
    """
    try:
        QtCore.QTimer.singleShot(2000, _apply_toggle_states)
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"MCP: could not schedule toggle sync: {e}\n")
