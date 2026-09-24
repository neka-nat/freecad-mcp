"""Build one half of a joint so it keeps its clearance from the other.

Adding material that has to stand a set distance from a neighbour is done by
hand as ``slab.cut(neighbour)``, which is wrong in a way that survives every
check: the cut stops exactly at the neighbour's surface, so the two touch. Where
the neighbour's shape varies -- a wall that thickens towards a corner -- the
error appears only there, and only in the render.

``keep_out`` is the neighbour grown by the clearance: cutting against that
leaves the gap instead of closing it. ``mating_addition`` is the whole job in
one call, and reports what it built so the caller can see the clearance held
before committing to it.

Both work on a region rather than a whole body. A housing half is nine hundred
faces of geometry the joint never touches, and offsetting all of it either fails
outright or takes long enough to stall the GUI thread.
"""

from typing import Any

_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def _vec(x: float, y: float, z: float) -> Any:
    import FreeCAD

    return FreeCAD.Vector(x, y, z)


def _direction(towards: str) -> tuple[float, float, float]:
    """Unit vector from a name like ``-x``."""
    sign = -1.0 if towards.startswith("-") else 1.0
    axis = towards.lstrip("+-")
    if axis not in _AXES:
        raise ValueError(f"towards must be ±x, ±y or ±z, not {towards!r}")
    return tuple(sign * c for c in _AXES[axis])


def keep_out(neighbour: Any, clearance: float, towards: str,
             region: Any = None, steps: int = 5) -> Any:
    """The neighbour grown by ``clearance`` in one direction.

    Cut a candidate against this and it stands ``clearance`` off the neighbour
    wherever the neighbour reaches, including the places its surface moves.

    Grown by sweeping rather than by ``makeOffsetShape``, which on a part of any
    size either refuses outright or runs for minutes. ``steps`` is how finely
    the sweep is sampled: the shape is copied that many times along the
    direction, so a step coarser than the features it must cover will miss the
    gap between them.
    """
    if clearance < 0:
        raise ValueError("clearance cannot be negative")
    if steps < 1:
        raise ValueError("steps must be at least 1")
    dx, dy, dz = _direction(towards)

    local = neighbour.common(region) if region is not None else neighbour
    if not local.Faces:
        # Nothing of the neighbour here, so nothing to keep out of. Returning
        # an empty shape lets the caller cut against it harmlessly; refusing
        # would make "the neighbour is not in the way" an error.
        return local
    if clearance == 0:
        return local

    grown = local
    for k in range(1, steps + 1):
        d = clearance * k / steps
        grown = grown.fuse(local.translated(_vec(dx * d, dy * d, dz * d)))
    return grown.removeSplitter()


def mating_addition(target: Any, blank: Any, neighbour: Any, clearance: float,
                    towards: str, avoid: list[Any] | None = None,
                    steps: int = 5) -> dict[str, Any]:
    """Material to add to ``target`` that stands clear of ``neighbour``.

    ``blank`` is the region to fill -- the volume the addition would occupy if
    nothing were in the way. What comes back is that blank with the neighbour's
    keep-out and anything in ``avoid`` removed, fused onto the target.

    The reply carries the numbers that decide whether this was right: how much
    material it adds, how much of it overlaps the target it must weld to, and
    whether it ends up in one piece. An addition that overlaps nothing is one
    that will hang in the render.
    """
    # The zone is worked out in a region wider than the blank: clipping the
    # neighbour to the blank first throws away the very material whose growth
    # was supposed to push the addition back, and the two end up touching.
    margin = clearance + 1.0
    bb = blank.BoundBox
    import Part

    around = Part.makeBox(
        bb.XLength + 2 * margin, bb.YLength + 2 * margin, bb.ZLength + 2 * margin,
        _vec(bb.XMin - margin, bb.YMin - margin, bb.ZMin - margin),
    )
    zone = keep_out(neighbour, clearance, towards, around, steps)
    addition = blank.cut(zone) if zone.Faces else blank
    for other in (avoid or []):
        addition = addition.cut(other)

    overlap = addition.common(target).Volume if addition.Faces else 0.0
    result = target.fuse(addition).removeSplitter() if addition.Faces else target
    return {
        "shape": result,
        "addition": addition,
        "added_volume": round(addition.Volume, 4),
        "overlap_with_target": round(overlap, 4),
        "addition_pieces": len(addition.Solids),
        "result_solids": len(result.Solids),
        "result_valid": bool(result.isValid()),
        "clash_with_neighbour": round(result.common(neighbour).Volume, 6),
    }
