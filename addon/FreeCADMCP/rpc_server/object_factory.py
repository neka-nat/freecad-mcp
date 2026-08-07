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


def _create_in_body(doc: FreeCAD.Document, obj: Object):
    """Create a feature inside a ``PartDesign::Body``.

    Body membership is a METHOD call, not a property, so it cannot be expressed
    through the generic property interface. Measured on 1.1.1, assigning
    ``body.Group = [feature]`` over the wire fails outright ("Type must be
    App.DocumentObject or None, not str"), and even with real objects it leaves
    ``Tip`` unset so the Body produces no solid. A feature created outside the
    Body also fails PartDesign's scope check when it references a sketch inside
    it ("Link(s) to object(s) ... go out of the allowed scope").

    ``body.newObject(type, name)`` creates the feature, adds it to the Body and
    advances ``Tip`` in one call -- verified to yield a valid solid both for
    sketch-free primitives (``PartDesign::AdditiveBox``) and for a sketch-based
    ``PartDesign::Pad``.
    """
    body = doc.getObject(obj.body)
    if body is None:
        raise ValueError(f"Body '{obj.body}' not found in document '{doc.Name}'.")
    if not body.isDerivedFrom("PartDesign::Body"):
        raise ValueError(
            f"'{obj.body}' is not a PartDesign::Body (TypeId={body.TypeId})."
        )

    res = body.newObject(obj.type, obj.name)
    set_object_property(doc, res, obj.properties)
    FreeCAD.Console.PrintMessage(
        f"{res.TypeId} '{res.Name}' created inside Body '{body.Name}' via RPC.\n"
    )
    return res


def _create_generic_object(doc: FreeCAD.Document, obj: Object):
    res = doc.addObject(obj.type, obj.name)
    set_object_property(doc, res, obj.properties)
    FreeCAD.Console.PrintMessage(
        f"{res.TypeId} '{res.Name}' added to '{doc.Name}' via RPC.\n"
    )
    return res


def validity_error(obj) -> str | None:
    """Return an error string if ``obj`` failed to compute, else ``None``.

    ``obj.isValid()`` is the discriminator, NOT the presence of a shape.
    Containers and empty features are legitimately shapeless and must not be
    flagged -- an empty ``PartDesign::Body`` and a geometry-less
    ``Sketcher::SketchObject`` both report a null Shape while being perfectly
    valid intermediate states in any PartDesign workflow. Measured on 1.1.1:

        Part::Box healthy      State ['Up-to-date']        isValid True
        empty Body / Sketch    State ['Up-to-date']        isValid True   (null shape)
        Analysis / Group / Sheet  State ['Up-to-date']     isValid True   (no shape)
        bodyless Pad           State ['Touched','Invalid'] isValid False
        linkless Part::Cut     State ['Touched','Invalid'] isValid False

    ``getStatusString()`` carries FreeCAD's own reason (e.g. "Linked shape
    object is empty"), which otherwise only reaches the Report View -- invisible
    to a remote caller.
    """
    try:
        if obj.isValid():
            return None
    except Exception:
        return None  # object type without isValid(); nothing to assert

    try:
        reason = obj.getStatusString()
    except Exception:
        reason = None
    try:
        state = ", ".join(obj.State)
    except Exception:
        state = "unknown"

    detail = f": {reason}" if reason else ""
    return (
        f"Object '{obj.Name}' was created but failed to compute{detail} "
        f"(State: {state}). It exists in the document but has no valid shape. "
        "Fix the cause or remove it with delete_object. Common causes: a "
        "PartDesign feature that is not inside a Body, a sketch profile that is "
        "empty or not closed, or an unset Base/Tool/Profile link."
    )


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
        elif obj.body:
            created = _create_in_body(doc, obj)
        elif obj.type.startswith("PartDesign::") and obj.type != "PartDesign::Body":
            # A PartDesign feature outside a Body is not "invalid" -- a loose
            # AdditiveBox reports isValid() True -- so the C1 check will not catch
            # it, yet it contributes to no solid and cannot be moved in later by
            # property assignment. Refuse it up front rather than hand back a
            # success for an object that can never do anything.
            return (
                f"'{obj.type}' is a PartDesign feature and must be created inside a "
                "Body: pass body_name naming an existing PartDesign::Body. "
                "Create the Body first if there is none. Body membership cannot be "
                "set afterwards through properties."
            )
        else:
            created = _create_generic_object(doc, obj)

        doc.recompute()
        # Report the object name even on failure: it exists in the document, and
        # the caller needs it to delete or repair the object rather than blindly
        # retrying and accumulating Pad001, Pad002, ...
        problem = validity_error(created)
        if problem:
            FreeCAD.Console.PrintError(problem + "\n")
            return {"success": False, "object_name": created.Name, "error": problem}
        return {"success": True, "object_name": created.Name}
    except Exception as e:
        return str(e)
