"""Failed tool calls reach MCP clients with isError set."""

import asyncio
import json
from pathlib import Path
import sys
from typing import Any

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from freecad_mcp import server
from freecad_mcp.operations import (
    create_object_operation,
    execute_code_headless_operation,
    execute_code_operation,
    run_fem_analysis_operation,
)
from freecad_mcp.responses import ErrorResponse
from freecad_mcp.server_state import ServerState


class _Connection:
    def __init__(self, notice: str = "") -> None:
        self.notice = notice

    def ping(self) -> bool:
        return True

    def check_addon_version(self) -> str:
        return self.notice

    def create_object(self, _doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        if obj_data["Properties"].get("Length") == "abc":
            return {"success": False, "error": "Failed to set property: Length: syntax error"}
        return {"success": True, "object_name": obj_data["Name"]}

    def execute_code(self, code: str, _timeout: float | None = None) -> dict[str, Any]:
        if "raise" in code:
            return {"success": False, "error": "ValueError: boom"}
        return {"success": True, "message": "ok"}

    def run_fem_analysis(self, *_args: Any) -> dict[str, Any]:
        return {"success": False, "error": "no solver"}

    def list_documents(self) -> list[str]:
        raise ConnectionError("RPC unavailable")

    def get_active_screenshot(self, *_args: Any) -> str:
        return "cG5n"

    def disconnect(self) -> None:
        pass


@pytest.fixture
def connected(monkeypatch: pytest.MonkeyPatch):
    def connect(notice: str = "") -> None:
        monkeypatch.setattr(server, "state", ServerState())
        monkeypatch.setattr(server, "FreeCADConnection", lambda **_kwargs: _Connection(notice))

    return connect


def _error(content: Any) -> bool:
    # mcp 2.x renamed the field to is_error; both serialize as isError.
    return isinstance(content, CallToolResult) and content.model_dump(by_alias=True)["isError"]


def test_failed_tool_call_is_flagged(connected) -> None:
    connected()

    result = server.execute_code(None, "raise ValueError('boom')", include_screenshot=False)

    assert _error(result)
    assert result.content[0].text == "Failed to execute code: ValueError: boom"


def test_successful_tool_call_is_not_flagged(connected) -> None:
    connected()

    result = server.create_object(
        None, "Doc", "Part::Box", "Box", obj_properties={"Length": 5}, include_screenshot=False
    )

    assert not _error(result)
    assert result[0].text == "Object 'Box' created successfully"


def test_version_warning_is_kept_on_a_failed_call(connected) -> None:
    connected(notice="addon is old")

    result = server.create_object(
        None, "Doc", "Part::Box", "Bad", obj_properties={"Length": "abc"}, include_screenshot=False
    )

    assert _error(result)
    assert [c.text for c in result.content] == [
        "Warning: addon is old",
        "Failed to create object: Failed to set property: Length: syntax error",
    ]


def test_operations_mark_failures() -> None:
    conn = _Connection()

    assert isinstance(execute_code_operation(conn, True, "raise X"), ErrorResponse)
    assert not isinstance(execute_code_operation(conn, True, "pass"), ErrorResponse)
    assert isinstance(
        create_object_operation(conn, True, "Doc", "Part::Box", "B", None, {"Length": "abc"}),
        ErrorResponse,
    )

    fem = run_fem_analysis_operation(conn, True, "Doc", "Analysis")
    assert isinstance(fem, ErrorResponse)
    assert json.loads(fem[0].text)["summary"] == "FEM analysis 'Analysis' failed: no solver"


def test_failed_headless_run_is_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    import freecad_mcp.headless as headless

    monkeypatch.setattr(
        headless, "run_headless", lambda *_args: {"success": False, "error": "exit 1"}
    )
    assert isinstance(execute_code_headless_operation(None, "", 10), ErrorResponse)

    monkeypatch.setattr(headless, "run_headless", lambda *_args: {"success": True})
    assert not isinstance(execute_code_headless_operation(None, "", 10), ErrorResponse)


def test_stdio_client_receives_error_flags_and_original_content() -> None:
    """Exercise SDK serialization, including MCP 1.x and 2.x normalization."""
    async def exercise() -> None:
        params = StdioServerParameters(command=sys.executable, args=[str(Path(__file__))])
        with anyio.fail_after(30):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    failed = await session.call_tool(
                        "execute_code", {"code": "raise ValueError('boom')", "include_screenshot": False}
                    )
                    assert _error(failed)
                    assert [c.text for c in failed.content] == [
                        "Warning: addon is old",
                        "Failed to execute code: ValueError: boom",
                    ]
                    invalid = await session.call_tool("create_object", {
                        "doc_name": "Doc", "obj_type": "Part::Box", "obj_name": "Bad",
                        "obj_properties": {"Length": "abc"}, "include_screenshot": False,
                    })
                    assert _error(invalid)
                    assert len(invalid.content) == 1  # The version notice is sent once.
                    assert "Failed to set property: Length" in invalid.content[0].text
                    fem = await session.call_tool(
                        "run_fem_analysis", {"doc_name": "Doc", "analysis_name": "Analysis"}
                    )
                    assert _error(fem)
                    assert json.loads(fem.content[0].text)["error"] == "no solver"
                    transport = await session.call_tool("list_documents", {})
                    assert _error(transport)
                    # SDK 2.x hides details of unexpected exceptions.
                    assert "list_documents" in transport.content[0].text
                    success = await session.call_tool("create_object", {
                        "doc_name": "Doc", "obj_type": "Part::Box", "obj_name": "Box",
                        "obj_properties": {"Length": 5},
                    })
                    assert not _error(success)
                    assert success.content[0].text == "Object 'Box' created successfully"
                    assert success.content[1].type == "image"
                    assert success.content[1].data == "cG5n"

    asyncio.run(exercise())


if __name__ == "__main__":
    # Only FreeCAD is stubbed; the real MCP server and client use stdio.
    server.state.freecad_connection = _Connection()
    server.state.version_notice = "addon is old"
    server.mcp.run()
