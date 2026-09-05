from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Literal

import FreeCAD
import FreeCADGui

CommentKind = Literal["edit_request", "approval"]
CommentStatus = Literal["open", "resolution_proposed", "resolved"]
AnchorType = Literal["point", "object", "subelement"]

ALLOWED_KINDS = {"edit_request", "approval"}
ALLOWED_STATUSES = {"open", "resolution_proposed", "resolved"}
ALLOWED_ANCHOR_TYPES = {"point", "object", "subelement"}
_MARKER_DELETE_SYNC_SUPPRESSIONS = 0


@contextmanager
def suppress_marker_delete_sync():
    """Temporarily ignore marker removals that are part of marker re-rendering."""
    global _MARKER_DELETE_SYNC_SUPPRESSIONS
    _MARKER_DELETE_SYNC_SUPPRESSIONS += 1
    try:
        yield
    finally:
        _MARKER_DELETE_SYNC_SUPPRESSIONS -= 1


def is_marker_delete_sync_suppressed() -> bool:
    return _MARKER_DELETE_SYNC_SUPPRESSIONS > 0


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sidecar_path_for_doc(doc: Any) -> str:
    """Return the comment sidecar path for a FreeCAD document."""
    if getattr(doc, "FileName", None):
        return doc.FileName + ".comments.json"

    base_dir = os.path.join(FreeCAD.getUserAppDataDir(), "freecad_mcp_comments")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, f"{doc.Name}.comments.json")


def _empty_store(doc: Any, **extra: Any) -> dict[str, Any]:
    store = {"version": 1, "document": doc.Name, "comments": []}
    store.update(extra)
    return store


def load_comment_store(doc: Any) -> dict[str, Any]:
    """Load sidecar JSON, quarantining malformed files instead of crashing RPC calls."""
    path = sidecar_path_for_doc(doc)
    if not os.path.exists(path):
        return _empty_store(doc)

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("comments"), list):
            raise TypeError("sidecar must be a JSON object with a comments list")
        return data
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as e:
        corrupt_path = path + ".corrupt"
        try:
            os.replace(path, corrupt_path)
        except OSError:
            corrupt_path = path
        FreeCAD.Console.PrintWarning(
            f"MCP comments sidecar could not be loaded ({e}); moved to {corrupt_path}\n"
        )
        return _empty_store(doc, load_error=str(e), corrupt_path=corrupt_path)


def save_comment_store(doc: Any, store: dict[str, Any]) -> None:
    path = sidecar_path_for_doc(doc)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    store["version"] = int(store.get("version", 1))
    store["document"] = doc.Name
    store["sidecar_path"] = path
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, ensure_ascii=False)


def _validate_kind_status(kind: str, status: str) -> None:
    if kind not in ALLOWED_KINDS:
        raise ValueError(f"Invalid comment kind: {kind!r}")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"Invalid comment status: {status!r}")


def _validate_anchor(anchor: dict[str, Any]) -> None:
    anchor_type = anchor.get("type", "point")
    if anchor_type not in ALLOWED_ANCHOR_TYPES:
        raise ValueError(f"Invalid anchor type: {anchor_type!r}")
    if anchor_type == "subelement" and not anchor.get("subelement"):
        raise ValueError(
            "Subelement anchors require a subelement value such as Face1, Edge2, or Vertex3."
        )


def _vec(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}


def _face_normal(face: Any) -> dict[str, float] | None:
    if not hasattr(face, "normalAt"):
        return None
    try:
        center = face.CenterOfMass
        u, v = face.Surface.parameter(center)
        return _vec(face.normalAt(u, v))
    except (AttributeError, TypeError, ValueError, RuntimeError):
        try:
            return _vec(face.normalAt(0, 0))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None


def _edge_tangent(edge: Any) -> dict[str, float] | None:
    if not hasattr(edge, "tangentAt"):
        return None
    try:
        return _vec(edge.tangentAt(getattr(edge, "FirstParameter", 0)))
    except (AttributeError, TypeError, ValueError, RuntimeError):
        try:
            return _vec(edge.tangentAt(0))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return None


def _object_anchor_position(obj: Any) -> dict[str, float] | None:
    """Return a stable fallback marker position for object-level comments."""
    bound_box = getattr(getattr(obj, "Shape", None), "BoundBox", None)
    for candidate in (
        getattr(bound_box, "Center", None),
        getattr(getattr(obj, "Placement", None), "Base", None),
    ):
        if candidate is None:
            continue
        try:
            return _vec(candidate)
        except (AttributeError, TypeError, ValueError):
            continue
    return None


def build_geometry_signature(
    obj: Any,
    subelement: str | None,
    point: dict[str, float] | None,
) -> dict[str, Any]:
    signature = {
        "object_name": obj.Name,
        "object_label": getattr(obj, "Label", None),
        "object_type": getattr(obj, "TypeId", None),
        "subelement": subelement,
        "picked_point": point,
        "center": None,
        "normal": None,
        "tangent": None,
        "measure": None,
    }
    if not subelement:
        signature["center"] = _object_anchor_position(obj)
        return signature
    if not hasattr(obj, "Shape"):
        return signature

    try:
        element = obj.Shape.getElement(subelement)
        if subelement.startswith("Face"):
            signature["center"] = _vec(element.CenterOfMass)
            signature["normal"] = _face_normal(element)
            signature["measure"] = float(getattr(element, "Area", 0.0))
        elif subelement.startswith("Edge"):
            signature["center"] = _vec(element.CenterOfMass)
            signature["tangent"] = _edge_tangent(element)
            signature["measure"] = float(getattr(element, "Length", 0.0))
        elif subelement.startswith("Vertex"):
            signature["center"] = _vec(element.Point)
    except (AttributeError, TypeError, ValueError, RuntimeError) as e:
        signature["signature_error"] = str(e)
    return signature


def _enrich_anchor(doc: Any, anchor: dict[str, Any]) -> dict[str, Any]:
    _validate_anchor(anchor)
    anchor.setdefault("type", "point")

    object_name = anchor.get("object_name")
    if not object_name:
        return anchor

    obj = doc.getObject(object_name)
    if obj is None:
        raise ValueError(f"Comment anchor object '{object_name}' not found.")

    signature = build_geometry_signature(
        obj, anchor.get("subelement"), anchor.get("position")
    )
    anchor.setdefault("geometry_signature", signature)
    if not anchor.get("position"):
        anchor["position"] = signature.get("center")
    if anchor.get("subelement"):
        anchor["type"] = "subelement"
    elif anchor.get("type") == "point":
        anchor["type"] = "object"
    return anchor


def anchor_from_selection(doc: Any) -> dict[str, Any]:
    selection = FreeCADGui.Selection.getSelectionEx(doc.Name)
    if not selection:
        raise ValueError(
            "Select an object, face, edge, vertex, or picked point before adding a comment."
        )

    selected = selection[0]
    obj = selected.Object
    subelement = selected.SubElementNames[0] if selected.SubElementNames else None
    point = None
    picked_points = getattr(selected, "PickedPoints", None) or []
    if picked_points:
        point = _vec(picked_points[0])

    signature = build_geometry_signature(obj, subelement, point)
    if point is None:
        if subelement and signature.get("center"):
            point = signature["center"]
        elif hasattr(obj, "Placement"):
            point = _vec(obj.Placement.Base)

    return {
        "type": "subelement" if subelement else "object",
        "object_name": obj.Name,
        "subelement": subelement,
        "position": point,
        "geometry_signature": signature,
    }


def create_comment(doc: Any, data: dict[str, Any]) -> dict[str, Any]:
    text = str(data.get("text", "")).strip()
    if not text:
        raise ValueError("Comment text is required.")

    store = load_comment_store(doc)
    comment_id = data.get("id") or str(uuid.uuid4())
    thread_id = data.get("thread_id") or comment_id
    kind = data.get("kind", "edit_request")
    status = data.get("status", "open")
    _validate_kind_status(kind, status)
    anchor = _enrich_anchor(doc, data.get("anchor") or anchor_from_selection(doc))

    comment = {
        "id": comment_id,
        "thread_id": thread_id,
        "text": text,
        "kind": kind,
        "status": status,
        "author": data.get("author", "user"),
        "anchor": anchor,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "resolved_at": None,
        "resolution_note": None,
        "thumbnail_png_base64": data.get("thumbnail_png_base64"),
    }
    store.setdefault("comments", []).append(comment)
    save_comment_store(doc, store)
    return comment


def list_comments(
    doc: Any, filters: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    comments = load_comment_store(doc).get("comments", [])
    filters = filters or {}

    if filters.get("status"):
        comments = [c for c in comments if c.get("status") == filters["status"]]
    elif not filters.get("include_resolved", False):
        comments = [c for c in comments if c.get("status") != "resolved"]

    if filters.get("object_name"):
        comments = [
            c
            for c in comments
            if c.get("anchor", {}).get("object_name") == filters["object_name"]
        ]
    if filters.get("thread_id"):
        comments = [c for c in comments if c.get("thread_id") == filters["thread_id"]]
    return comments


def update_comment(
    doc: Any, comment_id: str, patch: dict[str, Any]
) -> dict[str, Any] | None:
    if patch.get("status") == "resolved":
        raise ValueError(
            "Final resolution must be confirmed through the FreeCAD UI command."
        )

    store = load_comment_store(doc)
    for comment in store.get("comments", []):
        if comment.get("id") == comment_id:
            kind = patch.get("kind", comment.get("kind", "edit_request"))
            status = patch.get("status", comment.get("status", "open"))
            _validate_kind_status(kind, status)
            for key in [
                "text",
                "kind",
                "status",
                "resolution_note",
                "thumbnail_png_base64",
            ]:
                if key in patch:
                    comment[key] = patch[key]
            comment["updated_at"] = now_iso()
            save_comment_store(doc, store)
            return comment
    return None


def confirm_comment_resolution(
    doc: Any,
    comment_id: str,
    resolution_note: str | None = None,
) -> dict[str, Any] | None:
    store = load_comment_store(doc)
    for comment in store.get("comments", []):
        if comment.get("id") == comment_id:
            comment["status"] = "resolved"
            if resolution_note is not None:
                comment["resolution_note"] = resolution_note
            comment["resolved_at"] = now_iso()
            comment["updated_at"] = now_iso()
            save_comment_store(doc, store)
            return comment
    return None


def delete_comment(doc: Any, comment_id: str) -> bool:
    store = load_comment_store(doc)
    before = len(store.get("comments", []))
    store["comments"] = [
        c for c in store.get("comments", []) if c.get("id") != comment_id
    ]
    save_comment_store(doc, store)
    return len(store["comments"]) != before


def _detach_from_external_parents(
    obj: Any, allowed_parents: tuple[Any, ...] = ()
) -> None:
    """Keep comment marker objects out of active Parts/Bodies in the tree."""
    for parent in list(getattr(obj, "InList", [])):
        if parent in allowed_parents:
            continue
        remove_object = getattr(parent, "removeObject", None)
        if not callable(remove_object):
            continue
        try:
            remove_object(obj)
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            FreeCAD.Console.PrintWarning(
                f"Could not detach MCP comment marker from {parent.Name}: {e}\n"
            )


def _marker_group(doc: Any) -> Any:
    group = doc.getObject("MCP_Comment_Markers")
    if group is None:
        group = doc.addObject("App::DocumentObjectGroup", "MCP_Comment_Markers")
    _detach_from_external_parents(group)
    return group


def _comment_position(comment: dict[str, Any]) -> dict[str, float] | None:
    anchor = comment.get("anchor", {})
    return anchor.get("position") or anchor.get("geometry_signature", {}).get("center")


def _marker_color(comment: dict[str, Any]) -> tuple[float, float, float, float]:
    if comment.get("status") == "resolution_proposed":
        return (0.0, 0.75, 0.2, 1.0)
    return (1.0, 0.7, 0.0, 1.0)


def render_comment_markers(doc: Any) -> dict[str, Any]:
    group = _marker_group(doc)
    with suppress_marker_delete_sync():
        for child in list(getattr(group, "Group", [])):
            try:
                doc.removeObject(child.Name)
            except (AttributeError, TypeError, ValueError, RuntimeError) as e:
                FreeCAD.Console.PrintWarning(
                    f"Could not remove old MCP comment marker {child.Name}: {e}\n"
                )

    marker_count = 0
    for comment in list_comments(doc, {"include_resolved": False}):
        position = _comment_position(comment)
        if not position:
            continue
        marker = doc.addObject(
            "Part::Sphere",
            f"MCP_Comment_{comment['id'].replace('-', '_')[:16]}",
        )
        _detach_from_external_parents(marker)
        marker.Radius = 1.5
        marker.Placement.Base = FreeCAD.Vector(
            position["x"], position["y"], position["z"]
        )
        marker.addProperty(
            "App::PropertyString", "MCPCommentId", "MCP", "Spatial comment id"
        )
        marker.MCPCommentId = comment["id"]
        marker.Label = f"MCP Comment: {comment.get('text', '')[:40]}"
        if hasattr(marker, "ViewObject") and marker.ViewObject:
            marker.ViewObject.ShapeColor = _marker_color(comment)
            marker.ViewObject.Transparency = 20
        group.addObject(marker)
        _detach_from_external_parents(marker, (group,))
        marker_count += 1

    doc.recompute()
    return {"success": True, "marker_count": marker_count}
