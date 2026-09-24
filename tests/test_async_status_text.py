import json

from freecad_mcp.operations.core import (
    execute_code_async_operation,
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
        },
    })
    [text] = get_async_status_operation(conn, "job-7")
    assert text.text == (
        "Async job job-7: failed\nError: ValueError: boom\nTraceback ...\nValueError: boom"
    )


def test_async_status_lists_all_jobs_without_id() -> None:
    conn = FakeConnection(get_async_status={"success": True, "jobs": [{"id": "job-1", "state": "done"}]})
    [text] = get_async_status_operation(conn)
    assert json.loads(text.text) == [{"id": "job-1", "state": "done"}]


def test_older_addon_keeps_document_polling_instructions() -> None:
    conn = FakeConnection(execute_code_async={"success": True})
    [text] = execute_code_async_operation(conn, "pass")
    assert "get_object" in text.text
    assert "Report View" in text.text
    assert 'get_async_status(job_id="")' not in text.text
