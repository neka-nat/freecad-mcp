from pathlib import Path
import sys


ADDON_DIR = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
if str(ADDON_DIR) not in sys.path:
    sys.path.insert(0, str(ADDON_DIR))

from rpc_server.dispatch_health import DispatchHealth, stuck_failure


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_health_moves_from_busy_to_stuck_and_rejects_immediately() -> None:
    clock = FakeClock()
    health = DispatchHealth(clock)
    health.start(7, "execute_code")
    clock.now += 90.0

    busy = health.snapshot()
    stuck = health.mark_timed_out(7, 90)
    rejection = health.rejection()

    assert busy["state"] == "busy"
    assert busy["running_for_seconds"] == 90.0
    assert stuck is not None
    assert stuck["state"] == "stuck"
    assert rejection is not None
    assert rejection["code"] == "GUI_DISPATCH_STUCK"
    assert "execute_code" in rejection["error"]
    assert "restart FreeCAD" in rejection["error"]


def test_finishing_timed_out_task_restores_healthy_state() -> None:
    clock = FakeClock()
    health = DispatchHealth(clock)
    health.start(11, "delete_object")
    health.mark_timed_out(11, 60)

    health.finish(11)

    assert health.snapshot()["state"] == "healthy"
    assert health.rejection() is None


def test_other_task_cannot_mark_or_clear_active_task() -> None:
    clock = FakeClock()
    health = DispatchHealth(clock)
    health.start(3, "create_object")

    assert health.mark_timed_out(4, 60) is None
    health.finish(4)

    assert health.snapshot()["state"] == "busy"
    assert health.snapshot()["task_id"] == 3


def test_initial_timeout_message_explains_future_fail_fast() -> None:
    snapshot = {
        "state": "stuck",
        "task_id": 5,
        "operation": "remove_broken_feature",
        "running_for_seconds": 60.0,
        "timeout_seconds": 60.0,
    }

    result = stuck_failure(snapshot, just_timed_out=True)

    assert result["success"] is False
    assert result["dispatch"] == snapshot
    assert "timed out after 60s" in result["error"]
    assert "fail immediately" in result["error"]
