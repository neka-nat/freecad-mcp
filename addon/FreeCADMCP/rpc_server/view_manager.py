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


def get_displayed_3d_view() -> Any:
    """Return the 3D view currently displayed in the main window, or None.

    ``FreeCADGui.ActiveDocument.ActiveView`` can still return a document's 3D
    view while another tab (TechDraw page, Start page, spreadsheet...) is in
    front. Capturing that hidden view, and sending ``ViewSelection`` to an
    active MDI view that is not the one being captured, can crash FreeCAD a
    few seconds later. Only the view actually shown is safe to capture.
    """
    try:
        view = FreeCADGui.activeView()
    except Exception:
        return None
    if view is None or not hasattr(view, "saveImage"):
        return None
    return view


def _image_is_flat_color(path: str, threshold: int = 4) -> bool:
    """True when the saved PNG is (almost) a single flat color.

    A genuinely rendered scene always has many distinct pixel values; the
    broken offscreen captures come out as one solid color over the whole
    canvas. Sampling a sparse grid keeps this cheap even for large images.
    """
    try:
        from PySide6 import QtGui

        img = QtGui.QImage(path)
        if img.isNull() or img.width() == 0:
            return True
        colors = set()
        for sx in range(0, img.width(), max(1, img.width() // 32)):
            for sy in range(0, img.height(), max(1, img.height() // 32)):
                colors.add(img.pixel(sx, sy))
                if len(colors) > threshold:
                    return False
        return True
    except Exception:
        return False


def _find_active_gl_widget() -> Any:
    """Return the QOpenGLWidget of the ACTIVE 3D view, or None.

    mdi.findChild(QOpenGLWidget) returns the FIRST widget in the child tree,
    which may belong to a hidden/secondary MDI subwindow (e.g. an old empty
    document tab still sitting at its default 400x300 size). Grabbing that
    widget's rect produces a screenshot of the wrong region (or a flat color).
    """
    from PySide6 import QtOpenGLWidgets, QtWidgets

    win = FreeCADGui.getMainWindow()
    mdi = win.findChild(QtWidgets.QMdiArea)
    if mdi is None:
        return None
    # Prefer the GL widget belonging to the active MDI subwindow.
    active_sub = mdi.activeSubWindow() or mdi.currentSubWindow()
    if active_sub is not None:
        gl = active_sub.findChild(QtOpenGLWidgets.QOpenGLWidget)
        if gl is not None:
            return gl
    return None


def _grab_compositor_viewport(save_path: str, width: int, height: int) -> bool:
    """Opt-in screen capture, limited to the identified, unobscured FreeCAD view."""
    import os
    if os.environ.get("FREECAD_MCP_ALLOW_SCREEN_CAPTURE") != "1":
        return False
    try:
        from PySide6 import QtCore, QtGui
        from rpc_server.screencopy import capture_viewport
        win = FreeCADGui.getMainWindow()
        gl = _find_active_gl_widget()
        if gl is None or not gl.isVisible() or get_displayed_3d_view() is None:
            return False
        rel = gl.mapTo(win, QtCore.QPoint(0, 0))
        rect = (rel.x(), rel.y(), gl.width(), gl.height())
        image = capture_viewport(os.getpid(), rect, (win.width(), win.height()), QtGui.QImage)
        if image is None:
            return False
        if width and height:
            image = image.scaled(width, height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        return image.save(save_path, "PNG")
    except Exception:
        return False


def _grab_opengl_widget_fallback(save_path: str, width: int, height: int) -> bool:
    """Re-grab the active view from its live QOpenGLWidget framebuffer.

    Returns True when a non-empty image was written to ``save_path``.

    .. note::
        On NVIDIA + Wayland this readback produces artifact-laden frames
        (torn/stale buffers). Kept as the last-resort fallback only; prefer
        :func:`_grab_compositor_viewport`.
    """
    try:
        from PySide6 import QtCore, QtOpenGLWidgets, QtWidgets

        win = FreeCADGui.getMainWindow()
        mdi = win.findChild(QtWidgets.QMdiArea)
        if mdi is None:
            return False
        gl = _find_active_gl_widget()
        if gl is None:
            return False
        img = gl.grabFramebuffer()
        if img.isNull() or img.width() == 0:
            return False
        # Trim the capture to the requested aspect/size when it differs (the
        # framebuffer is the live viewport, not the requested size).
        if width and height and (img.width() != width or img.height() != height):
            img = img.scaled(
                width,
                height,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        return img.save(save_path, "PNG")
    except Exception:
        return False


def save_active_screenshot(
    save_path: str,
    view_name: str = "Isometric",
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> bool | str:
    """Save a PNG of the active view to ``save_path``.

    Returns ``True`` on success, or an error string on failure (preserves the
    legacy GUI-handler return contract).
    """
    try:
        view = get_displayed_3d_view()
        if view is None:
            return (
                "The tab in front is not a 3D view (TechDraw page, Start page...); "
                "bring the 3D view to the front"
            )

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
        # Screen capture is an explicit opt-in. Normally use FreeCAD's own
        # renderer/framebuffer without reading the desktop.
        if _grab_compositor_viewport(save_path, resolved_width, resolved_height):
            if focused_selection:
                FreeCADGui.Selection.clearSelection()
                _flush_gui_events(delay_ms=0)
            return True
        try:
            view.saveImage(save_path, resolved_width, resolved_height, "Current", "Framebuffer")
        except TypeError:
            view.saveImage(save_path, resolved_width, resolved_height, "Current")

        # Flat-color result means the offscreen path rendered nothing at all;
        # re-grab from the live QOpenGLWidget framebuffer as a last resort.
        if _image_is_flat_color(save_path):
            if _grab_opengl_widget_fallback(save_path, resolved_width, resolved_height):
                FreeCAD.Console.PrintLog("MCP RPC: used the active OpenGL framebuffer fallback\n")

        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events(delay_ms=0)
        return True
    except Exception as e:
        return str(e)
