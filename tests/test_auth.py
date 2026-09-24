"""Optional shared-secret token authentication for the RPC server (#89)."""

import base64
from collections.abc import Iterator
from contextlib import contextmanager
import http.client
import sys
import threading
import types
import xmlrpc.client

import pytest

from test_rpc_concurrency import filtered_server_class


TOKEN = "s3cret-token"


def ip_filter() -> types.ModuleType:
    return sys.modules[filtered_server_class().__module__]


def authorization_ok(header_value: str, token: str) -> bool:
    return ip_filter().authorization_ok(header_value, token)


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


class TestAuthorizationOk:
    def test_bearer_match(self):
        assert authorization_ok(f"Bearer {TOKEN}", TOKEN) is True

    def test_bearer_mismatch(self):
        assert authorization_ok("Bearer wrong", TOKEN) is False

    def test_bearer_trailing_whitespace_tolerated(self):
        assert authorization_ok(f"Bearer {TOKEN}  ", TOKEN) is True

    def test_basic_password_field_match(self):
        # stdlib xmlrpc clients send http://:token@host as Basic with empty user
        assert authorization_ok(_basic("", TOKEN), TOKEN) is True

    def test_basic_username_ignored(self):
        assert authorization_ok(_basic("anyuser", TOKEN), TOKEN) is True

    def test_basic_wrong_password(self):
        assert authorization_ok(_basic("", "wrong"), TOKEN) is False

    def test_basic_invalid_base64(self):
        assert authorization_ok("Basic !!!not-base64!!!", TOKEN) is False

    def test_empty_header(self):
        assert authorization_ok("", TOKEN) is False

    def test_unknown_scheme(self):
        assert authorization_ok(f"Digest {TOKEN}", TOKEN) is False

    def test_token_with_colon(self):
        token = "with:colon"
        # partition on the first colon keeps the rest as the password
        assert authorization_ok(_basic("", token), token) is True


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def ping(self) -> bool:
        self.calls.append("ping")
        return True


@contextmanager
def token_server(token: str) -> Iterator[tuple[Recorder, int]]:
    interface = Recorder()
    server = filtered_server_class()(
        ("127.0.0.1", 0), auth_token=token, allow_none=True, logRequests=False
    )
    server.register_instance(interface)
    loop = threading.Thread(target=server.serve_forever, daemon=True)
    loop.start()
    try:
        yield interface, server.server_address[1]
    finally:
        server.shutdown()
        loop.join(timeout=5)
        server.server_close()


def post(port: int, headers: dict[str, str]) -> int:
    body = xmlrpc.client.dumps((), "ping").encode()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(
            "POST", "/RPC2", body=body, headers={"Content-Type": "text/xml", **headers}
        )
        return connection.getresponse().status
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Authorization": f"Bearer {TOKEN}"}, 200),
        ({"Authorization": _basic("", TOKEN)}, 200),
    ],
)
def test_server_with_a_token_requires_it(headers: dict[str, str], status: int) -> None:
    with token_server(TOKEN) as (interface, port):
        assert post(port, headers) == status
    assert interface.calls == (["ping"] if status == 200 else [])


def test_empty_token_disables_authentication() -> None:
    with token_server("") as (interface, port):
        assert post(port, {}) == 200
    assert interface.calls == ["ping"]


def test_browser_requests_stay_refused_with_a_token_set() -> None:
    with token_server(TOKEN) as (interface, port):
        status = post(port, {
            "Content-Type": "text/plain",
            "Origin": "https://attacker.example",
            "Authorization": f"Bearer {TOKEN}",
        })
    assert status == 403
    assert interface.calls == []
