"""Document persistence and format import/export.

Format dispatch goes through FreeCAD's own registry rather than a hand-written
extension table: ``FreeCAD.getExportType(ext)`` / ``getImportType(ext)`` return
the handler modules FreeCAD itself would use, which is how all ~53 registered
formats are covered without naming any of them here. Measured on 1.1.1:

    step -> ['ImportGui']      stl -> ['Mesh', 'Fem']    brep -> ['Part']
    dxf  -> ['importDXF', ...] obj -> ['Mesh', ...]      3mf  -> ['Mesh']

Every handler exposes ``export(objects, path)``; importers expose
``insert(path, doc_name)`` and ``open(path)``.
"""

import importlib
import os

import FreeCAD


def _normalise_path(path):
    """Expand ~ and make absolute, so relative paths do not land in FreeCAD's cwd."""
    return os.path.abspath(os.path.expanduser(str(path)))


def _extension(path):
    ext = os.path.splitext(path)[1].lstrip(".")
    if not ext:
        raise ValueError(
            f"'{path}' has no file extension; the extension selects the format handler."
        )
    return ext


def _handler_module(ext, kind):
    """Resolve the module FreeCAD uses for this extension, or raise."""
    lookup = FreeCAD.getExportType if kind == "export" else FreeCAD.getImportType
    try:
        candidates = lookup(ext) or []
    except Exception:
        candidates = []
    if isinstance(candidates, str):
        candidates = [candidates]
    # De-duplicate while preserving order: getImportType repeats entries.
    seen, ordered = set(), []
    for name in candidates:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    if not ordered:
        raise ValueError(
            f"FreeCAD has no {kind} handler for '.{ext}'. "
            f"Known {kind} extensions: {', '.join(sorted(_known(kind)))}"
        )
    last_error = None
    for name in ordered:
        try:
            return importlib.import_module(name)
        except Exception as e:  # a GUI-only handler in a console session, say
            last_error = e
    raise ValueError(f"Could not import a {kind} handler for '.{ext}': {last_error}")


def _known(kind):
    lookup = FreeCAD.getExportType if kind == "export" else FreeCAD.getImportType
    try:
        return set(lookup().keys())
    except Exception:
        return set()


def _guard_overwrite(path, overwrite):
    if os.path.exists(path) and not overwrite:
        raise ValueError(
            f"'{path}' already exists. Pass overwrite=True to replace it."
        )


def _require_parent_dir(path):
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        raise ValueError(f"Directory '{parent}' does not exist.")


def _get_document(doc_name):
    try:
        return FreeCAD.getDocument(doc_name)
    except Exception:
        raise ValueError(f"Document '{doc_name}' not found.")


# --------------------------------------------------------------------- export

def export_objects_gui(doc_name, obj_names, path, overwrite=False):
    """Export named objects to ``path``; the extension picks the format."""
    doc = _get_document(doc_name)
    path = _normalise_path(path)
    _require_parent_dir(path)
    _guard_overwrite(path, overwrite)

    if not obj_names:
        objects = [o for o in doc.Objects if hasattr(o, "Shape") or hasattr(o, "Mesh")]
        if not objects:
            raise ValueError(f"Document '{doc_name}' has no exportable objects.")
    else:
        objects = []
        for name in obj_names:
            obj = doc.getObject(name)
            if obj is None:
                raise ValueError(f"Object '{name}' not found in document '{doc_name}'.")
            objects.append(obj)

    module = _handler_module(_extension(path), "export")
    module.export(objects, path)
    if not os.path.exists(path):
        raise ValueError(
            f"{module.__name__}.export reported no error but wrote nothing to '{path}'."
        )
    return {
        "success": True,
        "path": path,
        "handler": module.__name__,
        "exported": [o.Name for o in objects],
        "bytes": os.path.getsize(path),
    }


def _gui_document(doc):
    """The Gui.Document for this document, or None outside the GUI."""
    try:
        import FreeCADGui
        return FreeCADGui.getDocument(doc.Name)
    except Exception:
        return None


def _save_clearing_dirty_flag(doc):
    """Write the document and leave its modified flag accurate.

    ``App.Document.save()`` writes the file but does NOT reset
    ``Gui.Document.Modified``; only ``Gui.Document.save()`` does. Since Modified
    is the one usable dirty flag (see has_unsaved_changes), save through the GUI
    document when there is one so the flag stays truthful.

    NEVER assign ``doc.FileName`` to set the path first: it bypasses FreeCAD's
    path bookkeeping and raises a modal "Identical physical path detected"
    dialog. A modal blocks ``process_gui_tasks``, which freezes the RPC server
    until a human dismisses it.
    """
    gui_doc = _gui_document(doc)
    if gui_doc is not None:
        gui_doc.save()
    else:
        doc.save()


def save_document_gui(doc_name):
    doc = _get_document(doc_name)
    if not doc.FileName:
        raise ValueError(
            f"Document '{doc_name}' has never been saved, so it has no path. "
            "Use save_document_as with an explicit .FCStd path."
        )
    _save_clearing_dirty_flag(doc)
    return {"success": True, "document_name": doc.Name, "path": doc.FileName,
            "bytes": os.path.getsize(doc.FileName),
            "has_unsaved_changes": has_unsaved_changes(doc)}


def save_document_as_gui(doc_name, path, overwrite=False):
    doc = _get_document(doc_name)
    path = _normalise_path(path)
    if not path.lower().endswith(".fcstd"):
        raise ValueError("save_document_as expects a .FCStd path; use export_objects for other formats.")
    _require_parent_dir(path)
    _guard_overwrite(path, overwrite)
    # saveAs takes the path and does the bookkeeping properly. It leaves the GUI
    # modified flag set, so follow with a GUI save to clear it -- a second write,
    # but only on save-as, and it keeps close_document's guard trustworthy.
    doc.saveAs(path)
    _save_clearing_dirty_flag(doc)
    return {"success": True, "document_name": doc.Name, "path": doc.FileName,
            "bytes": os.path.getsize(doc.FileName),
            "has_unsaved_changes": has_unsaved_changes(doc)}


# --------------------------------------------------------------------- import

def open_document_gui(path):
    """Open a file as a document. .FCStd loads natively; anything else imports."""
    path = _normalise_path(path)
    if not os.path.isfile(path):
        raise ValueError(f"File '{path}' not found.")

    before = set(FreeCAD.listDocuments())
    if path.lower().endswith(".fcstd"):
        doc = FreeCAD.openDocument(path)
    else:
        module = _handler_module(_extension(path), "import")
        module.open(path)
        # An importer creates the document itself and does not return it, so
        # identify it by what appeared.
        new = set(FreeCAD.listDocuments()) - before
        doc = FreeCAD.getDocument(new.pop()) if new else FreeCAD.ActiveDocument
    if doc is None:
        raise ValueError(f"Opening '{path}' produced no document.")
    return {"success": True, "document_name": doc.Name, "path": path,
            "object_count": len(doc.Objects)}


def import_file_gui(path, doc_name):
    """Import a file's contents into an existing document."""
    doc = _get_document(doc_name)
    path = _normalise_path(path)
    if not os.path.isfile(path):
        raise ValueError(f"File '{path}' not found.")

    before = {o.Name for o in doc.Objects}
    module = _handler_module(_extension(path), "import")
    module.insert(path, doc.Name)
    doc.recompute()
    added = [o.Name for o in doc.Objects if o.Name not in before]
    return {"success": True, "document_name": doc.Name, "path": path,
            "handler": module.__name__, "imported": added}


def has_unsaved_changes(doc):
    """True / False, or None when it cannot be determined.

    ``Gui.Document.Modified`` is the only usable dirty flag on FreeCAD 1.1.1.
    The alternatives were measured and rejected:

        App.Document.Modified    does not exist
        App.Document.isSaved()   still True after a post-save edit
        App.Document.UndoCount   counts undo steps; does not reset on save

    Modified looks broken unless you know the catch: it is cleared only by
    ``Gui.Document.save()``, never by ``App.Document.save()``. Save through
    _save_clearing_dirty_flag and it tracks correctly -- verified across
    edit -> save -> edit -> save.

    Returns None in a console session (no GUI document), where callers should
    fall back to the FileName check rather than assume the document is clean.
    """
    gui_doc = _gui_document(doc)
    if gui_doc is None:
        return None
    try:
        return bool(gui_doc.Modified)
    except Exception:
        return None


def close_document_gui(doc_name, force=False):
    """Close a document, refusing to discard work unless forced.

    Two independent reasons to refuse, because they fail differently:
    a never-saved document has no file at all, while a saved one may still hold
    edits made since its last write.
    """
    doc = _get_document(doc_name)
    name = doc.Name
    file_name = doc.FileName
    dirty = has_unsaved_changes(doc)

    if not force:
        if not file_name:
            raise ValueError(
                f"Document '{doc_name}' has never been saved -- closing it would "
                "discard everything in it. Use save_document_as first, or pass "
                "force=True to close and lose it."
            )
        if dirty:
            raise ValueError(
                f"Document '{doc_name}' has unsaved changes. Use save_document "
                "first, or pass force=True to close and lose them."
            )
        if dirty is None:
            raise ValueError(
                f"Cannot tell whether '{doc_name}' has unsaved changes (no GUI "
                "document). Use save_document first, or pass force=True."
            )

    FreeCAD.closeDocument(name)
    return {"success": True, "document_name": name, "path": file_name or None,
            "had_unsaved_changes": dirty}
