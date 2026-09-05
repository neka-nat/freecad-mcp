"""Object creation dispatch for the RPC ``create_object`` handler.

The legacy ``_create_object_gui`` mixed three flows: FEM mesh (Gmsh) with
legacy parameter remapping, generic FEM-typed objects, and arbitrary
``doc.addObject`` types. Each lives in its own helper here, with a single
public entry point that selects the branch.
"""

import FreeCAD
import ObjectsFem

from rpc_server.property_mapper import Object, set_object_property
from rpc_server.object_validation import object_validity_error


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


def _create_generic_object(doc: FreeCAD.Document, obj: Object):
    res = doc.addObject(obj.type, obj.name)
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
        problem = object_validity_error(created)
        if problem:
            FreeCAD.Console.PrintError(problem + "\n")
            return {
                "success": False,
                "object_name": created.Name,
                "error": problem,
            }
        return {"success": True, "object_name": created.Name}
    except Exception as e:
        return str(e)


def edit_object_gui(doc_name: str, obj: Object):
    """Apply properties to an existing object and verify the recomputed state."""
    try:
        doc = FreeCAD.getDocument(doc_name)
    except Exception:
        FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
        return f"Document '{doc_name}' not found.\n"

    obj_ins = doc.getObject(obj.name)
    if obj_ins is None:
        FreeCAD.Console.PrintError(
            f"Object '{obj.name}' not found in document '{doc_name}'.\n"
        )
        return f"Object '{obj.name}' not found in document '{doc_name}'.\n"

    try:
        set_object_property(doc, obj_ins, obj.properties)
        doc.recompute()
        problem = object_validity_error(obj_ins)
        if problem:
            FreeCAD.Console.PrintError(problem + "\n")
            return {
                "success": False,
                "object_name": obj_ins.Name,
                "error": problem,
            }
        FreeCAD.Console.PrintMessage(f"Object '{obj_ins.Name}' updated via RPC.\n")
        return True
    except Exception as e:
        return str(e)
