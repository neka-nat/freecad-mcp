import importlib
import sys
import types
from collections.abc import Iterator

import pytest

from test_gui_dispatch import load_gui_dispatch


class FakeDoc:
    def __init__(self, name: str, refuse: bool = False):
        self.Name = name
        self.refuse = refuse
        self.events: list[str] = []
        self.UndoNames: list[str] = []
        self.recomputes = 0

    @property
    def UndoCount(self) -> int:
        return len(self.UndoNames)

    def openTransaction(self, label: str) -> None:
        if self.refuse:
            raise RuntimeError("transactions disabled")
        self.events.append(f"open:{label}")

    def commitTransaction(self) -> None:
        self.events.append("commit")
        self.UndoNames.insert(0, "MCP execute_code")

    def abortTransaction(self) -> None:
        self.events.append("abort")

    def undo(self) -> None:
        self.events.append("undo")
        self.UndoNames.pop(0)

    def recompute(self) -> None:
        self.recomputes += 1


@pytest.fixture
def guard() -> Iterator[tuple[types.ModuleType, dict[str, FakeDoc], types.ModuleType]]:
    with load_gui_dispatch() as dispatch:
        docs: dict[str, FakeDoc] = {}
        freecad = dispatch.FreeCAD

        def unexpected_scan():
            raise AssertionError("an edit must not enumerate every open document")

        freecad.listDocuments = unexpected_scan
        freecad.getDocument = lambda name: docs[name]
        freecad.ActiveDocument = None
        sys.modules.pop("rpc_server.undo_guard", None)
        module = importlib.import_module("rpc_server.undo_guard")
        try:
            yield module, docs, freecad
        finally:
            sys.modules.pop("rpc_server.undo_guard", None)


def test_commit_leaves_one_undo_step(guard) -> None:
    module, docs, freecad = guard
    docs["Doc"] = freecad.ActiveDocument = FakeDoc("Doc")
    module.commit(module.begin("MCP execute_code"))
    assert docs["Doc"].events == ["open:MCP execute_code", "commit"]
    assert docs["Doc"].UndoCount == 1


def test_abort_discards_the_edit(guard) -> None:
    module, docs, freecad = guard
    docs["Doc"] = freecad.ActiveDocument = FakeDoc("Doc")
    module.abort(module.begin("MCP execute_code"))
    assert docs["Doc"].events == ["open:MCP execute_code", "abort"]
    assert docs["Doc"].UndoCount == 0


def test_only_the_active_document_is_wrapped(guard) -> None:
    module, docs, freecad = guard
    docs["Doc"] = freecad.ActiveDocument = FakeDoc("Doc")
    docs["Other"] = FakeDoc("Other")
    module.commit(module.begin("MCP execute_code"))
    assert docs["Other"].events == []


def test_a_document_refusing_a_transaction_is_skipped(guard) -> None:
    module, docs, freecad = guard
    docs["Bad"] = freecad.ActiveDocument = FakeDoc("Bad", refuse=True)
    assert module.begin("MCP execute_code") == []


def test_no_active_document_is_not_an_error(guard) -> None:
    module, _, freecad = guard
    freecad.ActiveDocument = None
    assert module.begin("MCP execute_code") == []
    assert module.undo() == {"undone": []}


def test_undo_reverts_and_recomputes_a_named_document(guard) -> None:
    module, docs, freecad = guard
    docs["Doc"] = freecad.ActiveDocument = FakeDoc("Doc")
    module.commit(module.begin("MCP execute_code"))
    result = module.undo("Doc")
    assert result == {"undone": [{"document": "Doc", "undone": "MCP execute_code"}]}
    assert docs["Doc"].recomputes == 1


def test_undo_skips_a_document_with_nothing_to_revert(guard) -> None:
    module, docs, freecad = guard
    docs["Doc"] = freecad.ActiveDocument = FakeDoc("Doc")
    assert module.undo() == {"undone": []}
    assert docs["Doc"].recomputes == 0
