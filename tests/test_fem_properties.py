"""Reject ambiguous forces and resolve FEM direction links."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from typing import Any

import pytest


@pytest.fixture
def mapper(monkeypatch: pytest.MonkeyPatch) -> Any:
    class Quantity:
        def __init__(self, value: str):
            self.parts = value.split()

        def getValueAs(self, unit: str) -> Any:
            if len(self.parts) != 2 or self.parts[1] != unit:
                raise ValueError("incompatible units")
            return NS(Value=float(self.parts[0]))

    freecad = NS(Document=object, DocumentObject=object, Units=NS(Quantity=Quantity),
                 Console=NS(PrintError=lambda message: None))
    monkeypatch.setitem(sys.modules, "FreeCAD", freecad)
    path = Path(__file__).resolve().parents[1] / "addon/FreeCADMCP/rpc_server/property_mapper.py"
    spec = importlib.util.spec_from_file_location("_fem_property_mapper", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", [100, 100.0, "100", "100 mm", "nan N", "inf N"])
def test_force_requires_finite_explicit_units(mapper: Any, value: Any) -> None:
    obj = NS(TypeId="Fem::ConstraintForce", PropertiesList=["Force"], Force="1 N")
    with pytest.raises(ValueError, match="Force requires"):
        mapper.set_object_property(NS(), obj, {"Force": value})
    assert obj.Force == "1 N"


def test_explicit_force_is_not_rescaled(mapper: Any) -> None:
    obj = NS(TypeId="Fem::ConstraintForce", PropertiesList=["Force"], Force=None)
    mapper.set_object_property(NS(), obj, {"Force": "100 N"})
    assert obj.Force == "100 N"


@pytest.mark.parametrize("value", [{"object_name": "Beam", "edge": "Edge3"}, ["Beam", ["Edge3"]]])
def test_direction_resolves_one_linked_subelement(mapper: Any, value: Any) -> None:
    beam = NS(getSubObject=lambda sub: object() if sub == "Edge3" else None)
    doc = NS(getObject=lambda name: beam if name == "Beam" else None)
    obj = NS(TypeId="Fem::ConstraintForce", PropertiesList=["Direction"], Direction=None)
    mapper.set_object_property(doc, obj, {"Direction": value})
    assert obj.Direction == (beam, ["Edge3"])


def test_missing_direction_reference_is_an_error(mapper: Any) -> None:
    doc = NS(getObject=lambda name: None)
    obj = NS(TypeId="Fem::ConstraintForce", PropertiesList=["Direction"], Direction=None)
    with pytest.raises(ValueError, match="not found"):
        mapper.set_object_property(doc, obj, {"Direction": {"object_name": "Missing", "edge": "Edge1"}})
