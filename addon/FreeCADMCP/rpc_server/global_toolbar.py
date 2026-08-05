"""Always-visible MCP toolbar, independent of the active workbench.

``Workbench.appendToolbar`` builds a toolbar that exists only while that
workbench is active, so the MCP status dot would disappear the moment the user
switched to Part Design -- exactly when they still want to know whether the
server is up. This module instead adds a QToolBar straight to the main window,
which FreeCAD leaves in place across workbench switches, and inserts it before
the leftmost toolbar on the top row.
"""

import os

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

from rpc_server import commands as C


TOOLBAR_NAME = "MCP"
TOOLBAR_OBJECT_NAME = "FreeCADMCP_GlobalToolbar"
_COMMAND = "Toggle_RPC_Server"
_SETTINGS_COMMAND = "MCP_Settings"
_LOCATION_COMMAND = "MCP_Document_Location"


def _qtoolbar_class():
    return getattr(QtWidgets, "QToolBar", None) or QtGui.QToolBar


def _leftmost_top_toolbar(main_window):
    """The toolbar occupying the left of the top row, or None.

    Used as the anchor for ``insertToolBar`` so ours lands to its left. Only
    considers visible toolbars actually docked at the top -- a hidden or
    floating one is not what the user sees as "the first toolbar".
    """
    best, best_x = None, None
    for toolbar in main_window.findChildren(_qtoolbar_class()):
        try:
            if toolbar.objectName() == TOOLBAR_OBJECT_NAME:
                continue
            if main_window.toolBarArea(toolbar) != QtCore.Qt.TopToolBarArea:
                continue
            if toolbar.isHidden() or toolbar.isFloating():
                continue
            pos = toolbar.pos()
            # Prefer the topmost row, then the leftmost toolbar within it.
            key = (pos.y(), pos.x())
            if best_x is None or key < best_x:
                best, best_x = toolbar, key
        except Exception:
            continue
    return best


def install():
    """Create the global toolbar if it does not exist yet. Idempotent."""
    try:
        main_window = FreeCADGui.getMainWindow()
        if main_window is None:
            return None

        existing = main_window.findChild(_qtoolbar_class(), TOOLBAR_OBJECT_NAME)
        if existing is not None:
            C.refresh_server_action()
            return existing

        toolbar = _qtoolbar_class()(TOOLBAR_NAME, main_window)
        toolbar.setObjectName(TOOLBAR_OBJECT_NAME)

        action_class = C._qaction_class()

        # Same objectName as the registered command so commands._find_actions
        # picks this copy up and keeps its icon in step with the workbench one.
        toggle = action_class(C.BUTTON_TEXT, main_window)
        toggle.setObjectName(_COMMAND)
        toggle.setIcon(QtGui.QIcon(os.path.join(C._ICON_DIR, "mcp_off.svg")))
        toggle.triggered.connect(lambda: _run_command(_COMMAND))
        toolbar.addAction(toggle)

        gear = action_class("", main_window)
        gear.setObjectName(_SETTINGS_COMMAND)
        gear.setIcon(QtGui.QIcon(os.path.join(C._ICON_DIR, "mcp_settings.svg")))
        gear.setToolTip("MCP settings: auto-start, remote connections, allowed IPs")
        gear.triggered.connect(lambda: _run_command(_SETTINGS_COMMAND))
        toolbar.addAction(gear)

        folder = action_class("", main_window)
        folder.setObjectName(_LOCATION_COMMAND)
        folder.setIcon(QtGui.QIcon(os.path.join(C._ICON_DIR, "mcp_folder.svg")))
        folder.setToolTip("Where is this document saved? Open it in the file manager")
        folder.triggered.connect(lambda: _run_command(_LOCATION_COMMAND))
        toolbar.addAction(folder)

        anchor = _leftmost_top_toolbar(main_window)
        if anchor is not None:
            main_window.insertToolBar(anchor, toolbar)
        else:
            main_window.addToolBar(QtCore.Qt.TopToolBarArea, toolbar)

        # MUST come after insertion: QMainWindow pushes its own toolButtonStyle
        # onto toolbars as they are added, so setting this beforehand is silently
        # discarded. FreeCAD's default is icon-only, which would leave a bare
        # coloured dot with nothing saying what it belongs to. Scoped to this
        # toolbar; FreeCAD's own toolbars keep their usual appearance.
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        toolbar.setVisible(True)

        C.refresh_server_action()
        FreeCAD.Console.PrintLog("MCP: global toolbar installed.\n")
        return toolbar
    except Exception as e:
        FreeCAD.Console.PrintWarning(f"MCP: could not install global toolbar: {e}\n")
        return None


def _run_command(name):
    try:
        FreeCADGui.runCommand(name)
    except Exception as e:
        FreeCAD.Console.PrintError(f"MCP: toolbar command '{name}' failed: {e}\n")


def ensure_visible():
    """Re-assert the toolbar, cheaply.

    FreeCAD rebuilds toolbar layout on workbench switches and can hide toolbars
    it does not own, so a toolbar installed once is not guaranteed to stay
    visible. Called from the existing one-second status poll; it does nothing
    unless the toolbar is missing or hidden.
    """
    try:
        main_window = FreeCADGui.getMainWindow()
        if main_window is None:
            return
        toolbar = main_window.findChild(_qtoolbar_class(), TOOLBAR_OBJECT_NAME)
        if toolbar is None:
            install()
        elif toolbar.isHidden():
            toolbar.setVisible(True)
    except Exception:
        pass
