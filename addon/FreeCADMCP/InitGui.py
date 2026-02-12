class FreeCADMCPAddonWorkbench(Workbench):
    MenuText = "MCP Addon"
    ToolTip = "Addon for MCP Communication"

    def Initialize(self):
        from rpc_server import rpc_server

        commands = [
            "Toggle_RPC_Server",
            "Separator",
            "Toggle_Remote_Connections",
            "Configure_Allowed_IPs",
            "Separator",
            "Startup_Settings",
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
