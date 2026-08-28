"""The RPC server must answer a second request while one is still running.

``get_rpc_status`` reports GUI-dispatch health without touching the GUI
thread, so that a wedged operation can be identified while it is still wedged.
Serving requests one at a time defeated that: a blocked ``execute_code``
occupied the single accept loop, and the status call could not reach the
server until the operation it was meant to diagnose had already finished.
"""

from contextlib import contextmanager
from pathlib import Path
from socketserver import ThreadingMixIn
import sys
import threading
import time
import types
from typing import Iterator
import xmlrpc.client


ADDON_DIR = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
if str(ADDON_DIR) not in sys.path:
    sys.path.insert(0, str(ADDON_DIR))


_filtered_server_class = None


def filtered_server_class() -> type:
    """Import FilteredXMLRPCServer with a FreeCAD console stub in place.

    ip_filter.py logs rejected connections through FreeCAD.Console and keeps
    its own reference to the module after import, so the stub is withdrawn
    from sys.modules straight away to leave other test modules alone.
    """
    global _filtered_server_class
    if _filtered_server_class is not None:
        return _filtered_server_class

    saved = sys.modules.get("FreeCAD")
    stub = types.ModuleType("FreeCAD")
    stub.Console = types.SimpleNamespace(
        PrintWarning=lambda _message: None, PrintError=lambda _message: None
    )
    sys.modules["FreeCAD"] = stub
    try:
        sys.modules.pop("rpc_server.ip_filter", None)
        from rpc_server.ip_filter import FilteredXMLRPCServer
    finally:
        if saved is None:
            sys.modules.pop("FreeCAD", None)
        else:
            sys.modules["FreeCAD"] = saved

    _filtered_server_class = FilteredXMLRPCServer
    return FilteredXMLRPCServer


class WedgedGuiThread:
    """Stands in for FreeCADRPC while a GUI task refuses to finish.

    ``execute_code`` parks the way a real one does when ``dispatch_to_gui`` is
    waiting on a wedged GUI thread; ``get_rpc_status`` answers from
    lock-guarded state and never touches the GUI thread at all.
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def execute_code(self, code: str) -> dict:
        self.entered.set()
        self.release.wait(30)
        return {"success": True, "message": code}

    def get_rpc_status(self) -> dict:
        return {
            "success": True,
            "rpc_server": "running",
            "gui_dispatch": {"state": "stuck", "operation": "execute_code"},
        }


class _TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout: float):
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self._timeout
        return connection


def client(host: str, port: int, timeout: float) -> xmlrpc.client.ServerProxy:
    """A proxy with its own connection, so callers do not queue behind each other."""
    return xmlrpc.client.ServerProxy(
        f"http://{host}:{port}", allow_none=True, transport=_TimeoutTransport(timeout)
    )


def build_server(interface: object):
    server = filtered_server_class()(
        ("127.0.0.1", 0), allowed_ips_str="127.0.0.1", allow_none=True, logRequests=False
    )
    server.register_instance(interface)
    return server


@contextmanager
def running_server(interface: object) -> Iterator[tuple[str, int]]:
    server = build_server(interface)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        loop.join(timeout=5)
        server.server_close()


def test_request_threads_are_daemons() -> None:
    """server_close() joins non-daemon threads, which would hang Stop."""
    server_class = filtered_server_class()
    assert issubclass(server_class, ThreadingMixIn)
    assert server_class.daemon_threads is True


def test_status_is_answered_while_execute_code_is_blocked() -> None:
    interface = WedgedGuiThread()
    with running_server(interface) as (host, port):
        blocked = threading.Thread(
            target=lambda: client(host, port, 30).execute_code("while True: pass"),
            daemon=True,
        )
        blocked.start()
        try:
            assert interface.entered.wait(5), "execute_code never reached its handler"
            status = client(host, port, 5).get_rpc_status()
            assert status["gui_dispatch"]["state"] == "stuck"
            assert status["gui_dispatch"]["operation"] == "execute_code"
        finally:
            interface.release.set()
            blocked.join(timeout=10)


def test_ip_filter_still_runs_before_a_thread_is_spawned() -> None:
    """verify_request lives in the accept loop, ahead of process_request."""
    interface = WedgedGuiThread()
    server = build_server(interface)
    try:
        assert server.verify_request(None, ("127.0.0.1", 5000)) is True
        assert server.verify_request(None, ("10.1.2.3", 5000)) is False
    finally:
        server.server_close()


def test_stopping_does_not_wait_for_an_in_flight_request() -> None:
    """Stop must not block on a stuck execute_code (daemon_threads = True)."""
    interface = WedgedGuiThread()
    server = build_server(interface)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    host, port = server.server_address
    blocked = threading.Thread(
        target=lambda: client(host, port, 30).execute_code("while True: pass"),
        daemon=True,
    )
    blocked.start()
    try:
        assert interface.entered.wait(5), "execute_code never reached its handler"
        started = time.monotonic()
        server.shutdown()
        loop.join(timeout=5)
        server.server_close()
        assert time.monotonic() - started < 2.0, "shutdown waited for the in-flight request"
        assert not loop.is_alive()
    finally:
        interface.release.set()
        blocked.join(timeout=10)
