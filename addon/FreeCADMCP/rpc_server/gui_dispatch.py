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
   mouse buttons are held so MCP tasks cannot interrupt 3D navigation drags,
   for at most ``MOUSE_DEFER_MAX_S`` so a lost mouse-release cannot wedge
   dispatch. A queued call that times out names the guard that held it.
4. Clean shutdown: a shutdown flag and heartbeat generation invalidate pending
   timer callbacks, even if an immediate wake consumes the shutdown sentinel.
5. Exception isolation: exceptions inside a task are caught, logged, and
   returned as error strings; they never kill the dispatch loop.
6. Stuck-task fail-fast: once a task that already started times out, later GUI
   calls fail immediately until that task returns. Status remains available
   through a GUI-independent RPC method.
7. Timeout counts from task start: the GUI thread runs queued tasks one at a
   time, so a call that arrives while another task is running waits in the
   FIFO first. That wait is budgeted separately (``queue_timeout``) and does
   not consume the task's own ``timeout``. Two concurrent ``execute_code``
   calls therefore each get their full run budget instead of the second one
   being reported stuck because the first was slow.
"""

import itertools
import math
import queue
import threading
import time
import traceback
import uuid
from typing import Any, Callable

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

from rpc_server.dispatch_health import DispatchHealth, stuck_failure
from rpc_server.task_history import TaskHistory


_rpc_request_queue: "queue.Queue[Any]" = queue.Queue()
_SHUTDOWN = object()
_processing = False  # re-entrancy guard: True while process_gui_tasks is draining
_processing_since: float = 0.0  # wall-clock time when _processing became True
_heartbeat_generation = 0
_shutdown_requested = False
_task_ids = itertools.count(1)
_task_namespace = uuid.uuid4().hex
_dispatch_health = DispatchHealth()
_lifecycle_lock = threading.RLock()
_pending: dict[str, Callable[[], None]] = {}
_task_history = TaskHistory()
_last_tick: float | None = None

# Qt can miss a mouse-release when the button is released outside the FreeCAD
# window (drag out of the viewport, release there). QApplication.mouseButtons()
# then reports the button as held indefinitely. An unbounded mouse guard turns
# that into a permanently wedged RPC server: every tick defers, no task ever
# runs, and every call fails with an unexplained timeout. Cap how long we are
# willing to believe a drag is still in progress.
MOUSE_DEFER_MAX_S = 5.0
# None = unarmed. Do not use 0.0 as the sentinel: time.monotonic() may legitimately
# return 0.0, which would re-arm the timer every tick and never reach the cap.
_mouse_defer_since: "float | None" = None
_stale_mouse_warned = False

# Why and when the last tick declined to process, recorded on the GUI thread so
# the RPC thread can report it on timeout without touching Qt off-thread. One
# tuple assignment keeps reason and time consistent without a lock.
_last_defer: "tuple[str, float] | None" = None


def _mouse_guard_should_defer(mouse_down: bool, now: float) -> bool:
    """Whether to skip this tick because mouse buttons are held.

    Defers while a genuine 3D-navigation drag is plausibly in progress, but
    gives up after ``MOUSE_DEFER_MAX_S``: buttons reported held that long
    across an MCP call are far more likely stale Qt state than a real drag,
    and deferring forever is strictly worse than interrupting a drag.
    """
    global _mouse_defer_since, _stale_mouse_warned
    if not mouse_down:
        _mouse_defer_since = None
        _stale_mouse_warned = False
        return False
    if _mouse_defer_since is None:
        _mouse_defer_since = now
        return True
    return (now - _mouse_defer_since) < MOUSE_DEFER_MAX_S


def _warn_stale_mouse_once() -> None:
    """Announce the override once per stuck-button episode."""
    global _stale_mouse_warned
    if _stale_mouse_warned:
        return
    _stale_mouse_warned = True
    FreeCAD.Console.PrintWarning(
        f"MCP RPC: mouse buttons reported held for over {MOUSE_DEFER_MAX_S:.0f}s. "
        "Treating as stale Qt input state and processing queued tasks anyway.\n"
    )


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


def _wake(waker: Any) -> None:
    if waker is not None:
        try:
            waker.wake()
        except Exception as exc:
            # A disposed Qt signal must not leak admission ownership or lose
            # the queued task. The heartbeat remains the fallback.
            log_error(f"MCP RPC: immediate wake failed: {exc}\n")


def log_error(message: str) -> None:
    """Report View logging that cannot fail on unencodable text.

    PrintError raises for strings holding lone surrogates (an exception text
    built from undecodable bytes); on an error path that exception would
    replace the error being reported.
    """
    try:
        FreeCAD.Console.PrintError(message)
    except Exception:
        try:
            FreeCAD.Console.PrintError(message.encode("utf-8", "backslashreplace").decode("utf-8"))
        except Exception:
            pass


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


def _ui_should_defer() -> bool:
    """Sample GUI blockers even while idle and between queued callbacks."""
    global _last_defer
    now = time.monotonic()
    mouse_down = QtWidgets.QApplication.mouseButtons() != QtCore.Qt.NoButton
    if _mouse_guard_should_defer(mouse_down, now):
        _last_defer = ("mouse buttons held (3D navigation drag)", now)
        return True
    if mouse_down:
        _warn_stale_mouse_once()
    if QtWidgets.QApplication.activePopupWidget() is not None:
        _last_defer = ("a popup or context menu is open in FreeCAD", now)
        return True
    if QtWidgets.QApplication.activeModalWidget() is not None:
        _last_defer = ("a modal dialog is open in FreeCAD", now)
        return True
    _last_defer = None
    return False


def process_gui_tasks() -> None:
    """Drain queued GUI-thread callables without scheduling heartbeat timers.

    Skips the current tick when any mouse button is held (e.g., 3D navigation
    drag) or when already executing a task (re-entrancy guard). The guard
    prevents ``doc.recompute()`` or ``processEvents()`` inside a task from
    triggering a nested ``process_gui_tasks`` call that corrupts FreeCAD state.

    Both immediate wakes and heartbeat ticks use this drain. Only the heartbeat
    callback owns rescheduling, so immediate wakes cannot create another chain.
    """
    global _processing, _processing_since, _last_defer, _last_tick
    _last_tick = time.monotonic()
    if _processing:
        return  # re-entrant call from processEvents inside a task; skip

    try:
        if _ui_should_defer():
            return
        if _rpc_request_queue.empty():
            return  # nothing queued; skip cursor/status-bar churn on idle heartbeat ticks
        _processing = True
        _processing_since = time.monotonic()
        app = QtWidgets.QApplication.instance()
        try:
            status_bar = FreeCADGui.getMainWindow().statusBar()
        except Exception:
            status_bar = None

        if app is not None:
            app.setOverrideCursor(QtCore.Qt.WaitCursor)
        # Show our note only on an empty bar and remove only our own note, so
        # a message shown across calls (an async job's) is left alone.
        busy_message = "MCP: processing…"
        if status_bar is not None and not status_bar.currentMessage():
            status_bar.showMessage(busy_message)
        try:
            while not _rpc_request_queue.empty():
                if _ui_should_defer():
                    return
                task = _rpc_request_queue.get()
                if task is _SHUTDOWN:
                    if _shutdown_requested:
                        return
                    # A restart may precede consumption of the old sentinel.
                    continue
                try:
                    task()
                except BaseException as e:
                    # Also SystemExit/KeyboardInterrupt: leaving this Qt slot
                    # with one of them quits FreeCAD.
                    log_error(
                        f"MCP RPC: unhandled exception in GUI task: {type(e).__name__}: {e}\n"
                        f"{traceback.format_exc()}"
                    )
        finally:
            if app is not None:
                app.restoreOverrideCursor()
            if status_bar is not None and status_bar.currentMessage() == busy_message:
                status_bar.clearMessage()
    finally:
        _processing = False


def _heartbeat_tick(generation: int) -> None:
    if generation != _heartbeat_generation or _shutdown_requested:
        return
    try:
        process_gui_tasks()
    except BaseException as exc:
        # A cosmetic GUI failure must not permanently remove the fallback timer.
        log_error(f"MCP RPC: heartbeat failed: {type(exc).__name__}: {exc}\n")
    finally:
        if generation == _heartbeat_generation and not _shutdown_requested:
            QtCore.QTimer.singleShot(500, lambda: _heartbeat_tick(generation))


def start_heartbeat() -> None:
    """Start one fallback timer chain, invalidating old ticks on the GUI thread."""
    global _heartbeat_generation, _shutdown_requested
    with _lifecycle_lock:
        _heartbeat_generation += 1
        _shutdown_requested = False
        generation = _heartbeat_generation
    QtCore.QTimer.singleShot(500, lambda: _heartbeat_tick(generation))


def request_shutdown() -> None:
    """Invalidate pending heartbeat ticks and ask the current drain to stop."""
    global _shutdown_requested, _heartbeat_generation, _last_defer
    with _lifecycle_lock:
        _shutdown_requested = True
        _heartbeat_generation += 1
        for cancel in list(_pending.values()):
            cancel()
        _pending.clear()
        while True:
            try:
                _rpc_request_queue.get_nowait()
            except queue.Empty:
                break
        _last_defer = None
        _rpc_request_queue.put(_SHUTDOWN)


def get_dispatch_status() -> dict[str, Any]:
    """Return GUI dispatch health without touching FreeCAD's GUI thread."""
    snapshot = _dispatch_health.snapshot()
    with _lifecycle_lock:
        snapshot.update(generation=_heartbeat_generation, accepting=not _shutdown_requested,
                        queued_tasks=len(_pending), queue_depth=_rpc_request_queue.qsize())
        blocked = _last_defer
        snapshot["blocked_reason"] = blocked[0] if blocked else None
        snapshot["heartbeat_age_seconds"] = (
            None if _last_tick is None else max(0, time.monotonic() - _last_tick)
        )
        if snapshot["state"] == "healthy":
            if _shutdown_requested:
                snapshot["state"] = "stopped"
            elif blocked:
                snapshot["state"] = "blocked"
            elif _pending:
                snapshot["state"] = "queued"
        age = snapshot["heartbeat_age_seconds"]
        snapshot["heartbeat_stale"] = age is None or age > 2.0
        snapshot["ready"] = (snapshot["state"] == "healthy" and not _processing
                             and not snapshot["heartbeat_stale"])
    return snapshot


def get_task_status(task_id: str | None = None) -> dict[str, Any]:
    return _task_history.snapshot(task_id)


def dispatch_generation() -> int:
    with _lifecycle_lock:
        return _heartbeat_generation


def post_to_gui(task: Callable[[], Any]) -> None:
    """Queue a short best-effort GUI task without waiting for it to run.

    For cosmetic updates (status-bar text) that must not make the caller wait
    behind a long GUI task. Queued even while dispatch is stuck, so paired
    updates (show, then clear) both run in order once the GUI thread is free.
    Exceptions are logged by ``process_gui_tasks``.
    """
    with _lifecycle_lock:
        if _shutdown_requested:
            return
        generation = _heartbeat_generation

        def guarded() -> None:
            if generation == _heartbeat_generation and not _shutdown_requested:
                task()

        _rpc_request_queue.put(guarded)
        waker = _waker
    _wake(waker)


def dispatch_to_gui(
    task: Callable[[], Any],
    timeout: float = 60,
    operation_name: str | None = None,
    queue_timeout: float | None = None,
    on_cancel: Callable[[], None] | None = None,
    expected_generation: int | None = None,
) -> Any:
    """Run ``task`` on the GUI thread and return its result.

    Uses a per-call response queue so a timeout in one call never corrupts
    the response for a subsequent call. Wakes the GUI thread immediately via
    a Qt signal instead of waiting for the next 500 ms heartbeat.

    ``timeout`` is the run budget and starts counting when the task actually
    begins on the GUI thread. Time spent queued behind earlier tasks is
    budgeted separately by ``queue_timeout`` (defaults to ``timeout``); if the
    task has not started by then it is cancelled without marking dispatch
    stuck. A call that is already queued when an earlier task becomes stuck
    keeps waiting for its turn; only calls arriving after that point are
    rejected immediately.

    A task already running on the GUI thread cannot be interrupted; if it
    exceeds ``timeout`` it is marked as stuck and subsequent GUI calls fail
    immediately until it returns.

    Returns the task's return value on success, an error string if the task
    raises, or ``{"success": False, "error": ...}`` on timeout.
    """
    for name, budget in (("timeout", timeout), ("queue_timeout", queue_timeout)):
        if name == "queue_timeout" and budget is None:
            continue
        try:
            valid = (not isinstance(budget, bool) and isinstance(budget, (int, float))
                     and math.isfinite(budget) and budget > 0)
        except (ValueError, OverflowError):
            valid = False
        if not valid:
            if on_cancel:
                on_cancel()
            return {"success": False, "code": "INVALID_TIMEOUT", "mutation_outcome": "not_started",
                    "error": f"{name} must be a positive finite number"}

    rejection = _dispatch_health.rejection()
    if rejection is not None:
        if on_cancel:
            on_cancel()
        rejection["mutation_outcome"] = "not_started"
        return rejection

    if queue_timeout is None:
        queue_timeout = timeout

    task_id = f"{_task_namespace}:{next(_task_ids)}"
    operation = operation_name or getattr(task, "__name__", "GUI operation")
    if operation == "<lambda>":
        operation = "GUI operation"

    response_queue: "queue.Queue[Any]" = queue.Queue(maxsize=1)
    state_lock = threading.Lock()
    started_event = threading.Event()
    started_at: float | None = None
    cancelled = False
    generation = dispatch_generation()

    def cancel(reason: str = "stopped") -> None:
        nonlocal cancelled
        with state_lock:
            if started_at is not None or cancelled:
                return
            cancelled = True
            _task_history.update(task_id, state="cancelled", mutation_outcome="not_started",
                                 cancellation_reason=reason, caller_timed_out=reason == "queue_timeout")
            if on_cancel:
                on_cancel()
            started_event.set()

    def _wrapped() -> None:
        nonlocal started_at
        with _lifecycle_lock:
            if generation != _heartbeat_generation or _shutdown_requested:
                cancel()
            _pending.pop(task_id, None)
            with state_lock:
                if cancelled:
                    return
                started_at = time.monotonic()
                _task_history.update(task_id, state="running", started=time.time())
                _dispatch_health.start(task_id, operation)
                started_event.set()
        missing = object()
        res = missing
        failed = False
        try:
            try:
                res = task()
                failed = res is None or res is False or isinstance(res, str) or (
                    isinstance(res, dict) and res.get("success") is False
                )
            except BaseException as e:
                # SystemExit/KeyboardInterrupt from a script (sys.exit() in
                # execute_code) must fail this call rather than quit FreeCAD.
                res = f"{type(e).__name__}: {e}"
                failed = True
                log_error(f"MCP RPC: GUI task raised {res}\n{traceback.format_exc()}")
        finally:
            # Publish completion atomically with clearing health, so a deadline
            # racing with completion cannot report a missing successful result.
            with state_lock:
                _task_history.finish(task_id, res, failed)
                _dispatch_health.finish(task_id)
                if res is not missing:
                    response_queue.put_nowait(res)

    queued_at = time.monotonic()
    with _lifecycle_lock:
        if _shutdown_requested or generation != _heartbeat_generation or (
            expected_generation is not None and expected_generation != generation
        ):
            if on_cancel:
                on_cancel()
            return {"success": False, "code": "RPC_STOPPED", "mutation_outcome": "not_started",
                    "error": "RPC dispatch stopped or its generation changed; operation was not started."}
        _task_history.update(task_id, operation=operation, generation=generation,
                             state="queued", submitted=time.time(), caller_timed_out=False)
        _pending[task_id] = cancel
        _rpc_request_queue.put(_wrapped)
        waker = _waker
    _wake(waker)  # never hold the lifecycle lock across external callbacks

    # Phase 1: wait for the task to start. Earlier queued tasks run first on
    # the GUI thread; that wait must not eat into this task's run budget.
    queue_deadline = queued_at + queue_timeout
    if not started_event.wait(max(0, queue_deadline - time.monotonic())):
        with _lifecycle_lock:
            cancel("queue_timeout")
            _pending.pop(task_id, None)
    if cancelled:
        queued_for = time.monotonic() - queued_at
        last_defer = _last_defer
        if _processing:
            busy_for = time.monotonic() - _processing_since
            hint = (
                f" (GUI thread has been busy for {busy_for:.1f}s — for heavy OCCT"
                " geometry consider execute_code_async, which must apply document"
                " writes through its commit() helper)"
            )
        elif last_defer is not None and last_defer[1] >= queued_at:
            # Never silently time out on a guard: name it so the next wedge
            # diagnoses itself instead of looking like a dead server. A guard
            # that held only an earlier task says nothing about this one.
            hint = (
                f" (GUI thread is not processing tasks: {last_defer[0]}; "
                f"{_rpc_request_queue.qsize()} task(s) queued)"
            )
        else:
            hint = ""
        return {
            "success": False,
            "task_id": task_id,
            "mutation_outcome": "not_started",
            "error": (
                f"GUI dispatch cancelled after {queued_for:.1f}s waiting for "
                f"'{operation}' to start (queue_timeout={queue_timeout:g}s){hint}"
            ),
        }

    # Phase 2: count from actual GUI start, even if this RPC thread woke late.
    assert started_at is not None
    run_remaining = max(0, started_at + timeout - time.monotonic())
    try:
        return response_queue.get(timeout=run_remaining)
    except queue.Empty:
        with state_lock:
            # Completion may have won the race while we acquired the lock.
            try:
                return response_queue.get_nowait()
            except queue.Empty:
                stuck = _dispatch_health.mark_timed_out(task_id, timeout)
                if stuck is not None:
                    _task_history.update(task_id, state="timed_out_running", caller_timed_out=True,
                                         mutation_outcome="still_running")
                    failure = stuck_failure(stuck, just_timed_out=True)
                    failure.update(task_id=task_id, mutation_outcome="still_running")
                    failure["error"] += f" Poll get_task_status(task_id={task_id}) before retrying."
                    return failure
                return {"success": False, "error": f"GUI dispatch timed out after {timeout}s"}
