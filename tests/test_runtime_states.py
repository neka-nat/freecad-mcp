"""Exercise lifecycle boundaries, late outcomes and shared-state ownership."""

import json
import threading
import time
import types

import pytest

from freecad_mcp import server
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations import execute_code_operation, get_task_status_operation
from freecad_mcp.responses import ErrorResponse
from freecad_mcp.server_state import ServerState
from freecad_mcp.version import PROTOCOL_VERSION
from test_gui_dispatch import load_gui_dispatch, ThreadedWaker
from test_rpc_handlers import rpc_module, wait_for_job
from test_rpc_concurrency import running_server
from test_version_handshake import VersionedAddon, matching_status


def test_stop_cancels_waiters_and_drops_old_cosmetic_work() -> None:
    with load_gui_dispatch() as dispatch:
        executed, replies = [], []
        enqueued = threading.Event()
        dispatch._waker = types.SimpleNamespace(wake=enqueued.set)
        caller = threading.Thread(target=lambda: replies.append(dispatch.dispatch_to_gui(
            lambda: executed.append("operation"), timeout=10)))
        caller.start()
        assert enqueued.wait(1)
        dispatch.post_to_gui(lambda: executed.append("old UI"))
        dispatch.request_shutdown()
        caller.join(1)
        assert not caller.is_alive()
        assert replies[0]["mutation_outcome"] == "not_started"
        assert dispatch.get_task_status(replies[0]["task_id"])["task"]["state"] == "cancelled"
        dispatch.start_heartbeat()
        dispatch.process_gui_tasks()
        assert executed == []


def test_stopped_and_old_generation_dispatch_cannot_enqueue() -> None:
    with load_gui_dispatch() as dispatch:
        old = dispatch.dispatch_generation()
        dispatch.request_shutdown()
        assert dispatch.dispatch_to_gui(lambda: pytest.fail("ran"))["code"] == "RPC_STOPPED"
        dispatch.start_heartbeat()
        result = dispatch.dispatch_to_gui(lambda: pytest.fail("ran"), expected_generation=old)
        assert result["mutation_outcome"] == "not_started"


@pytest.mark.parametrize("guard", ["activeModalWidget", "activePopupWidget"])
def test_readiness_reports_ui_blockers(guard: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with load_gui_dispatch() as dispatch:
        dispatch.post_to_gui(lambda: None)
        monkeypatch.setattr(dispatch.QtWidgets.QApplication, guard, staticmethod(lambda: object()))
        dispatch.process_gui_tasks()
        status = dispatch.get_dispatch_status()
        assert status["state"] == "blocked"
        assert status["ready"] is False
        assert status["blocked_reason"]
        monkeypatch.setattr(dispatch.QtWidgets.QApplication, guard, staticmethod(lambda: None))
        dispatch.process_gui_tasks()
        assert dispatch.get_dispatch_status()["ready"] is True


def test_late_result_is_pollable_and_caller_timeout_is_retained() -> None:
    with load_gui_dispatch() as dispatch:
        release = threading.Event()
        dispatch._waker = ThreadedWaker(dispatch)
        try:
            reply = dispatch.dispatch_to_gui(lambda: (release.wait(2), {"answer": 42})[1], timeout=.02)
            task_id = reply["task_id"]
            assert reply["mutation_outcome"] == "still_running"
            assert dispatch.get_task_status(task_id)["task"]["state"] == "timed_out_running"
        finally:
            release.set()
            dispatch._waker.join()
        task = dispatch.get_task_status(task_id)["task"]
        assert task["state"] == "done"
        assert task["caller_timed_out"] is True
        assert task["result"] == {"answer": 42}
        assert task["mutation_outcome"] != "still_running"


def test_late_script_failure_preserves_output_and_releases_ownership(rpc_module: types.ModuleType) -> None:
    rpc = rpc_module.FreeCADRPC()
    release = threading.Event()
    rpc_module.FreeCAD.release = release
    try:
        result = rpc.execute_code("App.release.wait(3); print('late'); raise ValueError('boom')", .02)
        task_id = result["task_id"]
        assert rpc.execute_code_async("pass")["mutation_outcome"] == "not_started"
    finally:
        release.set()
        rpc_module.test_dispatch._waker.join()
    task = rpc.get_task_status(task_id)["task"]
    assert task["state"] == "failed"
    assert task["result"]["output"] == "late\n"
    assert task["mutation_outcome"] == "partial_or_unknown"
    assert rpc.execute_code("print('recovered')")["success"]


def test_queue_cancellation_releases_script_lease(rpc_module: types.ModuleType) -> None:
    rpc_module.test_dispatch._waker = None
    reply = rpc_module.FreeCADRPC().execute_code("never = 42", .01)
    assert reply["mutation_outcome"] == "not_started"
    assert rpc_module._scripts.snapshot()["state"] == "idle"
    rpc_module.test_dispatch.process_gui_tasks()
    assert "never" not in rpc_module._EXEC_NAMESPACE


def test_old_rpc_instance_and_async_commit_cannot_cross_restart(rpc_module: types.ModuleType) -> None:
    rpc = rpc_module.FreeCADRPC()
    release = threading.Event()
    rpc_module.FreeCAD.release = release
    job = rpc.execute_code_async("App.release.wait(3); commit(lambda: setattr(App, 'wrong_epoch', True))")
    assert job["success"]
    rpc_module.test_dispatch.request_shutdown()
    assert "still running" in rpc_module.start_rpc_server(port=0)
    release.set()
    assert wait_for_job(rpc, job["job_id"])["state"] == "failed"
    assert not hasattr(rpc_module.FreeCAD, "wrong_epoch")
    rpc_module.test_dispatch.start_heartbeat()
    assert rpc.execute_code("pass")["mutation_outcome"] == "not_started"
    with pytest.raises(Exception, match="RPC_STOPPED"):
        rpc.get_object("Doc", "Box")
    assert rpc_module.FreeCADRPC().execute_code("pass")["success"]


def test_job_indicator_tracks_registry_and_preserves_other_messages(rpc_module: types.ModuleType) -> None:
    dispatch = rpc_module.test_dispatch
    dispatch._waker = None
    bar = rpc_module.FreeCADGui.getMainWindow().statusBar()
    for job in ("a", "b"):
        rpc_module._record_job(job, state="running")
    rpc_module._refresh_job_status()
    dispatch.process_gui_tasks()
    assert "2 background" in bar.currentMessage()
    rpc_module._record_job("a", state="done")
    rpc_module._refresh_job_status()
    dispatch.process_gui_tasks()
    assert "1 background" in bar.currentMessage()
    bar.showMessage("another addon owns this")
    rpc_module._record_job("b", state="done")
    rpc_module._refresh_job_status()
    dispatch.process_gui_tasks()
    assert bar.currentMessage() == "another addon owns this"


def test_task_history_is_bounded_but_keeps_pending_and_truncates_results() -> None:
    with load_gui_dispatch() as dispatch:
        history = dispatch._task_history
        history.update(1, state="running")
        for task_id in range(2, 24):
            history.finish(task_id, "x" * 70000, failed=False)
        assert len(history.snapshot()["tasks"]) == 21
        assert history.snapshot(1)["task"]["state"] == "running"
        assert history.snapshot(2)["success"] is False
        assert history.snapshot(23)["task"]["result_truncated"] is True


def test_cached_connection_refreshes_generation_and_resets_missing_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    interface = VersionedAddon(matching_status(server_id="first", execute_code_timeout=45))
    with running_server(interface) as (host, port):
        connection = FreeCADConnection(host, port)
        monkeypatch.setattr(server, "state", ServerState(freecad_connection=connection))
        assert server.get_freecad_connection().EXECUTE_CODE_TIMEOUT == 45
        interface.status = {"protocol_version": PROTOCOL_VERSION - 1, "server_id": "second"}
        assert server.get_freecad_connection() is connection
        assert connection.server_id == "second"
        assert connection.EXECUTE_CODE_TIMEOUT == 90
        assert connection.compatibility["state"] == "mismatch"
        assert server.state.version_notice


def test_rpc_status_exposes_pending_config_without_tokens(rpc_module: types.ModuleType) -> None:
    rpc_module._applied_settings = {"remote_enabled": False, "auth_token": "old-secret"}
    rpc_module.load_settings = lambda: {"remote_enabled": True, "auth_token": "new-secret"}
    status = rpc_module.FreeCADRPC().get_rpc_status()
    assert status["configuration"]["restart_required"] is True
    assert status["configuration"]["changed_fields"] == ["remote_enabled", "auth_token"]
    assert "secret" not in json.dumps(status)


def test_mcp_failure_preserves_task_id_and_polling_result() -> None:
    connection = types.SimpleNamespace(
        execute_code=lambda *_: {"success": False, "error": "timeout", "task_id": 7,
                                "mutation_outcome": "still_running"},
        get_task_status=lambda _: {"success": True, "task": {"task_id": 7, "state": "done"}},
    )
    reply = execute_code_operation(connection, True, "pass")
    assert isinstance(reply, ErrorResponse)
    assert json.loads(reply[1].text)["task_id"] == 7
    assert json.loads(get_task_status_operation(connection, 7)[0].text)["task"]["state"] == "done"
