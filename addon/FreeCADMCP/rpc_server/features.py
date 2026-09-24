"""Cut pockets and slots the way a mill does, so the shape needs no repair.

Assembled by hand from boxes and cylinders, a pocket comes out with notches
where the primitives cross and slivers where their arcs almost meet. Each one
then gets patched, and the patch leaves its own. The geometry is wrong from the
first operation: a round cutter cannot produce a square inside corner, so a
shape built from square primitives was never machinable to begin with.

Here the cut is the region the cutter sweeps: the set of points within its
radius of the path its centre travels. Inside corners come out as arcs of that
radius because nothing else can be there, and the walls meet the floor in one
piece because it is one solid.
"""

import math
from typing import Any

import FreeCAD


def _part() -> Any:
    """Imported late: the module has to load where only FreeCAD is stubbed."""
    import Part

    return Part


def _vec(xy: Any, z: float) -> Any:
    return FreeCAD.Vector(float(xy[0]), float(xy[1]), z)


def _capsule(a: Any, b: Any, radius: float, z: float, depth: float) -> Any:
    """The volume a cutter clears travelling from ``a`` to ``b``.

    A rectangle between the two stops plus a full circle at each, which is the
    swept disc written as primitives. Building it per segment and fusing keeps
    every join inside the union, where it cannot leave a seam on the result.
    """
    Part = _part()
    body = Part.makeCylinder(radius, depth, _vec(a, z))
    body = body.fuse(Part.makeCylinder(radius, depth, _vec(b, z)))
    dx, dy = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
    length = (dx * dx + dy * dy) ** 0.5
    if length > 1e-9:
        # A box of the slot's width laid along the segment, rotated into place.
        box = Part.makeBox(length, 2 * radius, depth, FreeCAD.Vector(0, -radius, 0))
        angle = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1),
                                 math.degrees(math.atan2(dy, dx)))
        box.Placement = FreeCAD.Placement(_vec(a, z), angle)
        body = body.fuse(box)
    return body


def cutter_volume(path: list[Any], radius: float, z: float, depth: float,
                  closed: bool = False) -> Any:
    """The volume swept by a cutter of ``radius`` following ``path``.

    ``path`` is the centreline in XY, not the outline of the finished pocket:
    the cut reaches ``radius`` beyond it on every side. For a pocket, hand in
    the rectangle the cutter's centre can reach, which is the pocket inset by
    its own radius.
    """
    if len(path) < 1:
        raise ValueError("path needs at least one point")
    if radius <= 0:
        raise ValueError("radius must be positive")
    if depth <= 0:
        raise ValueError("depth must be positive")
    Part = _part()
    if len(path) == 1:
        return Part.makeCylinder(radius, depth, _vec(path[0], z))
    segments = list(zip(path, path[1:]))
    if closed and len(path) > 2:
        segments.append((path[-1], path[0]))
    body = None
    for a, b in segments:
        piece = _capsule(a, b, radius, z, depth)
        body = piece if body is None else body.fuse(piece)
    # A closed path only bounds its interior; the middle is still uncut.
    if closed and len(path) > 2:
        try:
            face = Part.Face(Part.makePolygon([_vec(p, z) for p in path] + [_vec(path[0], z)]))
            body = body.fuse(face.extrude(FreeCAD.Vector(0, 0, depth)))
        except Exception:  # noqa: BLE001 - a self-crossing path has no interior to fill
            pass
    return body.removeSplitter()


def check_cutter(target: Any, tool: Any, within: Any = None,
                 avoid: dict[str, Any] | None = None) -> dict[str, Any]:
    """What a cutting solid would take, before it takes it.

    A cutter placed by hand is placed from remembered numbers, and a block one
    tenth too tall or half a millimetre too far along reads as a clean boolean:
    valid, one solid, no warning. The damage is a sliver somewhere else on the
    part, found later by an audit that cannot say which edit made it.

    ``within`` is the region the cut is allowed to touch -- usually the feature
    being trimmed, as a box. Anything the tool removes outside it is reported as
    ``strays``, with the volume and where it sits, so the block can be corrected
    rather than the result repaired.

    ``avoid`` maps a name to a shape the cut must not reach at all.
    """
    if not tool.Solids:
        raise ValueError("tool has no solid to cut with")
    removed = target.common(tool)
    out: dict[str, Any] = {
        "removes": round(removed.Volume, 4),
        "touches_target": bool(removed.Solids),
        "strays": [],
        "hits": [],
    }
    if not removed.Solids:
        # A tool that misses entirely is the likelier mistake, and silently
        # cutting nothing looks identical to a cut that worked.
        out["warning"] = "tool does not intersect the target"
        return out

    bb = removed.BoundBox
    out["removed_bbox"] = [round(v, 4) for v in
                           (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)]

    if within is not None:
        stray = removed.cut(within)
        if stray.Solids and stray.Volume > 1e-9:
            for s in stray.Solids:
                sb = s.BoundBox
                out["strays"].append({
                    "volume": round(s.Volume, 4),
                    "at": [round(sb.Center.x, 3), round(sb.Center.y, 3),
                           round(sb.Center.z, 3)],
                    "bbox": [round(v, 4) for v in
                             (sb.XMin, sb.YMin, sb.ZMin, sb.XMax, sb.YMax, sb.ZMax)],
                })
    for name, shape in (avoid or {}).items():
        clash = tool.common(shape)
        if clash.Solids and clash.Volume > 1e-9:
            out["hits"].append({"name": name, "volume": round(clash.Volume, 4)})

    out["clean"] = not out["strays"] and not out["hits"]
    return out


def pocket(doc_name: str, obj_name: str, corners: list[Any], depth: float,
           tool_radius: float, z_top: float, through: bool = False) -> dict[str, Any]:
    """Cut a rectangular pocket, with the inside corners the cutter leaves.

    ``corners`` is the finished opening as [[x0, y0], [x1, y1]]; the cutter's
    centre stays ``tool_radius`` inside it, so the corners come out as arcs of
    that radius. A pocket whose sides are shorter than the cutter's diameter
    cannot be cut at all and is refused rather than approximated.
    """
    doc = FreeCAD.getDocument(doc_name)
    obj = doc.getObject(obj_name) if doc else None
    if obj is None:
        raise ValueError(f"no object {obj_name!r} in {doc_name!r}")
    (x0, y0), (x1, y1) = corners
    x0, x1 = sorted((float(x0), float(x1)))
    y0, y1 = sorted((float(y0), float(y1)))
    r = float(tool_radius)
    if x1 - x0 < 2 * r or y1 - y0 < 2 * r:
        raise ValueError(
            f"a Ø{2 * r:g} cutter does not fit a {x1 - x0:g}x{y1 - y0:g} pocket"
        )
    z_bottom = float(z_top) - float(depth)
    cut_depth = float(depth) + (1.0 if through else 0.0)
    centres = [(x0 + r, y0 + r), (x1 - r, y0 + r), (x1 - r, y1 - r), (x0 + r, y1 - r)]
    tool = cutter_volume(centres, r, z_bottom - (1.0 if through else 0.0),
                         cut_depth, closed=True)
    result = obj.Shape.cut(tool).removeSplitter()
    return {
        "shape": result,
        "opening": [x0, y0, x1, y1],
        "corner_radius": r,
        "z": [z_bottom, float(z_top)],
        "volume_removed": round(obj.Shape.Volume - result.Volume, 4),
    }


def slot(doc_name: str, obj_name: str, path: list[Any], width: float,
         depth: float, z_top: float) -> dict[str, Any]:
    """Cut a slot of ``width`` along ``path``, with rounded ends.

    The ends are round because the cutter is: a slot milled with a Ø``width``
    tool cannot have square ends without a second operation.
    """
    doc = FreeCAD.getDocument(doc_name)
    obj = doc.getObject(obj_name) if doc else None
    if obj is None:
        raise ValueError(f"no object {obj_name!r} in {doc_name!r}")
    r = float(width) / 2
    z_bottom = float(z_top) - float(depth)
    tool = cutter_volume(path, r, z_bottom, float(depth))
    result = obj.Shape.cut(tool).removeSplitter()
    return {
        "shape": result,
        "width": float(width),
        "end_radius": r,
        "z": [z_bottom, float(z_top)],
        "volume_removed": round(obj.Shape.Volume - result.Volume, 4),
    }
