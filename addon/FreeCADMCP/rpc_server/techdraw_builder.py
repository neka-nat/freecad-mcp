"""Build TechDraw pages, views and dimensions from plain JSON.

TechDraw was blocked by the same two walls that C2 and C3 removed elsewhere:

  * ``page.addView(view)`` is a METHOD, so a page could not be assembled through
    the property interface -- the PartDesign Body problem again.
  * ``dimension.References2D`` wants ``[(DocumentObject, "Vertex3")]``. Live
    objects cannot cross XML-RPC, so a dimension could not be described at all
    -- the sketch-geometry problem again.

The interesting part is how a dimension names what it measures. Vertex indices
exist but are an accident of projection order, and nothing outside FreeCAD can
predict them. What the caller *does* know is the model: it placed the corner at
(0, 40) and the hole at (12, 10). So dimensions may be given as **coordinates**
and are snapped to the nearest projected vertex or circle. Raw indices still
work when they are known.

Coordinates are in the view's own 2D frame, which is centred on the part: a
60 x 40 part spans -30..30 by -20..20. ``create_drawing_page`` returns every
projected vertex and circle so the caller can dimension without guessing.
"""

import math
import os

import FreeCAD


# Standard view directions. XDirection is pinned too, otherwise FreeCAD picks
# one and the drawing comes out rotated in a way the caller did not ask for.
_DIRECTIONS = {
    "Top":       ((0, 0, 1),   (1, 0, 0)),
    "Bottom":    ((0, 0, -1),  (1, 0, 0)),
    "Front":     ((0, -1, 0),  (1, 0, 0)),
    "Rear":      ((0, 1, 0),   (-1, 0, 0)),
    "Left":      ((-1, 0, 0),  (0, -1, 0)),
    "Right":     ((1, 0, 0),   (0, 1, 0)),
    "Isometric": ((1, -1, 1),  (1, 1, 0)),
}

_DIM_TYPES = {
    "DistanceX", "DistanceY", "Distance", "Diameter", "Radius", "Angle", "Angle3Pt",
}
_TWO_POINT_DIMS = {"DistanceX", "DistanceY", "Distance"}
_CIRCLE_DIMS = {"Diameter", "Radius"}


def _template_dir():
    return os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw", "Templates")


def find_template(name=None):
    """Resolve a template to an absolute path.

    Searches the Templates directory and its immediate subdirectories only.
    A recursive walk of the whole resource tree takes long enough to blow the
    90 s GUI-thread budget -- measured, it did exactly that.
    """
    root = _template_dir()
    if name and os.path.isabs(name) and os.path.isfile(name):
        return name

    candidates = []
    if os.path.isdir(root):
        for entry in sorted(os.listdir(root)):
            full = os.path.join(root, entry)
            if entry.lower().endswith(".svg"):
                candidates.append(full)
            elif os.path.isdir(full):
                for sub in sorted(os.listdir(full)):
                    if sub.lower().endswith(".svg"):
                        candidates.append(os.path.join(full, sub))
    if not candidates:
        raise ValueError(f"No TechDraw templates found under {root}.")

    if name:
        wanted = name.lower()
        exact = [c for c in candidates if os.path.basename(c).lower() == wanted]
        partial = [c for c in candidates if wanted in os.path.basename(c).lower()]
        found = exact or partial
        if not found:
            names = sorted({os.path.basename(c) for c in candidates})
            raise ValueError(
                f"No template matching '{name}'. Available include: "
                + ", ".join(names[:12]) + (" ..." if len(names) > 12 else "")
            )
        return found[0]

    for preferred in ("A4_Landscape_TD.svg", "A4_LandscapeTD.svg",
                      "Default_Template_A4_Landscape.svg"):
        for candidate in candidates:
            if os.path.basename(candidate) == preferred:
                return candidate
    return candidates[0]


def _vec(triple):
    return FreeCAD.Vector(*[float(v) for v in triple])


def view_geometry(view):
    """Projected vertices and circles, in the view's own 2D frame."""
    vertices, circles = [], []
    for i in range(500):
        try:
            point = view.getVertexByIndex(i).Point
        except Exception:
            break
        vertices.append({"index": i, "x": round(point.x, 3), "y": round(point.y, 3)})
    for i in range(500):
        try:
            edge = view.getEdgeByIndex(i)
        except Exception:
            break
        curve = getattr(edge, "Curve", None)
        if curve is not None and curve.__class__.__name__ == "Circle":
            circles.append({"edge": i, "radius": round(curve.Radius, 3),
                            "x": round(curve.Center.x, 3), "y": round(curve.Center.y, 3)})
    return vertices, circles


def wait_for_geometry(doc, view, attempts=25):
    """Recompute and pump the event loop until the view has projected geometry.

    TechDraw builds a view's geometry asynchronously: the object is valid and
    Up-to-date immediately, but ``getVertexByIndex`` returns nothing until the
    Qt event loop has turned. An RPC handler runs as one uninterrupted GUI task,
    so without pumping here the loop never turns and the view looks empty --
    measured, a view reporting 0 vertices inside the call had 111 a moment later.

    Bounded at roughly two seconds, far inside the 90 s GUI-thread budget.
    """
    from rpc_server.gui_dispatch import _flush_gui_events

    vertices, circles = view_geometry(view)
    if vertices:
        return vertices, circles

    # Kick the build ONCE. Touching on every pass restarts it, so a complex view
    # never finishes -- measured: a simple view resolved while an L-bracket with
    # three threaded holes stayed empty for as long as the loop kept touching it.
    view.touch()
    doc.recompute()
    for _ in range(attempts):
        _flush_gui_events(delay_ms=40)
        vertices, circles = view_geometry(view)
        if vertices:
            return vertices, circles
    return vertices, circles


def _nearest_vertex(vertices, x, y, where):
    if not vertices:
        raise ValueError(f"{where}: the view has no projected vertices to snap to.")
    best = min(vertices, key=lambda v: (v["x"] - x) ** 2 + (v["y"] - y) ** 2)
    distance = math.hypot(best["x"] - x, best["y"] - y)
    if distance > 5.0:
        raise ValueError(
            f"{where}: nearest vertex to ({x}, {y}) is ({best['x']}, {best['y']}), "
            f"{distance:.1f} away. View coordinates are centred on the part, so a "
            "60x40 part spans -30..30 by -20..20 -- not 0..60 by 0..40."
        )
    return best["index"]


def _nearest_circle(circles, x, y, where):
    if not circles:
        raise ValueError(f"{where}: the view has no circular edges.")
    best = min(circles, key=lambda c: (c["x"] - x) ** 2 + (c["y"] - y) ** 2)
    return best["edge"]


def create_drawing_page_gui(doc_name, page_name, source_objects=None, views=None,
                            template=None):
    """Create a page with views of the given objects.

    Returns each view's projected vertices and circles, so the caller can place
    dimensions immediately instead of making a second round trip to discover
    what the projection produced.
    """
    try:
        doc = FreeCAD.getDocument(doc_name)
    except Exception:
        raise ValueError(f"Document '{doc_name}' not found.")

    if not source_objects:
        source_objects = [o.Name for o in doc.Objects
                          if o.isDerivedFrom("Part::Feature") and o.Visibility]
        if not source_objects:
            raise ValueError(
                f"Document '{doc_name}' has no visible solid to draw. "
                "Pass source_objects explicitly."
            )
    sources = []
    for name in source_objects:
        obj = doc.getObject(name)
        if obj is None:
            raise ValueError(f"Object '{name}' not found in document '{doc_name}'.")
        sources.append(obj)

    template_path = find_template(template)

    page = doc.addObject("TechDraw::DrawPage", page_name)
    template_obj = doc.addObject("TechDraw::DrawSVGTemplate", f"{page_name}Template")
    template_obj.Template = template_path
    page.Template = template_obj

    if not views:
        views = [{"name": "View", "direction": "Front"}]

    created = []
    try:
        for index, spec in enumerate(views):
            where = f"views[{index}]"
            direction = str(spec.get("direction", "Front"))
            if direction not in _DIRECTIONS:
                raise ValueError(
                    f"{where}: unknown direction '{direction}'. Use one of: "
                    + ", ".join(_DIRECTIONS)
                )
            view = doc.addObject("TechDraw::DrawViewPart",
                                 str(spec.get("name") or f"View{index}"))
            # addView is a method -- the reason a page could not be built through
            # the property interface at all.
            page.addView(view)
            view.Source = sources
            forward, side = _DIRECTIONS[direction]
            view.Direction = _vec(forward)
            view.XDirection = _vec(side)
            view.Scale = float(spec.get("scale", 1.0))
            if "x" in spec:
                view.X = float(spec["x"])
            if "y" in spec:
                view.Y = float(spec["y"])
            created.append((view, direction))
        doc.recompute()
    except Exception:
        for view, _ in created:
            doc.removeObject(view.Name)
        doc.removeObject(template_obj.Name)
        doc.removeObject(page.Name)
        doc.recompute()
        raise

    result_views = []
    for view, direction in created:
        vertices, circles = wait_for_geometry(doc, view)
        result_views.append({
            "name": view.Name, "direction": direction,
            "scale": view.Scale, "valid": view.isValid(),
            "geometry_ready": bool(vertices),
            "vertices": vertices, "circles": circles,
        })

    pending = [v["name"] for v in result_views if not v["geometry_ready"]]
    result = {
        "success": True,
        "page_name": page.Name,
        "template": os.path.basename(template_path),
        "views": result_views,
        "hint": ("View coordinates are centred on the part: a 60x40 part spans "
                 "-30..30 by -20..20. Use them with add_dimensions -- 'between' "
                 "for linear, 'circle_at' for diameter/radius."),
    }
    if pending:
        # Do not let an empty list read as "this view has no geometry".
        result["note"] = (
            "Still projecting: " + ", ".join(pending) + ". TechDraw builds view "
            "geometry on the Qt event loop, which cannot turn inside this call, "
            "so a complex view reports nothing yet. This does NOT mean the view "
            "is empty. Call add_dimensions as normal -- it runs later, waits for "
            "the geometry, and snaps to the coordinates you give it."
        )
    return result


def add_dimensions_gui(doc_name, page_name, dimensions):
    """Add dimensions to views on a page. Returns one entry per dimension."""
    try:
        doc = FreeCAD.getDocument(doc_name)
    except Exception:
        raise ValueError(f"Document '{doc_name}' not found.")
    page = doc.getObject(page_name)
    if page is None:
        raise ValueError(f"Page '{page_name}' not found in document '{doc_name}'.")

    made, cache = [], {}
    try:
        for index, spec in enumerate(dimensions or []):
            where = f"dimensions[{index}]"
            kind = spec.get("type", "DistanceX")
            if kind not in _DIM_TYPES:
                raise ValueError(
                    f"{where}: unknown dimension type '{kind}'. Use one of: "
                    + ", ".join(sorted(_DIM_TYPES))
                )
            view_name = spec.get("view")
            view = doc.getObject(view_name) if view_name else None
            if view is None:
                raise ValueError(f"{where}: view '{view_name}' not found.")
            if view_name not in cache:
                cache[view_name] = wait_for_geometry(doc, view)
            vertices, circles = cache[view_name]

            if kind in _CIRCLE_DIMS:
                if "edge" in spec:
                    edge = int(spec["edge"])
                elif "circle_at" in spec:
                    point = spec["circle_at"]
                    edge = _nearest_circle(circles, float(point[0]), float(point[1]), where)
                else:
                    raise ValueError(f"{where}: {kind} needs 'circle_at': [x, y] or 'edge': N.")
                references = [(view, f"Edge{edge}")]
            else:
                if "vertices" in spec:
                    pair = [int(v) for v in spec["vertices"]]
                elif "between" in spec:
                    points = spec["between"]
                    if len(points) != 2:
                        raise ValueError(f"{where}: 'between' needs exactly two [x, y] points.")
                    pair = [_nearest_vertex(vertices, float(p[0]), float(p[1]), where)
                            for p in points]
                else:
                    raise ValueError(
                        f"{where}: {kind} needs 'between': [[x,y],[x,y]] or 'vertices': [a,b]."
                    )
                if pair[0] == pair[1]:
                    raise ValueError(
                        f"{where}: both points snapped to vertex {pair[0]} -- they are the "
                        "same corner. Check the coordinates."
                    )
                references = [(view, f"Vertex{pair[0]}"), (view, f"Vertex{pair[1]}")]

            dim = doc.addObject("TechDraw::DrawViewDimension",
                                str(spec.get("name") or f"Dim{index}"))
            page.addView(dim)
            dim.Type = kind
            # References2D wants live objects in tuples, which is precisely what
            # cannot cross the wire -- rebuilt here from names and indices.
            dim.References2D = references
            if "x" in spec:
                dim.X = float(spec["x"])
            if "y" in spec:
                dim.Y = float(spec["y"])
            if spec.get("text"):
                dim.Arbitrary = True
                dim.FormatSpec = str(spec["text"])
            made.append(dim)
        doc.recompute()
    except Exception:
        for dim in made:
            doc.removeObject(dim.Name)
        doc.recompute()
        raise

    return {
        "success": True,
        "page_name": page.Name,
        "dimensions": [{"name": d.Name, "type": d.Type, "valid": d.isValid()} for d in made],
    }
