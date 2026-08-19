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

# TechDraw page rendering.  The scene is vector, so ``width`` is a *render
# resolution*, not a resample ceiling: a larger value buys genuinely sharper
# linework, unlike scaling a raster.  1000 px is ample for judging layout
# (~940 tokens); go larger only to read fine detail.
DEFAULT_PAGE_WIDTH = 1000

# Token cost scales with width * height, so bounding width alone is not enough
# once a crop makes the aspect ratio arbitrary.  An A4 landscape at width=2400
# is 2400x1697 = 4.07M px, so a 4M ceiling would reject a legitimate detail
# render; 6M (~8k tokens) clears it with margin while still catching a typo'd
# width=16000 (~181M px).  The guard exists to catch mistakes, not to overrule
# deliberate choices.  Exceeding it is an error, never a silent clamp.
MAX_PAGE_PIXELS = 6_000_000


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
        # On Wayland the offscreen GL contexts used by the default saveImage()
        # method render solid black; "Framebuffer" reads back the on-screen GL
        # context and captures correctly (and also works on X11/Windows/macOS).
        # FreeCAD < 1.0 lacks the method argument — fall back to the legacy call.
        try:
            view.saveImage(save_path, resolved_width, resolved_height, "Current", "Framebuffer")
        except TypeError:
            view.saveImage(save_path, resolved_width, resolved_height, "Current")

        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events(delay_ms=0)
        return True
    except Exception as e:
        return str(e)


def save_page_screenshot(
    save_path: str,
    page_name: str,
    width: int | None = None,
    crop: tuple[float, float, float, float] | None = None,
    doc_name: str | None = None,
):
    """Save a PNG of a TechDraw page to ``save_path``.

    TechDraw pages are QGraphicsScenes in their own MDI subwindow, not 3D
    views, so ``view.saveImage`` does not apply to them. Rendering the scene
    directly also lets the resolution be chosen independently of window size.

    Args:
        save_path: Destination PNG path.
        page_name: Internal Name of the DrawPage object.
        width: Render width in px. Defaults to ``DEFAULT_PAGE_WIDTH``. Larger
            values buy real detail -- this is a vector render, not a resample.
        crop: ``(left, top, right, bottom)`` as fractions 0..1 of the page's
            bounding rect, origin top-left. Renders only that region, at the
            full ``width`` -- a true vector zoom. ``None`` renders the page.
        doc_name: Document to look the page up in. Defaults to the active
            document. Page names are not unique across documents, so pass this
            whenever more than one document is open.

    Returns:
        ``True`` on success, or an error string.
    """
    try:
        from PySide import QtCore, QtGui, QtWidgets
    except Exception:
        from PySide2 import QtCore, QtGui, QtWidgets

    if doc_name is None:
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return "No active document"
    else:
        try:
            doc = FreeCAD.getDocument(doc_name)          # raises, not None
        except Exception:
            return (
                f"No such document '{doc_name}'; open documents: "
                f"{sorted(FreeCAD.listDocuments())}"
            )

    page = doc.getObject(page_name)
    if page is None:
        return f"No object '{page_name}' in document '{doc.Name}'"
    if not page.isDerivedFrom("TechDraw::DrawPage"):
        return f"'{page_name}' in '{doc.Name}' is not a TechDraw page"

    if crop is not None:
        try:
            c_l, c_t, c_r, c_b = (float(v) for v in crop)
        except Exception:
            return "crop must be four numbers (left, top, right, bottom)"
        if not (0.0 <= c_l < c_r <= 1.0 and 0.0 <= c_t < c_b <= 1.0):
            return (
                f"crop {crop} out of range; need 0 <= left < right <= 1 "
                "and 0 <= top < bottom <= 1 (fractions of the page)"
            )

    try:
        page.ViewObject.doubleClicked()      # ensure the page has a window
    except Exception:
        pass
    _flush_gui_events()

    mw = FreeCADGui.getMainWindow()
    mdi = mw.findChild(QtWidgets.QMdiArea)
    target = None
    for sub in (mdi.subWindowList() if mdi else []):
        title = sub.windowTitle()
        if page_name in title or (page.Label and page.Label in title):
            target = sub
    if target is None:
        return f"No open window for page '{page_name}'"

    widget = target.widget()
    scene = None
    for w in [widget] + widget.findChildren(QtWidgets.QGraphicsView):
        if isinstance(w, QtWidgets.QGraphicsView) and w.scene() is not None:
            scene = w.scene()
            break

    if scene is not None:
        rect = scene.itemsBoundingRect()
        if rect.isEmpty():
            rect = scene.sceneRect()

        if crop is not None:
            rect = QtCore.QRectF(
                rect.x() + c_l * rect.width(),
                rect.y() + c_t * rect.height(),
                (c_r - c_l) * rect.width(),
                (c_b - c_t) * rect.height(),
            )
            if rect.isEmpty():
                return "crop selects an empty region"

        w_px = DEFAULT_PAGE_WIDTH if width is None else max(1, int(width))
        h_px = max(1, int(w_px * rect.height() / rect.width())) if rect.width() else w_px

        if w_px * h_px > MAX_PAGE_PIXELS:
            return (
                f"{w_px}x{h_px} = {w_px * h_px / 1e6:.1f}M pixels exceeds the "
                f"{MAX_PAGE_PIXELS / 1e6:.0f}M budget; reduce width or tighten crop"
            )

        img = QtGui.QImage(w_px, h_px, QtGui.QImage.Format_RGB32)
        img.fill(QtGui.QColor(255, 255, 255))
        painter = QtGui.QPainter(img)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        scene.render(painter, QtCore.QRectF(img.rect()), rect)
        painter.end()
        img.save(save_path, "PNG")
        return True

    if crop is not None:
        return "crop needs the scene renderer; no QGraphicsScene reachable for this page"
    pm = widget.grab()                        # fallback
    if width:
        pm = pm.scaledToWidth(int(width), QtCore.Qt.SmoothTransformation)
    if pm.width() * pm.height() > MAX_PAGE_PIXELS:
        return (
            f"{pm.width()}x{pm.height()} exceeds the "
            f"{MAX_PAGE_PIXELS / 1e6:.0f}M pixel budget"
        )
    pm.save(save_path, "PNG")
    return True
