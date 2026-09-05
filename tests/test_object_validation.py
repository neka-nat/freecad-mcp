from contextlib import contextmanager
from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import sys
import types
from typing import Iterator


ADDON_DIR = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
if str(ADDON_DIR) not in sys.path:
    sys.path.insert(0, str(ADDON_DIR))

from rpc_server.object_validation import object_validity_error


OBJECT_FACTORY_PATH = (
    ADDON_DIR / "rpc_server" / "object_factory.py"
)


class FakeConsole:
    messages: list[tuple[str, str]] = []

    @classmethod
    def PrintMessage(cls, message: str) -> None:
        cls.messages.append(("message", message))

    @classmethod
    def PrintError(cls, message: str) -> None:
        cls.messages.append(("error", message))


class FakeDocument:
    def __init__(self, obj: object):
        self.Name = "Doc"
        self.obj = obj
        self.recompute_count = 0

    def addObject(self, _obj_type: str, _name: str) -> object:
        return self.obj

    def getObject(self, name: str) -> object | None:
        return self.obj if name == getattr(self.obj, "Name", None) else None

    def recompute(self) -> None:
        self.recompute_count += 1


@contextmanager
def load_object_factory(
    doc: FakeDocument,
) -> Iterator[types.ModuleType]:
    """Load object_factory with minimal FreeCAD/ObjectsFem test doubles."""
    module_names = ["FreeCAD", "ObjectsFem", "rpc_server.property_mapper"]
    missing = object()
    saved = {name: sys.modules.get(name, missing) for name in module_names}

    freecad = types.ModuleType("FreeCAD")
    freecad.Document = FakeDocument
    freecad.DocumentObject = object
    freecad.Console = FakeConsole
    freecad.getDocument = lambda _name: doc

    sys.modules["FreeCAD"] = freecad
    sys.modules["ObjectsFem"] = types.ModuleType("ObjectsFem")
    sys.modules.pop("rpc_server.property_mapper", None)

    module_name = f"_object_factory_test_{id(doc)}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, OBJECT_FACTORY_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load object_factory from {OBJECT_FACTORY_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(module_name, None)
        for name, value in saved.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


@dataclass
class FakeObject:
    Name: str = "Object"
    TypeId: str = "Part::Feature"
    valid: bool = True
    State: list[str] = field(default_factory=lambda: ["Up-to-date"])
    status: str = ""
    Shape: object | None = None

    def isValid(self) -> bool:
        return self.valid

    def getStatusString(self) -> str:
        return self.status


def test_valid_shapeless_object_is_not_rejected() -> None:
    obj = FakeObject(Name="Body", Shape=None)

    assert object_validity_error(obj) is None


def test_invalid_object_reports_name_state_and_freecad_reason() -> None:
    obj = FakeObject(
        Name="Pad",
        valid=False,
        State=["Touched", "Invalid"],
        status="Linked shape object is empty",
    )

    error = object_validity_error(obj)

    assert error is not None
    assert "Pad" in error
    assert "Touched, Invalid" in error
    assert "Linked shape object is empty" in error


def test_object_without_validity_api_is_left_unchanged() -> None:
    obj = type("LegacyObject", (), {"Name": "Legacy"})()

    assert object_validity_error(obj) is None


def test_touched_object_is_rejected_even_when_is_valid_returns_true() -> None:
    obj = FakeObject(valid=True, State=["Touched"], status="Touched")

    error = object_validity_error(obj)

    assert error is not None
    assert "Touched" in error


def test_invalid_state_is_used_when_validity_api_is_missing() -> None:
    obj = type(
        "LegacyObject",
        (),
        {"Name": "Legacy", "State": ["Invalid"]},
    )()

    error = object_validity_error(obj)

    assert error is not None
    assert "Invalid" in error


def test_validity_check_exception_is_reported_as_failure() -> None:
    class BrokenObject:
        Name = "Broken"

        def isValid(self) -> bool:
            raise RuntimeError("invalid internal state")

    error = object_validity_error(BrokenObject())

    assert error is not None
    assert "validity could not be checked" in error
    assert "invalid internal state" in error


def test_create_object_returns_failure_with_created_object_name() -> None:
    created = FakeObject(
        Name="Pad",
        valid=False,
        State=["Touched", "Invalid"],
        status="Linked shape object is empty",
    )
    doc = FakeDocument(created)

    with load_object_factory(doc) as object_factory:
        request = object_factory.Object(
            name="Pad",
            type="PartDesign::Pad",
            properties={},
        )
        result = object_factory.create_object_gui("Doc", request)

    assert result["success"] is False
    assert result["object_name"] == "Pad"
    assert "Linked shape object is empty" in result["error"]
    assert doc.recompute_count == 1


def test_create_object_accepts_valid_shapeless_object() -> None:
    created = FakeObject(Name="Body", Shape=None)
    doc = FakeDocument(created)

    with load_object_factory(doc) as object_factory:
        request = object_factory.Object(
            name="Body",
            type="PartDesign::Body",
            properties={},
        )
        result = object_factory.create_object_gui("Doc", request)

    assert result == {"success": True, "object_name": "Body"}


def test_edit_object_returns_failure_with_existing_object_name() -> None:
    existing = FakeObject(
        Name="Cut",
        valid=False,
        State=["Touched", "Invalid"],
        status="Base or Tool is not set",
    )
    doc = FakeDocument(existing)

    with load_object_factory(doc) as object_factory:
        request = object_factory.Object(name="Cut", properties={})
        result = object_factory.edit_object_gui("Doc", request)

    assert result["success"] is False
    assert result["object_name"] == "Cut"
    assert "Base or Tool is not set" in result["error"]
    assert doc.recompute_count == 1
