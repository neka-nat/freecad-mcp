import json
from typing import Any

from freecad_mcp.operations import core


class FakeFreeCAD:
    """Returns loads together with the solve, like the addon."""

    def __init__(self, loads: list[dict[str, Any]] | None, solved: dict[str, Any]) -> None:
        self.loads = loads
        self.solved = solved

    def execute_code(self, code: str, timeout: float | None = None) -> dict[str, Any]:
        raise AssertionError("Loads must come from the solve response, not a separate query")

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        return {**self.solved, "applied_loads": self.loads}

    def get_active_screenshot(self, view_name: str = "Isometric") -> None:
        return None


SOLVED = {"success": True, "max_von_mises_MPa": 0.0488, "max_displacement_mm": 0.000158, "node_count": 1063}
ONE_NEWTON = [
    {"name": "Fixed", "kind": "fixed", "references": ["Beam:Face1"]},
    {"name": "Load", "kind": "force", "newtons": 1.0, "references": ["Beam:Face2"], "direction": [0.0, 0.0, -1.0],
     "direction_from": "normal of the loaded face", "reversed": False},
]


def test_the_summary_states_the_force_in_newtons() -> None:
    reply = core.run_fem_analysis_operation(FakeFreeCAD(ONE_NEWTON, SOLVED), True, "Doc", "Analysis", 600, False)
    data = json.loads(reply[0].text)
    assert "Load = 1 N on Beam:Face2" in data["summary"] and "millinewtons" in data["summary"]
    assert data["applied_loads"] == ONE_NEWTON


def test_an_old_addon_response_warns_that_loads_are_unavailable() -> None:
    reply = core.run_fem_analysis_operation(FakeFreeCAD(None, SOLVED), True, "Doc", "Analysis", 600, False)
    data = json.loads(reply[0].text)
    assert data["applied_loads"] is None
    assert "Applied loads unavailable" in data["summary"]


def test_failed_load_inspection_is_a_tool_error() -> None:
    from freecad_mcp.responses import ErrorResponse

    freecad = FakeFreeCAD(None, {"success": False, "error": "FEM analysis failed during load inspection"})
    reply = core.run_fem_analysis_operation(freecad, True, "Doc", "Analysis", 600, False)
    assert isinstance(reply, ErrorResponse)
    assert "load inspection" in reply[0].text
