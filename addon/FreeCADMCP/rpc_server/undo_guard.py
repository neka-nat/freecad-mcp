"""Wrap a script in a FreeCAD undo transaction so a bad edit can be reverted.

``execute_code`` mutates documents in place. Without a transaction the only way
back from a wrong boolean is to rebuild the geometry by hand, because FreeCAD
overwrites the ``.FCBak`` file on the next save. Opening a named transaction per
call makes every script a single undo step.

Documents opened *during* the script are left alone: they have no prior state to
return to, and closing them is the caller's business.
"""

from typing import Any

import FreeCAD


def _active_doc() -> list[Any]:
    """The document a script edits by default.

    Only this one is wrapped: enumerating every open document on each call would
    touch documents the script never intends to edit.
    """
    try:
        doc = FreeCAD.ActiveDocument
    except Exception:  # noqa: BLE001
        return []
    return [doc] if doc is not None else []


def begin(label: str) -> list[Any]:
    """Open an undo transaction on the active document."""
    docs = []
    for doc in _active_doc():
        try:
            doc.openTransaction(label)
            docs.append(doc)
        except Exception:  # noqa: BLE001 - a document that refuses a transaction must not abort the script
            pass
    return docs


def commit(docs: list[Any]) -> None:
    for doc in docs:
        try:
            doc.commitTransaction()
        except Exception:  # noqa: BLE001
            pass


def abort(docs: list[Any]) -> None:
    """Roll back the transaction opened by :func:`begin`."""
    for doc in docs:
        try:
            doc.abortTransaction()
        except Exception:  # noqa: BLE001
            pass


def undo(doc_name: str | None = None) -> dict[str, Any]:
    """Undo the last transaction, in a named document or in the active one."""
    if doc_name is not None:
        targets = [FreeCAD.getDocument(doc_name)]
    else:
        targets = _active_doc()
    done = []
    for doc in targets:
        try:
            if doc.UndoCount > 0:
                name = doc.UndoNames[0] if doc.UndoNames else ""
                doc.undo()
                doc.recompute()
                done.append({"document": doc.Name, "undone": name})
        except Exception as e:  # noqa: BLE001
            done.append({"document": getattr(doc, "Name", "?"), "error": f"{type(e).__name__}: {e}"})
    return {"undone": done}
