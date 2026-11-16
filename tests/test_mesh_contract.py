"""Mesher status and property validation must precede a success response."""

from types import SimpleNamespace as NS
import sys

import pytest
from test_create_object_atomic import factory


@pytest.mark.parametrize("mode,message", [
    ("exit", "exit code 1"), ("error", "mesher reported an error"),
    ("legacy", "legacy mesher error"), ("empty", "empty mesh"),
    ("unknown", "Unknown mesh property"),
])
def test_mesh_failures_are_not_reported_as_success(factory, monkeypatch, mode: str, message: str) -> None:
    module, doc = factory
    mesh = NS(Shape=None, Name="Mesh", FemMesh=NS(NodeCount=0 if mode == "empty" else 4, VolumeCount=1, FaceCount=0, EdgeCount=0))
    doc.Analysis = NS(addObject=lambda obj: [obj])
    doc.getObject = lambda name: object()
    monkeypatch.setattr(module.ObjectsFem, "makeMeshGmsh", lambda *args: mesh, raising=False)
    tool = NS(error=mode == "error", process=NS(exitCode=lambda: 1 if mode == "exit" else 0),
              create_mesh=lambda: "legacy mesher error" if mode == "legacy" else None)
    monkeypatch.setitem(sys.modules, "femmesh.gmshtools", NS(GmshTools=lambda obj: tool))
    props = {"Shape": "Box"}
    if mode == "unknown":
        props["UnknownSetting"] = 2
    request = module.TestObject("Mesh", "Fem::FemMeshGmsh", "Analysis", props)
    with pytest.raises((ValueError, RuntimeError), match=message):
        module._create_fem_mesh(doc, request)
