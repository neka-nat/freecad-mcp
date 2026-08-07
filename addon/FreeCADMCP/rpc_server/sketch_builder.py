"""Build Sketcher geometry and constraints from plain JSON.

This is the piece that lets a sketch cross the wire. ``sketch.Geometry`` is a
settable property, but XML-RPC carries only primitives -- ``Part.LineSegment``
raises ``TypeError: cannot marshal`` -- so a sketch previously had to be built
with ``execute_code``. Here the geometry is described as JSON and rebuilt on
this side.

Coordinates are 2D: a sketch has its own plane and z is always 0.

PointPos encoding, measured on 1.1.1 with ``sketch.getPoint(geoId, pos)``:

    1 = start   (line start, arc start)
    2 = end     (line end, arc end)
    3 = centre  (circle centre, arc centre)
    geoId -1, pos 1 = the sketch origin

so constraints take readable names ("start", "end", "center", "origin")
instead of magic integers.
"""

import math

import FreeCAD
import Part
import Sketcher


_POINT_POS = {"none": 0, "start": 1, "end": 2, "center": 3, "centre": 3, "mid": 3}

# Constraint type -> the argument counts FreeCAD accepts after the type name,
# and a human description of each form. Every entry was verified by construction
# on 1.1.1; see the arity matrix in docs/version_history.md.
#
# This table is a SAFETY GATE, not documentation. Handing Sketcher.Constraint an
# unknown type or a wrong argument count is not reliably catchable: the same call
# raised TypeError in one script and terminated the FreeCAD process in another.
# Since a constraint spec comes from an LLM and will sometimes be wrong, validate
# here and never construct anything that has not been checked.
_CONSTRAINT_FORMS = {
    "Horizontal":    ({1}, "first (an edge)"),
    "Vertical":      ({1}, "first (an edge)"),
    "Block":         ({1}, "first (an edge)"),
    "Coincident":    ({4}, "first+first_pos, second+second_pos (two points)"),
    "PointOnObject": ({3}, "first+first_pos (a point), second (an edge)"),
    "Parallel":      ({2}, "first, second (two edges)"),
    "Perpendicular": ({2}, "first, second (two edges)"),
    "Equal":         ({2}, "first, second (two edges)"),
    "Tangent":       ({2}, "first, second (two edges)"),
    "Symmetric":     ({5}, "first+first_pos, second+second_pos, then a symmetry edge"),
    "Distance":      ({2, 3, 5}, "first+value, or first+second+value, or two points+value"),
    "DistanceX":     ({2, 5}, "first+value, or first+first_pos+second+second_pos+value"),
    "DistanceY":     ({2, 5}, "first+value, or first+first_pos+second+second_pos+value"),
    "Angle":         ({3}, "first, second, value (radians)"),
    "Radius":        ({2}, "first (a circle or arc), value"),
    "Diameter":      ({2}, "first (a circle or arc), value"),
    "Weight":        ({2}, "first, value"),
}


def _vec(pair, what):
    """[x, y] -> Vector. Sketch coordinates are 2D; z is always 0."""
    if not isinstance(pair, (list, tuple)) or len(pair) < 2:
        raise ValueError(f"{what} must be a two-number list like [10, 5], got {pair!r}")
    return FreeCAD.Vector(float(pair[0]), float(pair[1]), 0)


def _pos(name, where):
    if name is None:
        return 0
    if isinstance(name, int):
        return name
    key = str(name).lower()
    if key not in _POINT_POS:
        raise ValueError(
            f"{where}: unknown point '{name}'. Use one of: "
            + ", ".join(sorted(set(_POINT_POS)))
        )
    return _POINT_POS[key]


def _add_line(sketch, a, b, construction):
    return [sketch.addGeometry(Part.LineSegment(a, b), construction)]


def add_geometry(sketch, spec, index):
    """Add one geometry spec. Returns the list of geoIds it created."""
    if not isinstance(spec, dict):
        raise ValueError(f"geometry[{index}] must be an object, got {type(spec).__name__}")
    kind = str(spec.get("type", "")).lower()
    construction = bool(spec.get("construction", False))
    where = f"geometry[{index}] ({kind or 'no type'})"

    if kind == "line":
        return _add_line(sketch, _vec(spec["start"], f"{where}.start"),
                         _vec(spec["end"], f"{where}.end"), construction)

    if kind == "circle":
        centre = _vec(spec["center"], f"{where}.center")
        return [sketch.addGeometry(
            Part.Circle(centre, FreeCAD.Vector(0, 0, 1), float(spec["radius"])),
            construction)]

    if kind == "arc":
        centre = _vec(spec["center"], f"{where}.center")
        circle = Part.Circle(centre, FreeCAD.Vector(0, 0, 1), float(spec["radius"]))
        start = math.radians(float(spec.get("start_angle", 0)))
        end = math.radians(float(spec.get("end_angle", 90)))
        return [sketch.addGeometry(Part.ArcOfCircle(circle, start, end), construction)]

    if kind == "point":
        return [sketch.addGeometry(Part.Point(_vec(spec["at"], f"{where}.at")),
                                   construction)]

    if kind == "ellipse":
        centre = _vec(spec["center"], f"{where}.center")
        major = float(spec["major_radius"])
        minor = float(spec["minor_radius"])
        angle = math.radians(float(spec.get("angle", 0)))
        major_point = centre + FreeCAD.Vector(major * math.cos(angle),
                                              major * math.sin(angle), 0)
        minor_point = centre + FreeCAD.Vector(-minor * math.sin(angle),
                                              minor * math.cos(angle), 0)
        return [sketch.addGeometry(Part.Ellipse(major_point, minor_point, centre),
                                   construction)]

    if kind in ("polyline", "rectangle"):
        if kind == "rectangle":
            corner = _vec(spec["corner"], f"{where}.corner")
            w, h = float(spec["width"]), float(spec["height"])
            pts = [corner,
                   corner + FreeCAD.Vector(w, 0, 0),
                   corner + FreeCAD.Vector(w, h, 0),
                   corner + FreeCAD.Vector(0, h, 0)]
            closed = True
        else:
            raw = spec.get("points") or []
            if len(raw) < 2:
                raise ValueError(f"{where}: a polyline needs at least two points.")
            pts = [_vec(p, f"{where}.points[{i}]") for i, p in enumerate(raw)]
            closed = bool(spec.get("closed", False))

        ids = []
        for i in range(len(pts) - 1):
            ids += _add_line(sketch, pts[i], pts[i + 1], construction)
        if closed:
            ids += _add_line(sketch, pts[-1], pts[0], construction)
        # Stitch the run together: this is the fiddly, error-prone part of
        # building a profile by hand, and an unclosed wire is the single most
        # common reason a Pad silently produces nothing.
        for i in range(len(ids) - 1):
            sketch.addConstraint(Sketcher.Constraint("Coincident", ids[i], 2, ids[i + 1], 1))
        if closed and len(ids) > 1:
            sketch.addConstraint(Sketcher.Constraint("Coincident", ids[-1], 2, ids[0], 1))
        return ids

    raise ValueError(
        f"{where}: unknown geometry type '{spec.get('type')}'. Supported: "
        "line, circle, arc, point, ellipse, polyline, rectangle."
    )


def add_constraint(sketch, spec, index):
    """Add one constraint spec. Returns its index in sketch.Constraints."""
    if not isinstance(spec, dict):
        raise ValueError(f"constraints[{index}] must be an object, got {type(spec).__name__}")
    kind = spec.get("type")
    if not kind:
        raise ValueError(f"constraints[{index}] needs a 'type'.")
    where = f"constraints[{index}] ({kind})"

    first = spec.get("first")
    second = spec.get("second")
    value = spec.get("value")
    first_pos = _pos(spec.get("first_pos"), where)
    second_pos = _pos(spec.get("second_pos"), where)

    if first is None:
        raise ValueError(f"{where} needs 'first' (a geometry index, or -1 for the origin).")

    if kind not in _CONSTRAINT_FORMS:
        raise ValueError(
            f"{where}: unknown constraint type '{kind}'. Names are case-sensitive. "
            "Supported: " + ", ".join(sorted(_CONSTRAINT_FORMS))
        )

    args = [int(first)]
    if spec.get("first_pos") is not None:
        args.append(first_pos)
    if second is not None:
        args.append(int(second))
        if spec.get("second_pos") is not None:
            args.append(second_pos)
    if value is not None:
        args.append(float(value))

    allowed, shape = _CONSTRAINT_FORMS[kind]
    if len(args) not in allowed:
        raise ValueError(
            f"{where}: got {len(args)} argument(s) but {kind} takes "
            f"{' or '.join(str(a) for a in sorted(allowed))}. Expected: {shape}."
        )

    # Guard the indices too: an out-of-range geoId raises IndexError here, but
    # only after the constraint object exists, and we would rather say which
    # index was wrong.
    limit = len(sketch.Geometry)
    for value_index, arg in ((0, args[0]), *(() if second is None else ((1, int(second)),))):
        if arg != -1 and not (0 <= arg < limit):
            raise ValueError(
                f"{where}: geometry index {arg} does not exist. The sketch has "
                f"{limit} edge(s), so valid indices are 0..{limit - 1}, or -1 for "
                "the sketch origin."
            )

    try:
        return sketch.addConstraint(Sketcher.Constraint(kind, *args))
    except Exception as e:
        raise ValueError(
            f"{where} rejected by FreeCAD: {type(e).__name__}: {e}. "
            f"Built as Constraint({kind!r}, {', '.join(repr(a) for a in args)}). "
            f"Expected form: {shape}."
        )


_PLANES = {"XY": "XY_Plane", "XZ": "XZ_Plane", "YZ": "YZ_Plane"}


def _attach_to_plane(doc, sketch, body, plane):
    """Attach the sketch to an origin plane. Returns a note, or None."""
    key = str(plane or "XY").upper()
    if key not in _PLANES:
        raise ValueError(f"plane must be one of XY, XZ, YZ (got {plane!r}).")

    origin_plane = None
    if body is not None and getattr(body, "Origin", None) is not None:
        for feature in body.Origin.OriginFeatures:
            if feature.Name.startswith(_PLANES[key][:2]) and "Plane" in feature.Name:
                origin_plane = feature
                break
    if origin_plane is not None:
        sketch.AttachmentSupport = [(origin_plane, "")]
        sketch.MapMode = "FlatFace"
        return None
    # No Body, so no origin planes: fall back to a plain placement rotation.
    if key == "XZ":
        sketch.Placement = FreeCAD.Placement(
            FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    elif key == "YZ":
        sketch.Placement = FreeCAD.Placement(
            FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90))
    return None if body is None else "Body has no Origin; used a plain placement."


def create_sketch_gui(doc_name, sketch_name, geometry, constraints=None,
                      body_name=None, plane="XY"):
    """Create a sketch from JSON geometry and constraints.

    Returns the created name, the geometry index map (needed because one
    polyline spec becomes several edges), and the solver's verdict.
    """
    try:
        doc = FreeCAD.getDocument(doc_name)
    except Exception:
        raise ValueError(f"Document '{doc_name}' not found.")

    body = None
    if body_name:
        body = doc.getObject(body_name)
        if body is None:
            raise ValueError(f"Body '{body_name}' not found in document '{doc_name}'.")
        if not body.isDerivedFrom("PartDesign::Body"):
            raise ValueError(f"'{body_name}' is not a PartDesign::Body (TypeId={body.TypeId}).")

    sketch = (body.newObject("Sketcher::SketchObject", sketch_name) if body is not None
              else doc.addObject("Sketcher::SketchObject", sketch_name))
    note = _attach_to_plane(doc, sketch, body, plane)

    index_map = []
    try:
        for i, spec in enumerate(geometry or []):
            ids = add_geometry(sketch, spec, i)
            index_map.append({"spec": i, "type": spec.get("type"), "geo_ids": ids})
        for i, spec in enumerate(constraints or []):
            add_constraint(sketch, spec, i)
    except Exception:
        # Do not leave a half-built sketch behind for the caller to clean up.
        doc.removeObject(sketch.Name)
        doc.recompute()
        raise

    doc.recompute()
    dof = sketch.solve()
    wires = sketch.Shape.Wires
    result = {
        "success": True,
        "object_name": sketch.Name,
        "geometry_index": index_map,
        "edge_count": len(sketch.Geometry),
        "constraint_count": len(sketch.Constraints),
        "degrees_of_freedom": dof,
        "fully_constrained": bool(sketch.FullyConstrained),
        "closed_wires": sum(1 for w in wires if w.isClosed()),
        "open_wires": sum(1 for w in wires if not w.isClosed()),
    }
    if note:
        result["note"] = note
    if dof != 0:
        result["warning"] = (
            f"The sketch solver returned {dof}; the geometry may be over- or "
            "under-determined. Check conflicting/redundant constraints."
        )
    if result["closed_wires"] == 0 and result["edge_count"] > 1:
        result["warning"] = (
            "No closed wire. A Pad or Pocket needs a closed profile, and an open "
            "one is the usual reason a feature computes to nothing."
        )
    return result
