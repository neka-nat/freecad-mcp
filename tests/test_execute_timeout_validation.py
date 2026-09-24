"""Reject unusable budgets before opening a socket or scheduling GUI work."""

from concurrent.futures import ThreadPoolExecutor
import threading
import types
from unittest.mock import MagicMock

import pytest

from freecad_mcp.freecad_client import FreeCADConnection
from test_rpc_concurrency import running_server
from test_rpc_handlers import rpc_module


INVALID_TIMEOUTS = [
    0, -1, float("nan"), float("inf"), -float("inf"), True, False, "soon",
    pytest.param(10**400, id="overflowing-integer"),
]


@pytest.mark.parametrize("timeout", INVALID_TIMEOUTS)
def test_client_rejects_invalid_timeout_before_connecting(
    monkeypatch: pytest.MonkeyPatch, timeout: object,
) -> None:
    connection = FreeCADConnection()
    make_proxy = MagicMock()
    monkeypatch.setattr(connection, "_make_proxy", make_proxy)
    try:
        with pytest.raises(ValueError, match="timeout"):
            connection.execute_code("raise AssertionError('must not execute')", timeout)
        make_proxy.assert_not_called()
    finally:
        connection.disconnect()


@pytest.mark.parametrize("timeout", INVALID_TIMEOUTS)
def test_addon_rejects_invalid_timeout_before_dispatch(
    rpc_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch, timeout: object,
) -> None:
    dispatch = MagicMock()
    monkeypatch.setattr(rpc_module, "dispatch_to_gui", dispatch)
    result = rpc_module.FreeCADRPC().execute_code("must_not_run = True", timeout)
    assert result["success"] is False
    assert "timeout" in result["error"]
    dispatch.assert_not_called()
    assert "must_not_run" not in rpc_module._EXEC_NAMESPACE


def test_client_caps_wire_and_socket_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = FreeCADConnection()
    proxy = MagicMock()
    proxy.__enter__.return_value = proxy
    proxy.execute_code.return_value = {"success": True}
    make_proxy = MagicMock(return_value=proxy)
    monkeypatch.setattr(connection, "_make_proxy", make_proxy)
    try:
        assert connection.execute_code("pass", 10**9)["success"] is True
        proxy.execute_code.assert_called_once_with("pass", 1800.0)
        make_proxy.assert_called_once_with(3630.0)
    finally:
        connection.disconnect()


@pytest.mark.parametrize("shared_connection", [False, True])
def test_custom_timeout_covers_queue_then_execution_over_tcp(
    rpc_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch, shared_connection: bool,
) -> None:
    rpc = rpc_module.FreeCADRPC()
    rpc.EXECUTE_CODE_TIMEOUT = 0.05
    monkeypatch.setattr(FreeCADConnection, "EXECUTE_CODE_TIMEOUT", 0.05)
    monkeypatch.setattr(FreeCADConnection, "RPC_TIMEOUT_MARGIN", 0.1)
    entered = threading.Event()
    rpc_module.FreeCAD.test_entered = entered
    with running_server(rpc) as (host, port):
        connection = FreeCADConnection(host, port, timeout=0.1)
        second = connection if shared_connection else FreeCADConnection(host, port, timeout=0.1)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                first = workers.submit(
                    connection.execute_code,
                    "import time\nFreeCAD.test_entered.set()\ntime.sleep(0.35)\nprint('first')",
                    0.6,
                )
                assert entered.wait(2)
                queued = workers.submit(
                    second.execute_code, "import time\ntime.sleep(0.35)\nprint('second')", 0.6,
                )
                first_result, second_result = first.result(timeout=4), queued.result(timeout=4)
            assert first_result["success"] is True
            assert first_result["message"].endswith("first\n")
            assert second_result["success"] is True
            assert second_result["message"].endswith("second\n")
            assert connection.get_rpc_status()["gui_dispatch"]["state"] == "healthy"
        finally:
            connection.disconnect()
            second.disconnect()
