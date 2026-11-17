"""Regression test: one invalid shape must not break the whole document serialization.

See https://github.com/neka-nat/freecad-mcp/issues/109
"""

import importlib
import sys
import types
from pathlib import Path

# --- Stub FreeCAD so serialize.py can be imported without a FreeCAD install ---
freecad_stub = types.ModuleType("FreeCAD")


class _StubVector:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


class _StubRotation:
    Axis = _StubVector(0, 0, 1)
    Angle = 0.0


class _StubPlacement:
    Base = _StubVector()
    Rotation = _StubRotation()


class _BrokenShape:
    """Shape whose compute failed: every attribute read raises RuntimeError."""

    def __getattr__(self, name):
        raise RuntimeError("shape is invalid")


class _GoodShape:
    Volume = 42.0
    Area = 10.0
    Vertexes = [object() for _ in range(8)]
    Edges = [object() for _ in range(6)]
    Faces = [object() for _ in range(4)]


class _BoxedShape(_GoodShape):
    BoundBox = types.SimpleNamespace(
        XMin=-1.5, XMax=8.5, YMin=0.0, YMax=4.0, ZMin=2.25, ZMax=6.75
    )


class _NoBoundBoxShape(_GoodShape):
    """Measurable, but its bounding box cannot be read."""

    @property
    def BoundBox(self):
        raise RuntimeError("no bounding box")


freecad_stub.Vector = _StubVector
freecad_stub.Rotation = _StubRotation
freecad_stub.Placement = _StubPlacement


class _StubDocument:
    Name = "Doc"
    Label = "Doc"
    FileName = ""
    Objects = []


freecad_stub.Document = _StubDocument
sys.modules["FreeCAD"] = freecad_stub

serialize_path = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
sys.path.insert(0, str(serialize_path))
serialize = importlib.import_module("rpc_server.serialize")


def test_good_shape_serializes():
    result = serialize.serialize_shape(_GoodShape())
    assert result["Volume"] == 42.0
    assert result["VertexCount"] == 8


def test_bounding_box_comes_back_with_the_measurements():
    # Where the shape sits, which otherwise takes a separate scripted query to
    # find out: the counts alone do not say whether a part is even the right
    # way up.
    result = serialize.serialize_shape(_BoxedShape())
    assert result["BoundBox"] == {
        "XMin": -1.5, "XMax": 8.5,
        "YMin": 0.0, "YMax": 4.0,
        "ZMin": 2.25, "ZMax": 6.75,
    }


def test_a_shape_without_a_bounding_box_keeps_its_measurements():
    # Losing the volume over a missing bounding box is the worse trade, so the
    # two are read separately.
    result = serialize.serialize_shape(_NoBoundBoxShape())
    assert result["Volume"] == 42.0
    assert "BoundBox" not in result


def test_broken_shape_returns_error_dict_instead_of_raising():
    result = serialize.serialize_shape(_BrokenShape())
    assert "error" in result
    assert "invalid shape" in result["error"]


def test_none_shape_returns_none():
    assert serialize.serialize_shape(None) is None


def test_serialize_object_survives_broken_shape():
    obj = types.SimpleNamespace(
        Name="Pad",
        Label="Pad",
        TypeId="PartDesign::Pad",
        PropertiesList=[],
        Placement=_StubPlacement(),
        Shape=_BrokenShape(),
    )
    result = serialize.serialize_object(obj)
    assert result["Name"] == "Pad"
    assert "error" in result["Shape"]
