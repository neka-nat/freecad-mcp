"""Client-side contract for the execute_code timeout parameter."""

from typing import Any

import pytest

from freecad_mcp.freecad_client import FreeCADConnection


class _RecordingProxy:
    def __init__(self, calls: list[tuple[str, tuple[Any, ...]]]) -> None:
        self._calls = calls

    def __enter__(self) -> "_RecordingProxy":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute_code(self, *args: Any) -> dict[str, Any]:
        self._calls.append(("execute_code", args))
        return {"success": True, "message": "ok"}


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, tuple[Any, ...]]] = []
    socket_timeouts: list[float] = []

    def fake_make_proxy(self: FreeCADConnection, timeout: float) -> _RecordingProxy:
        socket_timeouts.append(timeout)
        return _RecordingProxy(calls)

    monkeypatch.setattr(FreeCADConnection, "_make_proxy", fake_make_proxy)
    conn = FreeCADConnection()
    socket_timeouts.clear()  # drop the proxy built in __init__
    return conn, calls, socket_timeouts


def test_without_timeout_sends_one_argument(connection) -> None:
    """Keeps a newer client compatible with an addon predating the parameter."""
    conn, calls, socket_timeouts = connection
    assert conn.execute_code("x = 1")["success"] is True
    assert calls == [("execute_code", ("x = 1",))]
    # Queue budget plus run budget: 2 * 90 s plus the 30 s margin.
    assert socket_timeouts == [2 * conn.EXECUTE_CODE_TIMEOUT + conn.RPC_TIMEOUT_MARGIN]


def test_with_timeout_forwards_it_and_widens_the_socket(connection) -> None:
    """A 600 s GUI task must not be cut off by the 150 s default socket timeout."""
    conn, calls, socket_timeouts = connection
    assert conn.execute_code("x = 1", 600)["success"] is True
    assert calls == [("execute_code", ("x = 1", 600))]
    assert socket_timeouts == [1230]


def test_short_timeout_keeps_the_default_socket_timeout(connection) -> None:
    conn, calls, socket_timeouts = connection
    conn.execute_code("x = 1", 10)
    assert calls == [("execute_code", ("x = 1", 10))]
    assert socket_timeouts == [conn._timeout]
