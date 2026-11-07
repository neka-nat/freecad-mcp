"""FreeCAD 1.x solver lifecycle and load reporting without a native install."""

import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
from typing import Any

import pytest

ADDON = Path(__file__).resolve().parents[1] / "addon/FreeCADMCP/rpc_server"


def load_module(name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ADDON / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Quantity:
    def __init__(self, value: float, unit: str):
        self.Value, self.unit = value, unit

    def getValueAs(self, unit: str) -> Any:
        assert unit == self.unit
        return NS(Value=self.Value)


@pytest.fixture
def fem(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    solver = NS(Name="ConfiguredSolver", TypeId="Fem::FemSolverObjectPython", Proxy=NS(Type="Fem::SolverCcxTools"))
    force = NS(Name="Load", TypeId="Fem::ConstraintForce", Force=Quantity(0.1, "N"),
               DirectionVector=NS(x=0, y=0, z=-1), Direction=None, Reversed=True,
               References=[(NS(Name="Beam"), ["Face2"])])
    analysis = NS(Name="Analysis", TypeId="Fem::FemAnalysis", Group=[solver, force])
    doc = NS(Name="Doc", getObject=lambda name: analysis if name == "Analysis" else None, recompute=lambda: None)
    state = NS(analysis=analysis, doc=doc, force=force, solver=solver, created=0,
               runs=0, loads=0, tools=[], make_result=True, purge=True, fail=False)

    def make_solver(doc: Any, name: str) -> Any:
        state.created += 1
        return NS(Name=name, TypeId="Fem::FemSolverObjectPython", Proxy=NS(Type="Fem::SolverCcxTools"))

    analysis.addObject = analysis.Group.append

    class FemTools:
        def __init__(self, analysis: Any, solver: Any):
            self.analysis, self.solver = analysis, solver
            state.tools.append(self)

        def update_objects(self) -> None:
            pass

        def setup_working_dir(self, path: str | None = None, create: bool = False) -> None:
            self.working_dir = path or "global-preference-directory"

        def setup_ccx(self) -> None:
            self.ccx_binary = os.path.join(".", "ccx.exe")

        def check_prerequisites(self) -> str:
            return ""

        def purge_results(self) -> None:
            if state.purge:
                analysis.Group[:] = [o for o in analysis.Group if "Result" not in o.TypeId]

        def load_results(self) -> None:
            state.loads += 1
            if state.make_result:
                analysis.Group.append(NS(Name=f"Result{state.loads}", TypeId="Fem::FemResultObjectPython",
                                         vonMises=[1., 2.], DisplacementLengths=[0.1, 0.2]))

        def run(self) -> bool:
            state.runs += 1
            self.setup_working_dir()
            self.setup_ccx()  # upstream repeats both setup operations
            assert os.path.isabs(self.ccx_binary)
            assert self.working_dir != "global-preference-directory"
            if state.fail:
                return False
            self.load_results()
            return True

    modules = {
        "FreeCAD": NS(getDocument=lambda name: doc),
        "ObjectsFem": NS(makeSolverCalculiXCcxTools=make_solver),
        "femtools": NS(ccxtools=NS(FemToolsCcx=FemTools)),
        "rpc_server.fem_loads": load_module("_fem_loads", "fem_loads.py"),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    state.module = load_module("_fem_executor", "fem_executor.py")
    monkeypatch.setattr(state.module.tempfile, "mkdtemp", lambda **kw: str(tmp_path))
    return state


def test_repeated_runs_reuse_configured_solver_and_load_once(fem: Any) -> None:
    for count in (1, 2):
        result = fem.module.run_fem_analysis("Doc", "Analysis")
        assert result["success"], result
        assert result["solver_object"] == "ConfiguredSolver"
        assert result["result_objects"] == [f"Result{count}"]
        assert len(fem.module._mechanical_results(fem.analysis)) == 1
        assert result["applied_loads"][0]["newtons"] == 0.1
        assert result["applied_loads"][0]["direction"] == [0, 0, -1]
    assert fem.created == 0 and fem.loads == fem.runs == 2


def test_no_solver_creates_exactly_one(fem: Any) -> None:
    fem.analysis.Group.remove(fem.solver)
    for _ in range(2):
        assert fem.module.run_fem_analysis("Doc", "Analysis")["success"]
    assert fem.created == 1


def test_stale_result_is_not_reported_as_a_new_solve(fem: Any) -> None:
    fem.purge, fem.make_result = False, False
    fem.analysis.Group.append(NS(Name="Stale", TypeId="Fem::FemResultObjectPython", vonMises=[999]))
    result = fem.module.run_fem_analysis("Doc", "Analysis")
    assert not result["success"] and "no new mechanical result" in result["error"]
    assert fem.loads == 1


def test_new_result_is_selected_even_when_an_old_result_survives(fem: Any) -> None:
    fem.purge = False
    fem.analysis.Group.append(NS(Name="Stale", TypeId="Fem::FemResultObjectPython", vonMises=[999]))
    result = fem.module.run_fem_analysis("Doc", "Analysis")
    assert result["success"] and result["result_object"] == "Result1"
    assert result["max_von_mises_MPa"] == 2


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_failed_load_read_prevents_solver_and_preserves_results(fem: Any, value: float) -> None:
    fem.force.Force = Quantity(value, "N")
    fem.analysis.Group.append(NS(Name="Existing", TypeId="Fem::FemResultObjectPython", vonMises=[1]))
    result = fem.module.run_fem_analysis("Doc", "Analysis")
    assert not result["success"] and "load inspection" in result["error"]
    assert fem.runs == fem.loads == 0
    assert any(o.Name == "Existing" for o in fem.analysis.Group)


def test_solver_failure_does_not_load_or_report_results(fem: Any) -> None:
    fem.fail = True
    result = fem.module.run_fem_analysis("Doc", "Analysis")
    assert not result["success"] and "returned False" in result["error"]
    assert fem.loads == 0


def test_pressure_fixed_and_linked_direction_are_reported(fem: Any) -> None:
    beam = NS(Name="Beam")
    fem.force.Direction = (beam, ["Edge3"])
    fem.analysis.Group.extend([
        NS(Name="Pressure", TypeId="Fem::ConstraintPressure", Pressure=Quantity(2, "MPa"),
           References=[(beam, "Face3")], Reversed=False),
        NS(Name="Fixed", TypeId="Fem::ConstraintFixed", References=[(beam, ["Face1"])]),
    ])
    result = fem.module.run_fem_analysis("Doc", "Analysis")
    force, pressure, fixed = result["applied_loads"]
    assert force["direction_from"] == "along Beam:Edge3"
    assert pressure["megapascals"] == 2 and pressure["references"] == ["Beam:Face3"]
    assert fixed["kind"] == "fixed" and fixed["references"] == ["Beam:Face1"]
