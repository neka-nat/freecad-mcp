"""A lost XML-RPC response must not replay document mutations (#183)."""

import asyncio
import errno
import http.client
import json
import socket
import sys
import threading
import xmlrpc.client
from typing import Any, Iterator
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from freecad_mcp.freecad_client import FreeCADConnection, _TimeoutTransport


@pytest.fixture
def lost_response_server() -> Iterator[tuple[FreeCADConnection, list[str], int]]:
    created: list[str] = []
    dropped = False

    class Handler(SimpleXMLRPCRequestHandler):
        def do_POST(self) -> None:
            nonlocal dropped
            request = self.rfile.read(int(self.headers["Content-Length"]))
            _, method = xmlrpc.client.loads(request)
            response = self.server._marshaled_dispatch(request)
            if method == "create_object" and not dropped:
                dropped = True
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                return  # side effect committed; response never reaches the client
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *_args: Any) -> None:
            pass

    class Interface:
        def create_object(self, _doc: str, data: dict[str, Any]) -> dict[str, Any]:
            name = f"{data['Name']}{len(created) + 1}"
            created.append(name)
            return {"success": True, "object_name": name}

        def get_objects(self, _doc: str) -> list[dict[str, str]]:
            return [{"Name": name} for name in created]

    with SimpleXMLRPCServer(
        ("127.0.0.1", 0), requestHandler=Handler, allow_none=True, logRequests=False,
    ) as rpc:
        rpc.register_instance(Interface())
        port = rpc.server_address[1]
        thread = threading.Thread(target=rpc.serve_forever, daemon=True)
        thread.start()
        try:
            yield FreeCADConnection("127.0.0.1", port, timeout=2), created, port
        finally:
            rpc.shutdown()
            thread.join(timeout=5)


def test_lost_response_does_not_replay_a_mutation(lost_response_server) -> None:
    connection, created, _ = lost_response_server
    with pytest.raises(ConnectionError, match="may already have executed"):
        connection.create_object("Doc", {"Name": "Box"})
    assert created == ["Box1"]
    assert connection.get_objects("Doc") == [{"Name": "Box1"}]


@pytest.mark.parametrize("error", [
    http.client.RemoteDisconnected("lost response"),
    ConnectionResetError(errno.ECONNRESET, "connection reset"),
    ConnectionAbortedError(errno.ECONNABORTED, "connection aborted"),
    BrokenPipeError(errno.EPIPE, "broken pipe"),
])
def test_transport_connection_failures_attempt_only_once(error, monkeypatch) -> None:
    transport = _TimeoutTransport(timeout=2)
    calls = []

    def fail(*args):
        calls.append(args)
        raise error

    monkeypatch.setattr(transport, "single_request", fail)
    with pytest.raises(ConnectionError, match="may already have executed"):
        transport.request("localhost", "/RPC2", b"request")
    assert len(calls) == 1


def test_stdio_lost_response_is_an_error_without_replay(lost_response_server) -> None:
    _, created, port = lost_response_server
    # Keep the same source checkout and SDK, including uv --with overlays.
    bootstrap = (
        f"import sys; sys.path[:] = {sys.path!r}; "
        "from freecad_mcp import server; "
        "from freecad_mcp.freecad_client import FreeCADConnection; "
        f"server.state.freecad_connection = FreeCADConnection('127.0.0.1', {port}, timeout=2); "
        "server.state.only_text_feedback = True; server.mcp.run()"
    )
    params = StdioServerParameters(command=sys.executable, args=["-c", bootstrap])

    async def exercise() -> None:
        with anyio.fail_after(30):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("create_object", {
                        "doc_name": "Doc", "obj_type": "Part::Box", "obj_name": "Box",
                        "include_screenshot": False,
                    })
                    assert result.model_dump(by_alias=True)["isError"] is True
                    assert "may already have executed" in result.content[0].text
                    assert "Inspect" in result.content[0].text
                    inspected = await session.call_tool("get_objects", {
                        "doc_name": "Doc", "include_screenshot": False,
                    })
                    assert not inspected.model_dump(by_alias=True)["isError"]
                    assert json.loads(inspected.content[0].text) == [{"Name": "Box1"}]
    asyncio.run(exercise())
    assert created == ["Box1"]
