"""submit_feedback appends one JSON line per call and never needs FreeCAD."""

import asyncio
import json
from pathlib import Path

import pytest

from freecad_mcp import feedback, server
from freecad_mcp.server import mcp
from freecad_mcp.version import PROTOCOL_VERSION


def _call(arguments: dict) -> tuple[str, bool]:
    result = asyncio.run(mcp.call_tool("submit_feedback", arguments))
    # call_tool returns content (and, on some SDKs, structured output too)
    content = result[0] if isinstance(result, tuple) else result
    if hasattr(content, "content"):
        # mcp 2.x renamed the field to is_error; both serialize as isError.
        return content.content[0].text, bool(content.model_dump(by_alias=True)["isError"])
    return content[0].text, False


@pytest.fixture
def feedback_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "nested" / "feedback.jsonl"
    monkeypatch.setattr(server.state, "feedback_path", path)

    def no_freecad():
        raise AssertionError("submit_feedback must not contact FreeCAD")

    monkeypatch.setattr(server, "get_freecad_connection", no_freecad)
    return path


def test_appends_one_line_per_call(feedback_file: Path) -> None:
    text, is_error = _call({
        "kind": "bug",
        "summary": "  execute_code timed out with a modal open  ",
        "details": "Called execute_code while a QMessageBox was up.",
        "tool_name": "execute_code",
        "severity": "high",
    })
    assert not is_error
    _call({"kind": "missing_feature", "summary": "No tool to close task dialogs"})

    lines = feedback_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = (json.loads(line) for line in lines)
    assert first["id"] in text
    assert first["summary"] == "execute_code timed out with a modal open"
    assert first["tool"] == "execute_code"
    assert first["severity"] == "high"
    assert first["protocol_version"] == PROTOCOL_VERSION
    assert second["kind"] == "missing_feature"
    assert second["severity"] == "medium"
    assert "details" not in second and "tool" not in second and "workaround" not in second


def test_blank_summary_is_an_error(feedback_file: Path) -> None:
    text, is_error = _call({"kind": "other", "summary": "   "})
    assert is_error
    assert "summary" in text
    assert not feedback_file.exists()


def test_unknown_kind_is_rejected(feedback_file: Path) -> None:
    with pytest.raises(Exception):
        asyncio.run(mcp.call_tool("submit_feedback", {"kind": "rant", "summary": "x"}))
    assert not feedback_file.exists()


def test_long_fields_are_clipped() -> None:
    entry = feedback.build_entry("other", "s" * 1000, details="d" * 50_000)
    assert len(entry["summary"]) == feedback.MAX_SUMMARY_CHARS
    assert len(entry["details"]) == feedback.MAX_FIELD_CHARS


def test_unwritable_path_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    monkeypatch.setattr(server.state, "feedback_path", blocker / "feedback.jsonl")
    text, is_error = _call({"kind": "bug", "summary": "x"})
    assert is_error
    assert "Could not save feedback" in text


def test_default_path_honours_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(feedback.FEEDBACK_FILE_ENV, str(tmp_path / "fb.jsonl"))
    assert feedback.default_feedback_path() == tmp_path / "fb.jsonl"
    monkeypatch.delenv(feedback.FEEDBACK_FILE_ENV)
    assert feedback.default_feedback_path() == Path.home() / ".freecad-mcp" / "feedback.jsonl"
