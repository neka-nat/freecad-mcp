"""Detect shapes that a script left broken.

``snapshot`` records a cheap fingerprint of every shape-bearing object in every
open document; ``check`` re-reads them and, for the objects that changed,
runs the expensive validity test. Both must run on the GUI thread because they
read document state.
"""

from typing import Any

import FreeCAD


def _fingerprint(shape: Any) -> dict[str, Any]:
    if shape.isNull():
        return {"null": True}
    fp = {
        "null": False,
        "hash": shape.hashCode(),
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "volume": round(shape.Volume, 3),
        # Area and bounding box catch edits that keep the solid valid, keep the
        # solid count at 1, and move the volume only slightly, yet still deform
        # the part: a fill box wider than the wall it repairs thickens that wall
        # without tripping any of the checks above.
        "area": round(shape.Area, 3),
    }
    try:
        bb = shape.BoundBox
        fp["bbox"] = [round(v, 3) for v in (bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax)]
    except Exception:  # noqa: BLE001
        pass
    return fp


def _documents() -> dict[str, Any] | None:
    """Open documents, or ``None`` if they cannot be listed.

    The check is a diagnostic. It must never be the reason a script fails, so a
    document listing that raises degrades to "nothing to compare". ``None`` and
    ``{}`` must stay distinct: an empty listing means every object really is
    gone, while a failed one means the objects were never looked at.
    """
    try:
        return dict(FreeCAD.listDocuments())
    except Exception:  # noqa: BLE001
        return None


def snapshot() -> dict[str, dict[str, Any]]:
    """Fingerprint every object that exposes a ``Shape`` (no validity test)."""
    snap: dict[str, dict[str, Any]] = {}
    for doc_name, doc in (_documents() or {}).items():
        for obj in getattr(doc, "Objects", []):
            shape = getattr(obj, "Shape", None)
            if shape is None or not hasattr(shape, "isNull"):
                continue
            key = f"{doc_name}.{obj.Name}"
            try:
                snap[key] = _fingerprint(shape)
            except Exception as e:  # noqa: BLE001 - a broken shape must not abort the check
                snap[key] = {"error": f"{type(e).__name__}: {e}"}
    return snap


def _validity(shape: Any) -> bool | None:
    try:
        return bool(shape.isValid())
    except Exception:  # noqa: BLE001
        return None


_AXES = ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax")


def _growth_warnings(key: str, was: dict[str, Any] | None, now: dict[str, Any]) -> list[str]:
    """Flag an edit that grew the part outward.

    A cut can only shrink a solid. Material appearing outside the previous
    bounding box means a fuse reached past the region it was meant to repair,
    which is how a 2.5 mm wall silently becomes 3.5 mm thick.
    """
    if not was or was.get("null") or now.get("null"):
        return []
    out: list[str] = []
    old_bb, new_bb = was.get("bbox"), now.get("bbox")
    if old_bb and new_bb:
        moved = []
        for i, axis in enumerate(_AXES):
            delta = new_bb[i] - old_bb[i]
            # Mins growing more negative and maxes growing more positive both
            # mean the shape reaches further out than it did before.
            outward = -delta if axis.endswith("Min") else delta
            if outward > 1e-6:
                moved.append(f"{axis} {old_bb[i]:g}->{new_bb[i]:g}")
        if moved:
            out.append(f"{key}: bounding box grew ({', '.join(moved)})")
    return out


def check(before: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compare the current documents with ``before``; validate what changed."""
    docs = _documents()
    if docs is None:
        return {"changed": [], "warnings": []}
    shapes: dict[str, Any] = {}
    for doc_name, doc in docs.items():
        for obj in getattr(doc, "Objects", []):
            shape = getattr(obj, "Shape", None)
            if shape is not None and hasattr(shape, "isNull"):
                shapes[f"{doc_name}.{obj.Name}"] = shape
    after = {}
    for key, shape in shapes.items():
        try:
            after[key] = _fingerprint(shape)
        except Exception as e:  # noqa: BLE001
            after[key] = {"error": f"{type(e).__name__}: {e}"}

    changed: list[dict[str, Any]] = []
    warnings: list[str] = []
    for key in sorted(set(before) - set(after)):
        warnings.append(f"{key}: object removed")
    for key, now in sorted(after.items()):
        was = before.get(key)
        if was == now:
            continue
        entry: dict[str, Any] = {"object": key, "was": was, **now}
        if "error" in now:
            warnings.append(f"{key}: {now['error']}")
        elif now.get("null"):
            entry["valid"] = False
            warnings.append(f"{key}: null shape")
        else:
            valid = _validity(shapes[key])
            entry["valid"] = valid
            if not valid:
                warnings.append(f"{key}: shape is INVALID")
            # Curves and 2D wires (no faces) are not solids by design; only bodies are judged.
            is_body = now["faces"] > 0 or (was is not None and was.get("faces", 0) > 0)
            if is_body and now["solids"] != 1 and (was is None or was.get("solids") != now["solids"]):
                what = f"{now['solids']} solids" + (
                    f" (was {was['solids']})" if was and "solids" in was else ""
                )
                warnings.append(f"{key}: {what}")
            warnings.extend(_growth_warnings(key, was, now))
        changed.append(entry)
    return {"changed": changed, "warnings": warnings}
