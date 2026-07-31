"""Object creation dispatch for the RPC ``create_object`` handler.

The legacy ``_create_object_gui`` mixed three flows: FEM mesh (Gmsh) with
legacy parameter remapping, generic FEM-typed objects, and arbitrary
``doc.addObject`` types. Each lives in its own helper here, with a single
public entry point that selects the branch.
"""

from contextlib import contextmanager

import FreeCAD
import ObjectsFem

from rpc_server.property_mapper import Object, set_object_property


def _create_fem_mesh(doc: FreeCAD.Document, obj: Object):
    """Create a ``Fem::FemMeshGmsh`` and run Gmsh to populate it.

    Accepts both the FreeCAD 0.x and 1.x property names (``Part``/``Shape``,
    ``ElementSize{Max,Min}``/``CharacteristicLength{Max,Min}``).
    Returns the created mesh object.
    """
    from femmesh.gmshtools import GmshTools

    res = getattr(doc, obj.analysis).addObject(
        ObjectsFem.makeMeshGmsh(doc, obj.name)
    )[0]
    geom_attr = "Shape" if hasattr(res, "Shape") else ("Part" if hasattr(res, "Part") else None)
    legacy_to_new = {
        "Part": geom_attr,
        "ElementSizeMax": "CharacteristicLengthMax",
        "ElementSizeMin": "CharacteristicLengthMin",
    }
    geom_key = "Part" if "Part" in obj.properties else ("Shape" if "Shape" in obj.properties else None)
    if geom_key is None:
        raise ValueError("'Part' (or 'Shape') property not found in properties.")
    target_obj = doc.getObject(obj.properties[geom_key])
    if target_obj is None:
        raise ValueError(f"Referenced object '{obj.properties[geom_key]}' not found.")
    if geom_attr is None:
        raise ValueError("Mesh object has neither 'Shape' nor 'Part' property.")
    setattr(res, geom_attr, target_obj)
    del obj.properties[geom_key]

    for param, value in obj.properties.items():
        target_param = legacy_to_new.get(param, param)
        if target_param and hasattr(res, target_param):
            setattr(res, target_param, value)
    doc.recompute()

    GmshTools(res).create_mesh()
    FreeCAD.Console.PrintMessage(
        f"FEM Mesh '{res.Name}' generated successfully in '{doc.Name}'.\n"
    )
    return res


def _create_fem_object(doc: FreeCAD.Document, obj: Object):
    """Create a ``Fem::*`` object via the appropriate ``ObjectsFem.makeXxx`` factory."""
    fem_make_methods = {
        "MaterialCommon": ObjectsFem.makeMaterialSolid,
        "AnalysisPython": ObjectsFem.makeAnalysis,
    }
    obj_type_short = obj.type.split("::")[1]
    method_name = "make" + obj_type_short
    make_method = fem_make_methods.get(obj_type_short, getattr(ObjectsFem, method_name, None))

    if not callable(make_method):
        raise ValueError(f"No creation method '{method_name}' found in ObjectsFem.")

    res = make_method(doc, obj.name)
    set_object_property(doc, res, obj.properties)
    FreeCAD.Console.PrintMessage(
        f"FEM object '{res.Name}' created with '{method_name}'.\n"
    )
    if obj.type != "Fem::AnalysisPython" and obj.analysis:
        getattr(doc, obj.analysis).addObject(res)
    return res


@contextmanager
def _active_document(doc: FreeCAD.Document):
    """Make ``doc`` the active document for the duration of the block.

    The Draft factories create into ``FreeCAD.ActiveDocument`` rather than a
    document passed in, so without this an RPC call naming one document can
    drop geometry into whichever one the GUI happens to have focused.
    """
    previous = FreeCAD.ActiveDocument
    FreeCAD.setActiveDocument(doc.Name)
    try:
        yield
    finally:
        if previous is not None:
            try:
                FreeCAD.setActiveDocument(previous.Name)
            except Exception:
                pass


def _require(properties: dict, key: str, obj_type: str):
    """Pop a property the factory needs as a constructor argument.

    Popping keeps it out of the later ``set_object_property`` pass, which would
    otherwise try to re-assign the raw JSON value.
    """
    if key not in properties:
        raise ValueError(
            f"'{obj_type}' requires a '{key}' property, which was not supplied."
        )
    return properties.pop(key)


def _to_vectors(raw, obj_type: str) -> list:
    """Convert a JSON point list to FreeCAD.Vector, accepting dicts or sequences."""
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError(f"'{obj_type}' needs 'Points' to be a non-empty list.")
    points = []
    for entry in raw:
        if isinstance(entry, dict):
            points.append(
                FreeCAD.Vector(entry.get("x", 0), entry.get("y", 0), entry.get("z", 0))
            )
        elif isinstance(entry, (list, tuple)) and len(entry) in (2, 3):
            x, y, z = (list(entry) + [0])[:3]
            points.append(FreeCAD.Vector(x, y, z))
        else:
            raise ValueError(
                f"Invalid point {entry!r} for '{obj_type}'; expected "
                "{'x': .., 'y': .., 'z': ..} or [x, y, z]."
            )
    return points


def _make_tube(doc, name, properties):
    from BasicShapes import Shapes

    return Shapes.addTube(doc, name)


def _make_draft_circle(doc, name, properties):
    import Draft

    return Draft.make_circle(_require(properties, "Radius", "Draft::Circle"))


def _make_draft_rectangle(doc, name, properties):
    import Draft

    return Draft.make_rectangle(
        _require(properties, "Length", "Draft::Rectangle"),
        _require(properties, "Height", "Draft::Rectangle"),
    )


def _make_draft_polygon(doc, name, properties):
    import Draft

    return Draft.make_polygon(
        _require(properties, "FacesNumber", "Draft::Polygon"),
        _require(properties, "Radius", "Draft::Polygon"),
    )


def _make_draft_wire(doc, name, properties):
    import Draft

    points = _to_vectors(_require(properties, "Points", "Draft::Wire"), "Draft::Wire")
    return Draft.make_wire(points, closed=bool(properties.pop("Closed", False)))


#: Types implemented in Python rather than C++, so absent from FreeCAD's type
#: registry and rejected by ``doc.addObject``. Each entry adapts the real
#: factory to a uniform ``(doc, name, properties) -> DocumentObject`` call.
#: The signatures genuinely differ -- addTube takes the document and name,
#: the Draft factories take geometry and neither -- so this cannot collapse
#: into a (module, function) lookup the way the Fem:: branch does.
_PYTHON_FACTORIES = {
    "Part::Tube": _make_tube,
    "Draft::Circle": _make_draft_circle,
    "Draft::Rectangle": _make_draft_rectangle,
    "Draft::Polygon": _make_draft_polygon,
    "Draft::Wire": _make_draft_wire,
}


def _create_python_object(doc: FreeCAD.Document, obj: Object):
    """Create a Python-implemented feature via its factory."""
    with _active_document(doc):
        res = _PYTHON_FACTORIES[obj.type](doc, obj.name, obj.properties)
    if res is None:
        raise ValueError(f"The factory for '{obj.type}' returned no object.")
    # Only addTube honours a requested name; the Draft factories name objects
    # themselves (make_wire even yields "Line"), so carry the caller's name on
    # the Label and let the real Name go back in the response.
    res.Label = obj.name
    set_object_property(doc, res, obj.properties)
    FreeCAD.Console.PrintMessage(
        f"{obj.type} '{res.Name}' created in '{doc.Name}' via RPC.\n"
    )
    return res


#: Python-implemented features with no factory here yet. Keys must stay
#: disjoint from _PYTHON_FACTORIES, which handles its own types before
#: _create_generic_object is ever reached.
_UNREGISTERED_TYPE_HINTS = {
    "Draft::Point": "Draft.make_point(x, y, z)",
    "Draft::Ellipse": "Draft.make_ellipse(majradius, minradius)",
    "Draft::BSpline": "Draft.make_bspline(points, closed=False)",
}


def _unregistered_type_message(obj_type: str) -> str:
    """Explain an ``addObject`` type-registry miss in terms the caller can act on.

    FreeCAD's own error ("is not a document object type") gives no hint that
    the type may be perfectly real but Python-implemented, which sends callers
    hunting for a typo that isn't there.
    """
    hint = _UNREGISTERED_TYPE_HINTS.get(obj_type)
    if hint is None and obj_type.startswith("Draft::"):
        hint = "the matching Draft.make_* factory"
    suggestion = (
        f" It is implemented in Python rather than C++, so build it with "
        f"execute_code instead, e.g. {hint}."
        if hint
        else " Check the spelling, or build it with execute_code."
    )
    return (
        f"'{obj_type}' is not a type registered with FreeCAD, so create_object "
        f"cannot make it.{suggestion}"
    )


def _create_generic_object(doc: FreeCAD.Document, obj: Object):
    try:
        res = doc.addObject(obj.type, obj.name)
    except Exception as e:
        if "not a document object type" in str(e):
            raise ValueError(_unregistered_type_message(obj.type)) from e
        raise
    set_object_property(doc, res, obj.properties)
    FreeCAD.Console.PrintMessage(
        f"{res.TypeId} '{res.Name}' added to '{doc.Name}' via RPC.\n"
    )
    return res


def create_object_gui(doc_name: str, obj: Object):
    """Create an object in ``doc_name`` according to ``obj.type``.

    Returns the created object's actual ``Name`` on success (FreeCAD
    sanitises and de-duplicates requested names — ``Box`` may come back as
    ``Box001`` — and every later get_object/edit_object call needs the real
    one), or an error string on failure.
    """
    try:
        doc = FreeCAD.getDocument(doc_name)
    except Exception:
        FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
        return f"Document '{doc_name}' not found.\n"
    try:
        if obj.type == "Fem::FemMeshGmsh":
            if not obj.analysis:
                return (
                    "Fem::FemMeshGmsh requires an 'analysis_name' naming the "
                    "Fem::AnalysisPython container to add the mesh to."
                )
            created = _create_fem_mesh(doc, obj)
        elif obj.type.startswith("Fem::"):
            created = _create_fem_object(doc, obj)
        elif obj.type in _PYTHON_FACTORIES:
            created = _create_python_object(doc, obj)
        else:
            created = _create_generic_object(doc, obj)

        doc.recompute()
        return {"success": True, "object_name": created.Name}
    except Exception as e:
        return str(e)
