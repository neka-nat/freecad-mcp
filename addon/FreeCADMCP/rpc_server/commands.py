"""Qt Command classes for the MCP toolbar and workbench menu.

The three that matter live on the always-visible toolbar built by
``global_toolbar.py``:

    Toggle_RPC_Server      start/stop, with the red/green/amber status dot
    MCP_Settings           gear -> the consolidated settings dialog
    MCP_Document_Location  folder -> where the front document is saved

The older single-purpose commands (Start, Stop, Toggle Auto-Start, Toggle
Remote, Configure Allowed IPs) stay registered so existing custom toolbars and
shortcuts keep working, but the dialog is the maintained path.

Also holds the post-startup sync for the checkable items and the one-second
poll that keeps the status dot honest. ``register_commands()``,
``schedule_toggle_sync()`` and ``schedule_global_toolbar()`` are invoked from
``rpc_server.py`` at import time -- see InitGui.py on why that import is
load-bearing.
"""

import os

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

from rpc_server.ip_filter import validate_allowed_ips
from rpc_server.settings import load_settings, save_settings


def _qaction_class():
    """``QAction`` moved from QtWidgets (Qt5) to QtGui (Qt6/PySide6).

    FreeCAD 1.1 ships PySide6, where ``QtWidgets.QAction`` does not exist.
    Referencing it raised AttributeError inside ``_sync_toggle_states``' bare
    ``except``, so the startup sync failed silently on every retry and the
    checkable menu items never reflected the saved settings.
    """
    return getattr(QtGui, "QAction", None) or QtWidgets.QAction


def _find_actions(command_name):
    """Every QAction carrying this command's objectName.

    Deliberately plural: the same command can be present more than once -- the
    workbench toolbar/menu entry FreeCAD builds, plus the always-visible global
    toolbar in ``global_toolbar.py``. Updating only the first would leave the
    other showing a stale icon or checkbox.
    """
    found = []
    try:
        main_window = FreeCADGui.getMainWindow()
        for action in main_window.findChildren(_qaction_class()):
            if action.objectName() == command_name:
                found.append(action)
    except Exception:
        pass
    return found


def _find_action(command_name):
    """First QAction for this command, or None."""
    actions = _find_actions(command_name)
    return actions[0] if actions else None


def _set_checked_silently(action, value):
    """Set a checkable action's state without re-triggering its command.

    ``setChecked()`` emits ``toggled``, and FreeCAD has that wired to the
    command, so a plain call re-enters ``Activated`` -> ``_toggle_setting`` ->
    ``setChecked`` and the state bounces straight back. Measured live: without
    blocking, ``setChecked(False)`` leaves ``isChecked()`` True; with blocking it
    lands correctly. The same hazard applies to the startup sync, where the
    re-entry would flip the very settings it is meant to be displaying.
    """
    if action is None or action.isChecked() == value:
        return
    action.blockSignals(True)
    try:
        action.setChecked(value)
    finally:
        action.blockSignals(False)


def _toggle_setting(key, command_name):
    """Flip a boolean setting, persist it, and force the menu item to match.

    The ``checked`` argument FreeCAD passes to ``Activated`` CANNOT be trusted:
    measured on FreeCAD 1.1.1, it arrives as ``0`` in both directions, so
    ``settings[key] = bool(checked)`` pinned every toggle to False and made
    auto-start impossible to enable. Derive the new value from the stored
    setting instead, then drive the checkbox from it so UI and file agree.

    Returns the new boolean value.
    """
    settings = load_settings()
    new_value = not settings.get(key, False)
    settings[key] = new_value
    save_settings(settings)

    _set_checked_silently(_find_action(command_name), new_value)
    return new_value


_ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "icons")

BUTTON_TEXT = "MCP On/Off"

# The label stays fixed so the button is recognisable at a glance; the state is
# carried by the coloured dot and the tooltip.
# server state -> (icon file, tooltip)
_STATE_LOOKS = {
    "on":   ("mcp_on.svg",   "MCP server is RUNNING on {addr} - click to stop"),
    "off":  ("mcp_off.svg",  "MCP server is STOPPED - click to start"),
    "busy": ("mcp_busy.svg", "MCP server is shutting down, please wait"),
}


def _server_state():
    """Return 'on', 'off' or 'busy'.

    'busy' matters because stop_rpc_server() drains the in-flight request on a
    background thread: the instance is cleared immediately but the socket is
    still bound until that thread finishes, so a two-state indicator would
    invite a restart that fails with EADDRINUSE.
    """
    from . import rpc_server as R
    if R.rpc_server_instance is not None:
        return "on"
    stopper = getattr(R, "_stop_thread", None)
    if stopper is not None and stopper.is_alive():
        return "busy"
    return "off"


def _server_address():
    settings = load_settings()
    host = "0.0.0.0" if settings.get("remote_enabled") else "127.0.0.1"
    return f"{host}:9875"


def refresh_server_action():
    """Point every copy of the button at the current server state."""
    state = _server_state()
    icon_file, tip = _STATE_LOOKS[state]
    icon = QtGui.QIcon(os.path.join(_ICON_DIR, icon_file))
    tooltip = tip.format(addr=_server_address())
    for action in _find_actions("Toggle_RPC_Server"):
        try:
            action.setIcon(icon)
            action.setText(BUTTON_TEXT)
            action.setToolTip(tooltip)
            action.setEnabled(state != "busy")
        except Exception as e:
            FreeCAD.Console.PrintWarning(f"MCP: could not refresh status icon: {e}\n")


class ToggleRPCServerCommand:
    """Single toolbar button: start when stopped, stop when running.

    Replaces the old pair of always-enabled Start/Stop buttons, which gave no
    indication of which one was applicable.
    """

    def GetResources(self):
        return {
            "MenuText": BUTTON_TEXT,
            "ToolTip": "Start or stop the MCP RPC server",
            "Pixmap": os.path.join(_ICON_DIR, "mcp_off.svg"),
        }

    def Activated(self, checked=0):
        from . import rpc_server
        state = _server_state()
        if state == "busy":
            FreeCAD.Console.PrintMessage("MCP RPC server is still stopping; please wait.\n")
        elif state == "on":
            FreeCAD.Console.PrintMessage(rpc_server.stop_rpc_server() + "\n")
        else:
            FreeCAD.Console.PrintMessage(rpc_server.start_rpc_server() + "\n")
        refresh_server_action()

    def IsActive(self):
        return True


class MCPSettingsCommand:
    """Gear button: open the consolidated settings dialog."""

    def GetResources(self):
        return {
            "MenuText": "MCP Settings...",
            "ToolTip": "Auto-start, remote connections and allowed IPs",
            "Pixmap": os.path.join(_ICON_DIR, "mcp_settings.svg"),
        }

    def Activated(self, checked=0):
        from rpc_server import settings_dialog
        settings_dialog.show_dialog()

    def IsActive(self):
        return True


class DocumentLocationCommand:
    """Folder button: where the front document lives, and a way into the file manager."""

    def GetResources(self):
        return {
            "MenuText": "Document Location...",
            "ToolTip": "Show where the active document is saved, and open it in the file manager",
            "Pixmap": os.path.join(_ICON_DIR, "mcp_folder.svg"),
        }

    def Activated(self, checked=0):
        from rpc_server import document_location
        document_location.show_menu()

    def IsActive(self):
        return True


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
        # `checked` is ignored on purpose -- see _toggle_setting.
        enabled = _toggle_setting("remote_enabled", "Toggle_Remote_Connections")

        if enabled:
            allowed_ips = load_settings().get("allowed_ips", "127.0.0.1")
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
        # `checked` is ignored on purpose -- see _toggle_setting.
        enabled = _toggle_setting("auto_start_rpc", "Toggle_Auto_Start")

        if enabled:
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
    FreeCADGui.addCommand("Toggle_RPC_Server", ToggleRPCServerCommand())
    FreeCADGui.addCommand("MCP_Settings", MCPSettingsCommand())
    FreeCADGui.addCommand("MCP_Document_Location", DocumentLocationCommand())
    # Kept registered but off the toolbar/menu: existing custom toolbars or
    # keyboard shortcuts that reference them keep working.
    FreeCADGui.addCommand("Start_RPC_Server", StartRPCServerCommand())
    FreeCADGui.addCommand("Stop_RPC_Server", StopRPCServerCommand())
    FreeCADGui.addCommand("Toggle_Auto_Start", ToggleAutoStartCommand())
    FreeCADGui.addCommand("Toggle_Remote_Connections", ToggleRemoteConnectionsCommand())
    FreeCADGui.addCommand("Configure_Allowed_IPs", ConfigureAllowedIPsCommand())


# Map command objectName -> settings key. Matching on objectName rather than
# the localized menu text keeps this working under translation.
_TOGGLE_COMMANDS = {
    "Toggle_Remote_Connections": "remote_enabled",
    "Toggle_Auto_Start": "auto_start_rpc",
}
_SYNC_MAX_RETRIES = 10  # ~20 s at 2 s/retry before giving up


def sync_toggle_states_now() -> None:
    """Sync the checkable menu items once, without scheduling retries.

    Used after the settings dialog writes, where the actions certainly exist.
    """
    _sync_toggle_states(retries_left=0)


def _sync_toggle_states(retries_left: int = _SYNC_MAX_RETRIES) -> None:
    """Sync checkable menu items with saved settings on startup.

    The menu actions are created asynchronously, so retry a bounded number of
    times until they exist rather than polling forever.
    """
    try:
        settings = load_settings()
        main_window = FreeCADGui.getMainWindow()
        found = 0
        for action in main_window.findChildren(_qaction_class()):
            key = _TOGGLE_COMMANDS.get(action.objectName())
            if key is not None:
                _set_checked_silently(action, bool(settings.get(key, False)))
                found += 1
        if found == len(_TOGGLE_COMMANDS):
            return
    except Exception as e:
        # Do not swallow silently: this failing is why the toggles desynced
        # from the settings file for so long.
        FreeCAD.Console.PrintWarning(
            f"MCP: toggle-state sync attempt failed: {type(e).__name__}: {e}\n"
        )
    if retries_left > 0:
        QtCore.QTimer.singleShot(2000, lambda: _sync_toggle_states(retries_left - 1))


_STATUS_POLL_MS = 1000
_last_state = None


def _watch_server_state():
    """Keep the status dot honest, then reschedule.

    A poll rather than pure event-driven refresh because the server can change
    state without going through the button: auto-start at launch, the async stop
    thread finishing, or start/stop driven from a macro. Only touches the UI when
    the state actually changed, so the idle cost is one string comparison.
    """
    global _last_state
    try:
        from rpc_server import global_toolbar
        global_toolbar.ensure_visible()
        state = _server_state()
        if state != _last_state:
            _last_state = state
            refresh_server_action()
    except Exception:
        pass
    QtCore.QTimer.singleShot(_STATUS_POLL_MS, _watch_server_state)


def schedule_toggle_sync() -> None:
    QtCore.QTimer.singleShot(2000, _sync_toggle_states)
    QtCore.QTimer.singleShot(2000, _watch_server_state)


def schedule_global_toolbar() -> None:
    """Install the always-visible toolbar once the main window exists."""
    def _install():
        from rpc_server import global_toolbar
        global_toolbar.install()
    QtCore.QTimer.singleShot(1500, _install)
