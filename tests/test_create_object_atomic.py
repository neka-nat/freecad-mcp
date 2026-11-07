"""create_object_gui is all or nothing (issue #159)."""

from collections.abc import Iterator
from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import sys
import types
from typing import Any

import pytest

FACTORY_PATH = (
    Path(__file__).resolve().parents[1]
    / "addon" / "FreeCADMCP" / "rpc_server" / "object_factory.py"
)


@dataclass
class Item:
    Name: str
    TypeId: str
    State: list[str] = field(default_factory=list)


class Document:
    """Records transactions; aborting undoes nothing, like a document with undo off."""

    Name = "Doc"

    def __init__(self) -> None:
        self.Objects: list[Item] = [Item("Existing", "Part::Box")]
        self.events: list[str] = []

    def addObject(self, type_id: str, name: str) -> Item:
        item = Item(name, type_id)
        self.Objects.append(item)
        return item

    def removeObject(self, name: str) -> None:
        self.Objects = [o for o in self.Objects if o.Name != name]

    def openTransaction(self, name: str) -> None:
        self.events.append("open")

    def commitTransaction(self) -> None:
        self.events.append("commit")

    def abortTransaction(self) -> None:
        self.events.append("abort")

    def recompute(self) -> None:
        pass


def _set_property(doc: Document, obj: Item, properties: dict[str, Any]) -> None:
    if "Placement" in properties:
        raise ValueError("Failed to set property: Placement: Either three floats, tuple or Vector expected")


@pytest.fixture
def factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[types.ModuleType, Document]]:
    doc = Document()
    freecad = types.SimpleNamespace(
        Document=Document,
        getDocument=lambda name: doc,
        Console=types.SimpleNamespace(PrintMessage=lambda _m: None, PrintError=lambda _m: None),
    )

    @dataclass
    class Object:
        name: str
        type: str
        analysis: str | None = None
        properties: dict[str, Any] = field(default_factory=dict)

    stubs = {
        "FreeCAD": freecad,
        "ObjectsFem": types.SimpleNamespace(),
        "rpc_server": types.SimpleNamespace(),
        "rpc_server.property_mapper": types.SimpleNamespace(Object=Object, set_object_property=_set_property),
        "rpc_server.object_validation": types.SimpleNamespace(object_validity_error=lambda _obj: None),
    }
    with monkeypatch.context() as patch:
        for name, stub in stubs.items():
            patch.setitem(sys.modules, name, stub)
        spec = importlib.util.spec_from_file_location("_object_factory_test", FACTORY_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.TestObject = Object
        yield module, doc


def test_a_failed_property_leaves_nothing_behind(factory: tuple[types.ModuleType, Document]) -> None:
    module, doc = factory
    obj = module.TestObject(name="Hole", type="Part::Cylinder", properties={"Radius": 8, "Placement": {"Base": {"x": 1}}})
    reply = module.create_object_gui("Doc", obj)
    assert isinstance(reply, str) and "Placement" in reply and "nothing was created" in reply
    assert [o.Name for o in doc.Objects] == ["Existing"]
    assert doc.events == ["open", "abort"]


def test_a_successful_create_is_one_committed_transaction(factory: tuple[types.ModuleType, Document]) -> None:
    module, doc = factory
    reply = module.create_object_gui("Doc", module.TestObject(name="Hole", type="Part::Cylinder", properties={"Radius": 8}))
    assert reply == {"success": True, "object_name": "Hole"}
    assert [o.Name for o in doc.Objects] == ["Existing", "Hole"]
    assert doc.events == ["open", "commit"]
