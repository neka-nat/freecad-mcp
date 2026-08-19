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

        commands = [
            "Start_RPC_Server",
            "Stop_RPC_Server",
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


def _auto_start_mcp(attempt=1):
    # A single singleShot(0) at InitGui time is not reliable: it is scheduled
    # before the main event loop runs, and startup timing occasionally
    # swallows it, leaving auto_start_rpc=true with no server and no error.
    # Verify-and-retry (idempotent — start_rpc_server no-ops when running)
    # with a widening backstop until the server object actually exists.
    _MAX_ATTEMPTS = 4
    try:
        from rpc_server import rpc_server

        settings = rpc_server.load_settings()
        if not settings.get("auto_start_rpc", False):
            return

        if rpc_server.rpc_server_instance is None:
            msg = rpc_server.start_rpc_server()
            FreeCAD.Console.PrintMessage(
                f"[MCP] Auto-start (attempt {attempt}): {msg}\n"
            )
    except Exception as e:
        FreeCAD.Console.PrintWarning(
            f"[MCP] Auto-start attempt {attempt} failed: {e}\n"
        )

    if attempt < _MAX_ATTEMPTS:
        def _verify():
            try:
                from rpc_server import rpc_server as _rs
                if _rs.rpc_server_instance is None:
                    _auto_start_mcp(attempt + 1)
            except Exception:
                _auto_start_mcp(attempt + 1)

        QtCore.QTimer.singleShot(2000 * attempt, _verify)


from PySide import QtCore

QtCore.QTimer.singleShot(0, _auto_start_mcp)
