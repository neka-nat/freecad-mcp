"""Answer "what am I looking at" with geometry instead of a guess.

A screenshot shows a defect; the geometry that has to change is named by face
and coordinate. Without a way across that gap the only method is to scan the
whole part and hope the numbers match what is on screen -- which is how a
cutout that ends 1 mm above the sampled height got reported as absent.

The ray comes from the same view the screenshot did, so a pixel read off the
image resolves to the face that drew it.
"""

from typing import Any

import FreeCAD
import FreeCADGui


def _view() -> Any:
    doc = FreeCAD.ActiveDocument
    gui_doc = FreeCADGui.ActiveDocument
    if gui_doc is None and doc is not None:
        # Nothing has been clicked in this session, so no view is current yet;
        # the screenshot tools activate it the same way.
        FreeCADGui.setActiveDocument(doc.Name)
        gui_doc = FreeCADGui.ActiveDocument
    if gui_doc is None:
        raise ValueError("no active GUI document")
    view = gui_doc.ActiveView
    if view is None or not hasattr(view, "getObjectInfo"):
        raise ValueError("active view cannot be picked")
    return view


def _face_of(doc_name: str, obj_name: str, component: str) -> Any:
    if not component.startswith("Face"):
        return None
    doc = FreeCAD.getDocument(doc_name)
    obj = doc.getObject(obj_name) if doc else None
    shape = getattr(obj, "Shape", None)
    if shape is None:
        return None
    try:
        index = int(component[4:]) - 1
        return shape.Faces[index]
    except (ValueError, IndexError):
        return None


def _describe(face: Any) -> dict[str, Any]:
    surface = face.Surface
    kind = surface.__class__.__name__
    bb = face.BoundBox
    out: dict[str, Any] = {
        "surface": kind,
        "area": round(face.Area, 4),
        "bbox": [round(v, 4) for v in
                 (bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax)],
        "edges": len(face.Edges),
    }
    try:
        c = face.CenterOfMass
        out["centre"] = [round(c.x, 4), round(c.y, 4), round(c.z, 4)]
    except Exception:  # noqa: BLE001
        pass
    try:
        if kind == "Plane":
            n = surface.Axis
            out["normal"] = [round(n.x, 4), round(n.y, 4), round(n.z, 4)]
        elif kind in ("Cylinder", "Cone"):
            out["radius"] = round(surface.Radius, 4)
            a, c = surface.Axis, surface.Center
            out["axis"] = [round(a.x, 4), round(a.y, 4), round(a.z, 4)]
            out["axis_through"] = [round(c.x, 4), round(c.y, 4), round(c.z, 4)]
    except Exception:  # noqa: BLE001
        pass
    return out


def _scale(view: Any, image_width: int, image_height: int) -> tuple[float, float]:
    """Factor from a screenshot's pixels to the view's own.

    Screenshots are scaled down before they reach the caller, so a pixel read
    off one is not the pixel the view would pick: on a 1573-wide window sent as
    1024, everything is out by half a screen, and the reply is a confident hit
    on the wrong face.
    """
    width, height = view.getSize()
    sx = width / image_width if image_width else 1.0
    sy = height / image_height if image_height else 1.0
    return sx, sy


def pick(x: int, y: int, radius: int = 0,
         image_width: int = 0, image_height: int = 0) -> dict[str, Any]:
    """What the pixel at ``(x, y)`` is drawing.

    Coordinates are as in the screenshot: x from the left, y from the top.
    ``radius`` retries in a ring around the point, for a target too thin to hit
    dead-on -- the faces worth asking about are often a fraction of a pixel wide.

    Pass the screenshot's own size when it differs from the view's, so the
    pixel is scaled instead of landing somewhere else entirely.
    """
    view = _view()
    width, height = view.getSize()
    if image_width or image_height:
        sx, sy = _scale(view, image_width or width, image_height or height)
        x, y = int(round(x * sx)), int(round(y * sy))
    attempts = [(x, y)]
    for r in range(1, radius + 1):
        attempts += [(x + r, y), (x - r, y), (x, y + r), (x, y - r),
                     (x + r, y + r), (x - r, y - r), (x + r, y - r), (x - r, y + r)]
    for px, py in attempts:
        if not (0 <= px < width and 0 <= py < height):
            continue
        info = view.getObjectInfo((px, py))
        if not info:
            continue
        component = info.get("Component", "")
        result = {
            "hit": True,
            "pixel": [px, py],
            "document": info.get("Document"),
            "object": info.get("Object"),
            "component": component,
            "at": [round(info["x"], 4), round(info["y"], 4), round(info["z"], 4)],
            "view_size": [width, height],
        }
        face = _face_of(info.get("Document", ""), info.get("Object", ""), component)
        if face is not None:
            result["face"] = _describe(face)
        return result
    return {"hit": False, "pixel": [x, y], "view_size": [width, height],
            "searched_radius": radius}


def pick_region(x0: int, y0: int, x1: int, y1: int, step: int = 8,
                image_width: int = 0, image_height: int = 0) -> dict[str, Any]:
    """Every face drawn inside a rectangle of the screenshot.

    Sampling on a grid rather than tracing the outline: a region is usually
    drawn by a handful of faces, and the question is which ones, not their
    exact silhouette.

    Pass the screenshot's own size when it differs from the view's, so the
    rectangle covers the area that was actually looked at.
    """
    view = _view()
    width, height = view.getSize()
    if image_width or image_height:
        sx, sy = _scale(view, image_width or width, image_height or height)
        x0, x1 = int(round(x0 * sx)), int(round(x1 * sx))
        y0, y1 = int(round(y0 * sy)), int(round(y1 * sy))
        step = max(1, int(round(step * sx)))
    x0, x1 = sorted((max(0, x0), min(width - 1, x1)))
    y0, y1 = sorted((max(0, y0), min(height - 1, y1)))
    step = max(1, step)
    found: dict[tuple[str, str], dict[str, Any]] = {}
    samples = 0
    for py in range(y0, y1 + 1, step):
        for px in range(x0, x1 + 1, step):
            samples += 1
            info = view.getObjectInfo((px, py))
            if not info:
                continue
            key = (info.get("Object", ""), info.get("Component", ""))
            entry = found.get(key)
            if entry is None:
                entry = {
                    "object": info.get("Object"),
                    "component": info.get("Component"),
                    "pixels": 0,
                    "first_at": [round(info["x"], 4), round(info["y"], 4), round(info["z"], 4)],
                    "first_pixel": [px, py],
                }
                face = _face_of(info.get("Document", ""), key[0], key[1])
                if face is not None:
                    entry["face"] = _describe(face)
                found[key] = entry
            entry["pixels"] += 1
    ordered = sorted(found.values(), key=lambda e: -e["pixels"])
    return {
        "rect": [x0, y0, x1, y1],
        "step": step,
        "samples": samples,
        "faces": ordered,
        "view_size": [width, height],
    }


def locate(point: list[float]) -> dict[str, Any]:
    """Where a 3D point lands in the current view.

    The reverse of :func:`pick`: an audit reports a defect at a coordinate, and
    this says where to look for it on screen, or that it is not visible.
    """
    view = _view()
    width, height = view.getSize()
    vec = FreeCAD.Vector(*point)
    try:
        px, py = view.getPointOnScreen(vec)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"cannot project point: {e}") from e
    px, py = int(round(px)), int(round(py))
    out = {
        "at": [round(v, 4) for v in point],
        "pixel": [px, py],
        "view_size": [width, height],
        "on_screen": 0 <= px < width and 0 <= py < height,
    }
    if out["on_screen"]:
        info = view.getObjectInfo((px, py))
        # Whatever is drawn there may be a nearer face: the point can be inside
        # the part or behind a wall, and reporting it as visible would send the
        # reader to the wrong feature.
        out["drawn_there"] = {
            "object": info.get("Object"),
            "component": info.get("Component"),
            "at": [round(info["x"], 4), round(info["y"], 4), round(info["z"], 4)],
        } if info else None
    return out
