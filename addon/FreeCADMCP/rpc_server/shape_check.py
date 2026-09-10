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
    return {
        "null": False,
        "hash": shape.hashCode(),
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "volume": round(shape.Volume, 3),
    }


def snapshot() -> dict[str, dict[str, Any]]:
    """Fingerprint every object that exposes a ``Shape`` (no validity test)."""
    snap: dict[str, dict[str, Any]] = {}
    for doc_name, doc in FreeCAD.listDocuments().items():
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


def check(before: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compare the current documents with ``before``; validate what changed."""
    shapes: dict[str, Any] = {}
    for doc_name, doc in FreeCAD.listDocuments().items():
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
            if now["solids"] != 1 and (was is None or was.get("solids") != now["solids"]):
                what = f"{now['solids']} solids" + (
                    f" (was {was['solids']})" if was and "solids" in was else ""
                )
                warnings.append(f"{key}: {what}")
        changed.append(entry)
    return {"changed": changed, "warnings": warnings}
