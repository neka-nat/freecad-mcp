from freecad_mcp.operations.core import (
    execute_code_operation,
    format_execute_code_failure,
)


class _FakeConnection:
    def __init__(self, result: dict) -> None:
        self._result = result

    def execute_code(self, _code: str) -> dict:
        return self._result

    def get_active_screenshot(self, _view: str):  # pragma: no cover - not reached
        raise AssertionError("screenshot must not be requested after a failure")


def test_failure_text_includes_script_line_and_partial_output() -> None:
    text = format_execute_code_failure(
        {
            "success": False,
            "error": "ValueError: Null shape",
            "traceback": "Script line 19: l=l0.fuse(box(...))",
            "output": "state faces=1676 vol=34758.1\n",
        }
    )
    assert text == (
        "Failed to execute code: ValueError: Null shape\n"
        "Script line 19: l=l0.fuse(box(...))\n"
        "Output before error:\nstate faces=1676 vol=34758.1"
    )


def test_failure_text_without_context_stays_compact() -> None:
    assert format_execute_code_failure({"success": False, "error": "boom"}) == (
        "Failed to execute code: boom"
    )


def test_operation_forwards_failure_context_and_skips_screenshot() -> None:
    response = execute_code_operation(
        _FakeConnection(
            {"success": False, "error": "KeyError: 'x'", "traceback": "Script line 2: d['x']", "output": ""}
        ),
        only_text_feedback=False,
        code="d = {}\nd['x']",
    )
    assert len(response) == 1
    assert "Script line 2: d['x']" in response[0].text
    assert "Output before error" not in response[0].text
