"""Tests for the MCP-side operation layer (``freecad_mcp.operations.core``).

These cover the parts that run in the MCP server process: error handling,
the success/failure/exception branches, and the screenshot-gating policy.
They mock ``FreeCADConnection`` so no FreeCAD or RPC server is required.
"""

import json
from unittest.mock import MagicMock

from mcp.types import ImageContent, TextContent

from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations import core


def make_conn(**overrides) -> MagicMock:
    """A FreeCADConnection mock that returns a screenshot by default."""
    conn = MagicMock(spec=FreeCADConnection)
    conn.get_active_screenshot.return_value = "BASE64PNG"
    for name, value in overrides.items():
        getattr(conn, name).return_value = value
    return conn


def texts(response) -> str:
    return "\n".join(c.text for c in response if isinstance(c, TextContent))


def images(response) -> list[ImageContent]:
    return [c for c in response if isinstance(c, ImageContent)]


# --- create_document -------------------------------------------------------


def test_create_document_success():
    conn = make_conn(create_document={"success": True, "document_name": "Doc"})
    res = core.create_document_operation(conn, "Doc")
    assert len(res) == 1
    assert "created successfully" in texts(res)
    assert "Doc" in texts(res)


def test_create_document_failure_surfaces_error():
    conn = make_conn(create_document={"success": False, "error": "name taken"})
    res = core.create_document_operation(conn, "Doc")
    assert "Failed to create document" in texts(res)
    assert "name taken" in texts(res)


def test_create_document_exception_is_caught():
    conn = make_conn()
    conn.create_document.side_effect = RuntimeError("rpc down")
    res = core.create_document_operation(conn, "Doc")
    assert "Failed to create document" in texts(res)
    assert "rpc down" in texts(res)


# --- create_object: screenshot gating --------------------------------------


def test_create_object_success_attaches_screenshot():
    conn = make_conn(create_object={"success": True, "object_name": "Box"})
    res = core.create_object_operation(
        conn, only_text_feedback=False, doc_name="Doc", obj_type="Part::Box", obj_name="Box"
    )
    assert "created successfully" in texts(res)
    assert [img.data for img in images(res)] == ["BASE64PNG"]


def test_create_object_only_text_feedback_skips_screenshot():
    conn = make_conn(create_object={"success": True, "object_name": "Box"})
    res = core.create_object_operation(
        conn, only_text_feedback=True, doc_name="Doc", obj_type="Part::Box", obj_name="Box"
    )
    assert images(res) == []
    conn.get_active_screenshot.assert_not_called()


def test_create_object_failure_skips_screenshot():
    conn = make_conn(create_object={"success": False, "error": "bad type"})
    res = core.create_object_operation(
        conn, only_text_feedback=False, doc_name="Doc", obj_type="Nope", obj_name="X"
    )
    assert "Failed to create object" in texts(res)
    assert images(res) == []
    conn.get_active_screenshot.assert_not_called()


def test_create_object_forwards_properties_and_analysis():
    conn = make_conn(create_object={"success": True, "object_name": "Box"})
    core.create_object_operation(
        conn,
        only_text_feedback=True,
        doc_name="Doc",
        obj_type="Part::Box",
        obj_name="Box",
        analysis_name="Analysis",
        obj_properties={"Height": 10},
    )
    _, obj_data = conn.create_object.call_args.args
    assert obj_data == {
        "Name": "Box",
        "Type": "Part::Box",
        "Properties": {"Height": 10},
        "Analysis": "Analysis",
    }


# --- edit / delete ---------------------------------------------------------


def test_edit_object_success():
    conn = make_conn(edit_object={"success": True, "object_name": "Box"})
    res = core.edit_object_operation(
        conn, only_text_feedback=True, doc_name="Doc", obj_name="Box", obj_properties={"Height": 5}
    )
    assert "edited successfully" in texts(res)
    conn.edit_object.assert_called_once_with("Doc", "Box", {"Properties": {"Height": 5}})


def test_delete_object_failure():
    conn = make_conn(delete_object={"success": False, "error": "not found"})
    res = core.delete_object_operation(
        conn, only_text_feedback=False, doc_name="Doc", obj_name="Ghost"
    )
    assert "Failed to delete object" in texts(res)
    assert "not found" in texts(res)


# --- execute_code / execute_code_async -------------------------------------


def test_execute_code_success_includes_message_and_screenshot():
    conn = make_conn(execute_code={"success": True, "message": "ran"})
    res = core.execute_code_operation(conn, only_text_feedback=False, code="print(1)")
    assert "ran" in texts(res)
    assert len(images(res)) == 1


def test_execute_code_failure():
    conn = make_conn(execute_code={"success": False, "error": "SyntaxError"})
    res = core.execute_code_operation(conn, only_text_feedback=False, code="???")
    assert "Failed to execute code" in texts(res)
    conn.get_active_screenshot.assert_not_called()


def test_execute_code_async_success_message():
    conn = make_conn(execute_code_async={"success": True})
    res = core.execute_code_async_operation(conn, code="heavy()")
    body = texts(res)
    assert "background" in body
    # No longer recommends the removed SessionState.Label polling pattern.
    assert "SessionState.Label" not in body


def test_execute_code_async_failure_uses_default_when_no_error_key():
    conn = make_conn(execute_code_async={"success": False})
    res = core.execute_code_async_operation(conn, code="heavy()")
    assert "Failed to start async execution" in texts(res)
    assert "unknown" in texts(res)


# --- get_view --------------------------------------------------------------


def test_get_view_returns_image_when_screenshot_available():
    conn = make_conn()
    res = core.get_view_operation(conn, view_name="Isometric")
    assert images(res) == res
    assert res[0].data == "BASE64PNG"


def test_get_view_returns_text_when_unsupported_view():
    conn = make_conn()
    conn.get_active_screenshot.return_value = None
    res = core.get_view_operation(conn, view_name="Front")
    assert images(res) == []
    assert "Cannot get screenshot" in texts(res)


# --- parts list / documents ------------------------------------------------


def test_get_parts_list_empty_returns_hint():
    conn = make_conn(get_parts_list=[])
    res = core.get_parts_list_operation(conn)
    assert "No parts found" in texts(res)


def test_get_parts_list_non_empty_returns_json():
    conn = make_conn(get_parts_list=["a/b.fcstd"])
    res = core.get_parts_list_operation(conn)
    assert json.loads(texts(res)) == ["a/b.fcstd"]


def test_list_documents_returns_json():
    conn = make_conn(list_documents=["Doc1", "Doc2"])
    res = core.list_documents_operation(conn)
    assert json.loads(texts(res)) == ["Doc1", "Doc2"]


# --- run_fem_analysis ------------------------------------------------------


def test_run_fem_analysis_success_summarizes_results():
    conn = make_conn(
        run_fem_analysis={
            "success": True,
            "max_von_mises_MPa": 123.456,
            "max_displacement_mm": 0.07891,
            "node_count": 4096,
        }
    )
    res = core.run_fem_analysis_operation(
        conn, only_text_feedback=False, doc_name="Doc", analysis_name="Analysis"
    )
    payload = json.loads(texts(res))
    assert "solved" in payload["summary"]
    assert "123.5 MPa" in payload["summary"]
    assert "4096 nodes" in payload["summary"]
    assert len(images(res)) == 1


def test_run_fem_analysis_handles_missing_metric():
    conn = make_conn(
        run_fem_analysis={"success": True, "max_von_mises_MPa": None, "node_count": 0}
    )
    res = core.run_fem_analysis_operation(
        conn, only_text_feedback=True, doc_name="Doc", analysis_name="Analysis"
    )
    assert "unavailable (MPa)" in json.loads(texts(res))["summary"]


def test_run_fem_analysis_failure():
    conn = make_conn(run_fem_analysis={"success": False, "error": "no mesh"})
    res = core.run_fem_analysis_operation(
        conn, only_text_feedback=True, doc_name="Doc", analysis_name="Analysis"
    )
    payload = json.loads(texts(res))
    assert "failed" in payload["summary"]
    assert payload["error"] == "no mesh"


# --- reload_document -------------------------------------------------------


def test_reload_document_success():
    conn = make_conn(reload_document={"success": True, "document_name": "chassis"})
    res = core.reload_document_operation(conn, "chassis")
    assert "reloaded from disk" in texts(res)


def test_reload_document_failure():
    conn = make_conn(reload_document={"success": False, "error": "not loaded"})
    res = core.reload_document_operation(conn, "chassis")
    assert "Failed to reload document" in texts(res)
    assert "not loaded" in texts(res)
