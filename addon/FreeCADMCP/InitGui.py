import sys as _sys
import os as _os
try:
    _addon_dir = _os.path.dirname(_os.path.abspath(__file__))
except NameError:
    import inspect as _inspect
    _addon_dir = _os.path.dirname(_os.path.abspath(_inspect.getfile(_inspect.currentframe())))
if _addon_dir not in _sys.path:
    _sys.path.insert(0, _addon_dir)


class FreeCADMCPAddonWorkbench(Workbench):
    MenuText = "MCP Addon"
    ToolTip = "Addon for MCP Communication"

    def Initialize(self):
        from rpc_server import rpc_server

        # Toggle_RPC_Server is first so the status dot sits at the left of the
        # toolbar: red = stopped, green = running, amber = shutting down.
        commands = [
            "Toggle_RPC_Server",
            "MCP_Settings",
            "MCP_Document_Location",
            "Toggle_Auto_Start",
            "Toggle_Remote_Connections",
            "Configure_Allowed_IPs",
        ]
        self.appendToolbar("FreeCAD MCP", commands)
        self.appendMenu("FreeCAD MCP", commands)

    def Activated(self):
        pass

    def Deactivated(self):
        pass

    def ContextMenu(self, recipient):
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(FreeCADMCPAddonWorkbench())


def _mcp_startup():
    """Runs at FreeCAD launch, whether or not the MCP workbench is ever opened.

    Importing rpc_server is load-bearing, not incidental: at import it registers
    the commands, schedules the toggle-state sync and installs the always-visible
    MCP toolbar. Workbench.Initialize() only runs when the user actually selects
    the workbench, which would be far too late for a status indicator that is
    supposed to be visible from any workbench.
    """
    try:
        from rpc_server import rpc_server

        settings = rpc_server.load_settings()
        if not settings.get("auto_start_rpc", False):
            return

        msg = rpc_server.start_rpc_server()
        FreeCAD.Console.PrintMessage(f"[MCP] Auto-start: {msg}\n")
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"[MCP] Startup failed: {e}\n")


from PySide import QtCore

QtCore.QTimer.singleShot(0, _mcp_startup)
