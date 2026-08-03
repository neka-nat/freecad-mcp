"""Qt Command classes for the MCP Addon workbench menu.

Defines the five toolbar/menu entries (Start, Stop, Toggle Auto-Start,
Toggle Remote, Configure Allowed IPs), plus the post-startup sync that
reflects saved settings on the checkable items.

``register_commands()`` and ``schedule_toggle_sync()`` are invoked from
``rpc_server.py`` at import time to preserve current side-effect behavior.
"""

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

# QAction location differs between FreeCAD's Qt bindings:
#   PySide (Qt4): QtGui.QAction
#   PySide2/6: QtWidgets.QAction
try:
    _QAction = QtWidgets.QAction
except AttributeError:
    _QAction = QtGui.QAction

from rpc_server.ip_filter import validate_allowed_ips
from rpc_server.settings import load_settings, save_settings


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


# Map action menu text -> settings key.  Using text is more reliable than
# objectName since FreeCAD sets the former from GetResources() but does not
# guarantee objectName for every command.
_TOGGLE_COMMANDS: dict[str, str] = {
    "Remote Connections": "remote_enabled",
    "Auto-Start Server": "auto_start_rpc",
}


def _log(msg: str) -> None:
    FreeCAD.Console.PrintMessage(f"[MCP sync] {msg}\n")


def _sync_toggle_states() -> bool | None:
    """Sync checkable menu items with saved settings on startup.

    The MCP workbench must be activated first so its QAction objects are
    created in the main window's widget hierarchy.  We temporarily activate
    it, sync and verify the states, then restore the previous workbench.

    Returns True if all actions were found and verified to match the desired
    state.  Returns False (and schedules a retry) if anything failed — missing
    action, wrong current state, or an exception during the attempt.
    """
    try:
        settings = load_settings()

        main_window = FreeCADGui.getMainWindow()

        # MCP actions only exist in the widget hierarchy after their workbench
        # has been activated (toolbar/menu creation is lazy).  Activate it now,
        # remembering what was active before so we can restore it.
        prev_wb = FreeCADGui.activeWorkbench()
        FreeCADGui.activateWorkbench("FreeCADMCPAddonWorkbench")

        all_actions = main_window.findChildren(_QAction)

        matched_keys: set[str] = set()
        for action in all_actions:
            key = _TOGGLE_COMMANDS.get(action.text())
            if key is not None:
                desired = bool(settings.get(key, False))
                action.setChecked(desired)
                matched_keys.add(key)

        # All actions must be present before verification
        if len(matched_keys) != len(_TOGGLE_COMMANDS):
            _log(f"incomplete match: got {len(matched_keys)} of {len(_TOGGLE_COMMANDS)}")
            return False

        # Verify every action actually ended up in the correct state
        for action in all_actions:
            key = _TOGGLE_COMMANDS.get(action.text())
            if key is not None:
                desired = bool(settings.get(key, False))
                actual = action.isChecked()
                if actual != desired:
                    _log(f"verification failed: '{action.text()}' expected {desired}, got {actual}")
                    return False

        # Restore the previous workbench so we don't surprise the user.
        prev_name = getattr(prev_wb, 'name', None) or ""
        if callable(prev_name):
            prev_name = prev_name()
        if prev_name and prev_name != "FreeCADMCPAddonWorkbench":
            FreeCADGui.activateWorkbench(prev_name)

        _log("all actions synced and verified")
        return True  # all found and verified

    except Exception as e:
        FreeCAD.Console.PrintWarning(f"[MCP sync] exception: {e}\n")
        return False


def _schedule_sync_retry() -> None:
    """Schedule the next sync attempt after a delay."""
    QtCore.QTimer.singleShot(2000, _try_sync_toggle_states)


def _try_sync_toggle_states() -> None:
    result = _sync_toggle_states()
    if result is False:
        _schedule_sync_retry()


def schedule_toggle_sync() -> None:
    """Kick off the first sync attempt after a short startup delay."""
    QtCore.QTimer.singleShot(2000, _try_sync_toggle_states)
