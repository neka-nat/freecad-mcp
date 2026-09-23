"""Carry per-face colors across an edit that rebuilds the shape.

``DiffuseColor`` is a list indexed by face number. A boolean or
``removeSplitter`` renumbers faces, so the old list no longer lines up: FreeCAD
sees a length mismatch and falls back to the single ``ShapeColor``, and the part
turns one flat color. The mapping cannot be recovered afterwards because the
old face order is gone.

So it is captured before the script runs and re-applied after, keyed on where
each face sits rather than on its index. A face that survived the edit keeps its
color; a face that was split hands its color to both halves, since they share
the parent's plane. New faces fall back to ``ShapeColor``.
"""

from typing import Any

import FreeCAD


def _key(face: Any) -> tuple:
    """Locate a face by geometry, so renumbering does not lose it.

    The center of mass alone collides between concentric faces, so the surface
    type and area join it. Rounding is coarse enough to absorb the tolerance
    OCCT introduces when it rebuilds a face it did not really change.
    """
    c = face.CenterOfMass
    return (
        face.Surface.__class__.__name__,
        round(c.x, 3),
        round(c.y, 3),
        round(c.z, 3),
        round(face.Area, 3),
    )


def _plane_key(face: Any) -> tuple | None:
    """Where a face's surface lies, ignoring its outline.

    A face that got split keeps its surface but loses its center and area. Its
    halves still report the same plane, which is what lets them inherit the
    original color.
    """
    surface = face.Surface
    name = surface.__class__.__name__
    try:
        if name == "Plane":
            n = surface.Axis
            p = surface.Position
            d = n.x * p.x + n.y * p.y + n.z * p.z
            return ("Plane", round(n.x, 4), round(n.y, 4), round(n.z, 4), round(d, 3))
        if name == "Cylinder":
            a, c = surface.Axis, surface.Center
            return (
                "Cylinder",
                round(surface.Radius, 4),
                round(a.x, 4),
                round(a.y, 4),
                round(a.z, 4),
                round(c.x, 3),
                round(c.y, 3),
                round(c.z, 3),
            )
    except Exception:  # noqa: BLE001 - an exotic surface simply has no plane key
        return None
    return None


def _objects(doc: Any) -> list[Any]:
    out = []
    for obj in getattr(doc, "Objects", []):
        shape = getattr(obj, "Shape", None)
        view = getattr(obj, "ViewObject", None)
        if shape is None or view is None:
            continue
        try:
            if shape.isNull():
                continue
        except Exception:  # noqa: BLE001
            continue
        out.append(obj)
    return out


def snapshot() -> dict[str, Any]:
    """Record each object's per-face colors, keyed on face geometry."""
    try:
        docs = list(FreeCAD.listDocuments().values())
    except Exception:  # noqa: BLE001
        return {}

    state: dict[str, Any] = {}
    for doc in docs:
        for obj in _objects(doc):
            try:
                colors = list(obj.ViewObject.DiffuseColor)
            except Exception:  # noqa: BLE001
                continue
            faces = obj.Shape.Faces
            # A single entry means the object is uniformly colored; there is no
            # per-face assignment to lose, and recording it would only risk
            # re-applying a stale color later.
            if len(colors) < 2 or len(colors) != len(faces):
                continue
            by_face, by_plane = {}, {}
            for face, color in zip(faces, colors):
                by_face[_key(face)] = color
                pk = _plane_key(face)
                if pk is not None:
                    by_plane.setdefault(pk, color)
            state[f"{doc.Name}.{obj.Name}"] = {
                "by_face": by_face,
                "by_plane": by_plane,
                "count": len(faces),
            }
    return state


def restore(before: dict[str, Any]) -> list[str]:
    """Re-apply recorded colors to objects whose face count changed."""
    if not before:
        return []
    try:
        docs = list(FreeCAD.listDocuments().values())
    except Exception:  # noqa: BLE001
        return []

    repaired = []
    for doc in docs:
        for obj in _objects(doc):
            entry = before.get(f"{doc.Name}.{obj.Name}")
            if entry is None:
                continue
            faces = obj.Shape.Faces
            view = obj.ViewObject
            try:
                current = list(view.DiffuseColor)
            except Exception:  # noqa: BLE001
                continue
            fallback = view.ShapeColor
            by_face, by_plane = entry["by_face"], entry["by_plane"]
            # A rebuild can keep the face count and still reorder the faces, so
            # the count proves nothing; only the keys do.
            if len(current) == len(faces) and all(
                _key(face) in by_face for face in faces
            ):
                if [by_face[_key(face)] for face in faces] == current:
                    continue
            colors, matched = [], 0
            for face in faces:
                color = by_face.get(_key(face))
                if color is None:
                    pk = _plane_key(face)
                    color = by_plane.get(pk) if pk is not None else None
                if color is None:
                    colors.append(fallback)
                else:
                    colors.append(color)
                    matched += 1
            # Assigning a list of one repaints the whole object, which is worse
            # than the flat color the caller already has.
            if matched == 0:
                continue
            try:
                view.DiffuseColor = colors
                repaired.append(f"{doc.Name}.{obj.Name}: {matched}/{len(faces)} faces")
            except Exception:  # noqa: BLE001
                continue
    return repaired
