"""Qt Command classes for the MCP Addon workbench menu.

Defines toolbar/menu entries for RPC server control, remote access settings,
and spatial comments.

``register_commands()`` and ``schedule_toggle_sync()`` are invoked from
``rpc_server.py`` at import time to preserve current side-effect behavior.
"""

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

from rpc_server.comments import (
    delete_comment as comments_delete_comment,
    is_marker_delete_sync_suppressed,
    list_comments as comments_list_comments,
    render_comment_markers,
)
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
        settings = load_settings()
        return {
            "MenuText": "Remote Connections",
            "ToolTip": "Enable or disable remote connections for the RPC server.",
            "Checkable": bool(settings.get("remote_enabled", False)),
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
                    + (
                        "\n\nOnly valid entries will be saved."
                        if valid
                        else "\n\nNo valid entries found. Settings not changed."
                    ),
                )
            if not valid:
                FreeCAD.Console.PrintWarning(
                    "Allowed IPs not changed — no valid entries.\n"
                )
                return
            normalised = ", ".join(valid)
            settings["allowed_ips"] = normalised
            save_settings(settings)
            FreeCAD.Console.PrintMessage(f"Allowed IPs updated to: {normalised}\n")
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
        settings = load_settings()
        return {
            "MenuText": "Auto-Start Server",
            "ToolTip": "Automatically start the RPC server when FreeCAD launches.",
            "Checkable": bool(settings.get("auto_start_rpc", False)),
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
            FreeCAD.Console.PrintMessage("MCP RPC server auto-start disabled.\n")

    def IsActive(self):
        return True


_pending_spatial_comment_observer = None


class _SpatialCommentSelectionObserver:
    def __init__(self, command):
        self.command = command

    def addSelection(self, *args):
        FreeCADGui.Selection.removeObserver(self)
        global _pending_spatial_comment_observer
        _pending_spatial_comment_observer = None
        QtCore.QTimer.singleShot(0, self.command._show_comment_dialog)


class AddSpatialCommentCommand:
    def GetResources(self):
        return {
            "MenuText": "Add Spatial Comment",
            "ToolTip": "Select geometry in the 3D view, then add MCP feedback for the LLM.",
        }

    def _dialog_parent(self):
        return FreeCADGui.getMainWindow()

    def _get_comment_text(self, title="Add Spatial Comment", initial_text=""):
        dialog = QtWidgets.QDialog(self._dialog_parent())
        dialog.setWindowTitle(title)
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.setSizeGripEnabled(True)
        dialog.resize(420, 260)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel("Comment:"))
        editor = QtWidgets.QPlainTextEdit(dialog)
        editor.setPlainText(initial_text)
        layout.addWidget(editor)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return None
        return editor.toPlainText().strip()

    def _show_comment_dialog(self):
        from .rpc_server import FreeCADRPC

        doc = FreeCAD.ActiveDocument
        if not doc:
            QtWidgets.QMessageBox.warning(
                self._dialog_parent(),
                "Spatial Comment",
                "Open or create a document first.",
            )
            return
        text = self._get_comment_text()
        if not text:
            return
        result = FreeCADRPC()._create_spatial_comment_gui(
            doc.Name,
            {"text": text, "author": "user"},
        )
        if result.get("success"):
            FreeCAD.Console.PrintMessage(
                f"Spatial comment saved to {result.get('sidecar_path')}\n"
            )
        else:
            QtWidgets.QMessageBox.warning(
                self._dialog_parent(),
                "Spatial Comment",
                result.get("error", "Unknown error"),
            )

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        if not doc:
            QtWidgets.QMessageBox.warning(
                self._dialog_parent(),
                "Spatial Comment",
                "Open or create a document first.",
            )
            return
        if FreeCADGui.Selection.getSelectionEx(doc.Name):
            self._show_comment_dialog()
            return

        global _pending_spatial_comment_observer
        if _pending_spatial_comment_observer is not None:
            FreeCADGui.Selection.removeObserver(_pending_spatial_comment_observer)
        _pending_spatial_comment_observer = _SpatialCommentSelectionObserver(self)
        FreeCADGui.Selection.addObserver(_pending_spatial_comment_observer)
        QtWidgets.QMessageBox.information(
            self._dialog_parent(),
            "Spatial Comment",
            "Select a face, edge, vertex, object, or picked point to add a spatial comment.",
        )

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


class SyncSpatialCommentsCommand:
    def GetResources(self):
        return {
            "MenuText": "Sync Spatial Comments",
            "ToolTip": "Sync MCP comment markers with the sidecar JSON.",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        if doc:
            render_comment_markers(doc)

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


class EditSpatialCommentCommand:
    def GetResources(self):
        return {
            "MenuText": "Edit Spatial Comment",
            "ToolTip": "Edit the text of an unresolved MCP spatial comment.",
        }

    def _dialog_parent(self):
        return FreeCADGui.getMainWindow()

    def _get_updated_comment_text(self, current_text):
        command = AddSpatialCommentCommand()
        command._dialog_parent = self._dialog_parent
        return command._get_comment_text("Edit Spatial Comment", current_text)

    def Activated(self):
        from .rpc_server import FreeCADRPC

        doc = FreeCAD.ActiveDocument
        if not doc:
            QtWidgets.QMessageBox.warning(
                self._dialog_parent(),
                "Spatial Comments",
                "Open or create a document first.",
            )
            return

        comments = comments_list_comments(doc, {"include_resolved": False})
        if not comments:
            QtWidgets.QMessageBox.information(
                self._dialog_parent(),
                "Spatial Comments",
                "No unresolved spatial comments to edit.",
            )
            return

        labels = [
            f"{c['id']} — [{c.get('status', 'open')}] {c.get('text', '')[:60]}"
            for c in comments
        ]
        label, ok = QtWidgets.QInputDialog.getItem(
            self._dialog_parent(), "Edit Spatial Comment", "Comment:", labels, 0, False
        )
        if not ok:
            return
        comment_id = label.split(" — ", 1)[0]
        selected = next(c for c in comments if c["id"] == comment_id)
        new_text = self._get_updated_comment_text(selected.get("text", ""))
        if new_text is None:
            return
        if not new_text:
            QtWidgets.QMessageBox.warning(
                self._dialog_parent(),
                "Spatial Comments",
                "Comment text cannot be empty.",
            )
            return
        if new_text == selected.get("text", ""):
            return

        result = FreeCADRPC()._update_spatial_comment_gui(
            doc.Name, comment_id, {"text": new_text}
        )
        if result.get("success"):
            FreeCAD.Console.PrintMessage(f"MCP spatial comment updated: {comment_id}\n")
        else:
            QtWidgets.QMessageBox.warning(
                self._dialog_parent(),
                "Spatial Comments",
                result.get("error", "Unknown error"),
            )

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


def _confirm_spatial_comment_resolution(doc, selected):
    from .rpc_server import FreeCADRPC

    note = selected.get("resolution_note") or "No resolution note supplied."
    confirmed = QtWidgets.QMessageBox.question(
        FreeCADGui.getMainWindow(),
        "Confirm Resolution",
        f"Comment:\n{selected.get('text', '')}\n\n"
        f"Proposed resolution:\n{note}\n\nMark this comment resolved?",
    )
    if confirmed != QtWidgets.QMessageBox.Yes:
        return
    result = FreeCADRPC()._confirm_spatial_comment_resolution_gui(
        doc.Name, selected["id"]
    )
    if not result.get("success"):
        QtWidgets.QMessageBox.warning(
            FreeCADGui.getMainWindow(),
            "Spatial Comments",
            result.get("error", "Unknown error"),
        )


def _selected_marker_comment_id():
    for obj in FreeCADGui.Selection.getSelection():
        comment_id = getattr(obj, "MCPCommentId", None)
        if comment_id:
            return comment_id
    return None


def _is_tree_context_widget(widget) -> bool:
    while widget is not None:
        meta_name = widget.metaObject().className()
        if widget.objectName() == "DocumentTreeItems" or "Tree" in meta_name:
            return True
        widget = widget.parent()
    return False


def _document_has_spatial_comments() -> bool:
    doc = FreeCAD.ActiveDocument
    if doc is None:
        return False
    if doc.getObject("MCP_Comment_Markers") is not None:
        return True
    return bool(comments_list_comments(doc, {"include_resolved": True}))


def _append_spatial_comment_context_action(retries_left=4):
    popup = QtWidgets.QApplication.activePopupWidget()
    if popup is None:
        if retries_left > 0:
            QtCore.QTimer.singleShot(
                25,
                lambda: _append_spatial_comment_context_action(retries_left - 1),
            )
        return
    if not isinstance(popup, QtWidgets.QMenu):
        return
    if not _document_has_spatial_comments():
        return

    for action in list(popup.actions()):
        if action.text().startswith("Edit MCP Comment:"):
            popup.removeAction(action)

    if any(action.text() == "Spatial Comment" for action in popup.actions()):
        return

    spatial_menu = popup.addMenu("Spatial Comment")
    edit_action = spatial_menu.addAction("Edit Spatial Comment")
    edit_action.setObjectName("MCPEditSpatialCommentAction")
    edit_action.triggered.connect(
        lambda checked=False: FreeCADGui.runCommand("Edit_Spatial_Comment")
    )

    confirm_action = spatial_menu.addAction("Confirm Comment Resolution")
    confirm_action.setObjectName("MCPConfirmSpatialCommentAction")
    confirm_action.triggered.connect(
        lambda checked=False: FreeCADGui.runCommand(
            "Confirm_Selected_Spatial_Comment_Resolution"
        )
    )


class _SpatialCommentTreeContextFilter(QtCore.QObject):
    def eventFilter(self, watched, event):
        if (
            event.type() == QtCore.QEvent.ContextMenu
            and _document_has_spatial_comments()
            and _is_tree_context_widget(watched)
        ):
            QtCore.QTimer.singleShot(0, _append_spatial_comment_context_action)
        return False


_spatial_comment_tree_context_filter = None


def install_spatial_comment_tree_context_menu() -> None:
    global _spatial_comment_tree_context_filter
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    if _spatial_comment_tree_context_filter is None:
        _spatial_comment_tree_context_filter = _SpatialCommentTreeContextFilter(app)
        app.installEventFilter(_spatial_comment_tree_context_filter)


class ConfirmSpatialCommentResolutionCommand:
    def GetResources(self):
        return {
            "MenuText": "Confirm Comment Resolution",
            "ToolTip": "Confirm a proposed MCP comment resolution.",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        if not doc:
            return
        comments = comments_list_comments(doc, {"status": "resolution_proposed"})
        if not comments:
            QtWidgets.QMessageBox.information(
                None, "Spatial Comments", "No proposed resolutions to confirm."
            )
            return
        labels = [f"{c['id']} — {c.get('text', '')[:60]}" for c in comments]
        label, ok = QtWidgets.QInputDialog.getItem(
            None, "Confirm Resolution", "Comment:", labels, 0, False
        )
        if not ok:
            return
        comment_id = label.split(" — ", 1)[0]
        selected = next(c for c in comments if c["id"] == comment_id)
        _confirm_spatial_comment_resolution(doc, selected)

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


class ConfirmSelectedSpatialCommentResolutionCommand:
    def GetResources(self):
        return {
            "MenuText": "Confirm Comment Resolution",
            "ToolTip": "Confirm the proposed resolution for the selected MCP spatial comment marker.",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        comment_id = _selected_marker_comment_id()
        if not doc or not comment_id:
            QtWidgets.QMessageBox.information(
                FreeCADGui.getMainWindow(),
                "Spatial Comments",
                "Select a spatial comment marker first.",
            )
            return

        comments = comments_list_comments(doc, {"include_resolved": True})
        selected = next((c for c in comments if c.get("id") == comment_id), None)
        if not selected:
            QtWidgets.QMessageBox.warning(
                FreeCADGui.getMainWindow(),
                "Spatial Comments",
                f"Comment '{comment_id}' was not found in the sidecar.",
            )
            return
        if selected.get("status") != "resolution_proposed":
            QtWidgets.QMessageBox.information(
                FreeCADGui.getMainWindow(),
                "Spatial Comments",
                "Only comments with a proposed resolution can be confirmed.",
            )
            return

        _confirm_spatial_comment_resolution(doc, selected)

    def IsActive(self):
        return (
            FreeCAD.ActiveDocument is not None
            and _selected_marker_comment_id() is not None
        )


class SpatialCommentMarkerDeleteObserver:
    """Delete sidecar comments when their marker objects are deleted from the tree."""

    def slotDeletedObject(self, obj):
        if is_marker_delete_sync_suppressed():
            return
        comment_id = getattr(obj, "MCPCommentId", None)
        if not comment_id:
            return
        doc = getattr(obj, "Document", None)
        if doc is None:
            return
        try:
            if comments_delete_comment(doc, comment_id):
                FreeCAD.Console.PrintMessage(
                    f"MCP spatial comment deleted from sidecar: {comment_id}\n"
                )
        except Exception as e:
            FreeCAD.Console.PrintWarning(
                f"Could not delete MCP spatial comment {comment_id} from sidecar: {e}\n"
            )


_spatial_comment_marker_delete_observer = SpatialCommentMarkerDeleteObserver()
FreeCAD.addDocumentObserver(_spatial_comment_marker_delete_observer)


def register_commands() -> None:
    FreeCADGui.addCommand("Start_RPC_Server", StartRPCServerCommand())
    FreeCADGui.addCommand("Stop_RPC_Server", StopRPCServerCommand())
    FreeCADGui.addCommand("Toggle_Auto_Start", ToggleAutoStartCommand())
    FreeCADGui.addCommand("Toggle_Remote_Connections", ToggleRemoteConnectionsCommand())
    FreeCADGui.addCommand("Configure_Allowed_IPs", ConfigureAllowedIPsCommand())
    FreeCADGui.addCommand("Add_Spatial_Comment", AddSpatialCommentCommand())
    FreeCADGui.addCommand("Edit_Spatial_Comment", EditSpatialCommentCommand())
    FreeCADGui.addCommand("Sync_Spatial_Comments", SyncSpatialCommentsCommand())
    FreeCADGui.addCommand(
        "Confirm_Spatial_Comment_Resolution",
        ConfirmSpatialCommentResolutionCommand(),
    )
    FreeCADGui.addCommand(
        "Confirm_Selected_Spatial_Comment_Resolution",
        ConfirmSelectedSpatialCommentResolutionCommand(),
    )
    install_spatial_comment_tree_context_menu()


def schedule_toggle_sync() -> None:
    """Compatibility no-op; toggle state is initialized by ``GetResources``.

    FreeCAD treats the presence of the ``Checkable`` resource as making an
    action checkable and uses its boolean value as the action's initial checked
    state. Loading the saved setting in ``GetResources`` therefore avoids any
    delayed QAction lookup or workbench activation at startup.
    """
