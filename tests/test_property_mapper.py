"""Tests for the addon's property mapper.

Focused on ``_to_color`` (RGB/RGBA coercion) and the ``ShapeColor`` wiring in
``set_object_property``. The module imports FreeCAD at top level, so we stub it
and load the file directly, as with the other addon tests.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_PROPERTY_MAPPER_PATH = (
    Path(__file__).resolve().parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "property_mapper.py"
)


def _load_property_mapper():
    sys.modules.setdefault("FreeCAD", MagicMock())
    spec = importlib.util.spec_from_file_location("addon_property_mapper", _PROPERTY_MAPPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


property_mapper = _load_property_mapper()
_to_color = property_mapper._to_color
set_object_property = property_mapper.set_object_property


def test_to_color_rgba_passthrough():
    assert _to_color([0.1, 0.2, 0.3, 0.5]) == (0.1, 0.2, 0.3, 0.5)


def test_to_color_rgb_defaults_alpha_to_one():
    assert _to_color([0.1, 0.2, 0.3]) == (0.1, 0.2, 0.3, 1.0)


def test_to_color_accepts_tuple_and_ints():
    assert _to_color((1, 0, 0)) == (1.0, 0.0, 0.0, 1.0)


def test_to_color_ignores_extra_components():
    assert _to_color([0.1, 0.2, 0.3, 0.4, 0.9]) == (0.1, 0.2, 0.3, 0.4)


@pytest.mark.parametrize("bad", [[0.1, 0.2], [], "red", 5, None])
def test_to_color_rejects_too_few_components(bad):
    with pytest.raises(ValueError):
        _to_color(bad)


class _FakeViewObject:
    pass


class _FakeObject:
    """Minimal stand-in for a FreeCAD DocumentObject for the ShapeColor path."""

    PropertiesList: list[str] = []  # ShapeColor lives on the ViewObject, not here

    def __init__(self):
        self.ViewObject = _FakeViewObject()


def test_set_shapecolor_rgb_applies_to_view_object():
    obj = _FakeObject()
    set_object_property(MagicMock(), obj, {"ShapeColor": [0.2, 0.4, 0.6]})
    assert obj.ViewObject.ShapeColor == (0.2, 0.4, 0.6, 1.0)


def test_set_view_object_dict_coerces_nested_shapecolor():
    obj = _FakeObject()
    set_object_property(
        MagicMock(),
        obj,
        {"ViewObject": {"ShapeColor": [0.2, 0.4, 0.6], "Transparency": 50}},
    )
    assert obj.ViewObject.ShapeColor == (0.2, 0.4, 0.6, 1.0)
    assert obj.ViewObject.Transparency == 50
