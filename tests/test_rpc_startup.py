"""Startup failures must release the listener so a user can retry."""

import socket
import threading
import types
from typing import Any

import pytest

from test_rpc_handlers import rpc_module


def test_thread_start_failure_releases_port_and_allows_retry(
    rpc_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_thread = rpc_module.threading.Thread
    servers = []
    server_class = rpc_module.FilteredXMLRPCServer

    def recording_server(*args: Any, **kwargs: Any) -> Any:
        server = server_class(*args, **kwargs)
        servers.append(server)
        return server

    class CannotStart:
        def start(self) -> None:
            raise RuntimeError("cannot start server thread")

    monkeypatch.setattr(rpc_module, "FilteredXMLRPCServer", recording_server)
    monkeypatch.setattr(rpc_module, "init_waker", lambda: None)
    monkeypatch.setattr(rpc_module, "cleanup_waker", lambda: None)
    monkeypatch.setattr(rpc_module.threading, "Thread", lambda **kwargs: CannotStart())
    try:
        with pytest.raises(RuntimeError, match="cannot start server thread"):
            rpc_module.start_rpc_server(port=0)
        assert rpc_module.rpc_server_instance is None
        assert rpc_module.rpc_server_thread is None
        assert servers[0].socket.fileno() == -1

        monkeypatch.setattr(rpc_module.threading, "Thread", real_thread)
        port = servers[0].server_address[1]
        message = rpc_module.start_rpc_server(port=port)
        assert f"127.0.0.1:{port}" in message
        assert "PID" in message
        assert rpc_module.rpc_server_thread.is_alive()
    finally:
        monkeypatch.setattr(rpc_module.threading, "Thread", real_thread)
        if rpc_module.rpc_server_instance is not None and rpc_module.rpc_server_thread is not None:
            thread = rpc_module.rpc_server_thread
            if isinstance(thread, threading.Thread) and thread.is_alive():
                rpc_module.stop_rpc_server()
                rpc_module._stop_thread.join(3)
        for server in servers:
            server.server_close()


def test_busy_port_does_not_publish_running_state(rpc_module: types.ModuleType) -> None:
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        with pytest.raises(OSError):
            rpc_module.start_rpc_server(port=occupied.getsockname()[1])
    assert rpc_module.rpc_server_instance is None
    assert rpc_module.rpc_server_thread is None


def test_gui_setup_failure_releases_listener(
    rpc_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    servers = []
    server_class = rpc_module.FilteredXMLRPCServer

    def recording_server(*args: Any, **kwargs: Any) -> Any:
        server = server_class(*args, **kwargs)
        servers.append(server)
        return server

    def fail_setup() -> None:
        raise RuntimeError("GUI setup failed")

    monkeypatch.setattr(rpc_module, "FilteredXMLRPCServer", recording_server)
    monkeypatch.setattr(rpc_module, "init_waker", fail_setup)
    monkeypatch.setattr(rpc_module, "cleanup_waker", lambda: None)
    with pytest.raises(RuntimeError, match="GUI setup failed"):
        rpc_module.start_rpc_server(port=0)
    assert servers[0].socket.fileno() == -1
    assert rpc_module.rpc_server_instance is None
    assert rpc_module.rpc_server_thread is None
