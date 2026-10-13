"""Failed tool calls reach MCP clients with isError set."""

import json
from typing import Any

import pytest
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
