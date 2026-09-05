"""Thread-safe health state for the FreeCAD GUI dispatch bridge."""

import threading
import time
from collections.abc import Callable
from typing import Any


class DispatchHealth:
    """Track the currently running GUI task and whether it timed out."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._active_task_id = 0
        self._operation = ""
        self._started_at = 0.0
        self._timed_out = False
        self._timeout_seconds = 0.0

    def start(self, task_id: int, operation: str) -> None:
        with self._lock:
            self._active_task_id = task_id
            self._operation = operation
            self._started_at = self._clock()
            self._timed_out = False
            self._timeout_seconds = 0.0

    def finish(self, task_id: int) -> None:
        """Clear state only when the finishing task is still the active one."""
        with self._lock:
            if self._active_task_id != task_id:
                return
            self._active_task_id = 0
            self._operation = ""
            self._started_at = 0.0
            self._timed_out = False
            self._timeout_seconds = 0.0

    def mark_timed_out(self, task_id: int, timeout: float) -> dict[str, Any] | None:
        """Mark a running task as timed out and return the resulting snapshot."""
        with self._lock:
            if self._active_task_id != task_id:
                return None
            self._timed_out = True
            self._timeout_seconds = float(timeout)
            return self._snapshot_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def rejection(self) -> dict[str, Any] | None:
        """Return an immediate failure while a timed-out task is still running."""
        snapshot = self.snapshot()
        if snapshot["state"] != "stuck":
            return None
        return stuck_failure(snapshot, just_timed_out=False)

    def _snapshot_locked(self) -> dict[str, Any]:
        if self._active_task_id == 0:
            return {
                "state": "healthy",
                "task_id": 0,
                "operation": "",
                "running_for_seconds": 0.0,
                "timeout_seconds": 0.0,
            }

        elapsed = max(0.0, self._clock() - self._started_at)
        return {
            "state": "stuck" if self._timed_out else "busy",
            "task_id": self._active_task_id,
            "operation": self._operation,
            "running_for_seconds": round(elapsed, 3),
            "timeout_seconds": self._timeout_seconds,
        }


def stuck_failure(
    snapshot: dict[str, Any], *, just_timed_out: bool
) -> dict[str, Any]:
    """Build the structured error returned for an uninterruptible GUI task."""
    operation = snapshot.get("operation") or "unknown GUI operation"
    running_for = float(snapshot.get("running_for_seconds", 0.0))
    timeout = float(snapshot.get("timeout_seconds", 0.0))

    if just_timed_out:
        lead = (
            f"GUI dispatch timed out after {timeout:g}s while '{operation}' was "
            "still running on FreeCAD's GUI thread."
        )
    else:
        lead = (
            f"GUI dispatch unavailable: '{operation}' timed out after "
            f"{timeout:g}s and is still running "
            f"({running_for:.1f}s elapsed)."
        )

    return {
        "success": False,
        "code": "GUI_DISPATCH_STUCK",
        "error": (
            lead
            + " The task cannot be safely cancelled. Future GUI operations "
            "will fail immediately until it finishes; restart FreeCAD if it "
            "remains stuck."
        ),
        "dispatch": snapshot,
    }
