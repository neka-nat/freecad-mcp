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


def _grab_compositor_viewport(save_path: str, width: int, height: int) -> bool:
    """Capture the 3D viewport via the Wayland compositor (grim).

    On NVIDIA + Wayland, QOpenGLWidget.grabFramebuffer() reads back a torn or
    stale GPU buffer — the saved image is full of artifacts. The compositor
    (grim over Hyprland screencopy) always holds a clean frame, so locate the
    FreeCAD window with hyprctl, compute the 3D view's on-screen rect from Qt
    relative geometry, and let grim crop exactly that region.
    """
    try:
        from PySide6 import QtCore, QtGui, QtOpenGLWidgets, QtWidgets

        win = FreeCADGui.getMainWindow()
        mdi = win.findChild(QtWidgets.QMdiArea)
        if mdi is None:
            return False
        gl = mdi.findChild(QtOpenGLWidgets.QOpenGLWidget)
        if gl is None:
            return False

        # Flush pending paints so the compositor frame matches the view state.
        QtWidgets.QApplication.processEvents()
        QtCore.QThread.msleep(120)

        # mapToGlobal() is unreliable under this compositor (observed ~30px
        # offset), so capture the WHOLE screen with grim, then locate the
        # FreeCAD window via hyprctl and crop the 3D view's rect out of it.
        rel = gl.mapTo(win, QtCore.QPoint(0, 0))
        win_w = max(1, win.width())
        win_h = max(1, win.height())

        import json
        import subprocess
        import tempfile

        # Window position/size in logical screen coordinates from Hyprland.
        try:
            clients = subprocess.run(
                ["hyprctl", "clients", "-j"], capture_output=True, timeout=5
            )
            wins = json.loads(clients.stdout)
            # FreeCAD sets a unique WM class; match on it (fallback: title).
            me = next(
                w for w in wins
                if w.get("class") == "org.freecad.FreeCAD"
                or "freecad" in (w.get("title") or "").lower()
            )
            wx, wy = me["at"][0], me["at"][1]
            ww, wh = me["size"][0], me["size"][1]
        except Exception:
            return False

        # The 3D view's rect inside the window (fractional), scaled to the
        # compositor's actual window box on screen.
        fx0 = rel.x() / win_w
        fy0 = rel.y() / win_h
        # grim -g takes logical coordinates: grab exactly the view region.
        # Qt's logical window size already matches the compositor's reported
        # size, so no scale factor is needed — just clamp the rect into the
        # window box to avoid spilling onto overlapping surfaces (docks).
        geo_x = int(wx + rel.x() * ww / win_w)
        geo_y = int(wy + rel.y() * wh / win_h)
        geo_w = max(1, min(int(gl.width() * ww / win_w), wx + ww - geo_x))
        geo_h = max(1, min(int(gl.height() * wh / win_h), wy + wh - geo_y))

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            proc = subprocess.run(
                ["grim", "-g", f"{geo_x},{geo_y} {geo_w}x{geo_h}", tmp.name],
                capture_output=True,
                timeout=15,
            )
            if proc.returncode != 0:
                return False
            img = QtGui.QImage(tmp.name)
        if img.isNull():
            return False
        if width and height:
            img = img.scaled(
                width, height, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            )
        return img.save(save_path, "PNG")
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
        gl = mdi.findChild(QtOpenGLWidgets.QOpenGLWidget)
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
):
    """Save a PNG of the active view to ``save_path``.

    Returns ``True`` on success, or an error string on failure (preserves the
    legacy GUI-handler return contract).
    """
    try:
        view = FreeCADGui.ActiveDocument.ActiveView
        if not hasattr(view, "saveImage"):
            return "Current view does not support screenshots"

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
        # On this machine (NVIDIA + Hyprland/Wayland), EVERY saveImage() path —
        # including "Framebuffer" — returns a broken frame: either a flat color
        # or, worse, an artifact-laden readback. The compositor (grim)
        # always holds a clean frame of the live window, so try it FIRST and
        # only fall back to saveImage()/grabFramebuffer() when unavailable
        # (X11 sessions, headless, missing grim).
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
            _grab_opengl_widget_fallback(save_path, resolved_width, resolved_height)
            FreeCAD.Console.PrintLog(
                "MCP RPC: saveImage produced a flat image; used QOpenGLWidget.grabFramebuffer() fallback\n"
            )

        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events(delay_ms=0)
        return True
    except Exception as e:
        return str(e)
