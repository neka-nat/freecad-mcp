"""Measure material along a ray, so an edit can be checked instead of assumed.

A boolean that stays valid, stays a single solid and barely moves the volume can
still be wrong: a fill box 0.5 mm wider than the wall it repairs thickens that
wall, and nothing in ``shape_check`` notices because the bounding box does not
move. The only way to see it is to measure across the feature.

``probe`` reports the solid spans a line crosses. ``compare`` runs the same
probes before and after an edit and reports the spans that changed, which is the
check that distinguishes "cut the slot" from "cut the rib next to it".
"""

from typing import Any

import FreeCAD


def _shape_of(doc_name: str, obj_name: str) -> Any:
    doc = FreeCAD.getDocument(doc_name)
    obj = doc.getObject(obj_name)
    if obj is None:
        raise ValueError(f"no object {obj_name!r} in {doc_name!r}")
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        raise ValueError(f"{obj_name!r} has no shape")
    return shape


def _spans(shape: Any, start: Any, end: Any, axis: int) -> list[list[float]]:
    """Solid intervals where the segment start->end passes through material."""
    import Part  # imported late: the module must load where only FreeCAD is stubbed

    line = Part.makeLine(start, end)
    common = line.common(shape)
    out = []
    for edge in common.Edges:
        coords = [v.Point[axis] for v in edge.Vertexes]
        if len(coords) < 2:
            continue
        out.append([round(min(coords), 4), round(max(coords), 4)])
    return sorted(out)


def probe(
    doc_name: str,
    obj_name: str,
    start: list[float],
    end: list[float],
) -> dict[str, Any]:
    """Report where a ray enters and leaves material.

    ``start``/``end`` are ``[x, y, z]``. Spans are given along whichever axis
    the ray travels, together with the gaps between them: for a vented wall the
    spans are the ribs and the gaps are the slots.

    Spans, gaps and ``material`` are measured along that single dominant axis,
    so an axis-aligned ray reports true distances and a diagonal one reports the
    projection onto its dominant axis. Probe along X, Y or Z to read a thickness
    off the result directly.
    """
    shape = _shape_of(doc_name, obj_name)
    p0, p1 = FreeCAD.Vector(*start), FreeCAD.Vector(*end)
    delta = [abs(p1[i] - p0[i]) for i in range(3)]
    axis = delta.index(max(delta))
    spans = _spans(shape, p0, p1, axis)
    gaps = [
        [spans[i][1], spans[i + 1][0], round(spans[i + 1][0] - spans[i][1], 4)]
        for i in range(len(spans) - 1)
        if spans[i + 1][0] - spans[i][1] > 1e-9
    ]
    return {
        "axis": "xyz"[axis],
        "spans": spans,
        "gaps": gaps,
        "material": round(sum(s[1] - s[0] for s in spans), 4),
    }


def compare(
    doc_name: str,
    obj_name: str,
    rays: list[dict[str, list[float]]],
    before: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Probe several rays at once; with ``before``, report what each one lost or gained.

    Pass the ``probes`` list returned by an earlier call as ``before`` to get a
    per-ray verdict. ``grew`` is the flag that matters after a repair edit: a
    fill that added material where the ray previously passed through open space
    is the signature of an oversized fill box.
    """
    probes = [probe(doc_name, obj_name, r["start"], r["end"]) for r in rays]
    if before is None:
        return {"probes": probes}
    verdicts = []
    for i, now in enumerate(probes):
        was = before[i] if i < len(before) else None
        if was is None:
            verdicts.append({"ray": i, "note": "no baseline"})
            continue
        if was.get("axis") != now["axis"]:
            # Baselines are matched to rays by position. A different axis proves
            # the lists do not line up, and a delta between unrelated rays would
            # read as a confident verdict.
            verdicts.append({"ray": i, "note": "baseline is a different ray"})
            continue
        delta = round(now["material"] - was.get("material", 0.0), 4)
        verdicts.append(
            {
                "ray": i,
                "material_was": was.get("material"),
                "material_now": now["material"],
                "delta": delta,
                "grew": delta > 1e-6,
                "spans_changed": now["spans"] != was.get("spans"),
            }
        )
    return {"probes": probes, "verdicts": verdicts}
