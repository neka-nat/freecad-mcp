"""Web pages must not be able to call the RPC server; MCP clients must still work."""

from email.message import Message
import http.client
import sys
import types
import xmlrpc.client

import pytest

from test_rpc_concurrency import build_server, client, filtered_server_class, running_server


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute_code(self, code: str) -> dict:
        self.calls.append(code)
        return {"success": True}


def ip_filter() -> types.ModuleType:
    return sys.modules[filtered_server_class().__module__]


def headers(**values: str) -> Message:
    message = Message()
    for name, value in values.items():
        message[name.replace("_", "-")] = value
    return message


def post(port: int, request_headers: dict[str, str]) -> int:
    body = xmlrpc.client.dumps(("print('from a web page')",), "execute_code").encode()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("POST", "/RPC2", body=body, headers=request_headers)
        return connection.getresponse().status
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("request_headers", "status"),
    [
        # fetch(url, {method: "POST", mode: "no-cors", body: xml}) from any site
        ({"Content-Type": "text/plain;charset=UTF-8", "Origin": "https://attacker.example"}, 403),
        # the same without Origin, in case a browser omits it
        ({"Content-Type": "text/plain;charset=UTF-8"}, 415),
        # HTML form posts
        ({"Content-Type": "application/x-www-form-urlencoded"}, 415),
        ({"Content-Type": "multipart/form-data; boundary=x"}, 415),
        # a Blob body without a type sends no Content-Type at all
        ({}, 415),
        # DNS rebinding makes the page same-origin, so it may send text/xml
        ({"Content-Type": "text/xml", "Origin": "http://rebind.attacker.example:9875"}, 403),
        ({"Content-Type": "text/xml", "Host": "rebind.attacker.example:9875"}, 403),
    ],
)
def test_browser_style_requests_never_reach_the_handler(
    request_headers: dict[str, str], status: int
) -> None:
    interface = Recorder()
    with running_server(interface) as (_host, port):
        assert post(port, request_headers) == status
    assert interface.calls == []


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_xmlrpc_client_is_accepted(host: str) -> None:
    interface = Recorder()
    with running_server(interface) as (_bound, port):
        assert client(host, port, 5).execute_code("x = 1") == {"success": True}
    assert interface.calls == ["x = 1"]


def test_loopback_binding_is_detected() -> None:
    local = build_server(Recorder())
    try:
        assert local.loopback_only is True
    finally:
        local.server_close()
    remote = filtered_server_class()(("0.0.0.0", 0), bind_and_activate=False)
    try:
        assert remote.loopback_only is False
    finally:
        remote.server_close()


@pytest.mark.parametrize(
    "value",
    [
        headers(Content_Type="text/xml"),
        headers(Content_Type="text/xml; charset=utf-8", Host="localhost:9875"),
        headers(Content_Type="Application/XML", Host="127.0.0.1:9875"),
        headers(Content_Type="text/xml", Host="[::1]:9875"),
        headers(Content_Type="text/xml", Host="localhost."),
    ],
)
def test_local_mode_accepts_xmlrpc_requests_addressed_to_localhost(value: Message) -> None:
    assert ip_filter().browser_request_rejection(value, loopback_only=True) is None


def test_remote_mode_accepts_any_host_but_still_refuses_browsers() -> None:
    reject = ip_filter().browser_request_rejection
    assert reject(headers(Content_Type="text/xml", Host="192.168.1.10:9875"), False) is None
    assert reject(headers(Content_Type="text/xml", Host="freecad.lan:9875"), False) is None
    assert reject(
        headers(Content_Type="text/xml", Host="freecad.lan", Origin="null"), False
    ) == (403, "requests from web pages are not accepted")
    assert reject(headers(Content_Type="text/plain", Host="freecad.lan"), False)[0] == 415
