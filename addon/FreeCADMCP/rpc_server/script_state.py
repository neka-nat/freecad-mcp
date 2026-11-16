"""Exclusive ownership of the process-persistent script namespace."""

import threading
from typing import Any


class ScriptState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owner: str | None = None

    def claim(self, owner: str) -> bool:
        with self._lock:
            if self._owner is not None:
                return False
            self._owner = owner
            return True

    def release(self, owner: str) -> None:
        with self._lock:
            if self._owner == owner:
                self._owner = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"state": "busy" if self._owner else "idle", "owner": self._owner,
                    "namespace_lifetime": "FreeCAD process", "concurrency": "exclusive"}
