import importlib.util
import sys
import types
import unittest
from pathlib import Path


SERIALIZE_PATH = (
    Path(__file__).resolve().parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "serialize.py"
)


class FakeVector:
    pass


class FakeRotation:
    pass


class FakePlacement:
    pass


class FakeDocument:
    pass


class FakeQuantity:
    def __str__(self) -> str:
        return "20 mm"


def make_freecad_module(color_type: type | None = None) -> types.ModuleType:
    module = types.ModuleType("FreeCAD")
    module.Vector = FakeVector
    module.Rotation = FakeRotation
    module.Placement = FakePlacement
    module.Document = FakeDocument
    if color_type is not None:
        module.Color = color_type
    return module


def load_serialize_module(freecad_module: types.ModuleType) -> types.ModuleType:
    module_name = f"_freecad_mcp_serialize_test_{id(freecad_module)}"
    original_freecad = sys.modules.get("FreeCAD")
    sys.modules["FreeCAD"] = freecad_module
    try:
        spec = importlib.util.spec_from_file_location(module_name, SERIALIZE_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load serialize module from {SERIALIZE_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if original_freecad is None:
            sys.modules.pop("FreeCAD", None)
        else:
            sys.modules["FreeCAD"] = original_freecad
        sys.modules.pop(module_name, None)


class SerializeValueTests(unittest.TestCase):
    def test_unknown_values_serialize_when_color_type_is_missing(self) -> None:
        serialize = load_serialize_module(make_freecad_module())

        self.assertEqual(serialize.serialize_value(FakeQuantity()), "20 mm")

    def test_object_properties_do_not_hide_missing_color_type_errors(self) -> None:
        serialize = load_serialize_module(make_freecad_module())
        obj = types.SimpleNamespace(
            Name="TestBox",
            Label="TestBox",
            TypeId="Part::Box",
            PropertiesList=["Length"],
            Length=FakeQuantity(),
        )

        result = serialize.serialize_object(obj)

        self.assertEqual(result["Properties"]["Length"], "20 mm")

    def test_color_values_serialize_when_color_type_exists(self) -> None:
        class FakeColor:
            def __iter__(self):
                return iter((0.1, 0.2, 0.3, 1.0))

        serialize = load_serialize_module(make_freecad_module(FakeColor))

        self.assertEqual(serialize.serialize_value(FakeColor()), (0.1, 0.2, 0.3, 1.0))


if __name__ == "__main__":
    unittest.main()
