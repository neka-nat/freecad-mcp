import json

from freecad_mcp.operations.core import (
    execute_code_async_operation,
    execute_code_operation,
    format_shape_check,
    get_async_status_operation,
)


class FakeConnection:
    def __init__(self, **responses):
        self.responses = responses

    def execute_code(self, code):
        return self.responses["execute_code"]

    def execute_code_async(self, code):
        return self.responses["execute_code_async"]

    def get_async_status(self, job_id=""):
        return self.responses["get_async_status"]


def test_format_shape_check_lists_warnings_first_class() -> None:
    assert format_shape_check(None) == ""
    assert format_shape_check({"changed": [], "warnings": []}) == "\nShape check: no shapes changed."
    ok = {"changed": [{"object": "Doc.Lid", "valid": True}], "warnings": []}
    assert format_shape_check(ok) == "\nShape check: 1 shape(s) changed (Doc.Lid); all valid."
    bad = {
        "changed": [{"object": "Doc.Lid", "valid": False}],
        "warnings": ["Doc.Lid: shape is INVALID", "Doc.Gone: object removed"],
    }
    assert format_shape_check(bad) == (
        "\nShape check: 1 shape(s) changed (Doc.Lid)"
        "\nWARNING: Doc.Lid: shape is INVALID"
        "\nWARNING: Doc.Gone: object removed"
    )


def test_execute_code_text_carries_shape_warning() -> None:
    conn = FakeConnection(execute_code={
        "success": True,
        "message": "Python code executed successfully.\nOutput: done\n",
        "shape_check": {"changed": [{"object": "Doc.Lid"}], "warnings": ["Doc.Lid: 2 solids (was 1)"]},
    })
    [text] = execute_code_operation(conn, True, "x = 1", include_screenshot=False)
    assert text.text.endswith("Shape check: 1 shape(s) changed (Doc.Lid)\nWARNING: Doc.Lid: 2 solids (was 1)")


def test_async_start_text_names_the_job_and_how_to_poll_it() -> None:
    conn = FakeConnection(execute_code_async={"success": True, "job_id": "job-7", "message": "..."})
    [text] = execute_code_async_operation(conn, "x = 1")
    assert "job_id: job-7" in text.text
    assert 'get_async_status(job_id="job-7")' in text.text


def test_async_status_text_for_failed_job() -> None:
    conn = FakeConnection(get_async_status={
        "success": True,
        "job": {
            "id": "job-7", "state": "failed", "error": "ValueError: boom",
            "traceback": "Traceback ...\nValueError: boom",
            "shape_check": {"changed": [], "warnings": []},
        },
    })
    [text] = get_async_status_operation(conn, "job-7")
    assert text.text == (
        "Async job job-7: failed\nError: ValueError: boom\nTraceback ...\nValueError: boom"
        "\nShape check: no shapes changed."
    )


def test_async_status_lists_all_jobs_without_id() -> None:
    conn = FakeConnection(get_async_status={"success": True, "jobs": [{"id": "job-1", "state": "done"}]})
    [text] = get_async_status_operation(conn)
    assert json.loads(text.text) == [{"id": "job-1", "state": "done"}]
