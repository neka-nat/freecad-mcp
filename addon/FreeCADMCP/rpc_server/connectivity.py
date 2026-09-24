"""Find the parts of a solid that are only just attached, or not attached at all.

``Shape.Solids`` counts pieces that share no material, which is a weaker
question than "is this one part". A block fused onto a body it barely reaches
comes back as one solid and one shell, valid by every check the audit makes,
while in the render it hangs in mid-air joined by a sliver.

``islands`` walks the faces instead, treating two as connected when they share
an edge, and reports each group it finds. A piece attached across a handful of
faces is a piece the edit did not really weld on, and the reply says which faces
those are so the next attempt can reach further.
"""

from typing import Any


def _face_groups(shape: Any) -> list[list[int]]:
    """Face indices grouped by what shares an edge with what."""
    by_edge: dict[int, list[int]] = {}
    for i, face in enumerate(shape.Faces):
        for edge in face.Edges:
            by_edge.setdefault(edge.hashCode(), []).append(i)

    parent = list(range(len(shape.Faces)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for faces in by_edge.values():
        first = faces[0]
        for other in faces[1:]:
            a, b = find(first), find(other)
            if a != b:
                parent[a] = b

    groups: dict[int, list[int]] = {}
    for i in range(len(shape.Faces)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _describe(shape: Any, indices: list[int]) -> dict[str, Any]:
    faces = [shape.Faces[i] for i in indices]
    area = sum(f.Area for f in faces)
    xs, ys, zs = [], [], []
    for f in faces:
        bb = f.BoundBox
        xs += [bb.XMin, bb.XMax]
        ys += [bb.YMin, bb.YMax]
        zs += [bb.ZMin, bb.ZMax]
    return {
        "faces": len(indices),
        "area": round(area, 4),
        "bbox": [round(min(xs), 4), round(max(xs), 4),
                 round(min(ys), 4), round(max(ys), 4),
                 round(min(zs), 4), round(max(zs), 4)],
        "face_indices": sorted(indices)[:12],
    }


def count_islands(shape: Any) -> int:
    """How many separate pieces a part is in, without describing them.

    What an audit needs on every checkpoint. ``islands`` measures each group's
    area and bounding box, which on a nine-hundred-face housing is most of the
    cost and none of the answer.
    """
    total = 0
    for solid in shape.Solids:
        total += len(_face_groups(solid))
    return total or len(_face_groups(shape))


def islands(shape: Any) -> dict[str, Any]:
    """The separate pieces a part is actually made of.

    One piece is a part in one piece. More than one means something is only
    touching, and the smallest is usually what an edit just added.

    Counted per solid first: two blocks meeting at an edge share that edge, so
    walking faces alone joins them into one group while OCCT rightly calls them
    two. Faces are then walked within each solid, which is what catches a shell
    hanging off a body OCCT still counts as single.
    """
    pieces = []
    for solid in shape.Solids:
        for group in _face_groups(solid):
            pieces.append(_describe(solid, group))
    if not pieces:                      # a shell or a sheet, with no solid
        pieces = [_describe(shape, g) for g in _face_groups(shape)]
    pieces.sort(key=lambda d: -d["area"])
    return {
        "islands": len(pieces),
        "solids": len(shape.Solids),
        "groups": pieces,
    }


def gaps(shape: Any, ray_axis: str, step_axis: str, step_from: float,
         step_to: float, step: float, at: float,
         max_gap: float = 1.0) -> dict[str, Any]:
    """Thin slots of air inside a part, where an edit failed to reach.

    A block fused a fraction short of what it was meant to meet leaves a
    parallel gap rather than a join: two spans where there should be one. The
    body stays one solid and one island, every audit passes, and the fault is
    visible only in the render as a piece hanging free.

    Sweeps like ``measure_sweep`` and reports the gaps narrower than
    ``max_gap`` -- wide ones are cavities the part is meant to have.
    """
    import Part

    import FreeCAD

    axes = {"x": 0, "y": 1, "z": 2}
    if ray_axis == step_axis:
        raise ValueError("ray_axis and step_axis must differ")
    for name, value in (("ray_axis", ray_axis), ("step_axis", step_axis)):
        if value not in axes:
            raise ValueError(f"{name} must be x, y or z, not {value!r}")
    if step <= 0:
        raise ValueError("step must be positive")

    ray_i, step_i = axes[ray_axis], axes[step_axis]
    third_i = 3 - ray_i - step_i
    bb = shape.BoundBox
    lo = [bb.XMin, bb.YMin, bb.ZMin][ray_i] - 1.0
    hi = [bb.XMax, bb.YMax, bb.ZMax][ray_i] + 1.0

    found = []
    n = int(round((step_to - step_from) / step))
    for k in range(n + 1):
        pos = round(step_from + k * step, 6)
        p0, p1 = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        p0[ray_i], p1[ray_i] = lo, hi
        p0[step_i] = p1[step_i] = pos
        p0[third_i] = p1[third_i] = at
        line = Part.makeLine(FreeCAD.Vector(*p0), FreeCAD.Vector(*p1))
        spans = []
        for edge in line.common(shape).Edges:
            coords = [v.Point[ray_i] for v in edge.Vertexes]
            if len(coords) >= 2:
                spans.append((min(coords), max(coords)))
        spans.sort()
        for a, b in zip(spans, spans[1:]):
            width = b[0] - a[1]
            if 1e-9 < width <= max_gap:
                found.append({
                    step_axis: pos,
                    "gap": round(width, 4),
                    "between": [round(a[1], 4), round(b[0], 4)],
                })
    return {
        "ray_axis": ray_axis,
        "step_axis": step_axis,
        "at_axis": "xyz"[third_i],
        "at": at,
        "max_gap": max_gap,
        "gaps": found,
    }


def compare_section(a: Any, b: Any, axis: str, value: float,
                    ray_axis: str, step_from: float, step_to: float,
                    step: float) -> dict[str, Any]:
    """Where two parts' cross-sections agree and where they part company.

    For a lid and the housing it closes onto: both are probed on the same plane
    and the spans set side by side, so a tongue that stops short of its wall
    shows as a gap between the two rather than as a pair of numbers to line up
    by eye. That is the comparison a mating edit needs and the one that has to
    be done by reading two separate section dumps.
    """
    import Part

    import FreeCAD

    axes = {"x": 0, "y": 1, "z": 2}
    for name, value_ in (("axis", axis), ("ray_axis", ray_axis)):
        if value_ not in axes:
            raise ValueError(f"{name} must be x, y or z, not {value_!r}")
    if axis == ray_axis:
        raise ValueError("axis and ray_axis must differ")
    if step <= 0:
        raise ValueError("step must be positive")

    ray_i, plane_i = axes[ray_axis], axes[axis]
    step_i = 3 - ray_i - plane_i

    def spans_at(shape: Any, pos: float) -> list[list[float]]:
        bb = shape.BoundBox
        lo = [bb.XMin, bb.YMin, bb.ZMin][ray_i] - 1.0
        hi = [bb.XMax, bb.YMax, bb.ZMax][ray_i] + 1.0
        p0, p1 = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        p0[ray_i], p1[ray_i] = lo, hi
        p0[plane_i] = p1[plane_i] = value
        p0[step_i] = p1[step_i] = pos
        line = Part.makeLine(FreeCAD.Vector(*p0), FreeCAD.Vector(*p1))
        out = []
        for edge in line.common(shape).Edges:
            coords = [v.Point[ray_i] for v in edge.Vertexes]
            if len(coords) >= 2:
                out.append([round(min(coords), 4), round(max(coords), 4)])
        return sorted(out)

    rows = []
    n = int(round((step_to - step_from) / step))
    for k in range(n + 1):
        pos = round(step_from + k * step, 6)
        sa, sb = spans_at(a, pos), spans_at(b, pos)
        row = {"xyz"[step_i]: pos, "a": sa, "b": sb}
        # The clearance between them: the nearest approach of any span of one
        # to any span of the other, which is the number a mating fit turns on.
        best = None
        for x0, x1 in sa:
            for y0, y1 in sb:
                if x1 < y0:
                    d = y0 - x1
                elif y1 < x0:
                    d = x0 - y1
                else:
                    d = 0.0
                best = d if best is None else min(best, d)
        if best is not None:
            row["clearance"] = round(best, 4)
        rows.append(row)
    clearances = [r["clearance"] for r in rows if "clearance" in r]
    return {
        "plane": f"{axis}={value}",
        "ray_axis": ray_axis,
        "rows": rows,
        "clearance_min": round(min(clearances), 4) if clearances else None,
        "clearance_max": round(max(clearances), 4) if clearances else None,
    }


def clearance(a: Any, b: Any, along: str, step: float = 1.0,
              expect: float | None = None, tolerance: float = 0.01,
              ) -> dict[str, Any]:
    """The gap between two shapes, measured the whole way along one axis.

    A clearance holds at the station it was checked at and nowhere else unless
    someone looks: a tongue can sit right against its wall at one end and half a
    millimetre clear at the other, and a single section says the fit is fine.
    This walks the overlap of the two shapes and reports the gap at every stop.

    Made to run on a candidate before it is fused: build the piece, ask what
    clearance it would have, and only then commit. With ``expect`` set, the
    stops that disagree come back named, which is the answer to "does this hold
    all the way along" rather than "what is it here".
    """
    if step <= 0:
        raise ValueError("step must be positive")
    axes = {"x": 0, "y": 1, "z": 2}
    if along not in axes:
        raise ValueError(f"along must be x, y or z, not {along!r}")
    i = axes[along]

    ba, bb = a.BoundBox, b.BoundBox
    lo = max([ba.XMin, ba.YMin, ba.ZMin][i], [bb.XMin, bb.YMin, bb.ZMin][i])
    hi = min([ba.XMax, ba.YMax, ba.ZMax][i], [bb.XMax, bb.YMax, bb.ZMax][i])
    if hi <= lo:
        return {"along": along, "overlap": None,
                "note": "the two shapes do not overlap along this axis"}

    stops = []
    n = max(1, int(round((hi - lo) / step)))
    # Each stop cuts both shapes with a knife box and measures the pieces. On
    # two whole housing halves that is seconds apiece, and a run long enough to
    # wedge the GUI thread is worse than one that refuses and says why.
    if n > 60:
        raise ValueError(
            f"{n} stops over {round(hi - lo, 3)} mm would take minutes; "
            f"use a larger step, or measure the candidate piece against the "
            f"other part rather than two whole bodies"
        )
    for k in range(n + 1):
        # Inset from the ends: a slice exactly on a boundary face measures the
        # face itself and reports a distance of zero that means nothing.
        pos = lo + (hi - lo) * (k / n)
        pos = min(max(pos, lo + 1e-6), hi - 1e-6)
        try:
            d = _slice_distance(a, b, i, pos)
        except Exception:  # noqa: BLE001 - a slice that fails is not a verdict
            continue
        if d is not None:
            stops.append({along: round(pos, 4), "gap": round(d, 4)})

    gaps = [s["gap"] for s in stops]
    out: dict[str, Any] = {
        "along": along,
        "overlap": [round(lo, 4), round(hi, 4)],
        "stops": len(stops),
        "gap_min": round(min(gaps), 4) if gaps else None,
        "gap_max": round(max(gaps), 4) if gaps else None,
    }
    if expect is not None:
        off = [s for s in stops if abs(s["gap"] - expect) > tolerance]
        out["expect"] = expect
        out["holds"] = not off
        out["off_spec"] = off[:20]
        out["off_spec_count"] = len(off)
    return out


def _slice_distance(a: Any, b: Any, axis: int, pos: float) -> float | None:
    """Closest approach of two shapes within one thin slice."""
    import Part

    import FreeCAD

    span = []
    for shape in (a, b):
        bb = shape.BoundBox
        span.append((min(bb.XMin, bb.YMin, bb.ZMin), max(bb.XMax, bb.YMax, bb.ZMax)))
    reach = max(abs(span[0][0]), abs(span[0][1]), abs(span[1][0]), abs(span[1][1])) + 10

    sizes = [2 * reach, 2 * reach, 2 * reach]
    origin = [-reach, -reach, -reach]
    sizes[axis] = 1e-3
    origin[axis] = pos - 5e-4
    knife = Part.makeBox(*sizes, FreeCAD.Vector(*origin))

    sa, sb = a.common(knife), b.common(knife)
    if not sa.Faces or not sb.Faces:
        return None
    return sa.distToShape(sb)[0]


def weak_joins(shape: Any, min_area: float = 1.0) -> dict[str, Any]:
    """Faces whose whole attachment to the rest is smaller than ``min_area``.

    A block the fuse barely caught is joined across one or two small faces. The
    body stays a single solid, so nothing else notices, and the render shows it
    floating. Reported with where it is, which is what an edit needs to reach
    further rather than guess.
    """
    contact: dict[int, float] = {}
    by_edge: dict[int, list[int]] = {}
    for i, face in enumerate(shape.Faces):
        for edge in face.Edges:
            by_edge.setdefault(edge.hashCode(), []).append(i)

    # Shared edges are where faces meet; the area either side is what holds.
    neighbours: dict[int, set] = {}
    for faces in by_edge.values():
        for a in faces:
            for b in faces:
                if a != b:
                    neighbours.setdefault(a, set()).add(b)

    weak = []
    for i, face in enumerate(shape.Faces):
        touching = neighbours.get(i, set())
        if not touching:
            weak.append({"face": i, "reason": "no neighbours",
                         "area": round(face.Area, 4)})
            continue
        shared = sum(shape.Faces[j].Area for j in touching)
        contact[i] = shared
        if shared < min_area:
            bb = face.BoundBox
            weak.append({
                "face": i,
                "area": round(face.Area, 4),
                "neighbour_area": round(shared, 4),
                "at": [round((bb.XMin + bb.XMax) / 2, 3),
                       round((bb.YMin + bb.YMax) / 2, 3),
                       round((bb.ZMin + bb.ZMax) / 2, 3)],
            })
    return {"min_area": min_area, "weak": weak}
