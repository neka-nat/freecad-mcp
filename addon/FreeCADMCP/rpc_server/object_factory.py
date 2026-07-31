"""Object creation dispatch for the RPC ``create_object`` handler.

The legacy ``_create_object_gui`` mixed three flows: FEM mesh (Gmsh) with
legacy parameter remapping, generic FEM-typed objects, and arbitrary
``doc.addObject`` types. Each lives in its own helper here, with a single
public entry point that selects the branch.
"""

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


#: Python-implemented features that look like ordinary types but are absent
#: from FreeCAD's C++ type registry, mapped to the factory that does build
#: them. ``doc.addObject`` rejects every key here.
_UNREGISTERED_TYPE_HINTS = {
    "Part::Tube": "BasicShapes.Shapes.addTube(doc, name)",
    "Draft::Circle": "Draft.make_circle(radius)",
    "Draft::Rectangle": "Draft.make_rectangle(length, height)",
    "Draft::Polygon": "Draft.make_polygon(nfaces, radius)",
    "Draft::Wire": "Draft.make_wire(points, closed=False)",
    "Draft::Point": "Draft.make_point(x, y, z)",
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
        else:
            created = _create_generic_object(doc, obj)

        doc.recompute()
        return {"success": True, "object_name": created.Name}
    except Exception as e:
        return str(e)
