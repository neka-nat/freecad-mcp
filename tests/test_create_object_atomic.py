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
    assert isinstance(reply, str) and "Placement" in reply and "no new objects remain" in reply
    assert [o.Name for o in doc.Objects] == ["Existing"]
    assert doc.events == ["open", "abort"]


def test_a_successful_create_is_one_committed_transaction(factory: tuple[types.ModuleType, Document]) -> None:
    module, doc = factory
    reply = module.create_object_gui("Doc", module.TestObject(name="Hole", type="Part::Cylinder", properties={"Radius": 8}))
    assert reply == {"success": True, "object_name": "Hole"}
    assert [o.Name for o in doc.Objects] == ["Existing", "Hole"]
    assert doc.events == ["open", "commit"]


def test_failed_cleanup_reports_actual_remaining_names(
    factory: tuple[types.ModuleType, Document], monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, doc = factory

    def cannot_remove(name: str) -> None:
        raise RuntimeError(f"cannot remove {name}")

    monkeypatch.setattr(doc, "removeObject", cannot_remove)
    reply = module.create_object_gui("Doc", module.TestObject(
        name="Hole001", type="Part::Cylinder", properties={"Placement": {}},
    ))
    assert reply["success"] is False
    assert reply["remaining_objects"] == ["Hole001"]
    assert "Hole001" in reply["error"] and "before retrying" in reply["error"]
    assert "no new objects remain" not in reply["error"]
    assert [o.Name for o in doc.Objects] == ["Existing", "Hole001"]


def test_abort_failure_still_attempts_cleanup(
    factory: tuple[types.ModuleType, Document], monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, doc = factory

    def cannot_abort() -> None:
        raise RuntimeError("undo failure")

    monkeypatch.setattr(doc, "abortTransaction", cannot_abort)
    reply = module.create_object_gui("Doc", module.TestObject(
        name="Hole", type="Part::Cylinder", properties={"Placement": {}},
    ))
    assert reply["remaining_objects"] == []
    assert "undo failure" in reply["cleanup_errors"][0]
    assert [o.Name for o in doc.Objects] == ["Existing"]


def test_factory_failure_removes_all_new_objects_only(
    factory: tuple[types.ModuleType, Document], monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, doc = factory

    def fail_after_children(doc: Document, obj: Any) -> None:
        doc.addObject("App::FeaturePython", "Helper")
        doc.addObject("App::FeaturePython", "Material")
        raise ValueError("invalid material property")

    monkeypatch.setattr(module, "_create_by_type", fail_after_children)
    reply = module.create_object_gui("Doc", module.TestObject(name="Material", type="Fem::MaterialCommon"))
    assert "invalid material property" in reply
    assert [o.Name for o in doc.Objects] == ["Existing"]


def test_invalid_created_object_is_kept_and_named(
    factory: tuple[types.ModuleType, Document], monkeypatch: pytest.MonkeyPatch,
) -> None:
    module, doc = factory
    monkeypatch.setattr(module, "object_validity_error", lambda obj: "invalid shape")
    reply = module.create_object_gui("Doc", module.TestObject(name="Hole", type="Part::Cylinder"))
    assert reply == {"success": False, "object_name": "Hole", "error": "invalid shape"}
    assert [o.Name for o in doc.Objects] == ["Existing", "Hole"]
    assert doc.events == ["open", "commit"]


def test_missing_mesh_analysis_closes_transaction(factory: tuple[types.ModuleType, Document]) -> None:
    module, doc = factory
    reply = module.create_object_gui("Doc", module.TestObject(name="Mesh", type="Fem::FemMeshGmsh"))
    assert "analysis_name" in reply
    assert doc.events == ["open", "abort"]
