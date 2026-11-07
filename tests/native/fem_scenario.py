"""Executed inside native FreeCAD by test_headless_native.py."""

import json
import os
from pathlib import Path
import sys

import FreeCAD as App
import ObjectsFem

sys.path.insert(0, ADDON_PATH)
from rpc_server.fem_executor import run_fem_analysis
from rpc_server.object_factory import create_object_gui, edit_object_gui
from rpc_server.property_mapper import Object

doc = App.newDocument("NativePriority")
try:
    for undo in (0, 1):
        doc.UndoMode = undo
        before = [o.Name for o in doc.Objects]
        for kind, props in [
            ("Part::Cylinder", {"Radius": 8, "Placement": "not a placement"}),
            ("Fem::MaterialCommon", {"Material": {"PoissonRatio": 0.3}}),
            ("Fem::ConstraintForce", {"Force": 100}),
        ]:
            reply = create_object_gui(doc.Name, Object("Bad", kind, properties=props))
            assert isinstance(reply, str) and "no new objects remain" in reply, reply
            assert [o.Name for o in doc.Objects] == before

    from femexamples.ccx_cantilever_faceload import setup
    setup(doc, test_mode=True)  # bundled deterministic tetrahedral mesh
    analysis = doc.Analysis
    solver = doc.CalculiXCcxTools
    force = doc.ConstraintForce
    # No implicit reinterpretation: API calls need units; existing model
    # values set through native Python retain FreeCAD's original semantics.
    reply = edit_object_gui(doc.Name, Object(force.Name, properties={"Force": "9000000 N"}))
    assert reply is True, reply
    reply = edit_object_gui(doc.Name, Object(force.Name, properties={
        "Direction": {"object_name": "Box", "edge": "Edge5"}, "Reversed": True,
    }))
    assert reply is True, reply

    ccx = Path(CCX_PATH).resolve()
    os.chdir(ccx.parent)
    # Exercise the Windows first-run failure with a relative binary path.
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").SetString(
        "ccxBinaryPath", os.path.join(".", ccx.name),
    )
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").SetInt("AnalysisNumCPUs", 2)
    reports = []
    counts = []
    for index in range(2):
        if index:
            force.Force = 9000000  # native millinewtons -> 9000 N
            doc.recompute()
        reply = run_fem_analysis(doc.Name, analysis.Name)
        assert reply["success"], reply
        assert reply["solver_object"] == solver.Name
        reported_force = next(x for x in reply["applied_loads"] if x["kind"] == "force")
        assert reported_force["newtons"] == (9000 if index else 9000000), reported_force
        assert Path(reply["working_dir"]).is_dir()
        assert list(Path(reply["working_dir"]).glob("*.inp")), reply
        assert len(reply["result_objects"]) == 1, reply
        assert sum(getattr(getattr(o, "Proxy", None), "Type", "") == "Fem::SolverCcxTools" for o in analysis.Group) == 1
        counts.append(len(doc.Objects))
        reports.append(reply)
    assert counts[0] == counts[1], counts
    for key in ("max_von_mises_MPa", "max_displacement_mm"):
        assert abs(reports[0][key] / reports[1][key] - 1000) < 0.1, reports
    print("NATIVE_FEM_OK", json.dumps({"version": App.Version(), "reports": reports, "object_counts": counts}))
finally:
    App.closeDocument(doc.Name)
