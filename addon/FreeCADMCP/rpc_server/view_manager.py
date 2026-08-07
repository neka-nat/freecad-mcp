"""Active-view orientation, sizing, and screenshot capture."""

from typing import Any

import FreeCAD
import FreeCADGui

from rpc_server.gui_dispatch import _flush_gui_events


_VIEW_DISPATCH = {
    "Isometric": "viewIsometric",
    "Front": "viewFront",
    "Top": "viewTop",
    "Right": "viewRight",
    "Back": "viewBack",
    "Left": "viewLeft",
    "Bottom": "viewBottom",
    "Dimetric": "viewDimetric",
    "Trimetric": "viewTrimetric",
}


def _get_view_size(view: Any) -> tuple[int, int]:
    try:
        size = view.getSize()
        if isinstance(size, (list, tuple)) and len(size) >= 2:
            return max(1, int(size[0])), max(1, int(size[1]))
        return max(1, int(size.width())), max(1, int(size.height()))
    except Exception:
        return 1024, 768


# Longest edge used when the caller does not ask for a specific size. The
# screenshot's cost to an LLM client scales with its pixel count, and hosts
# commonly downscale anything larger than ~1.5k px before the model ever sees
# it, so rendering at the full window size just inflates the payload. An
# explicit width/height is always honoured as given.
MAX_AUTO_SCREENSHOT_EDGE = 1024


def _scale_to_max_edge(width: int, height: int, max_edge: int) -> tuple[int, int]:
    longest = max(width, height)
    if longest <= max_edge:
        return width, height
    scale = max_edge / longest
    return max(1, int(width * scale)), max(1, int(height * scale))


def _resolve_screenshot_size(
    view: Any,
    width: int | None,
    height: int | None,
) -> tuple[int, int]:
    view_width, view_height = _get_view_size(view)
    if width is None and height is None:
        return _scale_to_max_edge(view_width, view_height, MAX_AUTO_SCREENSHOT_EDGE)
    resolved_width = view_width if width is None else max(1, int(width))
    resolved_height = view_height if height is None else max(1, int(height))
    return resolved_width, resolved_height


_STD_COMMAND_DISPATCH = {
    "Isometric": "Std_ViewIsometric",
    "Front": "Std_ViewFront",
    "Top": "Std_ViewTop",
    "Right": "Std_ViewRight",
    "Back": "Std_ViewRear",
    "Left": "Std_ViewLeft",
    "Bottom": "Std_ViewBottom",
    "Dimetric": "Std_ViewDimetric",
    "Trimetric": "Std_ViewTrimetric",
}


def apply_view_orientation(view: Any, view_name: str) -> None:
    method_name = _VIEW_DISPATCH.get(view_name)
    if method_name is None:
        raise ValueError(f"Invalid view name: {view_name}")
    if hasattr(view, method_name):
        getattr(view, method_name)()
    else:
        # Fallback for views that lack the direct Python method
        # (e.g. some FreeCAD versions / view types)
        cmd = _STD_COMMAND_DISPATCH.get(view_name)
        if cmd:
            FreeCADGui.runCommand(cmd)
        else:
            FreeCAD.Console.PrintWarning(
                f"apply_view_orientation: no method or command for '{view_name}'\n"
            )


def _qwidget_class():
    from PySide import QtWidgets
    return QtWidgets.QWidget


def _render_scene_to_file(widget, save_path, width, height):
    """Render the widget's QGraphicsScene to a PNG.

    Returns True, an error string, or None when the widget has no usable scene
    (so the caller can fall back to a plain widget grab -- a spreadsheet view is
    a QTableView, not a QGraphicsView).
    """
    from PySide import QtCore, QtGui, QtWidgets

    scene = None
    for view in widget.findChildren(QtWidgets.QGraphicsView):
        candidate = view.scene()
        if candidate is not None and candidate.items():
            scene = candidate
            break
    if scene is None:
        return None

    # itemsBoundingRect, not sceneRect: it tracks the drawn content, so a page
    # with views placed outside the template border is still captured whole.
    source = scene.itemsBoundingRect()
    if source.isEmpty():
        return None

    target_w, target_h = _resolve_screenshot_size_for(
        max(1, int(round(source.width()))), max(1, int(round(source.height()))),
        width, height)

    image = QtGui.QImage(target_w, target_h, QtGui.QImage.Format_ARGB32)
    image.fill(QtGui.QColor("white"))
    painter = QtGui.QPainter(image)
    try:
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        scene.render(painter, QtCore.QRectF(image.rect()), source,
                     QtCore.Qt.KeepAspectRatio)
    finally:
        painter.end()

    if not image.save(save_path, "PNG"):
        return f"could not write PNG to {save_path}"
    return True


def grab_active_view(save_path: str, width: int | None = None, height: int | None = None):
    """Rasterise the active MDI sub-window, whatever kind of view it holds.

    The 3D view exposes ``saveImage``; a TechDraw page (``MDIViewPagePy``) and a
    spreadsheet do not, which made drawings invisible to a remote caller.
    ``QWidget.grab()`` renders any Qt widget offscreen, so one path covers every
    current and future view type. It captures what is on screen, so unlike
    ``saveImage`` it cannot re-orient or resize the scene -- for a drawing page
    or a sheet there is nothing to orient anyway.

    Returns ``True`` or an error string, matching the GUI-handler contract.
    """
    from PySide import QtCore, QtWidgets

    main_window = FreeCADGui.getMainWindow()
    if main_window is None:
        return "no FreeCAD main window"

    mdi_area = main_window.findChild(QtWidgets.QMdiArea)
    sub_window = mdi_area.activeSubWindow() if mdi_area is not None else None
    widget = sub_window.widget() if sub_window is not None else None
    if widget is None:
        return "no active MDI sub-window to capture"

    # Prefer rendering a QGraphicsScene when there is one. A TechDraw page's
    # MDI widget is a QMainWindow wrapping a QGraphicsView, and grabbing that
    # outer window yields a blank frame -- measured, an all-white PNG. Rendering
    # the scene draws the actual items instead, which also makes the capture
    # independent of scroll position, zoom and whether the window is occluded.
    rendered = _render_scene_to_file(widget, save_path, width, height)
    if rendered is not None:
        return rendered

    pixmap = widget.grab()
    if pixmap.isNull() or pixmap.width() == 0 or pixmap.height() == 0:
        return "widget grab produced an empty image"

    target_w, target_h = _resolve_screenshot_size_for(pixmap.width(), pixmap.height(),
                                                      width, height)
    if (target_w, target_h) != (pixmap.width(), pixmap.height()):
        pixmap = pixmap.scaled(target_w, target_h,
                               QtCore.Qt.KeepAspectRatio,
                               QtCore.Qt.SmoothTransformation)
    if not pixmap.save(save_path, "PNG"):
        return f"could not write PNG to {save_path}"
    return True


def _resolve_screenshot_size_for(view_width, view_height, width, height):
    """Same sizing policy as the 3D path, but for an already-rendered pixmap."""
    if width is None and height is None:
        return _scale_to_max_edge(view_width, view_height, MAX_AUTO_SCREENSHOT_EDGE)
    return (view_width if width is None else max(1, int(width)),
            view_height if height is None else max(1, int(height)))


def save_active_screenshot(
    save_path: str,
    view_name: str = "Isometric",
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
):
    """Save a PNG of the active view to ``save_path``.

    Uses the 3D view's own ``saveImage`` when available -- it can re-orient and
    render offscreen at an arbitrary size -- and falls back to a widget grab for
    view types that lack it (TechDraw pages, spreadsheets).

    Returns ``True`` on success, or an error string on failure (preserves the
    legacy GUI-handler return contract).
    """
    try:
        view = getattr(FreeCADGui.ActiveDocument, "ActiveView", None)
        if view is None or not hasattr(view, "saveImage"):
            return grab_active_view(save_path, width, height)

        apply_view_orientation(view, view_name)

        focused_selection = False
        # The resolved object we frame on (when focus_object is given), kept so
        # the framing can be re-applied synchronously right before saveImage().
        focus_target = None

        if focus_object:
            doc = FreeCAD.ActiveDocument
            obj = doc.getObject(focus_object) if doc else None
            if obj:
                FreeCADGui.Selection.clearSelection()
                FreeCADGui.Selection.addSelection(obj)
                FreeCADGui.SendMsgToActiveView("ViewSelection")
                focused_selection = True
                focus_target = obj
                _flush_gui_events()
                FreeCADGui.Selection.clearSelection()
            else:
                view.fitAll()
        else:
            view.fitAll()

        _flush_gui_events()
        # On macOS, when the FreeCAD window is not exposed (fully occluded or
        # minimized), saveImage() right after pumping the event loop grabs a blank
        # frame. Re-issuing the framing synchronously forces a redraw first. The
        # flush above is kept intentionally — Linux needs it for the stale-frame
        # fix (#51/#53).
        if focused_selection and focus_target is not None:
            FreeCADGui.Selection.addSelection(focus_target)
            FreeCADGui.SendMsgToActiveView("ViewSelection")
            FreeCADGui.Selection.clearSelection()
        else:
            view.fitAll()
        resolved_width, resolved_height = _resolve_screenshot_size(view, width, height)
        view.saveImage(save_path, resolved_width, resolved_height, "Current")

        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events(delay_ms=0)
        return True
    except Exception as e:
        return str(e)
