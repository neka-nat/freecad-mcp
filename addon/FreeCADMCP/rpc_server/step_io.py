"""STEP import/export and solid-metrics helpers.

These are plain functions (document/file paths in, plain dicts out) so they
can be unit-reasoned about independently of the RPC/GUI-thread plumbing,
mirroring the fem_executor.py convention.
"""

import os

import FreeCAD


def list_solids_with_bbox(doc_name: str, obj_name: str | None = None) -> dict:
    """List every solid in a document (or a single object), with bounding box
    dimensions, center, and volume. Read-only.
    """
    try:
        doc = FreeCAD.getDocument(doc_name)
    except Exception:
        return {"success": False, "error": f"Document '{doc_name}' not found."}

    if obj_name:
        obj = doc.getObject(obj_name)
        if obj is None:
            return {"success": False, "error": f"Object '{obj_name}' not found in document '{doc_name}'."}
        objects = [obj]
    else:
        objects = doc.Objects

    solids = []
    for obj in objects:
        shape = getattr(obj, "Shape", None)
        if shape is None or shape.isNull():
            continue
        for i, solid in enumerate(shape.Solids):
            bbox = solid.BoundBox
            solids.append({
                "object_name": obj.Name,
                "solid_index": i,
                "volume_mm3": solid.Volume,
                "bounding_box": {
                    "x_length": bbox.XLength,
                    "y_length": bbox.YLength,
                    "z_length": bbox.ZLength,
                    "center": {"x": bbox.Center.x, "y": bbox.Center.y, "z": bbox.Center.z},
                },
            })
    return {"success": True, "solids": solids}


def export_step(doc_name: str, save_path: str, obj_names: list[str] | None = None) -> dict:
    """Export objects (or all exportable objects) in a document to a STEP file."""
    import Part

    try:
        doc = FreeCAD.getDocument(doc_name)
    except Exception:
        return {"success": False, "error": f"Document '{doc_name}' not found."}

    if obj_names:
        objs = []
        missing = []
        for name in obj_names:
            obj = doc.getObject(name)
            if obj is None:
                missing.append(name)
            else:
                objs.append(obj)
        if missing:
            return {"success": False, "error": f"Object(s) not found: {', '.join(missing)}"}
    else:
        objs = [
            o for o in doc.Objects
            if getattr(o, "Shape", None) is not None and not o.Shape.isNull()
        ]

    if not objs:
        return {"success": False, "error": "No exportable objects (with a Shape) found."}

    try:
        Part.export(objs, save_path)
    except Exception as e:
        return {"success": False, "error": f"STEP export failed: {type(e).__name__}: {e}"}

    return {"success": True, "save_path": save_path, "object_count": len(objs)}


def import_step(doc_name: str, file_path: str, preserve_hierarchy: bool = True) -> dict:
    """Import a STEP file into a document (created if it doesn't already exist).

    Uses the non-GUI ``Import`` module rather than ``ImportGui``, which
    avoids the "Unknown document" error that ``ImportGui.insert`` raises
    when the target document isn't already the active one.
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        doc = FreeCAD.getDocument(doc_name)
    except Exception:
        doc = FreeCAD.newDocument(doc_name)

    existing_names = {o.Name for o in doc.Objects}

    try:
        if preserve_hierarchy:
            import Import
            Import.insert(file_path, doc.Name)
        else:
            import Part
            shape = Part.Shape()
            shape.read(file_path)
            obj = doc.addObject("Part::Feature", "ImportedSTEP")
            obj.Shape = shape
        doc.recompute()
    except Exception as e:
        return {"success": False, "error": f"STEP import failed: {type(e).__name__}: {e}"}

    imported_objects = [o.Name for o in doc.Objects if o.Name not in existing_names]
    return {"success": True, "document_name": doc.Name, "imported_objects": imported_objects}
