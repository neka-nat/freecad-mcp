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
        view.saveImage(save_path, resolved_width, resolved_height, "Current")

        if focused_selection:
            FreeCADGui.Selection.clearSelection()
            _flush_gui_events(delay_ms=0)
        return True
    except Exception as e:
        return str(e)
