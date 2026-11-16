"""Real HTTP/SSE sessions exercise authentication and MCP tool calls on both SDKs."""
import asyncio
from contextlib import contextmanager
import os
import socket
import subprocess
import sys
import time

import anyio
import pytest
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client


@contextmanager
def running_http(transport: str):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    bootstrap = (
        f"import sys; sys.path[:] = {sys.path!r}; "
        "from freecad_mcp import server; "
        "from freecad_mcp.http_transport import run_http; "
        "from freecad_mcp.version import PROTOCOL_VERSION; "
        "from types import SimpleNamespace; "
        "server.get_freecad_connection=lambda:SimpleNamespace(get_rpc_status=lambda:"
        "{'protocol_version':PROTOCOL_VERSION},list_documents=lambda:[]); "
        f"run_http(server.mcp, {transport!r}, '127.0.0.1', {port}, 'session-test-token')"
    )
    with subprocess.Popen([sys.executable, "-c", bootstrap], env=dict(os.environ),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as proc:
        try:
            deadline = time.monotonic()+10
            while True:
                assert proc.poll() is None, "HTTP server exited during startup"
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.1):
                        break
                except OSError:
                    assert time.monotonic() < deadline, "HTTP server did not start"
                    time.sleep(.03)
            yield f"http://127.0.0.1:{port}"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


@pytest.mark.parametrize("transport", ["streamable-http", "sse"])
def test_authenticated_session_can_call_tools(transport: str) -> None:
    with running_http(transport) as url:
        async def exercise() -> None:
            with anyio.fail_after(15):
                async with create_mcp_http_client() as client:
                    path = "/sse" if transport == "sse" else "/mcp"
                    response = await client.get(url+path)
                    assert response.status_code == 401
                    response = await client.get(url+path, headers={"Authorization":"Bearer wrong"})
                    assert response.status_code == 401
                headers = {"Authorization":"Bearer session-test-token"}
                async with create_mcp_http_client(headers=headers) as client:
                    channel = (sse_client(url+"/sse", headers=headers) if transport == "sse"
                               else streamable_http_client(url+"/mcp", http_client=client))
                    async with channel as streams:
                        async with ClientSession(streams[0], streams[1]) as session:
                            await session.initialize()
                            listed = await session.list_tools()
                            assert any(t.name == "get_rpc_status" for t in listed.tools)
                            result = await session.call_tool("get_rpc_status", {})
                            assert not result.model_dump(by_alias=True)["isError"]
                            assert '"version_check": "ok"' in result.content[0].text
        asyncio.run(exercise())
