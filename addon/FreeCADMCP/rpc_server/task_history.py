"""Bounded, GUI-independent history of dispatched operations and late results."""

import copy
import json
import threading
import time
from typing import Any


class TaskHistory:
    def __init__(self, keep: int = 20) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, dict[str, Any]] = {}
        self.keep = keep

    def update(self, task_id: str, **fields: Any) -> None:
        with self._lock:
            record = self._tasks.setdefault(task_id, {"task_id": task_id})
            record.update(fields)
            if fields.get("state") in {"done", "failed", "cancelled"}:
                record["finished"] = time.time()
                # Retain terminal records in completion order, not submission order.
                self._tasks.pop(task_id)
                self._tasks[task_id] = record
            finished = [key for key, item in self._tasks.items()
                        if item.get("state") in {"done", "failed", "cancelled"}]
            for key in finished[:-self.keep]:
                del self._tasks[key]

    def finish(self, task_id: str, result: Any, failed: bool) -> None:
        # Convert on the executing thread: readers must never inspect native
        # FreeCAD objects off-thread. Arbitrary commit() return values stay opaque.
        try:
            encoded = json.dumps(result, default=lambda _: "<non-JSON result>", allow_nan=False)
            truncated = len(encoded) > 65536
            value = {"preview": encoded[:65536]} if truncated else json.loads(encoded)
        except Exception:
            value, truncated = "<result unavailable>", False
        outcome = result.get("mutation_outcome") if type(result) is dict else None
        self.update(task_id, state="failed" if failed else "done",
                    mutation_outcome=outcome or ("partial_or_unknown" if failed else "completed"),
                    result=value, result_truncated=truncated)

    def snapshot(self, task_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if task_id is None:
                return {"success": True, "tasks": copy.deepcopy(list(self._tasks.values()))}
            if task_id not in self._tasks:
                return {"success": False, "error": f"Unknown or expired GUI task: {task_id}"}
            return {"success": True, "task": copy.deepcopy(self._tasks[task_id])}
