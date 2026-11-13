"""HTTP/SSE transport and its exposure guards."""

import pytest
from starlette.testclient import TestClient

from freecad_mcp import server
from freecad_mcp.http_transport import (
    UnsafeListenConfigError,
    build_allowed_hosts,
    build_app,
    is_loopback,
    validate_listen_config,
)

TOKEN = "s3cret-token"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "t", "version": "0"},
    },
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.mark.parametrize("host", ["127.0.0.1", "127.5.5.5", "::1", "localhost", "LOCALHOST"])
def test_loopback_hosts(host: str) -> None:
    assert is_loopback(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "example.com"])
def test_non_loopback_hosts(host: str) -> None:
    assert not is_loopback(host)


def test_non_loopback_requires_token() -> None:
    with pytest.raises(UnsafeListenConfigError):
        validate_listen_config("0.0.0.0", None)
    validate_listen_config("0.0.0.0", TOKEN)
    validate_listen_config("127.0.0.1", None)


def test_insecure_remote_override() -> None:
    validate_listen_config("0.0.0.0", None, allow_insecure_remote=True)


def test_allowed_hosts() -> None:
    hosts = build_allowed_hosts("0.0.0.0", 8000, ["mybox", "other:9000", "[::1]:1"])
    assert "localhost:8000" in hosts and "127.0.0.1:8000" in hosts
    assert "0.0.0.0:8000" not in hosts
    assert "mybox:8000" in hosts and "other:9000" in hosts and "[::1]:1" in hosts


@pytest.fixture(params=["streamable-http", "sse"])
def fresh_mcp(request: pytest.FixtureRequest):
    # build_app mutates settings; use a throwaway server instead of the global.
    FastMCP = server.FastMCP

    return FastMCP("t"), request.param


def test_build_app_refuses_unsafe(fresh_mcp) -> None:
    mcp, transport = fresh_mcp
    with pytest.raises(UnsafeListenConfigError):
        build_app(mcp, transport, "0.0.0.0", 8000, None)


def test_token_enforced() -> None:
    FastMCP = server.FastMCP

    app = build_app(FastMCP("t"), "streamable-http", "127.0.0.1", 8000, TOKEN)
    with TestClient(app, base_url="http://localhost:8000") as c:
        assert c.post("/mcp", json=INIT, headers=HEADERS).status_code == 401
        bad = {**HEADERS, "Authorization": "Bearer nope"}
        assert c.post("/mcp", json=INIT, headers=bad).status_code == 401
        basic = {**HEADERS, "Authorization": f"Basic {TOKEN}"}
        assert c.post("/mcp", json=INIT, headers=basic).status_code == 401
        good = {**HEADERS, "Authorization": f"Bearer {TOKEN}"}
        assert c.post("/mcp", json=INIT, headers=good).status_code == 200


def test_dns_rebinding_rejected_even_with_valid_token() -> None:
    FastMCP = server.FastMCP

    app = build_app(FastMCP("t"), "streamable-http", "127.0.0.1", 8000, TOKEN)
    with TestClient(app, base_url="http://evil.example:8000") as c:
        good = {**HEADERS, "Authorization": f"Bearer {TOKEN}"}
        assert c.post("/mcp", json=INIT, headers=good).status_code == 421


def test_no_token_on_loopback_still_checks_host() -> None:
    FastMCP = server.FastMCP

    app = build_app(FastMCP("t"), "streamable-http", "127.0.0.1", 8000, None)
    # One client: sse_starlette's exit event is global and binds to one loop.
    with TestClient(app, base_url="http://localhost:8000") as c:
        evil = {**HEADERS, "Host": "evil.example:8000"}
        assert c.post("/mcp", json=INIT, headers=evil).status_code == 421
        assert c.post("/mcp", json=INIT, headers=HEADERS).status_code == 200


@pytest.mark.parametrize(
    "argv",
    [
        ["--transport", "streamable-http", "--listen-host", "0.0.0.0"],
        ["--listen-port", "9000"],
        ["--listen-token", "x"],
    ],
)
def test_cli_rejects_unsafe_or_misplaced_flags(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FREECAD_MCP_LISTEN_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv", ["freecad-mcp", *argv])
    monkeypatch.setattr(server, "run_http", lambda *a, **k: pytest.fail("must not start"))
    monkeypatch.setattr(server.mcp, "run", lambda *a, **k: pytest.fail("must not start"))
    with pytest.raises(SystemExit) as exc:
        server.main()
    assert exc.value.code == 2


def test_cli_env_token_allows_non_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FREECAD_MCP_LISTEN_TOKEN", TOKEN)
    monkeypatch.setattr(
        "sys.argv", ["freecad-mcp", "--transport", "sse", "--listen-host", "0.0.0.0"]
    )
    calls: list[tuple] = []
    monkeypatch.setattr(server, "run_http", lambda *a: calls.append(a))
    server.main()
    assert calls[0][1:5] == ("sse", "0.0.0.0", 8000, TOKEN)


def test_cli_insecure_remote_flag_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FREECAD_MCP_LISTEN_TOKEN", raising=False)
    calls: list[tuple] = []
    monkeypatch.setattr(server, "run_http", lambda *a: calls.append(a))
    argv = ["freecad-mcp", "--transport", "streamable-http", "--listen-host", "0.0.0.0"]
    monkeypatch.setattr("sys.argv", [*argv, "--allow-insecure-remote"])
    server.main()
    assert calls[-1][3:6] == (8000, None, []) and calls[-1][6] is True
    monkeypatch.setenv("FREECAD_MCP_ALLOW_INSECURE_REMOTE", "1")
    monkeypatch.setattr("sys.argv", argv)
    server.main()
    assert len(calls) == 2


def test_cli_insecure_remote_flag_rejected_for_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FREECAD_MCP_ALLOW_INSECURE_REMOTE", raising=False)
    monkeypatch.setattr("sys.argv", ["freecad-mcp", "--allow-insecure-remote"])
    with pytest.raises(SystemExit):
        server.main()
