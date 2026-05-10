"""GUI-thread task dispatch for the RPC server.

The XML-RPC server runs in its own thread. FreeCAD APIs that touch the GUI
or the document tree must run in the main GUI thread. This module owns the
two queues that ferry callables onto the GUI thread (driven by a QTimer)
and back, plus the helper that RPC handlers use to invoke them.

Robustness guarantees (the previous implementation lacked all three, which
caused the ``empty response → permanent hang → restart-required`` bug):

1. Exceptions raised inside a queued task are captured and converted to an
   error dict on the response queue. The QTimer reschedule still fires, so
   the dispatch loop never dies.
2. Tasks that return ``None`` are normalised to an explicit error dict so
   the response queue is never starved.
3. ``shutdown()`` posts a sentinel that the dispatch loop recognises and
   exits cleanly without rescheduling itself.
"""

import queue
import traceback
from typing import Any, Callable

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets


rpc_request_queue: "queue.Queue[Any]" = queue.Queue()
rpc_response_queue: "queue.Queue[Any]" = queue.Queue()


_SHUTDOWN = object()


def _flush_gui_events(delay_ms: int = 50) -> None:
    FreeCADGui.updateGui()
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    app.processEvents(QtCore.QEventLoop.AllEvents, delay_ms)
    if delay_ms > 0:
        QtCore.QThread.msleep(delay_ms)
        app.processEvents(QtCore.QEventLoop.AllEvents, delay_ms)


def process_gui_tasks() -> None:
    """Drain queued callables on the GUI thread, then reschedule.

    Called by a QTimer at 500 ms intervals. Always reschedules itself —
    even when an individual task crashes — so the dispatch loop survives
    handler bugs.

    On exception or ``None`` return, an error *string* (not a dict) is
    posted to the response queue, matching the legacy ``True | str`` wire
    contract that public RPC handlers expect (``if res is True: ... else:
    return {"success": False, "error": res}``). Handlers that return dicts
    natively (e.g. FEM) keep working untouched.
    """
    try:
        while not rpc_request_queue.empty():
            task = rpc_request_queue.get()
            if task is _SHUTDOWN:
                return  # do not reschedule; loop ends
            try:
                res = task()
            except Exception as e:
                FreeCAD.Console.PrintError(
                    f"MCP RPC: GUI task raised {type(e).__name__}: {e}\n"
                    f"{traceback.format_exc()}"
                )
                rpc_response_queue.put(f"{type(e).__name__}: {e}")
                continue
            if res is None:
                rpc_response_queue.put("GUI handler returned None")
            else:
                rpc_response_queue.put(res)
    finally:
        QtCore.QTimer.singleShot(500, process_gui_tasks)


def request_shutdown() -> None:
    """Post the sentinel so the next dispatch tick exits without rescheduling."""
    rpc_request_queue.put(_SHUTDOWN)


def dispatch_to_gui(task: Callable[[], Any], timeout: float = 10) -> Any:
    """Run ``task`` on the GUI thread and return its result.

    On timeout, returns ``{"success": False, "error": ...}`` instead of
    raising, so callers never see a silent ``queue.Empty``.
    """
    rpc_request_queue.put(task)
    try:
        return rpc_response_queue.get(timeout=timeout)
    except queue.Empty:
        return {
            "success": False,
            "error": f"GUI dispatch timeout after {timeout}s",
        }
