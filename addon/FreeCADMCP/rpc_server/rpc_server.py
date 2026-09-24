import FreeCAD
import FreeCADGui

import contextlib
import base64
import io
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any
from xmlrpc.client import Fault

from PySide import QtCore

from rpc_server.commands import register_commands, schedule_toggle_sync
from rpc_server.fem_executor import run_fem_analysis as _run_fem_analysis
from rpc_server.gui_dispatch import (
    cleanup_waker,
    dispatch_to_gui,
    get_dispatch_status,
    init_waker,
    process_gui_tasks,
    request_shutdown,
)
from rpc_server.ip_filter import FilteredXMLRPCServer, validate_allowed_ips
from rpc_server import dfm as _dfm
from rpc_server import measure as _measure
from rpc_server.object_factory import create_object_gui, edit_object_gui
from rpc_server.parts_library import get_parts_list, insert_part_from_library
from rpc_server.property_mapper import Object
from rpc_server.serialize import serialize_object
from rpc_server import face_colors
from rpc_server import features as _features
from rpc_server import picking as _picking
from rpc_server import shape_check
from rpc_server import transaction as _transaction
from rpc_server import undo_guard
from rpc_server.settings import load_settings, save_settings
from rpc_server.view_manager import save_active_screenshot

rpc_server_thread = None
rpc_server_instance = None
_stop_thread = None  # drains shutdown off the GUI thread; see stop_rpc_server

# Persistent namespace for execute_code / execute_code_async. A dedicated dict
# (instead of this module's globals()) keeps user code from shadowing server
# internals like dispatch_to_gui while preserving the documented pattern of
# sharing module-level variables between successive calls.
_EXEC_NAMESPACE: dict[str, Any] = {
    "FreeCAD": FreeCAD,
    "App": FreeCAD,
    "FreeCADGui": FreeCADGui,
    "Gui": FreeCADGui,
}
_async_execution = threading.local()

# Background jobs started by execute_code_async, newest last. Errors raised off
# the GUI thread used to reach only the Report View; the registry lets the
# client read them via get_async_status. Retain all running jobs and bound only
# completed history, in completion order.
_ASYNC_JOBS: dict[str, dict[str, Any]] = {}
_ASYNC_JOBS_LOCK = threading.Lock()
_ASYNC_JOBS_KEEP = 20


def _record_job(job_id: str, **fields: Any) -> None:
    with _ASYNC_JOBS_LOCK:
        job = _ASYNC_JOBS.pop(job_id, {"id": job_id})
        job.update(fields)
        _ASYNC_JOBS[job_id] = job
        finished = [
            key for key, value in _ASYNC_JOBS.items()
            if value.get("state") in {"done", "failed"}
        ]
        for key in finished[:max(0, len(finished) - _ASYNC_JOBS_KEEP)]:
            del _ASYNC_JOBS[key]


def _ok(res) -> bool:
    """True when a GUI-thread handler returned success."""
    return res is True


def _err(res) -> dict:
    """Convert any non-True result (error string or timeout dict) to a failure dict."""
    if isinstance(res, dict):
        return res
    return {"success": False, "error": str(res)}


def _commit_async(fn: Callable[[], Any], timeout: float = 120) -> Any:
    """Run an async script's document/view writes on the GUI thread."""
    if not getattr(_async_execution, "active", False):
        raise RuntimeError("commit() is only available inside execute_code_async workers")
    res = dispatch_to_gui(
        lambda: (fn(),), timeout=timeout, operation_name="async_commit"
    )
    if isinstance(res, tuple):
        return res[0]
    error = _err(res)
    raise RuntimeError(f"commit() failed: {error['error']}")


# Keep one live namespace, including the helper: saved functions retain this
# dictionary as their globals. The thread-local guard prevents a GUI callback
# or synchronous script from waiting on its own GUI thread through commit().
_EXEC_NAMESPACE["commit"] = _commit_async


def _query_on_gui(task: Callable[[], Any], operation: str) -> Any:
    """Preserve query results while reporting dispatch failures as RPC faults."""
    # A tuple distinguishes valid results (including None and empty lists)
    # from the dispatcher's error strings and failure dictionaries.
    res = dispatch_to_gui(lambda: (task(),), operation_name=operation)
    if isinstance(res, tuple):
        return res[0]
    error = _err(res)
    code = error.get("code", "GUI_DISPATCH_FAILED")
    raise Fault(1, f"{code}: {error['error']}")


class FreeCADRPC:
    """RPC server for FreeCAD"""
    TIMEOUT = 60               # generous wait for GUI thread to become free
    EXECUTE_CODE_TIMEOUT = 90  # GUI-thread execution; use execute_code_async for heavy OCCT ops

    def ping(self):
        return True

    def get_rpc_status(self) -> dict[str, Any]:
        """Report server and GUI-dispatch health without using the GUI thread."""
        with _ASYNC_JOBS_LOCK:
            running = [j["id"] for j in _ASYNC_JOBS.values() if j.get("state") == "running"]
        return {
            "success": True,
            "rpc_server": "running",
            "gui_dispatch": get_dispatch_status(),
            "async_jobs_running": running,
        }

    def get_async_status(self, job_id: str = "") -> dict[str, Any]:
        """Report background jobs without using the GUI thread.

        With ``job_id`` returns that job (state ``running``/``done``/``failed``,
        error and traceback when failed). Without it returns all running jobs
        and up to 20 recently finished jobs. History resets when FreeCAD exits.
        """
        with _ASYNC_JOBS_LOCK:
            if job_id:
                job = _ASYNC_JOBS.get(job_id)
                if job is None:
                    return {"success": False, "error": f"unknown async job: {job_id}"}
                return {"success": True, "job": dict(job)}
            return {"success": True, "jobs": [dict(j) for j in _ASYNC_JOBS.values()]}

    def create_document(self, name="New_Document"):
        # The GUI handler reports the document's ACTUAL name — FreeCAD
        # sanitises requested names ("My Doc" -> "My_Doc") and de-duplicates
        # ("Doc" -> "Doc001"); reporting the requested name breaks every
        # follow-up call that uses it.
        res = dispatch_to_gui(
            lambda: self._create_document_gui(name),
            operation_name="create_document",
        )
        if isinstance(res, dict) and res.get("success"):
            return res
        return _err(res)

    def create_object(self, doc_name, obj_data: dict[str, Any]):
        obj = Object(
            name=obj_data.get("Name", "New_Object"),
            type=obj_data["Type"],
            analysis=obj_data.get("Analysis", None),
            properties=obj_data.get("Properties", {}),
        )
        # create_object_gui reports the created object's actual Name (see
        # its docstring) — same sanitise/de-duplicate concern as documents.
        res = dispatch_to_gui(
            lambda: self._create_object_gui(doc_name, obj),
            operation_name="create_object",
        )
        if isinstance(res, dict) and res.get("success"):
            return res
        return _err(res)

    def edit_object(self, doc_name: str, obj_name: str, properties: dict[str, Any]) -> dict[str, Any]:
        obj = Object(
            name=obj_name,
            properties=properties.get("Properties", {}),
        )
        res = dispatch_to_gui(
            lambda: self._edit_object_gui(doc_name, obj),
            operation_name="edit_object",
        )
        if _ok(res):
            return {"success": True, "object_name": obj.name}
        return _err(res)

    def delete_object(self, doc_name: str, obj_name: str):
        res = dispatch_to_gui(
            lambda: self._delete_object_gui(doc_name, obj_name),
            operation_name="delete_object",
        )
        if _ok(res):
            return {"success": True, "object_name": obj_name}
        return _err(res)


    def reload_document(self, doc_name: str) -> dict[str, Any]:
        """Close and re-open a document by name to pick up external file
        changes (e.g. edits made by another process such as `freecadcmd`
        running headlessly). Returns success once the new document is
        loaded from disk.
        """
        res = dispatch_to_gui(
            lambda: self._reload_document_gui(doc_name),
            operation_name="reload_document",
        )
        if _ok(res):
            return {"success": True, "document_name": doc_name}
        return _err(res)

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        """Run the CalculiX solver on an existing Fem::FemAnalysis and return summary results."""
        try:
            timeout_s = int(timeout)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid timeout: {timeout!r}"}
        res = dispatch_to_gui(
            lambda: self._run_fem_analysis_gui(doc_name, analysis_name),
            timeout=timeout_s,
            operation_name="run_fem_analysis",
        )
        if isinstance(res, dict):
            return res
        return {"success": False, "error": str(res)}

    def execute_code_async(self, code: str) -> dict[str, Any]:
        """Start code execution in a background thread and return immediately.

        Use for long-running OCCT *geometry* work (fuse/cut/loft on shapes) that
        would otherwise exceed the MCP timeout. The caller should poll a document
        object for completion status (e.g. check SessionState.Label via get_object).

        Thread-safety contract — read before using this method:

        FreeCAD documents and the Coin3D scenegraph are NOT thread-safe. Code run
        here executes off the GUI thread, so it must not touch them directly.
        Assigning ``obj.Shape``, calling ``doc.recompute()``, ``doc.addObject()``,
        ``doc.save()`` or any ``ViewObject`` from this thread races the GUI thread
        and can wedge FreeCAD's event loop, after which the RPC server stops
        answering entirely.

        Safe pattern: build shapes in the background, then hand the document write
        to the GUI thread via the injected ``commit`` helper::

            box = Part.makeBox(10, 10, 10)          # background: fine
            fused = base.fuse(box).removeSplitter()  # background: fine, this is the slow part

            def apply():                             # runs on the GUI thread
                obj.Shape = fused
                doc.recompute()

            commit(apply)                            # blocks until the GUI thread ran it

        ``commit(fn, timeout=...)`` returns ``fn``'s value, or raises RuntimeError
        if the GUI dispatch failed or timed out. The helper persists so saved
        functions can reuse it in later async calls. It may only be called from
        an async worker, not from a synchronous script or GUI callback.
        """
        def _set_status(msg):
            dispatch_to_gui(
                lambda: FreeCADGui.getMainWindow().statusBar().showMessage(msg),
                operation_name="show_async_status",
            )

        def _clear_status():
            # Short timeout: this runs in the worker's finally block, so a wedged
            # or busy GUI thread must not keep the worker alive for the full
            # default dispatch timeout. Losing a status-bar reset is harmless.
            dispatch_to_gui(
                lambda: FreeCADGui.getMainWindow().statusBar().clearMessage(),
                timeout=5,
                operation_name="clear_async_status",
            )

        job_id = f"job-{uuid.uuid4().hex}"
        code_preview = code if len(code) <= 200 else code[:200] + "…"

        def worker() -> None:
            # NOTE: we do NOT redirect sys.stdout here. contextlib.redirect_stdout
            # swaps stdout process-wide, not per-thread, so it would race with the
            # GUI thread and other concurrent work. Background code should report
            # via FreeCAD.Console (which is thread-safe) instead.
            # Execute against the live dictionary. Merging a snapshot on exit
            # would restore stale values and lose deletions/concurrent writes.
            _async_execution.active = True
            outcome: dict[str, Any] = {"state": "done"}
            # Fingerprint shapes before the script; a failed snapshot never fails the job.
            snap = dispatch_to_gui(lambda: (shape_check.snapshot(),), timeout=30, operation_name="async_shape_snapshot")
            before = snap[0] if isinstance(snap, tuple) else None
            csnap = dispatch_to_gui(lambda: (face_colors.snapshot(),), timeout=30, operation_name="async_color_snapshot")
            colors_before = csnap[0] if isinstance(csnap, tuple) else None
            try:
                exec(code, _EXEC_NAMESPACE)
            except BaseException as e:
                # SystemExit/KeyboardInterrupt raised by a worker script must
                # also finish its job record rather than leave it running.
                import traceback as _tb
                outcome = {
                    "state": "failed",
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": _tb.format_exc().rstrip(),
                }
            finally:
                del _async_execution.active
                if colors_before:
                    rep = dispatch_to_gui(
                        lambda: (face_colors.restore(colors_before),),
                        timeout=30,
                        operation_name="async_color_restore",
                    )
                    if isinstance(rep, tuple) and rep[0]:
                        outcome["face_colors_restored"] = rep[0]
                if before is not None:
                    chk = dispatch_to_gui(lambda: (shape_check.check(before),), timeout=30, operation_name="async_shape_check")
                    if isinstance(chk, tuple):
                        outcome["shape_check"] = chk[0]
                # Publish the result before best-effort GUI/log cleanup. A busy
                # GUI must not prevent a client from observing script failure.
                _record_job(job_id, finished=time.time(), **outcome)
                for w in outcome.get("shape_check", {}).get("warnings", []):
                    try:
                        FreeCAD.Console.PrintWarning(f"Shape check ({job_id}): {w}\n")
                    except Exception:
                        pass
                try:
                    if outcome["state"] == "done":
                        FreeCAD.Console.PrintMessage("Async code execution completed.\n")
                    else:
                        FreeCAD.Console.PrintError(
                            f"Async code error ({job_id}): {outcome['error']}\n{outcome['traceback']}\n"
                        )
                except Exception:
                    pass
                try:
                    _clear_status()
                except Exception:
                    pass  # never let status cleanup mask or outlive the real work

        _record_job(job_id, state="running", started=time.time(), code=code_preview)
        try:
            _set_status("MCP: running background task…")
            threading.Thread(target=worker, daemon=True).start()
        except Exception as e:
            import traceback as _tb
            error = f"{type(e).__name__}: {e}"
            _record_job(
                job_id, state="failed", finished=time.time(), error=error,
                traceback=_tb.format_exc().rstrip(),
            )
            return {"success": False, "job_id": job_id, "error": error}
        return {
            "success": True,
            "job_id": job_id,
            "message": (
                "Code execution started in background. Document writes "
                "(obj.Shape = ..., recompute, addObject, save, ViewObject) must "
                "go through commit(fn) — direct writes from this thread can wedge "
                "FreeCAD."
            ),
        }

    def undo_last_edit(self, doc_name: str | None = None) -> dict[str, Any]:
        """Revert the last execute_code transaction."""
        res = dispatch_to_gui(
            lambda: (undo_guard.undo(doc_name),),
            timeout=60,
            operation_name="undo_last_edit",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def measure_probe(
        self, doc_name: str, obj_name: str, start: list[float], end: list[float]
    ) -> dict[str, Any]:
        """Report the solid spans and open gaps a ray crosses."""
        res = dispatch_to_gui(
            lambda: (_measure.probe(doc_name, obj_name, start, end),),
            timeout=60,
            operation_name="measure_probe",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def cut_pocket(
        self, doc_name: str, obj_name: str, corners: list[Any], depth: float,
        tool_radius: float, z_top: float, through: bool = False,
        policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Cut a pocket with the corner radii a cutter leaves, and audit it."""
        def task():
            cp = _transaction.checkpoint(doc_name, "before pocket", [obj_name])
            try:
                out = _features.pocket(doc_name, obj_name, corners, depth,
                                       tool_radius, z_top, through)
                doc = FreeCAD.getDocument(doc_name)
                doc.getObject(obj_name).Shape = out["shape"]
                doc.recompute()
            except Exception as e:  # noqa: BLE001
                _transaction.restore(cp["checkpoint_id"])
                return ({"verdict": "reject", "restored": True,
                         "errors": [{"code": "FEATURE_FAILED",
                                     "detail": f"{type(e).__name__}: {e}"}]},)
            report = _transaction.audit(doc_name, cp["checkpoint_id"], policy)
            if report["verdict"] == "reject":
                _transaction.restore(cp["checkpoint_id"])
                report["restored"] = True
            else:
                report["restored"] = False
                report["opening"] = out["opening"]
                report["corner_radius"] = out["corner_radius"]
                report["volume_removed"] = out["volume_removed"]
            return (report,)

        res = dispatch_to_gui(task, timeout=self.EXECUTE_CODE_TIMEOUT,
                              operation_name="cut_pocket")
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def cut_slot(
        self, doc_name: str, obj_name: str, path: list[Any], width: float,
        depth: float, z_top: float, policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Cut a slot with the rounded ends a cutter leaves, and audit it."""
        def task():
            cp = _transaction.checkpoint(doc_name, "before slot", [obj_name])
            try:
                out = _features.slot(doc_name, obj_name, path, width, depth, z_top)
                doc = FreeCAD.getDocument(doc_name)
                doc.getObject(obj_name).Shape = out["shape"]
                doc.recompute()
            except Exception as e:  # noqa: BLE001
                _transaction.restore(cp["checkpoint_id"])
                return ({"verdict": "reject", "restored": True,
                         "errors": [{"code": "FEATURE_FAILED",
                                     "detail": f"{type(e).__name__}: {e}"}]},)
            report = _transaction.audit(doc_name, cp["checkpoint_id"], policy)
            if report["verdict"] == "reject":
                _transaction.restore(cp["checkpoint_id"])
                report["restored"] = True
            else:
                report["restored"] = False
                report["end_radius"] = out["end_radius"]
                report["volume_removed"] = out["volume_removed"]
            return (report,)

        res = dispatch_to_gui(task, timeout=self.EXECUTE_CODE_TIMEOUT,
                              operation_name="cut_slot")
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def pick_pixel(self, x: int, y: int, radius: int = 0,
                   image_width: int = 0, image_height: int = 0) -> dict[str, Any]:
        """Report the face drawn at a pixel of the current view."""
        res = dispatch_to_gui(
            lambda: (_picking.pick(x, y, radius, image_width, image_height),),
            timeout=30,
            operation_name="pick_pixel",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def pick_region(
        self, x0: int, y0: int, x1: int, y1: int, step: int = 8,
        image_width: int = 0, image_height: int = 0
    ) -> dict[str, Any]:
        """Report every face drawn inside a rectangle of the current view."""
        res = dispatch_to_gui(
            lambda: (_picking.pick_region(
                x0, y0, x1, y1, step, image_width, image_height),),
            timeout=120,
            operation_name="pick_region",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def locate_point(self, point: list[float]) -> dict[str, Any]:
        """Report where a 3D point falls in the current view."""
        res = dispatch_to_gui(
            lambda: (_picking.locate(point),),
            timeout=30,
            operation_name="locate_point",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def create_checkpoint(
        self, doc_name: str, label: str = "", objects: list[str] | None = None
    ) -> dict[str, Any]:
        """Copy the shapes so a later edit can be rolled back to this state."""
        res = dispatch_to_gui(
            lambda: (_transaction.checkpoint(doc_name, label, objects),),
            timeout=120,
            operation_name="create_checkpoint",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def list_checkpoints(self) -> dict[str, Any]:
        res = dispatch_to_gui(
            lambda: ({"checkpoints": _transaction.list_checkpoints()},),
            timeout=30,
            operation_name="list_checkpoints",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def restore_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        """Put every shape back the way the checkpoint recorded it."""
        res = dispatch_to_gui(
            lambda: (_transaction.restore(checkpoint_id),),
            timeout=180,
            operation_name="restore_checkpoint",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def audit_shapes(
        self, doc_name: str, checkpoint_id: str = "", policy: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Compare the document against a checkpoint and return a verdict."""
        res = dispatch_to_gui(
            lambda: (_transaction.audit(doc_name, checkpoint_id, policy),),
            timeout=180,
            operation_name="audit_shapes",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def execute_guarded(
        self, doc_name: str, code: str, label: str = "",
        policy: dict[str, Any] | None = None, objects: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run an edit and keep it only if the audit passes."""
        output_buffer = io.StringIO()

        def task():
            colors_before = face_colors.snapshot()
            with contextlib.redirect_stdout(output_buffer):
                report = _transaction.guarded(
                    doc_name, code, _EXEC_NAMESPACE, label, policy, objects
                )
            # Only a kept edit needs its colors carried over; a rejected one was
            # restored from the checkpoint, which already holds the old ones.
            if not report.get("restored"):
                repainted = face_colors.restore(colors_before)
                if repainted:
                    report["face_colors_restored"] = repainted
            return (report,)

        res = dispatch_to_gui(
            task,
            timeout=self.EXECUTE_CODE_TIMEOUT,
            operation_name="execute_guarded",
        )
        if isinstance(res, tuple):
            return {"success": True, "output": output_buffer.getvalue(), **res[0]}
        return _err(res)

    def measure_sweep(
        self,
        doc_name: str,
        obj_name: str,
        ray_axis: str,
        step_axis: str,
        step_from: float,
        step_to: float,
        step: float,
        at: float,
    ) -> dict[str, Any]:
        """Probe parallel rays across a range and report where the pattern changes."""
        res = dispatch_to_gui(
            lambda: (
                _measure.sweep(
                    doc_name,
                    obj_name,
                    ray_axis,
                    step_axis,
                    step_from,
                    step_to,
                    step,
                    at,
                ),
            ),
            timeout=180,
            operation_name="measure_sweep",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def measure_compare(
        self,
        doc_name: str,
        obj_name: str,
        rays: list[dict[str, list[float]]],
        before: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Probe several rays; with a baseline, report which ones gained material."""
        res = dispatch_to_gui(
            lambda: (_measure.compare(doc_name, obj_name, rays, before),),
            timeout=120,
            operation_name="measure_compare",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def check_manufacturability(
        self,
        doc_name: str = "",
        obj_name: str = "",
        file_path: str = "",
        r_min: float = 2.0,
        max_width: float = 0.3,
        min_edge: float = 0.1,
        vertical_only: bool = True,
    ) -> dict[str, Any]:
        """Internal radii, sharp inside corners, thin faces and short edges of one shape."""
        res = dispatch_to_gui(
            lambda: (
                _dfm.check(
                    _dfm.load_shape(doc_name, obj_name, file_path), r_min, max_width, min_edge, vertical_only
                ),
            ),
            timeout=300,
            operation_name="check_manufacturability",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def section_profile(
        self,
        doc_name: str,
        obj_name: str,
        axis: str,
        value: float,
        min_segment: float = 0.1,
        max_jog_deg: float = 2.0,
        file_path: str = "",
    ) -> dict[str, Any]:
        """Outline of the shape in the plane axis=value, with short segments and steps flagged."""
        res = dispatch_to_gui(
            lambda: (
                _dfm.section_profile(
                    _dfm.load_shape(doc_name, obj_name, file_path), axis, value, min_segment, max_jog_deg
                ),
            ),
            timeout=120,
            operation_name="section_profile",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def shape_diff(
        self, doc_a: str, obj_a: str, doc_b: str, obj_b: str, file_a: str = "", file_b: str = ""
    ) -> dict[str, Any]:
        """Material present in one shape and absent from the other, as solids with bounding boxes."""
        res = dispatch_to_gui(
            lambda: (
                _dfm.shape_diff(_dfm.load_shape(doc_a, obj_a, file_a), _dfm.load_shape(doc_b, obj_b, file_b)),
            ),
            timeout=300,
            operation_name="shape_diff",
        )
        if isinstance(res, tuple):
            return {"success": True, **res[0]}
        return _err(res)

    def execute_code(self, code: str) -> dict[str, Any]:
        """Execute Python code on the GUI thread and wait for the result.

        Runs on the GUI thread so that FreeCAD document operations
        (addObject, recompute, save) are safe and correctly ordered.
        Use execute_code_async for heavy OCCT boolean ops (fuse/cut)
        that would block the GUI thread too long.
        """
        output_buffer = io.StringIO()

        def task():
            before = shape_check.snapshot()
            # Face colors are index-based, so a boolean renumbering the faces
            # drops them to one flat color and the old order cannot be recovered.
            colors_before = face_colors.snapshot()
            # One undo step per call, so a wrong boolean can be reverted with
            # undo_last_edit instead of rebuilt by hand: FreeCAD overwrites the
            # .FCBak file on the next save, so the file on disk is no fallback.
            docs = undo_guard.begin("MCP execute_code")
            try:
                with contextlib.redirect_stdout(output_buffer):
                    exec(code, _EXEC_NAMESPACE)
            except Exception:
                undo_guard.abort(docs)
                raise
            repainted = face_colors.restore(colors_before)
            undo_guard.commit(docs)
            # Report shapes the script changed and whether they are still sound;
            # a silently invalid solid is the costliest failure to catch late.
            result = {"success": True, "shape_check": shape_check.check(before)}
            if repainted:
                result["face_colors_restored"] = repainted
            return result

        res = dispatch_to_gui(
            task,
            timeout=self.EXECUTE_CODE_TIMEOUT,
            operation_name="execute_code",
        )
        if isinstance(res, dict) and res.get("success"):
            FreeCAD.Console.PrintMessage("Python code executed successfully.\n")
            for w in res["shape_check"]["warnings"]:
                FreeCAD.Console.PrintWarning(f"Shape check: {w}\n")
            return {
                "success": True,
                "message": "Python code executed successfully.\nOutput: " + output_buffer.getvalue(),
                "shape_check": res["shape_check"],
            }
        # Log the offending code (truncated) to make errors traceable
        code_preview = code if len(code) <= 800 else code[:800] + "\n...(truncated)"
        FreeCAD.Console.PrintError(
            f"Error executing Python code: {res}\n"
            f"--- code ---\n{code_preview}\n--- end ---\n"
        )
        return _err(res)

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return _query_on_gui(lambda: self._get_objects_gui(doc_name), "get_objects")

    def _get_objects_gui(self, doc_name: str) -> list[dict[str, Any]]:
        # FreeCAD.getDocument raises (not returns None) for an unknown name.
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception:
            return []
        return [serialize_object(obj) for obj in doc.Objects]

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any] | None:
        return _query_on_gui(
            lambda: self._get_object_gui(doc_name, obj_name), "get_object"
        )

    def _get_object_gui(self, doc_name: str, obj_name: str) -> dict[str, Any] | None:
        # FreeCAD.getDocument raises (not returns None) for an unknown name.
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception:
            return None
        obj = doc.getObject(obj_name)
        if obj:
            return serialize_object(obj)
        return None

    def insert_part_from_library(self, relative_path):
        res = dispatch_to_gui(
            lambda: self._insert_part_from_library(relative_path),
            operation_name="insert_part_from_library",
        )
        if _ok(res):
            return {"success": True, "message": "Part inserted from library."}
        return _err(res)

    def list_documents(self) -> list[str]:
        return _query_on_gui(
            lambda: list(FreeCAD.listDocuments().keys()), "list_documents"
        )

    def get_parts_list(self):
        return get_parts_list()

    def get_active_screenshot(
        self,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
    ) -> str:
        """Get a screenshot of the active view as a base64-encoded PNG string.

        Returns None if the active view does not support screenshots
        (e.g., TechDraw or Spreadsheet workbench).
        """
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)

        def task():
            try:
                active_view = FreeCADGui.ActiveDocument.ActiveView
            except Exception:
                return False
            if active_view is None or not hasattr(active_view, "saveImage"):
                view_type = type(active_view).__name__ if active_view is not None else "None"
                FreeCAD.Console.PrintWarning(
                    f"MCP RPC: view type '{view_type}' does not support screenshots\n"
                )
                return False
            return save_active_screenshot(tmp_path, view_name, width, height, focus_object)

        try:
            res = dispatch_to_gui(task, operation_name="get_active_screenshot")
            if _ok(res):
                with open(tmp_path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            if res is False:
                return None
            FreeCAD.Console.PrintWarning(f"MCP RPC: screenshot failed: {res}\n")
            return None
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _create_document_gui(self, name):
        doc = FreeCAD.newDocument(name)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Document '{doc.Name}' created via RPC.\n")
        return {"success": True, "document_name": doc.Name}

    def _create_object_gui(self, doc_name, obj: Object):
        return create_object_gui(doc_name, obj)

    def _edit_object_gui(self, doc_name: str, obj: Object):
        return edit_object_gui(doc_name, obj)

    def _run_fem_analysis_gui(self, doc_name: str, analysis_name: str):
        return _run_fem_analysis(doc_name, analysis_name)

    def _delete_object_gui(self, doc_name: str, obj_name: str):
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

        try:
            doc.removeObject(obj_name)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj_name}' deleted via RPC.\n")
            return True
        except Exception as e:
            return str(e)


    def _reload_document_gui(self, doc_name: str):
        if doc_name not in FreeCAD.listDocuments():
            return f"Document '{doc_name}' is not loaded."
        doc = FreeCAD.getDocument(doc_name)
        file_path = doc.FileName
        if not file_path:
            return (
                f"Document '{doc_name}' has no file on disk "
                "(unsaved scratch document); nothing to reload from."
            )
        if not os.path.exists(file_path):
            return f"File for '{doc_name}' not found at {file_path!r}."
        # Close, then reopen from the same file. Reopen preserves the
        # original document name when the file was previously saved
        # under that name.
        FreeCAD.closeDocument(doc_name)
        FreeCAD.openDocument(file_path)
        FreeCAD.Console.PrintMessage(
            f"Document '{doc_name}' reloaded from '{file_path}' via RPC.\n"
        )
        return True

    def _insert_part_from_library(self, relative_path):
        try:
            insert_part_from_library(relative_path)
            return True
        except Exception as e:
            return str(e)

    def _save_active_screenshot(
        self,
        save_path: str,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
    ):
        return save_active_screenshot(save_path, view_name, width, height, focus_object)


def start_rpc_server(port=9875):
    global rpc_server_thread, rpc_server_instance

    if rpc_server_instance:
        return "RPC Server already running."

    # A previous stop may still be draining an in-flight request off-thread;
    # binding before its server_close() would hit the old socket.
    if _stop_thread is not None and _stop_thread.is_alive():
        _stop_thread.join(timeout=5.0)
        if _stop_thread.is_alive():
            return ("RPC Server is still stopping (a request is draining); "
                    "try again in a few seconds.")

    settings = load_settings()
    remote_enabled = settings.get("remote_enabled", False)
    allowed_ips = settings.get("allowed_ips", "127.0.0.1")

    if remote_enabled:
        host = "0.0.0.0"
    else:
        host = "127.0.0.1"

    rpc_server_instance = FilteredXMLRPCServer(
        (host, port), allowed_ips_str=allowed_ips, allow_none=True, logRequests=False
    )
    rpc_server_instance.register_instance(FreeCADRPC())

    def server_loop():
        FreeCAD.Console.PrintMessage(f"RPC Server started at {host}:{port}\n")
        if remote_enabled:
            FreeCAD.Console.PrintMessage(f"Remote connections enabled. Allowed IPs: {allowed_ips}\n")
        rpc_server_instance.serve_forever()

    rpc_server_thread = threading.Thread(target=server_loop, daemon=True)
    rpc_server_thread.start()

    init_waker()
    QtCore.QTimer.singleShot(500, process_gui_tasks)

    msg = f"RPC Server started at {host}:{port}."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    return msg


def stop_rpc_server():
    global rpc_server_instance, rpc_server_thread, _stop_thread

    if not rpc_server_instance:
        return "RPC Server was not running."

    server = rpc_server_instance
    thread = rpc_server_thread
    rpc_server_instance = None
    rpc_server_thread = None

    request_shutdown()
    cleanup_waker()

    def _shutdown_and_close():
        # shutdown() only stops the accept loop; in-flight requests run in
        # their own daemon threads and are not waited for. Kept off the GUI
        # thread so a menu command cannot block the UI. server_close() must
        # always follow, or the listening socket stays bound and Stop -> Start
        # fails with EADDRINUSE.
        try:
            server.shutdown()
            if thread is not None:
                thread.join(timeout=10.0)
                if thread.is_alive():
                    FreeCAD.Console.PrintWarning(
                        "MCP RPC: server thread still draining a request; "
                        "socket closes when it finishes.\n"
                    )
        finally:
            server.server_close()
        FreeCAD.Console.PrintMessage("RPC Server stopped.\n")

    _stop_thread = threading.Thread(target=_shutdown_and_close, daemon=True)
    _stop_thread.start()
    return "RPC Server stopping…"


register_commands()
schedule_toggle_sync()
