"""CalculiX-driven FEM analysis execution."""

import os
import tempfile
import traceback
from typing import Any

import FreeCAD
import ObjectsFem

from rpc_server.fem_loads import applied_loads


def _solver_tools(analysis: Any, solver: Any) -> Any:
    from femtools import ccxtools

    class AbsoluteCcxTools(ccxtools.FemToolsCcx):
        """Keep ccx executable paths valid when FreeCAD changes directory."""

        def setup_working_dir(self, param_working_dir: str | None = None, create: bool = False) -> None:
            if param_working_dir is not None:
                self._mcp_working_dir = param_working_dir
            # run() repeats setup with no argument; retain this call's isolated
            # directory instead of falling back to global FEM preferences.
            super().setup_working_dir(getattr(self, "_mcp_working_dir", None), create=create)

        def setup_ccx(self, *args: Any, **kwargs: Any) -> None:
            super().setup_ccx(*args, **kwargs)
            # ccx_run calls setup_ccx again, so normalize on every lookup.
            if self.ccx_binary:
                self.ccx_binary = os.path.abspath(self.ccx_binary)

    return AbsoluteCcxTools(analysis=analysis, solver=solver)


def _mechanical_results(analysis: Any) -> list[Any]:
    return [
        member for member in analysis.Group
        if "Result" in getattr(member, "TypeId", "") and hasattr(member, "vonMises")
    ]


def run_fem_analysis(doc_name: str, analysis_name: str) -> dict:
    """Run the CalculiX solver on an existing FEM analysis container.

    Always returns a dict with at least ``success`` and ``error``/result keys
    so the caller can pass it through to the wire response unchanged.
    """
    work_dir = None
    stage = "initialization"
    try:
        stage = "document lookup"
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception:
            return {"success": False, "error": f"Document '{doc_name}' not found."}
        analysis = doc.getObject(analysis_name)
        if analysis is None:
            return {"success": False, "error": f"Analysis '{analysis_name}' not found."}
        if analysis.TypeId not in ("Fem::FemAnalysis", "Fem::FemAnalysisPython"):
            return {"success": False, "error": f"'{analysis_name}' is not a FEM analysis (TypeId={analysis.TypeId})."}

        stage = "solver resolution"
        solver = None
        for member in analysis.Group:
            tid = getattr(member, "TypeId", "")
            proxy_type = getattr(getattr(member, "Proxy", None), "Type", "")
            if "SolverCcx" in tid or "SolverCalculix" in tid or proxy_type in {
                "Fem::SolverCcxTools", "Fem::SolverCalculiX", "Fem::SolverCalculix",
            }:
                solver = member
                break
        if solver is None:
            solver_factory = (
                getattr(ObjectsFem, "makeSolverCalculiXCcxTools", None)
                or getattr(ObjectsFem, "makeSolverCalculixCcxTools", None)
            )
            if solver_factory is None:
                return {"success": False, "error": "ObjectsFem has no Calculix solver factory."}
            solver = solver_factory(doc, "CalculiX")
            analysis.addObject(solver)

        stage = "solver setup"
        fea = _solver_tools(analysis, solver)
        fea.update_objects()

        work_dir = tempfile.mkdtemp(prefix="freecad_mcp_fem_")
        fea.setup_working_dir(work_dir)
        fea.setup_ccx()

        stage = "prerequisite check"
        prereq_msg = fea.check_prerequisites()
        if prereq_msg:
            return {"success": False, "error": f"Prerequisites failed: {prereq_msg}", "working_dir": work_dir}

        stage = "load inspection"
        doc.recompute()
        loads = applied_loads(analysis)

        stage = "solver execution"
        fea.purge_results()
        old_results = {member.Name for member in _mechanical_results(analysis)}
        # FemToolsCcx.run() reports CalculiX failures by returning False rather
        # than raising; None is returned on success in some FreeCAD versions,
        # so only an explicit False is treated as a failure.
        if fea.run() is False:
            return {
                "success": False,
                "error": "CalculiX solver run failed (fea.run() returned False); inspect the .dat/.frd output in working_dir.",
                "working_dir": work_dir,
            }

        stage = "result loading"
        # run() loads the results itself. Loading again duplicates meshes,
        # result sets and DAT text objects. Never report a surviving old set.
        results = [member for member in _mechanical_results(analysis) if member.Name not in old_results]
        if not results:
            return {"success": False, "error": "Solver ran but no new mechanical result object was produced.", "working_dir": work_dir}
        result_obj = results[0]

        stage = "result extraction"
        # vonMises / DisplacementLengths can be None on a degenerate run.
        vm = list(getattr(result_obj, "vonMises", None) or [])
        disp = list(getattr(result_obj, "DisplacementLengths", None) or [])
        doc.recompute()

        return {
            "success": True,
            "result_object": result_obj.Name,
            "result_objects": [member.Name for member in results],
            "solver_object": solver.Name,
            "applied_loads": loads,
            "node_count": len(vm),
            "max_von_mises_MPa": max(vm) if vm else None,
            "min_von_mises_MPa": min(vm) if vm else None,
            "max_displacement_mm": max(disp) if disp else None,
            "working_dir": work_dir,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"FEM analysis failed during {stage}: {type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "working_dir": work_dir,
        }
