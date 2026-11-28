"""All-or-nothing document changes for ``execute_code(rollback=True)``.

FreeCAD records undo history per document, and a script can reach any open
document through ``App.getDocument``. So a transaction is opened in every open
document, not only the active one. A script that commits on its own (an
explicit ``commitTransaction()`` or a command such as Std_ToggleFreeze) leaves
extra entries on the undo stack; a rollback undoes those too.

Kept free of a module-level FreeCAD import so the logic is testable with fakes.
"""

from typing import Any


def _alive(doc: Any) -> bool:
    """False once the document was closed by the script."""
    try:
        return bool(doc.Name)
    except Exception:
        return False


def _undo_added(doc: Any, before: list[str]) -> int:
    """Undo entries on top of the stack that were not there before the script.

    The stack is capped, so UndoCount alone cannot tell once it is full: find
    the smallest k for which the stack minus its k newest entries is the old
    stack minus the entries that dropped off its bottom.
    """
    now = list(doc.UndoNames)
    return next((k for k in range(len(now) + 1) if now[k:] == before[: len(now) - k]), 0)


class ScriptTransaction:
    """Open a transaction in every open document; commit or roll back all."""

    def __init__(self, freecad: Any, name: str) -> None:
        self._freecad = freecad
        self._name = name[:60] or "execute_code"
        self._docs: list[Any] = []
        self._undo_before: dict[str, list[str]] = {}
        self._undo_mode: dict[str, int] = {}
        self._names_before: set[str] = set()

    def open(self) -> None:
        self._docs = list(self._freecad.listDocuments().values())
        self._names_before = {d.Name for d in self._docs}
        for doc in self._docs:
            self._undo_mode[doc.Name] = doc.UndoMode
            if not doc.UndoMode:
                doc.UndoMode = 1  # without undo, abortTransaction keeps the changes
            self._undo_before[doc.Name] = list(doc.UndoNames)
            doc.openTransaction(self._name)

    def commit(self) -> list[str]:
        """Commit in every document still open; return restore errors."""
        for doc in self._docs:
            if _alive(doc):
                doc.commitTransaction()
        return self._restore_undo_mode()

    def rollback(self) -> dict[str, Any]:
        """Revert every document the script reached.

        Returns ``mutation_outcome`` (``rolled_back`` or ``cleanup_incomplete``)
        and, when incomplete, the reasons.
        """
        problems: list[str] = []
        live = [d for d in self._docs if _alive(d)]
        closed = sorted(self._names_before - {d.Name for d in live})
        if closed:
            problems.append(f"closed by the script, not restored: {', '.join(closed)}")
        opened = sorted(set(self._freecad.listDocuments()) - self._names_before)
        if opened:
            problems.append(f"opened by the script, left open: {', '.join(opened)}")
        reverted = []
        for doc in live:
            try:
                changed = doc.HasPendingTransaction or list(doc.UndoNames) != self._undo_before[doc.Name]
                doc.abortTransaction()
                for _ in range(_undo_added(doc, self._undo_before[doc.Name])):
                    doc.undo()
                if changed:
                    reverted.append(doc)
            except Exception as exc:
                problems.append(f"{doc.Name}: {type(exc).__name__}: {exc}")
        # Recompute only after every document is reverted, sources before the
        # documents that link to them.
        for doc in sorted(reverted, key=lambda d: len(d.getDependentDocuments())):
            try:
                doc.recompute()
            except Exception as exc:
                problems.append(f"recompute {doc.Name}: {type(exc).__name__}: {exc}")
        problems += self._restore_undo_mode()
        if problems:
            return {"mutation_outcome": "cleanup_incomplete", "cleanup_errors": problems}
        return {"mutation_outcome": "rolled_back"}

    def _restore_undo_mode(self) -> list[str]:
        errors = []
        for doc in self._docs:
            mode = self._undo_mode.get(doc.Name) if _alive(doc) else None
            if mode is not None and doc.UndoMode != mode:
                try:
                    doc.UndoMode = mode
                except Exception as exc:
                    errors.append(f"restore UndoMode of {doc.Name}: {exc}")
        return errors
