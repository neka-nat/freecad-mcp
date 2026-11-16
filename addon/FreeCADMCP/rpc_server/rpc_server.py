import FreeCAD
import FreeCADGui

import base64
import io
import json
import math
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any
from xmlrpc.client import Fault

from rpc_server.commands import register_commands, schedule_toggle_sync
from rpc_server.fem_executor import run_fem_analysis as _run_fem_analysis
from rpc_server.gui_dispatch import (
    cleanup_waker,
    dispatch_to_gui,
    dispatch_generation,
    get_dispatch_status,
    get_task_status,
    init_waker,
    log_error,
    post_to_gui,
    request_shutdown,
    start_heartbeat,
)
from rpc_server.ip_filter import FilteredXMLRPCServer, validate_allowed_ips
from rpc_server.object_factory import create_object_gui, edit_object_gui
from rpc_server.parts_library import get_parts_list, insert_part_from_library
from rpc_server.property_mapper import Object
from rpc_server.serialize import serialize_object
from rpc_server.settings import load_settings, save_settings
from rpc_server.stdout_capture import capture_stdout
from rpc_server.script_state import ScriptState
from rpc_server.version import PROTOCOL_VERSION, __version__ as ADDON_VERSION
from rpc_server.view_manager import get_displayed_3d_view, save_active_screenshot

rpc_server_thread = None
rpc_server_instance = None
_stop_thread = None  # drains shutdown off the GUI thread; see stop_rpc_server
_listener_state = "stopped"
_server_id = uuid.uuid4().hex
_applied_settings: dict[str, Any] | None = None
_scripts = ScriptState()
_job_status_message = ""

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
        return {"mutation_outcome": "partial_or_unknown", **res}
    return {"success": False, "error": str(res), "mutation_outcome": "partial_or_unknown"}


def _claim_script(owner: str, generation: int) -> dict[str, Any] | None:
    dispatch = get_dispatch_status()
    if not dispatch["accepting"] or generation != dispatch_generation() or dispatch["state"] == "stuck":
        return {"success": False, "code": "SCRIPT_UNAVAILABLE", "mutation_outcome": "not_started",
                "error": "Script execution unavailable while dispatch is stopped or stuck."}
    if not _scripts.claim(owner):
        return {"success": False, "code": "SCRIPT_BUSY", "mutation_outcome": "not_started",
                "error": "Another script owns the shared namespace; wait for it to finish before retrying.",
                "script_execution": _scripts.snapshot()}
    return None


def _refresh_job_status() -> None:
    """Reconcile the GUI indicator with live jobs instead of clearing by job."""
    def update() -> None:
        global _job_status_message
        with _ASYNC_JOBS_LOCK:
            count = sum(job.get("state") == "running" for job in _ASYNC_JOBS.values())
        bar = FreeCADGui.getMainWindow().statusBar()
        current = bar.currentMessage()
        if count:
            if current in ("", "MCP: processing…", _job_status_message):
                _job_status_message = f"MCP: {count} background task(s) running…"
                bar.showMessage(_job_status_message)
        elif _job_status_message and current == _job_status_message:
            bar.clearMessage()
            _job_status_message = ""
    post_to_gui(update)


def _commit_async(fn: Callable[[], Any], timeout: float = 120) -> Any:
    """Run an async script's document/view writes on the GUI thread."""
    if not getattr(_async_execution, "active", False):
        raise RuntimeError("commit() is only available inside execute_code_async workers")
    res = dispatch_to_gui(
        lambda: (fn(),), timeout=timeout, operation_name="async_commit",
        expected_generation=_async_execution.generation,
    )
    if isinstance(res, tuple):
        return res[0]
    error = _err(res)
    raise RuntimeError(f"commit() failed: {json.dumps(error, default=str)}")


# Keep one live namespace, including the helper: saved functions retain this
# dictionary as their globals. The thread-local guard prevents a GUI callback
# or synchronous script from waiting on its own GUI thread through commit().
_EXEC_NAMESPACE["commit"] = _commit_async


def _query_on_gui(task: Callable[[], Any], operation: str, generation: int | None = None) -> Any:
    """Preserve query results while reporting dispatch failures as RPC faults."""
    # A tuple distinguishes valid results (including None and empty lists)
    # from the dispatcher's error strings and failure dictionaries.
    res = dispatch_to_gui(lambda: (task(),), operation_name=operation, expected_generation=generation)
    if isinstance(res, tuple):
        return res[0]
    error = _err(res)
    code = error.get("code", "GUI_DISPATCH_FAILED")
    raise Fault(1, f"{code}: {json.dumps(error, default=str)}")


class FreeCADRPC:
    """RPC server for FreeCAD"""
    TIMEOUT = 60               # generous wait for GUI thread to become free
    EXECUTE_CODE_TIMEOUT = 90  # GUI-thread execution; use execute_code_async for heavy OCCT ops
    # Ceiling for a caller-supplied execute_code timeout. A GUI task cannot be
    # cancelled once started, so an unbounded wait would hide a wedged GUI
    # thread from the caller indefinitely.
    MAX_EXECUTE_CODE_TIMEOUT = 1800

    def __init__(self) -> None:
        self._generation = dispatch_generation()

    def _dispatch_gui(self, task: Callable[[], Any], **kwargs: Any) -> Any:
        return dispatch_to_gui(task, expected_generation=self._generation, **kwargs)

    def ping(self):
        return True

    def get_rpc_status(self) -> dict[str, Any]:
        """Report server and GUI-dispatch health without using the GUI thread."""
        dispatch = get_dispatch_status()
        scripts = _scripts.snapshot()
        with _ASYNC_JOBS_LOCK:
            running = [j["id"] for j in _ASYNC_JOBS.values() if j.get("state") == "running"]
        return {
            "success": True,
            "rpc_server": _listener_state,
            "server_id": _server_id,
            "gui_dispatch": dispatch,
            "async_jobs_running": running,
            "script_execution": scripts,
            "configuration": self._configuration_status(),
            "quiescent": not running and scripts["state"] == "idle"
                         and dispatch["state"] not in {"busy", "stuck"}
                         and dispatch["queued_tasks"] == 0,
            "addon_version": ADDON_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "execute_code_timeout": self.EXECUTE_CODE_TIMEOUT,
            "max_execute_code_timeout": self.MAX_EXECUTE_CODE_TIMEOUT,
        }

    def _configuration_status(self) -> dict[str, Any]:
        desired = load_settings()
        keys = ("remote_enabled", "allowed_ips", "auth_token")
        changed = [key for key in keys if _applied_settings is not None
                   and desired.get(key) != _applied_settings.get(key)]
        return {"restart_required": bool(changed), "changed_fields": changed,
                "applied": None if _applied_settings is None else {
                    "remote_enabled": bool(_applied_settings.get("remote_enabled")),
                    "allowed_ips": _applied_settings.get("allowed_ips", "127.0.0.1"),
                    "authentication_required": bool(_applied_settings.get("auth_token")),
                }}

    def get_task_status(self, task_id: str | None = None) -> dict[str, Any]:
        """Read pending/late GUI results without dispatching to the GUI thread."""
        return get_task_status(task_id)

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
        res = self._dispatch_gui(
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
        res = self._dispatch_gui(
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
        res = self._dispatch_gui(
            lambda: self._edit_object_gui(doc_name, obj),
            operation_name="edit_object",
        )
        if _ok(res):
            return {"success": True, "object_name": obj.name}
        return _err(res)

    def delete_object(self, doc_name: str, obj_name: str):
        res = self._dispatch_gui(
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
        loaded from disk, with the name FreeCAD gave it: reopening uses the
        file stem, so it can differ from the requested name.
        """
        res = self._dispatch_gui(
            lambda: self._reload_document_gui(doc_name),
            operation_name="reload_document",
        )
        if isinstance(res, dict) and res.get("success"):
            return res
        return _err(res)

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        """Run the CalculiX solver on an existing Fem::FemAnalysis and return summary results."""
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 0 < timeout <= 2**31 - 1:
            return {"success": False, "mutation_outcome": "not_started",
                    "error": "timeout must be an integer between 1 and 2147483647 seconds"}
        timeout_s = timeout
        res = self._dispatch_gui(
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
        if not isinstance(code, str):
            return {"success": False, "code": "INVALID_CODE", "mutation_outcome": "not_started",
                    "error": "code must be a string"}
        code_preview = code if len(code) <= 200 else code[:200] + "…"
        job_id = f"job-{uuid.uuid4().hex}"
        rejection = _claim_script(job_id, self._generation)
        if rejection:
            return rejection
        generation = self._generation

        def worker() -> None:
            # Synchronous capture routes only the GUI thread, so this worker's
            # prints stay on the console rather than entering another RPC reply.
            # Execute against the live dictionary. Merging a snapshot on exit
            # would restore stale values and lose deletions/concurrent writes.
            _async_execution.active = True
            _async_execution.generation = generation
            outcome: dict[str, Any] = {"state": "done", "mutation_outcome": "completed"}
            try:
                if generation != dispatch_generation() or not get_dispatch_status()["accepting"]:
                    outcome = {"state": "failed", "mutation_outcome": "not_started",
                               "error": "RPC stopped before the worker started"}
                    return
                exec(code, _EXEC_NAMESPACE)
            except BaseException as e:
                # SystemExit/KeyboardInterrupt raised by a worker script must
                # also finish its job record rather than leave it running.
                import traceback as _tb
                outcome = {
                    "state": "failed",
                    "mutation_outcome": "partial_or_unknown",
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": _tb.format_exc().rstrip(),
                }
            finally:
                del _async_execution.active
                del _async_execution.generation
                _scripts.release(job_id)
                # Publish the result before best-effort GUI/log cleanup. A busy
                # GUI must not prevent a client from observing script failure.
                _record_job(job_id, finished=time.time(), **outcome)
                try:
                    if outcome["state"] == "done":
                        FreeCAD.Console.PrintMessage("Async code execution completed.\n")
                    else:
                        log_error(
                            f"Async code error ({job_id}): {outcome['error']}\n{outcome['traceback']}\n"
                        )
                except Exception:
                    pass
                try:
                    _refresh_job_status()
                except Exception:
                    pass  # never let status cleanup mask or outlive the real work

        try:
            _record_job(job_id, state="running", started=time.time(), code=code_preview)
            _refresh_job_status()
            threading.Thread(target=worker, daemon=True).start()
        except Exception as e:
            import traceback as _tb
            error = f"{type(e).__name__}: {e}"
            _scripts.release(job_id)
            _record_job(
                job_id, state="failed", finished=time.time(), error=error, mutation_outcome="not_started",
                traceback=_tb.format_exc().rstrip(),
            )
            _refresh_job_status()
            return {"success": False, "job_id": job_id, "error": error, "mutation_outcome": "not_started"}
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

    def execute_code(self, code: str, timeout: Any = None) -> dict[str, Any]:
        """Execute Python code on the GUI thread and wait for the result.

        Runs on the GUI thread so that FreeCAD document operations
        (addObject, recompute, save) are safe and correctly ordered.
        Use execute_code_async for heavy OCCT boolean ops (fuse/cut)
        that would block the GUI thread too long.

        ``timeout`` overrides EXECUTE_CODE_TIMEOUT for this call only, capped at
        MAX_EXECUTE_CODE_TIMEOUT. Raise it for genuinely slow GUI-thread work
        that cannot move off the GUI thread, such as importing or exporting a
        large STEP assembly. Without it such a call reports a timeout while the
        task keeps running. Poll get_task_status with the returned task_id for
        the eventual result before retrying.
        """
        timeout_s = self.EXECUTE_CODE_TIMEOUT
        if timeout is not None:
            try:
                timeout_s = float(timeout)
            except (TypeError, ValueError, OverflowError):
                return {"success": False, "mutation_outcome": "not_started", "error": f"invalid timeout: {timeout!r}"}
            if isinstance(timeout, bool) or not math.isfinite(timeout_s) or timeout_s <= 0:
                return {"success": False, "mutation_outcome": "not_started", "error": f"invalid timeout: {timeout!r}"}
            timeout_s = min(timeout_s, self.MAX_EXECUTE_CODE_TIMEOUT)

        owner = f"sync-{uuid.uuid4().hex}"
        rejection = _claim_script(owner, self._generation)
        if rejection:
            return rejection
        output_buffer = io.StringIO()

        def task() -> dict[str, Any]:
            try:
                with capture_stdout(output_buffer):
                    exec(code, _EXEC_NAMESPACE)
                return {"success": True, "mutation_outcome": "completed",
                        "message": "Python code executed successfully.\nOutput: " + output_buffer.getvalue()}
            except BaseException as exc:
                return {"success": False, "mutation_outcome": "partial_or_unknown",
                        "error": f"{type(exc).__name__}: {exc}", "output": output_buffer.getvalue()}
            finally:
                _scripts.release(owner)

        res = self._dispatch_gui(
            task,
            timeout=timeout_s,
            operation_name="execute_code",
            on_cancel=lambda: _scripts.release(owner),
        )
        if isinstance(res, dict) and res.get("success"):
            FreeCAD.Console.PrintMessage("Python code executed successfully.\n")
            return res
        # Log the offending code (truncated) to make errors traceable
        code_preview = code if len(code) <= 800 else code[:800] + "\n...(truncated)"
        log_error(
            f"Error executing Python code: {res}\n"
            f"--- code ---\n{code_preview}\n--- end ---\n"
        )
        failure = _err(res)
        failure["output"] = output_buffer.getvalue()
        return failure

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return _query_on_gui(lambda: self._get_objects_gui(doc_name), "get_objects", self._generation)

    def _get_objects_gui(self, doc_name: str) -> list[dict[str, Any]]:
        # FreeCAD.getDocument raises (not returns None) for an unknown name.
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception as exc:
            raise ValueError(f"Document '{doc_name}' not found.") from exc
        return [serialize_object(obj) for obj in doc.Objects]

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return _query_on_gui(
            lambda: self._get_object_gui(doc_name, obj_name), "get_object", self._generation
        )

    def _get_object_gui(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        # FreeCAD.getDocument raises (not returns None) for an unknown name.
        try:
            doc = FreeCAD.getDocument(doc_name)
        except Exception as exc:
            raise ValueError(f"Document '{doc_name}' not found.") from exc
        obj = doc.getObject(obj_name)
        if obj is None:
            raise ValueError(f"Object '{obj_name}' not found in document '{doc_name}'.")
        return serialize_object(obj)

    def insert_part_from_library(self, relative_path):
        res = self._dispatch_gui(
            lambda: self._insert_part_from_library(relative_path),
            operation_name="insert_part_from_library",
        )
        if _ok(res):
            return {"success": True, "message": "Part inserted from library."}
        return _err(res)

    def list_documents(self) -> list[str]:
        return _query_on_gui(
            lambda: list(FreeCAD.listDocuments().keys()), "list_documents", self._generation
        )

    def get_parts_list(self):
        return get_parts_list()

    def get_active_screenshot(
        self,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
        doc_name: str | None = None,
    ) -> str | None:
        """Capture the displayed view, optionally restricted to its document.

        None means no matching displayed 3D view. Other failures are RPC faults.
        The GUI task owns the file, including cleanup after a caller timeout.
        """
        def task() -> dict[str, Any]:
            if doc_name is not None:
                active = FreeCAD.ActiveDocument
                if active is None or active.Name != doc_name:
                    return {"image": None}
            if get_displayed_3d_view() is None:
                return {"image": None}
            fd, tmp_path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            try:
                result = save_active_screenshot(tmp_path, view_name, width, height, focus_object)
                if result is not True:
                    raise RuntimeError(f"Screenshot failed: {result}")
                with open(tmp_path, "rb") as stream:
                    data = stream.read()
                if not data:
                    raise RuntimeError("Screenshot renderer produced an empty image")
                return {"image": base64.b64encode(data).decode("utf-8")}
            finally:
                os.unlink(tmp_path)

        result = self._dispatch_gui(task, operation_name="get_active_screenshot")
        if isinstance(result, dict) and "image" in result:
            return result["image"]
        raise Fault(1, json.dumps(_err(result), default=str))

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
            return {"success": False, "mutation_outcome": "not_started", "error": f"Document '{doc_name}' not found."}

        try:
            doc.removeObject(obj_name)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj_name}' deleted via RPC.\n")
            return True
        except Exception as e:
            return str(e)


    def _reload_document_gui(self, doc_name: str) -> dict[str, Any] | str:
        if doc_name not in FreeCAD.listDocuments():
            return {"success": False, "mutation_outcome": "not_started", "error": f"Document '{doc_name}' is not loaded."}
        doc = FreeCAD.getDocument(doc_name)
        file_path = doc.FileName
        if not file_path:
            return {"success": False, "mutation_outcome": "not_started", "error": (
                f"Document '{doc_name}' has no file on disk "
                "(unsaved scratch document); nothing to reload from.")}
        if not os.path.exists(file_path):
            return {"success": False, "mutation_outcome": "not_started", "error": f"File for '{doc_name}' not found at {file_path!r}."}
        # Close, then reopen from the same file. FreeCAD names the reopened
        # document after the file stem, not after the name it had before
        # ("HandleConcept3D" saved as handle-concept-3d.FCStd comes back as
        # handle_concept_3d), so the handler reports the name FreeCAD
        # actually used. Reporting the requested name breaks every follow-up
        # call that still uses it.
        FreeCAD.closeDocument(doc_name)
        try:
            reopened = FreeCAD.openDocument(file_path)
        except Exception as exc:
            return {"success": False, "mutation_outcome": "partial_or_unknown",
                    "error": f"Document '{doc_name}' was closed but reopening failed: {exc}",
                    "closed_document": doc_name, "file_path": file_path}
        FreeCAD.Console.PrintMessage(
            f"Document '{doc_name}' reloaded from '{file_path}' via RPC "
            f"(now '{reopened.Name}').\n"
        )
        return {"success": True, "document_name": reopened.Name}

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


def start_rpc_server(port: int = 9875) -> str:
    global rpc_server_thread, rpc_server_instance, _listener_state, _server_id, _applied_settings

    if rpc_server_instance:
        if _listener_state == "stop_failed":
            return "RPC Server stop failed; retry Stop before restarting."
        host, bound_port = rpc_server_instance.server_address
        return f"RPC Server already running at {host}:{bound_port} (PID {os.getpid()})."

    # A previous stop may still be draining an in-flight request off-thread;
    # binding before its server_close() would hit the old socket.
    if _stop_thread is not None and _stop_thread.is_alive():
        _stop_thread.join(timeout=5.0)
        if _stop_thread.is_alive():
            return ("RPC Server is still stopping (a request is draining); "
                    "try again in a few seconds.")

    if _scripts.snapshot()["state"] == "busy" or get_dispatch_status()["state"] in {"busy", "stuck"}:
        return "RPC Server cannot restart while an operation is still running; wait for completion."

    settings = load_settings()
    remote_enabled = settings.get("remote_enabled", False)
    allowed_ips = settings.get("allowed_ips", "127.0.0.1")
    auth_token = settings.get("auth_token", "")

    if remote_enabled:
        host = "0.0.0.0"
        if not auth_token:
            FreeCAD.Console.PrintWarning(
                "MCP RPC: remote connections are enabled WITHOUT an auth token. "
                "Anyone on an allowed IP can execute code in FreeCAD. "
                "Set a token via 'Set Auth Token' in the FreeCAD MCP menu.\n"
            )
    else:
        host = "127.0.0.1"

    _listener_state = "starting"
    try:
        server = FilteredXMLRPCServer(
            (host, port),
            allowed_ips_str=allowed_ips,
            auth_token=auth_token,
            allow_none=True,
            logRequests=False,
        )
    except Exception:
        _listener_state = "stopped"
        raise
    try:
        init_waker()
        start_heartbeat()
        server.register_instance(FreeCADRPC())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
    except Exception:
        # A failed start must not retain a listening socket or appear running.
        # This allows the toolbar command to be retried without restarting FreeCAD.
        server.server_close()
        request_shutdown()
        cleanup_waker()
        _listener_state = "stopped"
        raise

    _server_id = uuid.uuid4().hex
    _applied_settings = dict(settings)
    _listener_state = "running"
    rpc_server_instance = server
    rpc_server_thread = thread
    bound_host, bound_port = server.server_address
    msg = f"RPC Server started at {bound_host}:{bound_port} (PID {os.getpid()})."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    if auth_token:
        msg += " Auth token required."
    return msg


def stop_rpc_server() -> str:
    global rpc_server_instance, rpc_server_thread, _stop_thread, _listener_state, _job_status_message

    if not rpc_server_instance:
        return "RPC Server was not running."

    server = rpc_server_instance
    thread = rpc_server_thread

    _listener_state = "stopping"
    request_shutdown()
    cleanup_waker()
    try:
        bar = FreeCADGui.getMainWindow().statusBar()
        if _job_status_message and bar.currentMessage() == _job_status_message:
            bar.clearMessage()
    except Exception:
        pass
    _job_status_message = ""

    def _shutdown_and_close() -> None:
        global _listener_state
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
            _listener_state = "stopped"
        FreeCAD.Console.PrintMessage("RPC Server stopped.\n")

    try:
        stopper = threading.Thread(target=_shutdown_and_close, daemon=True)
        stopper.start()
    except Exception as exc:
        # Keep the live listener reachable so Stop can be retried. Dispatch
        # stays closed to new work after the failed stop attempt.
        _stop_thread = None
        _listener_state = "stop_failed"
        return f"RPC Server stop failed: {exc}. Retry Stop; the listener is still open."
    _stop_thread = stopper
    rpc_server_instance = None
    rpc_server_thread = None
    return "RPC Server stopping… Queued work cancelled; running work may finish. Shared script variables are retained."


register_commands()
schedule_toggle_sync()
