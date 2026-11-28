"""execute_code(rollback=True): a failed script leaves no document changes."""

import importlib.util
from pathlib import Path
import types
from typing import Any
from unittest.mock import MagicMock

import pytest

from freecad_mcp.freecad_client import FreeCADConnection
from test_rpc_handlers import rpc_module  # noqa: F401  (fixture)

TXN_PATH = (
    Path(__file__).resolve().parents[1]
    / "addon" / "FreeCADMCP" / "rpc_server" / "script_transaction.py"
)
_spec = importlib.util.spec_from_file_location("_script_transaction_test", TXN_PATH)
assert _spec is not None and _spec.loader is not None
txn_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(txn_module)


class FakeDoc:
    """Undo model of a FreeCAD document: pending changes plus a capped stack."""

    def __init__(self, name: str, undo_mode: int = 1, links: int = 0, cap: int = 20) -> None:
        self.Name = name
        self.UndoMode = undo_mode
        self.objects: list[str] = []
        self._pending: list[str] | None = None
        self._pending_name = ""
        self._stack: list[tuple[str, list[str]]] = []  # newest first: (name, objects before)
        self._cap = cap
        self._links = links
        self.recomputed = 0

    @property
    def UndoNames(self) -> list[str]:
        return [n for n, _ in self._stack]

    @property
    def HasPendingTransaction(self) -> bool:
        return self._pending is not None and self._pending != self.objects

    def openTransaction(self, name: str) -> None:
        if self._pending is None:
            self._pending, self._pending_name = list(self.objects), name

    def commitTransaction(self) -> None:
        if self._pending is not None and self._pending != self.objects and self.UndoMode:
            self._stack.insert(0, (self._pending_name, self._pending))
            del self._stack[self._cap:]
        self._pending = None

    def abortTransaction(self) -> None:
        if self._pending is not None and self.UndoMode:
            self.objects = self._pending
        self._pending = None

    def undo(self) -> None:
        _, before = self._stack.pop(0)
        self.objects = before

    def recompute(self) -> None:
        self.recomputed += 1

    def getDependentDocuments(self) -> list[object]:
        # FreeCAD returns the documents this one links to, itself included.
        return [object()] * (self._links + 1)

    def add(self, name: str) -> None:
        self.objects = self.objects + [name]


def freecad_with(*docs: FakeDoc) -> types.SimpleNamespace:
    open_docs = {d.Name: d for d in docs}
    return types.SimpleNamespace(listDocuments=lambda: dict(open_docs), open_docs=open_docs)


def test_rollback_reverts_every_open_document() -> None:
    a, b = FakeDoc("A"), FakeDoc("B")
    a.add("Base")
    a.commitTransaction()
    txn = txn_module.ScriptTransaction(freecad_with(a, b), "edit")
    txn.open()
    a.add("Pad")
    b.add("Sketch")  # reached through App.getDocument("B")
    assert txn.rollback() == {"mutation_outcome": "rolled_back"}
    assert a.objects == ["Base"] and b.objects == []
    assert a.recomputed == 1 and b.recomputed == 1


def test_rollback_undoes_steps_the_script_committed_itself() -> None:
    doc = FakeDoc("A", cap=3)
    for name in ("x", "y", "z"):  # full stack: the oldest entry drops off on commit
        doc.openTransaction(name)
        doc.add(name)
        doc.commitTransaction()
    txn = txn_module.ScriptTransaction(freecad_with(doc), "edit")
    txn.open()
    doc.add("first")
    doc.commitTransaction()  # e.g. Std_ToggleFreeze or an explicit commit
    doc.openTransaction("script")
    doc.add("second")
    doc.commitTransaction()
    doc.add("third")
    assert txn.rollback()["mutation_outcome"] == "rolled_back"
    assert doc.objects == ["x", "y", "z"]


def test_rollback_works_with_undo_disabled_and_restores_mode() -> None:
    doc = FakeDoc("A", undo_mode=0)
    txn = txn_module.ScriptTransaction(freecad_with(doc), "edit")
    txn.open()
    doc.add("Box")
    assert txn.rollback()["mutation_outcome"] == "rolled_back"
    assert doc.objects == [] and doc.UndoMode == 0


def test_rollback_reports_documents_opened_or_closed_by_the_script() -> None:
    a, b = FakeDoc("A"), FakeDoc("B")
    freecad = freecad_with(a, b)
    txn = txn_module.ScriptTransaction(freecad, "edit")
    txn.open()
    a.add("Pad")
    del freecad.open_docs["B"]
    b.Name = ""  # FreeCAD raises on a closed document; the helper treats it as gone
    freecad.open_docs["New"] = FakeDoc("New")
    result = txn.rollback()
    assert result["mutation_outcome"] == "cleanup_incomplete"
    assert any("closed" in e and "B" in e for e in result["cleanup_errors"])
    assert any("opened" in e and "New" in e for e in result["cleanup_errors"])
    assert a.objects == []


def test_sources_recompute_before_their_dependents() -> None:
    order: list[str] = []
    top, src = FakeDoc("Assembly", links=1), FakeDoc("Part")
    for d in (top, src):
        d.recompute = lambda d=d: order.append(d.Name)  # type: ignore[method-assign]
    txn = txn_module.ScriptTransaction(freecad_with(top, src), "edit")
    txn.open()
    top.add("Joint")
    src.add("Pad")
    txn.rollback()
    assert order == ["Part", "Assembly"]


def test_commit_keeps_changes() -> None:
    doc = FakeDoc("A")
    txn = txn_module.ScriptTransaction(freecad_with(doc), "edit")
    txn.open()
    doc.add("Pad")
    assert txn.commit() == []
    assert doc.objects == ["Pad"] and doc.UndoNames == ["edit"]


def test_handler_rolls_back_a_failed_script(rpc_module: types.ModuleType) -> None:  # noqa: F811
    doc = FakeDoc("Doc")
    rpc_module.FreeCAD.listDocuments = lambda: {"Doc": doc}
    rpc_module.FreeCAD.fake_doc = doc
    rpc = rpc_module.FreeCADRPC()
    result = rpc.execute_code("App.fake_doc.add('Pad')\nraise ValueError('sketch not closed')", None, True)
    assert result["success"] is False
    assert result["mutation_outcome"] == "rolled_back"
    assert "sketch not closed" in result["error"]
    assert doc.objects == []


def test_handler_commits_a_successful_script(rpc_module: types.ModuleType) -> None:  # noqa: F811
    doc = FakeDoc("Doc")
    rpc_module.FreeCAD.listDocuments = lambda: {"Doc": doc}
    rpc_module.FreeCAD.fake_doc = doc
    result = rpc_module.FreeCADRPC().execute_code("App.fake_doc.add('Pad')", None, True)
    assert result["success"] is True and result["mutation_outcome"] == "completed"
    assert doc.objects == ["Pad"]


def test_handler_without_rollback_keeps_partial_changes(rpc_module: types.ModuleType) -> None:  # noqa: F811
    doc = FakeDoc("Doc")
    rpc_module.FreeCAD.fake_doc = doc
    result = rpc_module.FreeCADRPC().execute_code("App.fake_doc.add('Pad')\nraise ValueError('x')")
    assert result["mutation_outcome"] == "partial_or_unknown"
    assert doc.objects == ["Pad"]


@pytest.mark.parametrize("value", [1, "yes", None])
def test_handler_rejects_non_bool_rollback(rpc_module: types.ModuleType, value: Any) -> None:  # noqa: F811
    result = rpc_module.FreeCADRPC().execute_code("must_not_run = True", None, value)
    assert result["mutation_outcome"] == "not_started"
    assert "must_not_run" not in rpc_module._EXEC_NAMESPACE


def test_client_sends_rollback_only_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FreeCADConnection()
    proxy = MagicMock()
    proxy.__enter__.return_value = proxy
    proxy.execute_code.return_value = {"success": True}
    monkeypatch.setattr(connection, "_make_proxy", MagicMock(return_value=proxy))
    try:
        connection.execute_code("pass")
        proxy.execute_code.assert_called_with("pass")
        connection.execute_code("pass", rollback=True)
        proxy.execute_code.assert_called_with("pass", connection.EXECUTE_CODE_TIMEOUT, True)
    finally:
        connection.disconnect()
