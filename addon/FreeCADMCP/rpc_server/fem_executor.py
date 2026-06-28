"""CalculiX-driven FEM analysis execution."""

import tempfile
import traceback

import FreeCAD
import ObjectsFem


def run_fem_analysis(doc_name: str, analysis_name: str) -> dict:
    """Run the CalculiX solver on an existing FEM analysis container.

    Always returns a dict with at least ``success`` and ``error``/result keys
    so the caller can pass it through to the wire response unchanged.
    """
    work_dir = None
    try:
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception:
            return {"success": False, "error": f"Document '{doc_name}' not found."}
        analysis = doc.getObject(analysis_name)
        if analysis is None:
            return {"success": False, "error": f"Analysis '{analysis_name}' not found."}
        if analysis.TypeId not in ("Fem::FemAnalysis", "Fem::FemAnalysisPython"):
            return {"success": False, "error": f"'{analysis_name}' is not a FEM analysis (TypeId={analysis.TypeId})."}

        solver = None
        for member in analysis.Group:
            tid = getattr(member, "TypeId", "")
            if "SolverCcx" in tid or "SolverCalculix" in tid:
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

        from femtools import ccxtools

        fea = ccxtools.FemToolsCcx(analysis=analysis, solver=solver)
        fea.update_objects()

        work_dir = tempfile.mkdtemp(prefix="freecad_mcp_fem_")
        fea.setup_working_dir(work_dir)
        fea.setup_ccx()

        prereq_msg = fea.check_prerequisites()
        if prereq_msg:
            return {"success": False, "error": f"Prerequisites failed: {prereq_msg}", "working_dir": work_dir}

        fea.purge_results()
        fea.run()
        fea.load_results()

        result_obj = None
        for member in analysis.Group:
            if "Result" in getattr(member, "TypeId", "") and hasattr(member, "vonMises"):
                result_obj = member
                break
        if result_obj is None:
            return {"success": False, "error": "Solver ran but no result object was produced.", "working_dir": work_dir}

        # vonMises / DisplacementLengths can be None on a degenerate run.
        vm = list(getattr(result_obj, "vonMises", None) or [])
        disp = list(getattr(result_obj, "DisplacementLengths", None) or [])
        doc.recompute()

        return {
            "success": True,
            "result_object": result_obj.Name,
            "node_count": len(vm),
            "max_von_mises_MPa": max(vm) if vm else None,
            "min_von_mises_MPa": min(vm) if vm else None,
            "max_displacement_mm": max(disp) if disp else None,
            "working_dir": work_dir,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "working_dir": work_dir,
        }
