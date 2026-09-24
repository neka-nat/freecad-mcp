"""Make an edit provable before it is kept.

An edit used to be applied and then described. Nothing stopped a boolean that
left the part in two pieces, or grew a wall, or littered the surface with faces
too small to see in a render: the warnings went into the reply and the damaged
shape stayed in the document. Finding it fell to whoever was looking at the
screen, several edits later, when the cause was no longer obvious.

Here an edit runs against a checkpoint. The audit decides: a clean result is
kept, a rejected one is put back from the shapes copied beforehand and never
reaches the document. GUI undo is not that mechanism -- it is a stack the user
also drives, and it silently does nothing once its depth is exhausted -- so the
checkpoint holds its own copies and restores the same way every time.
"""

import time
from typing import Any

import FreeCAD

from rpc_server import connectivity
from rpc_server import dfm

# Defects worth rejecting an edit for. A part that is still one valid solid can
# be unusable: a 0.05 mm face is a cutter that cannot follow the surface, and a
# concave corner tighter than the mill leaves a corner no tool will reach.
DEFAULT_POLICY = {
    "require_valid": True,
    "require_solid_count": True,
    "require_one_piece": True,
    "max_new_thin_faces": 0,
    "max_new_short_edges": 0,
    "max_new_sharp_concave": 0,
    "forbid_bbox_growth": True,
    "thin_face_width": 0.3,
    "short_edge_length": 0.1,
}

_checkpoints: dict[str, dict[str, Any]] = {}
_counter = [0]


def _doc(doc_name: str) -> Any:
    doc = FreeCAD.getDocument(doc_name)
    if doc is None:
        raise ValueError(f"no document {doc_name!r}")
    return doc


def _shapes(doc: Any) -> dict[str, Any]:
    out = {}
    for obj in getattr(doc, "Objects", []):
        shape = getattr(obj, "Shape", None)
        if shape is None or not hasattr(shape, "isNull"):
            continue
        try:
            if shape.isNull():
                continue
        except Exception:  # noqa: BLE001
            continue
        out[obj.Name] = shape
    return out


def _measure(shape: Any, policy: dict[str, Any]) -> dict[str, Any]:
    """The numbers an audit compares, defect counts included."""
    m: dict[str, Any] = {}
    try:
        m["valid"] = bool(shape.isValid())
        m["solids"] = len(shape.Solids)
        m["faces"] = len(shape.Faces)
        m["volume"] = round(shape.Volume, 4)
        m["area"] = round(shape.Area, 4)
        bb = shape.BoundBox
        m["bbox"] = [round(v, 4) for v in
                     (bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax)]
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}
    # A scan that fails is recorded as such, not as an empty result: "found no
    # slivers" and "could not look for slivers" must not both read as a pass.
    #
    # Only the count and a few examples are kept. The verdict needs the count,
    # the reply needs something to point at, and holding every defect of a
    # 400-face lid in each checkpoint costs memory for detail nobody reads.
    # How many pieces the part is really in. A block fused a fraction short of
    # what it was meant to meet stays one solid and one valid shape, and hangs
    # free in the render with nothing else to report it.
    try:
        m["pieces"] = connectivity.count_islands(shape)
    except Exception as e:  # noqa: BLE001
        m["pieces"] = None
        m.setdefault("scan_errors", {})["pieces"] = f"{type(e).__name__}: {e}"

    for key, fn, args in (
        ("thin_faces", dfm.thin_faces, (policy["thin_face_width"],)),
        ("short_edges", dfm.short_edges, (policy["short_edge_length"],)),
        ("sharp_concave", dfm.sharp_concave_edges, ()),
    ):
        try:
            found = fn(shape, *args)
        except Exception as e:  # noqa: BLE001
            m[key] = 0
            m[f"{key}_sample"] = []
            m.setdefault("scan_errors", {})[key] = f"{type(e).__name__}: {e}"
            continue
        m[key] = len(found)
        m[f"{key}_sample"] = found[:3]
    return m


_AXES = ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax")


def _same(was: dict[str, Any], now: dict[str, Any]) -> bool:
    """Whether two measurements describe the same shape.

    The kept examples are excluded: they are there to point at a defect, and
    two scans of one unchanged shape can pick different ones.
    """
    keys = {k for k in (*was, *now) if not k.endswith("_sample")}
    return all(was.get(k) == now.get(k) for k in keys)


def _judge(name: str, was: dict[str, Any] | None, now: dict[str, Any],
           policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Defects this edit introduced. Pre-existing ones are not its fault."""
    errors: list[dict[str, Any]] = []
    if "error" in now:
        return [{"code": "MEASURE_FAILED", "object": name, "detail": now["error"]}]
    if now.get("scan_errors"):
        errors.append({
            "code": "DEFECT_SCAN_FAILED", "object": name,
            "scans": now["scan_errors"],
        })
    if policy["require_valid"] and not now["valid"]:
        errors.append({"code": "SHAPE_INVALID", "object": name})
    if was and not was.get("error"):
        if policy["require_solid_count"] and now["solids"] != was["solids"]:
            errors.append({
                "code": "SOLID_COUNT_CHANGED", "object": name,
                "before": was["solids"], "after": now["solids"],
            })
        if (policy["require_one_piece"] and now.get("pieces") is not None
                and was.get("pieces") is not None
                and now["pieces"] > was["pieces"]):
            errors.append({
                "code": "PART_IN_PIECES", "object": name,
                "before": was["pieces"], "after": now["pieces"],
                "detail": "the edit left material joined to nothing, or only touching",
            })
        if policy["forbid_bbox_growth"] and was.get("bbox") and now.get("bbox"):
            grew = []
            for i, axis in enumerate(_AXES):
                delta = now["bbox"][i] - was["bbox"][i]
                outward = -delta if axis.endswith("Min") else delta
                if outward > 1e-6:
                    grew.append(f"{axis} {was['bbox'][i]:g}->{now['bbox'][i]:g}")
            if grew:
                errors.append({"code": "BBOX_GREW", "object": name, "axes": grew})
        for key, limit_key, code in (
            ("thin_faces", "max_new_thin_faces", "NEW_THIN_FACES"),
            ("short_edges", "max_new_short_edges", "NEW_SHORT_EDGES"),
            ("sharp_concave", "max_new_sharp_concave", "NEW_SHARP_CONCAVE"),
        ):
            added = now.get(key, 0) - was.get(key, 0)
            if added > policy[limit_key]:
                errors.append({
                    "code": code, "object": name, "added": added,
                    "total": now.get(key, 0),
                    "sample": now.get(f"{key}_sample", []),
                })
    return errors


def checkpoint(doc_name: str, label: str = "", objects: list[str] | None = None) -> dict[str, Any]:
    """Copy the shapes now, so a rejected edit has something to go back to.

    The copies are held in memory. Writing the whole document to disk per edit
    took long enough to stall the GUI thread, and the shapes are the only part
    an audit can reject.
    """
    doc = _doc(doc_name)
    _counter[0] += 1
    cid = f"cp_{_counter[0]:04d}"
    shapes = _shapes(doc)
    if objects:
        shapes = {n: s for n, s in shapes.items() if n in set(objects)}
    saved, measures, colors = {}, {}, {}
    for name, shape in shapes.items():
        try:
            saved[name] = shape.copy()
        except Exception:  # noqa: BLE001 - a shape that cannot be copied cannot be restored
            continue
        measures[name] = _measure(shape, DEFAULT_POLICY)
        # Face colours are indexed by face number, so putting an old shape back
        # under the current colour list leaves them scattered across the wrong
        # faces -- a restore that repairs the geometry and ruins the appearance.
        view = getattr(doc.getObject(name), "ViewObject", None)
        try:
            colors[name] = list(view.DiffuseColor) if view is not None else None
        except Exception:  # noqa: BLE001
            colors[name] = None
    _checkpoints[cid] = {
        "id": cid,
        "label": label,
        "document": doc_name,
        "created": time.time(),
        "shapes": saved,
        "colors": colors,
        "measures": measures,
    }
    return {
        "checkpoint_id": cid,
        "label": label,
        "document": doc_name,
        "objects": sorted(measures),
    }


def list_checkpoints() -> list[dict[str, Any]]:
    return [
        {"checkpoint_id": c["id"], "label": c["label"],
         "document": c["document"], "created": c["created"]}
        for c in sorted(_checkpoints.values(), key=lambda c: c["created"])
    ]


def restore(checkpoint_id: str) -> dict[str, Any]:
    """Put every shape back the way the checkpoint recorded it."""
    cp = _checkpoints.get(checkpoint_id)
    if cp is None:
        raise ValueError(f"no checkpoint {checkpoint_id!r}")
    doc = _doc(cp["document"])
    restored, failed = [], []
    for name, shape in cp["shapes"].items():
        target = doc.getObject(name)
        if target is None:
            failed.append(name)
            continue
        try:
            target.Shape = shape.copy()
            restored.append(name)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}: {type(e).__name__}: {e}")
            continue
        # Put the colours back with the shape they were recorded against: the
        # list is indexed by face number, and the restored shape numbers its
        # faces the old way again.
        saved = cp.get("colors", {}).get(name)
        view = getattr(target, "ViewObject", None)
        if saved and view is not None and len(saved) == len(shape.Faces):
            try:
                view.DiffuseColor = saved
            except Exception:  # noqa: BLE001
                pass
    doc.recompute()
    out = {"checkpoint_id": checkpoint_id, "restored": restored}
    # A restore that silently skipped an object would leave the caller believing
    # the edit was undone.
    if failed:
        out["failed"] = failed
    return out


def audit(doc_name: str, checkpoint_id: str = "",
          policy: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare the document against a checkpoint and return a verdict."""
    pol = {**DEFAULT_POLICY, **(policy or {})}
    cp = _checkpoints.get(checkpoint_id) if checkpoint_id else None
    before = cp["measures"] if cp else {}
    doc = _doc(doc_name)
    errors: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    for name, shape in _shapes(doc).items():
        # A narrowed checkpoint means the caller declared which objects the edit
        # may touch; judging the rest would charge it for shapes it never saw.
        if before and name not in before:
            continue
        now = _measure(shape, pol)
        was = before.get(name)
        if was is not None and _same(was, now):
            continue
        changed.append({
            "object": name,
            "volume": now.get("volume"),
            "volume_before": (was or {}).get("volume"),
            "solids": now.get("solids"),
            "valid": now.get("valid"),
        })
        errors.extend(_judge(name, was, now, pol))
    return {
        "verdict": "reject" if errors else "pass",
        "checkpoint_id": checkpoint_id,
        "errors": errors,
        "changed": changed,
    }


def guarded(doc_name: str, code: str, namespace: dict[str, Any],
            label: str = "", policy: dict[str, Any] | None = None,
            objects: list[str] | None = None) -> dict[str, Any]:
    """Run an edit, and keep it only if the audit passes.

    The checkpoint is taken first, so a rejected edit is undone from copies made
    before it ran rather than from the shapes it just damaged. Naming the
    objects an edit touches keeps that copy cheap on a large document.
    """
    cp = checkpoint(doc_name, label or "before guarded edit", objects)
    cid = cp["checkpoint_id"]
    try:
        exec(code, namespace)
    except Exception as e:  # noqa: BLE001 - the edit's failure is the result, not a crash
        restore(cid)
        return {
            "verdict": "reject",
            "checkpoint_id": cid,
            "errors": [{"code": "SCRIPT_FAILED", "detail": f"{type(e).__name__}: {e}"}],
            "restored": True,
        }
    report = audit(doc_name, cid, policy)
    if report["verdict"] == "reject":
        restore(cid)
        report["restored"] = True
    else:
        report["restored"] = False
    return report
