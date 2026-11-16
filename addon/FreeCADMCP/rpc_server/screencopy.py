"""Guards for optional Hyprland screen capture; never identify apps by title."""
import json
import math
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable


def _query(name: str) -> Any:
    reply = subprocess.run(["hyprctl", name, "-j"], capture_output=True, timeout=3, check=True)
    return json.loads(reply.stdout)


def _rect(values: Any) -> tuple[int, int, int, int]:
    if len(values) != 4 or any(type(n) not in (int, float) or not math.isfinite(n) for n in values):
        raise ValueError("Invalid compositor geometry")
    x, y, w, h = map(int, values)
    if w <= 0 or h <= 0:
        raise ValueError("Empty compositor geometry")
    return x, y, w, h


def _overlaps(a: tuple, b: tuple) -> bool:
    return a[0] < b[0]+b[2] and b[0] < a[0]+a[2] and a[1] < b[1]+b[3] and b[1] < a[1]+a[3]


def _capture_target(pid: int, viewport: tuple, window_size: tuple) -> tuple[str, tuple]:
    clients = _query("clients")
    matches = [w for w in clients if w.get("pid") == pid and w.get("class") == "org.freecad.FreeCAD"
               and w.get("mapped") is True and w.get("hidden") is False]
    if len(matches) != 1:
        raise ValueError("Cannot identify a unique FreeCAD window")
    window = matches[0]
    active = _query("activewindow")
    if not window.get("address") or active.get("address") != window["address"] or active.get("pid") != pid:
        raise ValueError("FreeCAD is not the active window")
    wx, wy, ww, wh = _rect(window["at"] + window["size"])
    x, y, w, h = _rect(viewport)
    qw, qh = window_size
    if qw <= 0 or qh <= 0 or x < 0 or y < 0 or x+w > qw or y+h > qh:
        raise ValueError("Viewport is outside the FreeCAD window")
    region = _rect((wx+x*ww/qw, wy+y*wh/qh, w*ww/qw, h*wh/qh))
    for other in clients:
        if other["address"] == window["address"] or other.get("mapped") is False or other.get("hidden") is True:
            continue
        # Conservative even for windows behind FreeCAD or on other workspaces.
        if _overlaps(region, _rect(other["at"] + other["size"])):
            raise ValueError("Another window overlaps the capture")
    for monitor in _query("layers").values():
        for level in ("2", "3"):  # top and overlay layer surfaces
            for layer in monitor["levels"][level]:
                if _overlaps(region, _rect([layer[k] for k in ("x", "y", "w", "h")])):
                    raise ValueError("An overlay overlaps the capture")
    return window["address"], region


def capture_viewport(pid: int, viewport: tuple, window_size: tuple, image_type: Callable) -> Any:
    """Return an image only if identity and visibility checks hold around capture.

    This is still screen capture, not a private window surface. The caller must
    require an explicit opt-in: transient compositor content can race snapshots.
    """
    try:
        before = _capture_target(pid, viewport, window_size)
        x, y, w, h = before[1]
        with tempfile.TemporaryDirectory(prefix="freecad-mcp-capture-") as folder:
            path = str(Path(folder) / "viewport.png")
            subprocess.run(["grim", "-g", f"{x},{y} {w}x{h}", path], capture_output=True, timeout=5, check=True)
            if _capture_target(pid, viewport, window_size) != before:
                return None
            image = image_type(path)
            return None if image.isNull() else image
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError):
        return None
