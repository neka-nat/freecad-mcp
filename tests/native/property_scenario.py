"""Native property round-trips, transactional edits and mesh failure checks."""

import math
import sys
from types import SimpleNamespace as NS

import FreeCAD as App
import Fem
import ObjectsFem

sys.path.insert(0, ADDON_PATH)
from rpc_server.serialize import serialize_value
from rpc_server.property_mapper import Object, set_object_property
from rpc_server.object_factory import create_object_gui, edit_object_gui
from rpc_server import object_factory
from femmesh import gmshtools

doc = App.newDocument("NativeContracts")
original_mesher = gmshtools.GmshTools
try:
    box = doc.addObject("Part::Box", "Box")
    box.Placement = App.Placement(App.Vector(1, 2, 3), App.Rotation(App.Vector(0, 0, 1), 90))
    placement = serialize_value(box.Placement)
    assert abs(placement["Rotation"]["Angle"] - 90) < 1e-9
    set_object_property(doc, box, {"Placement": placement})
    assert abs(math.degrees(box.Placement.Rotation.Angle) - 90) < 1e-9
    assert serialize_value({"name": "Steel", "empty": None}) == {"name": "Steel", "empty": None}
    group = doc.addObject("App::DocumentObjectGroup", "Group")
    group.addObject(box)
    set_object_property(doc, group, {"Group": serialize_value(group.Group)})
    assert group.Group == [box]
    doc.recompute()

    for undo_mode in (0, 1):
        doc.UndoMode = undo_mode
        before = box.Length.Value
        reply = edit_object_gui(doc.Name, Object(box.Name, properties={"Length": 42, "Width": "invalid"}))
        assert not reply["success"] and "rolled back" in reply["error"], reply
        assert box.Length.Value == before
        assert doc.UndoMode == undo_mode
        assert edit_object_gui(doc.Name, Object(box.Name, properties={"Length": 15})) is True
        assert box.Length.Value == 15
        assert doc.UndoMode == undo_mode

    analysis = ObjectsFem.makeAnalysis(doc, "Analysis")
    original_factory = object_factory._create_by_type
    try:
        for undo_mode in (0, 1):
            doc.UndoMode = undo_mode
            box.Length = 10
            doc.recompute()
            before = {item.Name for item in doc.Objects}
            def failing_factory(document, request):
                box.Length = 77
                document.addObject("Part::Box", "Temporary")
                raise ValueError("factory changed an existing object")
            object_factory._create_by_type = failing_factory
            result = create_object_gui(doc.Name, Object("Temporary", "Part::Box"))
            assert result["mutation_outcome"] == "rolled_back", result
            assert box.Length.Value == 10
            assert {item.Name for item in doc.Objects} == before
            assert doc.UndoMode == undo_mode
    finally:
        object_factory._create_by_type = original_factory
    class Mesher:
        exit_code = 0
        empty = False
        def __init__(self, mesh):
            self.mesh = mesh
            self.process = NS(exitCode=lambda: self.exit_code)
        def create_mesh(self):
            if self.exit_code or self.empty:
                return None
            mesh = Fem.FemMesh()
            for index, point in enumerate([(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)], 1):
                mesh.addNode(*point, index)
            mesh.addVolume([1, 2, 3, 4])
            self.mesh.FemMesh = mesh
            return None
    gmshtools.GmshTools = Mesher
    before = {obj.Name for obj in doc.Objects}
    for mode in ("exit", "empty", "unknown"):
        Mesher.exit_code = 1 if mode == "exit" else 0
        Mesher.empty = mode == "empty"
        properties = {"Shape": box.Name}
        if mode == "unknown":
            properties["CharacteristicLenghtMax"] = 3
        result = create_object_gui(doc.Name, Object("BadMesh", "Fem::FemMeshGmsh", analysis.Name, properties))
        assert result["mutation_outcome"] == "rolled_back" and "no new objects remain" in result["error"], result
        assert {obj.Name for obj in doc.Objects} == before
    Mesher.exit_code = 0
    Mesher.empty = False
    result = create_object_gui(doc.Name, Object("Mesh", "Fem::FemMeshGmsh", analysis.Name, {"Part": box.Name, "ElementSizeMax": 3}))
    assert result["success"], result
    mesh = doc.getObject(result["object_name"])
    assert mesh.FemMesh.NodeCount == 4
    assert edit_object_gui(doc.Name, Object(mesh.Name, properties={"Shape": box.Name, "ElementSizeMax": 4})) is True
    assert mesh.Shape == box and mesh.CharacteristicLengthMax.Value == 4
    print("NATIVE_PROPERTY_CONTRACTS_OK", flush=True)
finally:
    gmshtools.GmshTools = original_mesher
    App.closeDocument(doc.Name)
