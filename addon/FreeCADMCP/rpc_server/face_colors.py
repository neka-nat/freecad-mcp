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


def _facing(face: Any) -> tuple | None:
    """Which way a planar face points, and where its centre is.

    Recorded so a face that merely moved can be found again: growing a pad
    0.35 mm thicker replaces its end cap with one 0.35 mm further out, facing
    the same way. Neither the exact key nor the plane key survives that -- the
    plane itself changed -- so without this the new cap falls back to the
    object's colour, and a yellow pad comes out part grey.
    """
    surface = face.Surface
    if surface.__class__.__name__ != "Plane":
        return None
    try:
        n = surface.Axis
        c = face.CenterOfMass
        return ((round(n.x, 4), round(n.y, 4), round(n.z, 4)), (c.x, c.y, c.z))
    except Exception:  # noqa: BLE001
        return None


def _nearest_colour(face: Any, moved: dict, limit: float = 1.0) -> Any:
    """Colour the recorded faces around this one agree on.

    A face that moved sits among the faces it used to border: the new end cap
    of a thicker pad is surrounded by that pad's sides. When they all carried
    one colour, it is the face's own; when they disagree, the neighbourhood
    says nothing and guessing would be worse than the fallback.

    The radius follows the face's own size, so a pad's cap consults that pad
    and a small chip's face consults that chip.
    """
    facing = _facing(face)
    if facing is None:
        return None
    cx, cy, cz = facing[1]
    try:
        limit = max(limit, face.Area ** 0.5)
    except Exception:  # noqa: BLE001
        pass
    near = set()
    for candidates in moved.values():
        for (px, py, pz), colour in candidates:
            d = ((px - cx) ** 2 + (py - cy) ** 2 + (pz - cz) ** 2) ** 0.5
            if d < limit:
                near.add(tuple(colour))
    if len(near) != 1:
        return None
    return next(iter(near))


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


def _shape_id(shape: Any) -> tuple | None:
    """Enough of a shape to tell whether an edit replaced it.

    Face positions are part of it: growing a pad moves a face without changing
    how many there are or how much they cover, and a shape that reads as
    unchanged there would have its restore skipped.
    """
    try:
        centres = []
        for face in shape.Faces:
            c = face.CenterOfMass
            centres.append((round(c.x, 5), round(c.y, 5), round(c.z, 5),
                            round(face.Area, 5)))
        return (len(shape.Faces), tuple(centres))
    except Exception:  # noqa: BLE001
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
            by_face, by_plane, by_facing = {}, {}, {}
            for face, color in zip(faces, colors):
                by_face[_key(face)] = color
                facing = _facing(face)
                if facing is not None:
                    by_facing.setdefault(facing[0], []).append((facing[1], color))
                pk = _plane_key(face)
                if pk is None:
                    continue
                # A plane only speaks for a new face if everything already on it
                # agrees. Two parts can share a plane -- a mounting pad's side
                # and the connector's side sit flush -- and taking whichever was
                # recorded first paints the new face in its neighbour's colour.
                if pk in by_plane and by_plane[pk] != color:
                    by_plane[pk] = None
                else:
                    by_plane.setdefault(pk, color)
            state[f"{doc.Name}.{obj.Name}"] = {
                "by_face": by_face,
                "by_plane": by_plane,
                "by_facing": by_facing,
                "count": len(faces),
                "shape": _shape_id(obj.Shape),
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
            # Only an edit that rebuilt the shape can scramble the colour list.
            # A script that deliberately recoloured a face left the shape alone,
            # and restoring there would undo what it was asked to do.
            if entry.get("shape") is not None and _shape_id(obj.Shape) == entry["shape"]:
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
            by_facing = entry.get("by_facing", {})
            colors, matched = [], 0
            for face in faces:
                color = by_face.get(_key(face))
                if color is None:
                    pk = _plane_key(face)
                    color = by_plane.get(pk) if pk is not None else None
                if color is None:
                    # Last: a face that moved rather than appeared.
                    color = _nearest_colour(face, by_facing)
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
