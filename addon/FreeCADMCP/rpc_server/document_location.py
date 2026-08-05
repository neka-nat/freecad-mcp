"""Show where the active document lives on disk, and reveal it in the OS file manager.

Purely a GUI convenience driven by a toolbar button, so it is deliberately not
behind a capability gate: a human clicking in FreeCAD is not something a remote
MCP client can trigger. The gates exist to constrain what reaches the RPC
surface, and nothing here does.
"""

import os
import subprocess
import sys

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets


def _file_manager_name():
    if sys.platform == "darwin":
        return "Finder"
    if sys.platform.startswith("win"):
        return "Explorer"
    return "file manager"


def reveal_in_file_manager(path):
    """Open the OS file manager at ``path``, selecting it when it is a file.

    Returns None on success or an error string. Uses Popen rather than run():
    the file manager is a long-lived application and waiting on it would block
    FreeCAD's GUI thread.
    """
    if not path or not os.path.exists(path):
        return f"'{path}' no longer exists on disk."
    try:
        if sys.platform == "darwin":
            args = ["open", "-R", path] if os.path.isfile(path) else ["open", path]
        elif sys.platform.startswith("win"):
            args = (["explorer", f"/select,{path}"] if os.path.isfile(path)
                    else ["explorer", path])
        else:
            target = path if os.path.isdir(path) else os.path.dirname(path)
            args = ["xdg-open", target]
        subprocess.Popen(args)
        return None
    except Exception as e:
        return f"Could not open {_file_manager_name()}: {e}"


def _ancestry(path):
    """[(depth, label, full_path)] from filesystem root down to the file itself."""
    parts, current = [], os.path.abspath(path)
    while True:
        parts.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    parts.reverse()
    rows = []
    for depth, full in enumerate(parts):
        label = os.path.basename(full) or full  # basename of "/" is empty
        rows.append((depth, label, full))
    return rows


def _active_document():
    """The document behind the front window, falling back to ActiveDocument."""
    try:
        gui_doc = FreeCADGui.ActiveDocument
        if gui_doc is not None:
            return gui_doc.Document
    except Exception:
        pass
    return FreeCAD.ActiveDocument


def _qaction_class():
    return getattr(QtGui, "QAction", None) or QtWidgets.QAction


def _style_icon(path):
    style = QtWidgets.QApplication.style()
    which = (QtWidgets.QStyle.SP_FileIcon if os.path.isfile(path)
             else QtWidgets.QStyle.SP_DirIcon)
    return style.standardIcon(which)


def build_menu(parent=None):
    """A menu listing the front document's path, root first, file last.

    Each entry reveals that level in the file manager. Built fresh on every
    click rather than cached, since the front document and its path change.
    """
    menu = QtWidgets.QMenu(parent or FreeCADGui.getMainWindow())
    action_class = _qaction_class()

    doc = _active_document()
    if doc is None:
        menu.addAction("No document is open").setEnabled(False)
        return menu

    name = doc.Label or doc.Name
    path = doc.FileName

    header = menu.addAction(name)
    header.setEnabled(False)
    font = header.font()
    font.setBold(True)
    header.setFont(font)
    menu.addSeparator()

    if not path:
        menu.addAction("Not saved yet - no location on disk").setEnabled(False)
        return menu

    if not os.path.exists(path):
        missing = menu.addAction("File is missing from disk")
        missing.setEnabled(False)

    for depth, label, full in _ancestry(path):
        entry = action_class("    " * depth + label, menu)
        entry.setIcon(_style_icon(full))
        entry.setToolTip(full)
        if os.path.exists(full):
            entry.triggered.connect(lambda _=False, p=full: _reveal(p))
        else:
            entry.setEnabled(False)
        menu.addAction(entry)

    menu.addSeparator()
    copy = action_class("Copy full path", menu)
    copy.triggered.connect(
        lambda _=False, p=path: QtWidgets.QApplication.clipboard().setText(p)
    )
    menu.addAction(copy)
    return menu


def _reveal(path):
    error = reveal_in_file_manager(path)
    if error:
        FreeCAD.Console.PrintWarning(f"MCP: {error}\n")


def show_menu():
    """Pop the menu under the toolbar button, or at the cursor as a fallback."""
    try:
        menu = build_menu()
        main_window = FreeCADGui.getMainWindow()
        point = QtGui.QCursor.pos()
        for toolbar in main_window.findChildren(QtWidgets.QToolBar):
            for action in toolbar.actions():
                if action.objectName() == "MCP_Document_Location":
                    widget = toolbar.widgetForAction(action)
                    if widget is not None:
                        point = widget.mapToGlobal(
                            QtCore.QPoint(0, widget.height())
                        )
                    break
        menu.exec_(point)
    except Exception as e:
        FreeCAD.Console.PrintError(f"MCP: could not open the location menu: {e}\n")
