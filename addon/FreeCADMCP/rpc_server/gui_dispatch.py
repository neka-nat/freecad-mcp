"""GUI-thread task dispatch for the RPC server.

The XML-RPC server runs in its own thread. FreeCAD APIs that touch the GUI
or the document tree must run in the main GUI thread. This module owns the
queue that ferries wrapped callables onto the GUI thread and the helper that
RPC handlers use to invoke them.

Robustness and performance guarantees:

1. Per-call response queues: each ``dispatch_to_gui`` call owns its own
   ``queue.Queue``. A timeout in one call can never corrupt the response for
   a subsequent call.
2. Immediate wake via Qt signal: ``dispatch_to_gui`` emits a signal from the
   RPC thread; the GUI thread processes the task immediately rather than
   waiting for the next 500 ms heartbeat tick. The 500 ms heartbeat is kept
   only as a fallback.
3. Mouse-button guard: ``process_gui_tasks`` skips the current tick while
   mouse buttons are held so MCP tasks cannot interrupt 3D navigation drags.
4. Clean shutdown: ``request_shutdown`` sets a module flag (and posts the
   ``_SHUTDOWN`` sentinel to break an in-progress drain). Heartbeat ticks
   carry a generation id from ``start_heartbeat``; a tick whose id is stale
   or that observes the shutdown flag exits without rescheduling, so
   stop/start cycles can never stack multiple live heartbeat chains.
5. Exception isolation: exceptions inside a task are caught, logged, and
   returned as error strings; they never kill the dispatch loop.
"""

import queue
import time
import traceback
from typing import Any, Callable

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets


_rpc_request_queue: "queue.Queue[Any]" = queue.Queue()
_SHUTDOWN = object()
_processing = False  # re-entrancy guard: True while process_gui_tasks is draining
_processing_since: float = 0.0  # wall-clock time when _processing became True
_chain_id = 0  # heartbeat generation; bumped by start_heartbeat to kill stale chains
_shutdown_requested = False  # set by request_shutdown; suppresses heartbeat rescheduling


class _WakeSignal(QtCore.QObject):
    """Qt signal bridge for cross-thread GUI-task wakeup.

    Must be created on the GUI thread (``init_waker``). Emitting from the
    RPC thread is safe: Qt delivers the connection with ``QueuedConnection``,
    so the slot always fires in the GUI thread's event loop.
    """
    _sig = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self._sig.connect(self._on_wake, QtCore.Qt.QueuedConnection)

    def wake(self) -> None:
        self._sig.emit()

    def _on_wake(self) -> None:
        process_gui_tasks()


_waker: "_WakeSignal | None" = None


def init_waker() -> None:
    """Create the wake-signal bridge. Call once from the GUI thread."""
    global _waker
    _waker = _WakeSignal()


def cleanup_waker() -> None:
    """Release the wake-signal bridge on server stop."""
    global _waker
    _waker = None


def _flush_gui_events(delay_ms: int = 20) -> None:
    FreeCADGui.updateGui()
    app = QtWidgets.QApplication.instance()
    if app is None:
        return

    # ExcludeUserInputEvents: skip mouse/keyboard events to avoid re-entrancy
    # with ongoing navigation. ExcludeSocketNotifiers keeps network I/O out.
    flags = (
        QtCore.QEventLoop.ExcludeUserInputEvents
        | QtCore.QEventLoop.ExcludeSocketNotifiers
    )
    app.processEvents(flags, delay_ms)
    if delay_ms > 0:
        QtCore.QThread.msleep(delay_ms)
        app.processEvents(flags, delay_ms)


def process_gui_tasks() -> None:
    """Drain queued GUI-thread callables.

    Skips the current tick when any mouse button is held (e.g., 3D navigation
    drag) or when already executing a task (re-entrancy guard). The guard
    prevents ``doc.recompute()`` or ``processEvents()`` inside a task from
    triggering a nested ``process_gui_tasks`` call that corrupts FreeCAD state.

    Rescheduling is owned by ``_heartbeat_tick``; this function only drains.
    """
    global _processing, _processing_since, _shutdown_requested
    if _processing:
        return  # re-entrant call from processEvents inside a task; skip

    try:
        if _rpc_request_queue.empty():
            return  # nothing queued; skip cursor/status-bar churn on idle heartbeat ticks
        if QtWidgets.QApplication.mouseButtons() != QtCore.Qt.NoButton:
            return  # user is dragging; defer to next tick
        if QtWidgets.QApplication.activePopupWidget() is not None:
            return  # context menu or popup open; defer to next tick
        if QtWidgets.QApplication.activeModalWidget() is not None:
            return  # modal dialog open; defer to next tick

        _processing = True
        _processing_since = time.monotonic()
        app = QtWidgets.QApplication.instance()
        try:
            status_bar = FreeCADGui.getMainWindow().statusBar()
        except Exception:
            status_bar = None

        if app is not None:
            app.setOverrideCursor(QtCore.Qt.WaitCursor)
        if status_bar is not None:
            status_bar.showMessage("MCP: processing…")
        try:
            while not _rpc_request_queue.empty():
                task = _rpc_request_queue.get()
                if task is _SHUTDOWN:
                    # Safety net in case the sentinel is consumed by a wake-path
                    # drain before request_shutdown's flag write is observed.
                    _shutdown_requested = True
                    return
                try:
                    task()
                except Exception as e:
                    FreeCAD.Console.PrintError(
                        f"MCP RPC: unhandled exception in GUI task: {type(e).__name__}: {e}\n"
                        f"{traceback.format_exc()}"
                    )
        finally:
            if app is not None:
                app.restoreOverrideCursor()
            if status_bar is not None:
                status_bar.clearMessage()
    finally:
        _processing = False


def _heartbeat_tick(chain_id: int) -> None:
    """One 500 ms fallback tick. Only the chain matching the current
    generation id reschedules itself; stale chains (from a previous
    start/stop cycle) and post-shutdown ticks die here.
    """
    if chain_id != _chain_id or _shutdown_requested:
        return
    process_gui_tasks()
    if chain_id == _chain_id and not _shutdown_requested:
        QtCore.QTimer.singleShot(500, lambda: _heartbeat_tick(chain_id))


def start_heartbeat() -> None:
    """Start the 500 ms fallback heartbeat chain. Call from the GUI thread
    on server start. Bumping the generation id invalidates any pending tick
    from a previous chain, so repeated stop/start cycles keep exactly one
    live chain.
    """
    global _chain_id, _shutdown_requested
    _shutdown_requested = False
    _chain_id += 1
    chain_id = _chain_id
    QtCore.QTimer.singleShot(500, lambda: _heartbeat_tick(chain_id))


def request_shutdown() -> None:
    """Stop the heartbeat and post the sentinel to break an in-progress drain."""
    global _shutdown_requested
    _shutdown_requested = True
    _rpc_request_queue.put(_SHUTDOWN)


def dispatch_to_gui(task: Callable[[], Any], timeout: float = 60) -> Any:
    """Run ``task`` on the GUI thread and return its result.

    Uses a per-call response queue so a timeout in one call never corrupts
    the response for a subsequent call. Wakes the GUI thread immediately via
    a Qt signal instead of waiting for the next 500 ms heartbeat.

    Returns the task's return value on success, an error string if the task
    raises, or ``{"success": False, "error": ...}`` on timeout.
    """
    response_queue: "queue.Queue[Any]" = queue.Queue(maxsize=1)

    def _wrapped() -> None:
        try:
            res = task()
        except Exception as e:
            FreeCAD.Console.PrintError(
                f"MCP RPC: GUI task raised {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()}"
            )
            res = f"{type(e).__name__}: {e}"
        response_queue.put(res)

    _rpc_request_queue.put(_wrapped)
    if _waker is not None:
        _waker.wake()  # immediate wake via Qt signal (thread-safe)

    try:
        return response_queue.get(timeout=timeout)
    except queue.Empty:
        # Diagnose why: if _processing is still True, the GUI thread is occupied
        # by a long-running task that was queued before this one.
        if _processing:
            busy_for = time.monotonic() - _processing_since
            hint = (
                f" (GUI thread has been busy for {busy_for:.1f}s — "
                "consider execute_code_async for heavy OCCT operations)"
            )
        else:
            hint = ""
        return {"success": False, "error": f"GUI dispatch timed out after {timeout}s{hint}"}
