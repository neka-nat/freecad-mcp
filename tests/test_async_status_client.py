from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from freecad_mcp.freecad_client import FreeCADConnection
from test_rpc_concurrency import running_server


@pytest.mark.parametrize("method", ["get_async_status", "get_rpc_status"])
def test_status_uses_its_own_connection_while_gui_request_is_blocked(method: str) -> None:
    entered, release = threading.Event(), threading.Event()

    class Interface:
        def execute_code_async(self, code: str) -> dict:
            entered.set()
            release.wait(5)
            return {"success": True, "job_id": "job-1"}

        def get_async_status(self, job_id: str = "") -> dict:
            return {"success": True, "job": {"id": job_id, "state": "running"}}

        def get_rpc_status(self) -> dict:
            return {"success": True, "async_jobs_running": ["job-1"]}

    with running_server(Interface()) as (host, port):
        connection = FreeCADConnection(host, port, timeout=2)
        try:
            with ThreadPoolExecutor(max_workers=1) as workers:
                blocked = workers.submit(connection.execute_code_async, "pass")
                try:
                    assert entered.wait(2)
                    args = ("job-1",) if method == "get_async_status" else ()
                    result = getattr(connection, method)(*args)
                    assert result["success"] is True
                    assert not blocked.done()
                finally:
                    release.set()
                assert blocked.result(timeout=2)["success"] is True
        finally:
            release.set()
            connection.disconnect()
