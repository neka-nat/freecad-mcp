from concurrent.futures import ThreadPoolExecutor
import threading
import types
from unittest.mock import MagicMock

import pytest

from freecad_mcp.freecad_client import FreeCADConnection
from test_rpc_concurrency import running_server
from test_rpc_handlers import rpc_module


@pytest.mark.parametrize("shared_connection", [False, True])
def test_concurrent_execute_calls_cover_queue_and_run_time(
    rpc_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch, shared_connection: bool,
) -> None:
    """Use the real client, TCP server and dispatcher with shortened budgets."""
    rpc = rpc_module.FreeCADRPC()
    rpc.EXECUTE_CODE_TIMEOUT = 1
    monkeypatch.setattr(FreeCADConnection, "EXECUTE_CODE_TIMEOUT", 1, raising=False)
    monkeypatch.setattr(FreeCADConnection, "RPC_TIMEOUT_MARGIN", 0.3, raising=False)
    entered = threading.Event()
    rpc_module.FreeCAD.test_entered = entered
    with running_server(rpc) as (host, port):
        connection = FreeCADConnection(host, port, timeout=1)
        second_connection = connection if shared_connection else FreeCADConnection(host, port, timeout=1)
        try:
            with ThreadPoolExecutor(max_workers=2) as workers:
                first = workers.submit(
                    connection.execute_code,
                    "import time\nFreeCAD.test_entered.set()\ntime.sleep(0.7)",
                )
                assert entered.wait(2)
                second = workers.submit(second_connection.execute_code, "import time\ntime.sleep(0.7)")
                assert first.result(timeout=4)["success"] is True
                assert second.result(timeout=4)["success"] is True
            assert connection.get_rpc_status()["gui_dispatch"]["state"] == "healthy"
        finally:
            connection.disconnect()
            second_connection.disconnect()


@pytest.mark.parametrize(
    ("method", "args", "minimum", "configured"),
    [
        ("execute_code", ("pass",), 210, 150),
        ("execute_code", ("pass",), 500, 500),
        ("run_fem_analysis", ("Doc", "Analysis", 600), 1230, 150),
        ("run_fem_analysis", ("Doc", "Analysis", 600), 2000, 2000),
    ],
)
@pytest.mark.parametrize("fails", [False, True])
def test_long_call_socket_budgets_and_cleanup(
    monkeypatch: pytest.MonkeyPatch, method: str, args: tuple,
    minimum: float, configured: float, fails: bool,
) -> None:
    """Check response budget policy and connection cleanup on both exit paths."""
    connection = FreeCADConnection(timeout=configured)
    proxy = MagicMock()
    proxy.__enter__.return_value = proxy
    getattr(proxy, method).return_value = {"success": True}
    if fails:
        getattr(proxy, method).side_effect = TimeoutError("socket expired")
    make_proxy = MagicMock(return_value=proxy)
    monkeypatch.setattr(connection, "_make_proxy", make_proxy)
    try:
        if fails:
            with pytest.raises(TimeoutError, match="socket expired"):
                getattr(connection, method)(*args)
        else:
            assert getattr(connection, method)(*args) == {"success": True}
        assert make_proxy.call_args.args[0] >= minimum
        getattr(proxy, method).assert_called_once_with(*args)
        proxy.__exit__.assert_called_once()
    finally:
        connection.disconnect()
