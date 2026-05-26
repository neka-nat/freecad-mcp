"""Qt Command classes for the MCP Addon workbench menu.

Defines the five toolbar/menu entries (Start, Stop, Toggle Auto-Start,
Toggle Remote, Configure Allowed IPs), plus the post-startup sync that
reflects saved settings on the checkable items.

``register_commands()`` and ``schedule_toggle_sync()`` are invoked from
``rpc_server.py`` at import time to preserve current side-effect behavior.
"""

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

from .ip_filter import validate_allowed_ips
from .settings import load_settings, save_settings


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
        return {
            "MenuText": "Remote Connections",
            "ToolTip": "Enable or disable remote connections for the RPC server.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        from . import rpc_server
        settings = load_settings()
        settings["remote_enabled"] = bool(checked)
        save_settings(settings)

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
        return {
            "MenuText": "Auto-Start Server",
            "ToolTip": "Automatically start the RPC server when FreeCAD launches.",
            "Checkable": True,
        }

    def Activated(self, checked=0):
        settings = load_settings()
        settings["auto_start_rpc"] = bool(checked)
        save_settings(settings)

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


def _sync_toggle_states() -> None:
    """Sync checkable menu items with saved settings on startup."""
    try:
        settings = load_settings()
        main_window = FreeCADGui.getMainWindow()
        toggle_map = {
            "Remote Connections": settings.get("remote_enabled", False),
            "Auto-Start Server": settings.get("auto_start_rpc", False),
        }
        found = 0
        for action in main_window.findChildren(QtWidgets.QAction):
            if action.text() in toggle_map:
                action.setChecked(toggle_map[action.text()])
                found += 1
                if found == len(toggle_map):
                    return
    except Exception:
        pass
    QtCore.QTimer.singleShot(2000, _sync_toggle_states)


def schedule_toggle_sync() -> None:
    QtCore.QTimer.singleShot(2000, _sync_toggle_states)
