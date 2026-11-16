"""Rejected work cannot leak ownership or execute later; lifecycle failures recover."""
import types
from unittest.mock import Mock

import pytest

from test_gui_dispatch import load_gui_dispatch, ThreadedWaker
from test_rpc_handlers import rpc_module


@pytest.mark.parametrize("code", [42, None, {}, ["pass"]])
def test_invalid_async_code_does_not_claim_namespace(rpc_module, code) -> None:
    rpc = rpc_module.FreeCADRPC()
    reply = rpc.execute_code_async(code)
    assert reply["mutation_outcome"] == "not_started"
    assert rpc_module._scripts.snapshot()["state"] == "idle"
    assert rpc.execute_code("print('next')")["success"]


@pytest.mark.parametrize("budget", ["bad", 0, -1, True, float("nan"), float("inf"), 10**400])
@pytest.mark.parametrize("parameter", ["timeout", "queue_timeout"])
def test_invalid_dispatch_budget_never_enqueues(budget, parameter: str) -> None:
    with load_gui_dispatch() as dispatch:
        called = Mock()
        cancelled = Mock()
        reply = dispatch.dispatch_to_gui(called, on_cancel=cancelled, **{parameter: budget})
        assert reply["mutation_outcome"] == "not_started"
        assert reply["code"] == "INVALID_TIMEOUT"
        assert dispatch._rpc_request_queue.empty()
        dispatch.process_gui_tasks()
        called.assert_not_called()
        cancelled.assert_called_once_with()


@pytest.mark.parametrize("guard", ["activeModalWidget", "activePopupWidget"])
def test_idle_heartbeat_observes_blockers(monkeypatch, guard: str) -> None:
    with load_gui_dispatch() as dispatch:
        monkeypatch.setattr(dispatch.QtWidgets.QApplication, guard, staticmethod(lambda: object()))
        dispatch.process_gui_tasks()
        assert not dispatch.get_dispatch_status()["ready"]
        assert dispatch.get_dispatch_status()["state"] == "blocked"
        monkeypatch.setattr(dispatch.QtWidgets.QApplication, guard, staticmethod(lambda: None))
        dispatch.process_gui_tasks()
        assert dispatch.get_dispatch_status()["ready"]


def test_drain_stops_when_a_callback_opens_a_modal(monkeypatch) -> None:
    with load_gui_dispatch() as dispatch:
        modal = []
        calls = []
        monkeypatch.setattr(dispatch.QtWidgets.QApplication, "activeModalWidget",
                            staticmethod(lambda: modal[0] if modal else None))
        dispatch.post_to_gui(lambda: modal.append(object()))
        dispatch.post_to_gui(lambda: calls.append("second"))
        dispatch.process_gui_tasks()
        assert not calls
        assert not dispatch.get_dispatch_status()["ready"]
        modal.clear()
        dispatch.process_gui_tasks()
        assert calls == ["second"]


def test_task_ids_do_not_alias_a_new_dispatcher_instance() -> None:
    ids = []
    for _ in range(2):
        with load_gui_dispatch() as dispatch:
            dispatch._waker = ThreadedWaker(dispatch)
            assert dispatch.dispatch_to_gui(lambda: {"success": True}, timeout=1)["success"]
            dispatch._waker.join()
            current = dispatch.get_task_status()["tasks"][0]["task_id"]
            assert isinstance(current, str)
            for previous in ids:
                assert not dispatch.get_task_status(previous)["success"]
            ids.append(current)
    assert ids[0] != ids[1]


@pytest.mark.parametrize("failure", ["construct", "start"])
def test_failed_stop_thread_keeps_listener_available_for_retry(rpc_module, monkeypatch, failure: str) -> None:
    server = Mock()
    listener = Mock()
    listener.is_alive.return_value = False
    rpc_module.rpc_server_instance = server
    rpc_module.rpc_server_thread = listener
    rpc_module._listener_state = "running"

    class Stopper:
        def __init__(self, target, **_kwargs):
            if failure == "construct":
                raise RuntimeError("no thread")
        def start(self) -> None:
            raise RuntimeError("cannot start")
    monkeypatch.setattr(rpc_module.threading, "Thread", Stopper)
    assert "stop failed" in rpc_module.stop_rpc_server()
    assert rpc_module.rpc_server_instance is server
    assert rpc_module._listener_state == "stop_failed"
    assert not rpc_module.test_dispatch.get_dispatch_status()["accepting"]
    server.server_close.assert_not_called()

    monkeypatch.setattr(rpc_module.threading, "Thread",
                        lambda target, **_kw: types.SimpleNamespace(start=target, is_alive=lambda: False))
    assert "stopping" in rpc_module.stop_rpc_server()
    server.shutdown.assert_called_once_with()
    server.server_close.assert_called_once_with()
    assert rpc_module.rpc_server_instance is None
    assert rpc_module._listener_state == "stopped"
