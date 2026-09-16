"""Find geometry a 3-axis mill cannot make, or that a boolean left behind by accident.

Four checks, each a plain function over a shape so they can be combined and
tested on their own:

``thin_faces``      faces narrower than a threshold (2·Area/Perimeter, exact for
                    a strip). A 0.14 mm ledge on a tab bottom is one of these.
``short_edges``     edges shorter than a threshold. A fill that overhangs an arc
                    by 0.04 mm shows up as 0.04 mm edges, on a face that is
                    otherwise 0.5 mm wide and would pass the width test.
``sharp_concave_edges``  concave edges between non-tangent faces, of any surface
                    type. An end mill leaves a radius in every vertical inside
                    corner, so a sharp one in the model is either wrong or needs
                    a radius agreed with the shop.
``internal_radii``  concave cylindrical faces below the smallest cutter radius.

``section_profile`` slices the shape with a plane and reports each segment of
the outline, flagging short ones and steps (a short segment between two nearly
parallel neighbours). ``shape_diff`` lists the material one shape has and the
other does not.

Everything here is read-only and works on any shape: a document object or a
STEP/BREP file, so the audit can run on the exact file a shop receives.
"""

import math
from typing import Any

import FreeCAD

_AXES = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}


def load_shape(doc_name: str = "", obj_name: str = "", file_path: str = "") -> Any:
    """Shape from a document object, or from a STEP/BREP/IGES file when ``file_path`` is set."""
    import Part  # imported late: the module must load where only FreeCAD is stubbed

    if file_path:
        shape = Part.Shape()
        shape.read(file_path)
        if shape.isNull():
            raise ValueError(f"no shape read from {file_path!r}")
        return shape
    doc = FreeCAD.getDocument(doc_name)
    obj = doc.getObject(obj_name)
    if obj is None:
        raise ValueError(f"no object {obj_name!r} in {doc_name!r}")
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        raise ValueError(f"{obj_name!r} has no shape")
    return shape


def _kind(face: Any) -> str:
    return face.Surface.__class__.__name__


def _round(v: Any, n: int = 3) -> list[float]:
    return [round(v.x, n), round(v.y, n), round(v.z, n)]


def _centre(shape: Any) -> list[float]:
    b = shape.BoundBox
    return [round((b.XMin + b.XMax) / 2, 3), round((b.YMin + b.YMax) / 2, 3), round((b.ZMin + b.ZMax) / 2, 3)]


def thin_faces(shape: Any, max_width: float = 0.3) -> list[dict[str, Any]]:
    """Faces whose mean width (2·Area/Perimeter) is under ``max_width``."""
    out = []
    for face in shape.Faces:
        perimeter = face.Length
        if perimeter <= 0:
            continue
        width = 2 * face.Area / perimeter
        if width < max_width:
            out.append({"surface": _kind(face), "width": round(width, 4), "area": round(face.Area, 4), "at": _centre(face)})
    return out


def short_edges(shape: Any, min_length: float = 0.1) -> list[dict[str, Any]]:
    """Edges shorter than ``min_length``."""
    return [
        {"length": round(edge.Length, 4), "at": _centre(edge)}
        for edge in shape.Edges
        if 0 < edge.Length < min_length
    ]


def _is_concave(shape: Any, face_b: Any, mid: Any, tangent: Any, n_a: Any, n_b: Any) -> bool:
    """An edge is concave when face B rises on the outer side of face A.

    Step off the edge into face B (perpendicular to the edge, within B's tangent
    plane) and ask whether that direction has a positive component along A's
    outward normal. Classifying a point on a face is cheap; classifying a point
    against the whole solid rebuilds a classifier each call and turned a
    1400-face part into a minute-long check, so that is only the fallback.
    """
    step = n_b.cross(tangent)
    if step.Length > 1e-9:
        step.normalize()
        for candidate in (step, step * -1):
            try:
                on_b = face_b.isInside(mid + candidate * 0.05, 0.01, True)
            except Exception:  # noqa: BLE001
                on_b = False
            if on_b:
                return candidate.dot(n_a) > 1e-6
    bisector = n_a + n_b
    if bisector.Length < 1e-9:
        return False
    bisector.normalize()
    return bool(shape.isInside(mid + bisector * 0.05, 1e-7, False))


def sharp_concave_edges(
    shape: Any, min_angle: float = 5.0, vertical_only: bool = False
) -> list[dict[str, Any]]:
    """Concave edges where the two faces meet at more than ``min_angle`` degrees.

    Tangent joins (fillets) are skipped. Concavity is decided by stepping a
    little way along the sum of the two outward normals: for an inside corner
    that point lies in material, for an outside corner it lies in air.
    """
    out = []
    cos_min = math.cos(math.radians(min_angle))
    # One pass over the faces instead of shape.ancestorsOfType per edge, which
    # walks the whole shape each time and made a 1400-face lid take minutes.
    adjacent: dict[int, list[Any]] = {}
    for face in shape.Faces:
        for e in face.Edges:
            adjacent.setdefault(e.hashCode(), []).append(face)
    for edge in shape.Edges:
        if edge.Length <= 0:
            continue
        faces = adjacent.get(edge.hashCode(), [])
        if len(faces) != 2:
            continue
        mid_param = (edge.FirstParameter + edge.LastParameter) / 2
        mid = edge.valueAt(mid_param)
        tangent = edge.tangentAt(mid_param)
        if vertical_only and abs(tangent.z) < 0.99:
            continue
        normals = []
        for face in faces:
            try:
                u, v = face.Surface.parameter(mid)
                normals.append(face.normalAt(u, v))
            except Exception:  # noqa: BLE001 - degenerate parametrisation: judge the rest
                break
        if len(normals) != 2:
            continue
        n1, n2 = normals
        if n1.dot(n2) > cos_min:
            continue
        if not _is_concave(shape, faces[1], mid, tangent, n1, n2):
            continue
        dihedral = 180 - math.degrees(math.acos(max(-1.0, min(1.0, n1.dot(n2)))))
        out.append(
            {
                "at": _round(mid),
                "length": round(edge.Length, 3),
                "direction": "vertical" if abs(tangent.z) >= 0.99 else "horizontal" if abs(tangent.z) < 0.01 else "sloped",
                "dihedral_deg": round(dihedral, 1),
                "surfaces": sorted(_kind(f) for f in faces),
            }
        )
    return out


def internal_radii(shape: Any, r_min: float = 2.0) -> list[dict[str, Any]]:
    """Concave cylindrical faces with radius under ``r_min``, grouped by radius and axis."""
    groups: dict[tuple[float, str], list[list[float]]] = {}
    for face in shape.Faces:
        if _kind(face) != "Cylinder":
            continue
        surf = face.Surface
        if surf.Radius >= r_min - 1e-6:
            continue
        u0, u1, v0, v1 = face.ParameterRange
        p = face.valueAt((u0 + u1) / 2, (v0 + v1) / 2)
        n = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        pc = p - surf.Center
        radial = pc - surf.Axis * pc.dot(surf.Axis)
        if n.dot(radial) >= 0:
            continue  # normal points away from the axis: a boss, not a hole
        ax = surf.Axis
        axis = "z" if abs(ax.z) > 0.9 else "x" if abs(ax.x) > 0.9 else "y" if abs(ax.y) > 0.9 else "skew"
        groups.setdefault((round(surf.Radius, 3), axis), []).append(_centre(face))
    return [
        {"radius": r, "axis": axis, "count": len(where), "at": where[:6]}
        for (r, axis), where in sorted(groups.items())
    ]


def check(
    shape: Any,
    r_min: float = 2.0,
    max_width: float = 0.3,
    min_edge: float = 0.1,
    vertical_only: bool = True,
) -> dict[str, Any]:
    """Run every check; the caller decides what is acceptable for their shop."""
    return {
        "valid": bool(shape.isValid()),
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "volume": round(shape.Volume, 3),
        "internal_radii": internal_radii(shape, r_min),
        "sharp_concave_edges": sharp_concave_edges(shape, vertical_only=vertical_only),
        "thin_faces": thin_faces(shape, max_width),
        "short_edges": short_edges(shape, min_edge),
    }


def section_profile(
    shape: Any, axis: str, value: float, min_segment: float = 0.1, max_jog_deg: float = 2.0
) -> dict[str, Any]:
    """Outline of the shape cut by the plane ``axis = value``.

    Each wire is returned as ordered segments with their length and curve type.
    ``short`` lists segments under ``min_segment``. ``steps`` narrows that to the
    ones that break the outline's tangent by more than ``max_jog_deg`` at *both*
    ends: a fillet or chamfer blends into at least one neighbour, so a short
    segment that blends into neither is a leftover, not a feature.
    """
    normal = FreeCAD.Vector(*_AXES[axis.lower()])
    wires = shape.slice(normal, value)
    out_wires, short, steps = [], [], []
    for wi, wire in enumerate(wires):
        edges = wire.OrderedEdges
        segs = []
        for edge in edges:
            p0, p1 = edge.valueAt(edge.FirstParameter), edge.valueAt(edge.LastParameter)
            segs.append(
                {
                    "curve": edge.Curve.__class__.__name__,
                    "length": round(edge.Length, 4),
                    "from": _round(p0, 4),
                    "to": _round(p1, 4),
                    # tangents at the ends, not the chord: a wall running into an
                    # arc is tangent-continuous even though the chords are not
                    "t_in": edge.tangentAt(edge.FirstParameter),
                    "t_out": edge.tangentAt(edge.LastParameter),
                    "p0": p0,
                    "p1": p1,
                }
            )
        n = len(segs)

        def meeting_tangents(seg: dict[str, Any], other: dict[str, Any]) -> tuple[Any, Any] | None:
            """Tangents of two segments at the point where they meet, both pointing away from it.

            Wire order does not say which end of an edge touches which neighbour,
            so the shared point is found by distance.
            """
            best, gap = None, 1e-6
            for pa, ta in ((seg["p0"], seg["t_in"]), (seg["p1"], seg["t_out"])):
                for pb, tb in ((other["p0"], other["t_in"]), (other["p1"], other["t_out"])):
                    d = (pa - pb).Length
                    if best is None or d < gap:
                        best, gap = (pa, ta, pb, tb), d
            if best is None:
                return None
            pa, ta, pb, tb = best
            # orient each tangent to point away from the joint
            out_a = ta if (pa - seg["p0"]).Length > (pa - seg["p1"]).Length else ta * -1
            out_b = tb if (pb - other["p0"]).Length > (pb - other["p1"]).Length else tb * -1
            return out_a, out_b

        def tangent_break_deg(seg: dict[str, Any], other: dict[str, Any]) -> float:
            """How far the outline turns at the joint between two segments, degrees."""
            pair = meeting_tangents(seg, other)
            if pair is None:
                return 0.0
            a, b = pair
            if a.Length < 1e-9 or b.Length < 1e-9:
                return 0.0
            # tangents point away from each other along a smooth outline, so a
            # straight-through joint reads as 180 degrees between them
            cos = max(-1.0, min(1.0, a.dot(b) / (a.Length * b.Length)))
            return round(180 - math.degrees(math.acos(cos)), 2)

        for i, s in enumerate(segs):
            if s["length"] >= min_segment:
                continue
            item = {"wire": wi, "index": i, "length": s["length"], "at": s["from"]}
            short.append(item)
            if n < 3:
                continue
            # A fillet or chamfer is put there to smooth a corner, so it meets its
            # neighbours tangentially on at least one side. A leftover from a
            # mis-sized feature breaks the tangent at both joints: the arc it was
            # meant to blend into starts off-axis, which is exactly what a fill
            # box 0.04 mm too wide leaves behind.
            breaks = [tangent_break_deg(s, segs[(i - 1) % n]), tangent_break_deg(s, segs[(i + 1) % n])]
            if min(breaks) > max_jog_deg:
                steps.append({**item, "tangent_break_deg": max(breaks)})
        for s in segs:
            for k in ("t_in", "t_out", "p0", "p1"):
                del s[k]
        out_wires.append({"closed": bool(wire.isClosed()), "length": round(wire.Length, 4), "segments": segs})
    return {"axis": axis.lower(), "value": value, "wires": out_wires, "short": short, "steps": steps}


def shape_diff(a: Any, b: Any, min_volume: float = 0.001) -> dict[str, Any]:
    """Material only in ``a``, material only in ``b``, and how much they share."""

    def solids(shape: Any) -> list[dict[str, Any]]:
        items = []
        for s in shape.Solids:
            if s.Volume < min_volume:
                continue
            bb = s.BoundBox
            items.append(
                {
                    "volume": round(s.Volume, 3),
                    "bbox": [round(v, 3) for v in (bb.XMin, bb.XMax, bb.YMin, bb.YMax, bb.ZMin, bb.ZMax)],
                }
            )
        return sorted(items, key=lambda i: -i["volume"])

    only_a, only_b = a.cut(b), b.cut(a)
    return {
        "only_in_a": solids(only_a),
        "only_in_b": solids(only_b),
        "volume_only_in_a": round(only_a.Volume, 3),
        "volume_only_in_b": round(only_b.Volume, 3),
        "common_volume": round(a.common(b).Volume, 3),
    }
