import json
import logging
from typing import Any

from mcp.types import ImageContent

from ..freecad_client import FreeCADConnection
from ..responses import (
    ErrorResponse,
    ToolResponse,
    add_screenshot_if_available,
    error_response,
    json_response,
    text_response,
)
from ..version import addon_version_warning, is_missing_method_fault


logger = logging.getLogger("FreeCADMCPserver")


def _decode_json_values(value: Any) -> Any:
    """Undo JSON-encoding that MCP clients apply to nested property values.

    ``obj_properties`` is typed ``dict[str, Any]``, so its schema says nothing
    about the shape of each value, and some clients send a nested value such as
    ``Placement`` as a JSON string instead of an object. The addon only maps
    dicts and lists onto FreeCAD types, so decode any string that holds a JSON
    object or array. Other strings (object names, quantities like "210 GPa")
    are left as they are.
    """
    if isinstance(value, dict):
        return {key: _decode_json_values(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_decode_json_values(val) for val in value]
    if isinstance(value, str) and value.lstrip()[:1] in ("{", "["):
        try:
            decoded = json.loads(value)
        except ValueError:
            return value
        if isinstance(decoded, (dict, list)):
            return _decode_json_values(decoded)
    return value


def create_document_operation(freecad: FreeCADConnection, name: str) -> ToolResponse:
    try:
        res = freecad.create_document(name)
        if res["success"]:
            return text_response(f"Document '{res['document_name']}' created successfully")
        return error_response(f"Failed to create document: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to create document: {str(e)}")
        return error_response(f"Failed to create document: {str(e)}")


def create_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] | None = None,
    include_screenshot: bool = True,
    view_name: str = "Isometric",
) -> ToolResponse:
    try:
        obj_data = {
            "Name": obj_name,
            "Type": obj_type,
            "Properties": _decode_json_values(obj_properties or {}),
            "Analysis": analysis_name,
        }
        res = freecad.create_object(doc_name, obj_data)
        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' created successfully")
        else:
            return error_response(f"Failed to create object: {res['error']}")
        skip_screenshot = only_text_feedback or not include_screenshot
        screenshot = None if skip_screenshot else freecad.get_active_screenshot(view_name)
        return add_screenshot_if_available(response, screenshot, skip_screenshot)
    except Exception as e:
        logger.error(f"Failed to create object: {str(e)}")
        return error_response(f"Failed to create object: {str(e)}")


def edit_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    obj_properties: dict[str, Any],
    include_screenshot: bool = True,
    view_name: str = "Isometric",
) -> ToolResponse:
    try:
        res = freecad.edit_object(
            doc_name, obj_name, {"Properties": _decode_json_values(obj_properties)}
        )
        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' edited successfully")
        else:
            return error_response(f"Failed to edit object: {res['error']}")
        skip_screenshot = only_text_feedback or not include_screenshot
        screenshot = None if skip_screenshot else freecad.get_active_screenshot(view_name)
        return add_screenshot_if_available(response, screenshot, skip_screenshot)
    except Exception as e:
        logger.error(f"Failed to edit object: {str(e)}")
        return error_response(f"Failed to edit object: {str(e)}")


def delete_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    include_screenshot: bool = True,
    view_name: str = "Isometric",
) -> ToolResponse:
    try:
        res = freecad.delete_object(doc_name, obj_name)
        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' deleted successfully")
        else:
            return error_response(f"Failed to delete object: {res['error']}")
        skip_screenshot = only_text_feedback or not include_screenshot
        screenshot = None if skip_screenshot else freecad.get_active_screenshot(view_name)
        return add_screenshot_if_available(response, screenshot, skip_screenshot)
    except Exception as e:
        logger.error(f"Failed to delete object: {str(e)}")
        return error_response(f"Failed to delete object: {str(e)}")


def execute_code_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    include_screenshot: bool = True,
    view_name: str = "Isometric",
    timeout: float | None = None,
) -> ToolResponse:
    try:
        res = freecad.execute_code(code, timeout)
        if res["success"]:
            response = text_response(f"Code executed successfully: {res['message']}")
            # Only attempt screenshot when code completed and screenshots are wanted.
            # Skipping on failure avoids a second hanging call while the worker thread
            # may still be running.
            skip_screenshot = only_text_feedback or not include_screenshot
            screenshot = None if skip_screenshot else freecad.get_active_screenshot(view_name)
            return add_screenshot_if_available(response, screenshot, skip_screenshot)
        return error_response(f"Failed to execute code: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to execute code: {str(e)}")
        return error_response(f"Failed to execute code: {str(e)}")


def execute_code_async_operation(
    freecad: FreeCADConnection,
    code: str,
) -> ToolResponse:
    try:
        res = freecad.execute_code_async(code)
        if res["success"]:
            job_id = res.get("job_id", "")
            if not job_id:
                return text_response(
                    "Code execution started in background.\n"
                    "This addon does not report job IDs; use get_object to poll "
                    "a document status object and inspect FreeCAD's Report View for errors."
                )
            return text_response(
                f"Code execution started in background (job_id: {job_id}).\n"
                f"Poll get_async_status(job_id=\"{job_id}\") for state, error "
                "and traceback. "
                "FreeCAD's Report View shows printed output when done."
            )
        return error_response(f"Failed to start async execution: {res.get('error', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to start async code execution: {str(e)}")
        return error_response(f"Failed to start async code execution: {str(e)}")


def format_headless_result(res: dict) -> str:
    if res.get("success"):
        text = "Headless FreeCAD script finished (exit 0)."
    else:
        text = f"Headless FreeCAD script FAILED: {res.get('error', 'unknown error')}"
    if res.get("output"):
        text += "\nOutput:\n" + str(res["output"]).rstrip()
    if res.get("success"):
        text += "\nIf the script saved a document that is open in the GUI, call reload_document to see the result."
    return text


def execute_code_headless_operation(
    command: list[str] | None, code: str, timeout: float
) -> ToolResponse:
    from ..headless import run_headless

    try:
        res = run_headless(code, timeout, command)
        respond = text_response if res.get("success") else error_response
        return respond(format_headless_result(res))
    except Exception as e:
        logger.error(f"Failed to run headless code: {str(e)}")
        return error_response(f"Failed to run headless code: {str(e)}")


def get_async_status_operation(
    freecad: FreeCADConnection, job_id: str = ""
) -> ToolResponse:
    try:
        res = freecad.get_async_status(job_id)
        if not res.get("success"):
            return error_response(f"Failed to get async status: {res.get('error', 'unknown')}")
        job = res.get("job")
        if job is None:
            return json_response(res.get("jobs", []))
        text = f"Async job {job['id']}: {job.get('state', 'unknown')}"
        if job.get("error"):
            text += f"\nError: {job['error']}"
        if job.get("traceback"):
            text += f"\n{job['traceback']}"
        return text_response(text)
    except Exception as e:
        logger.error(f"Failed to get async status: {str(e)}")
        return error_response(f"Failed to get async status: {str(e)}")


def get_view_operation(
    freecad: FreeCADConnection,
    view_name: str,
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> ToolResponse:
    try:
        screenshot = freecad.get_active_screenshot(view_name, width, height, focus_object)
        if screenshot is not None:
            return [ImageContent(type="image", data=screenshot, mimeType="image/png")]
        return error_response("Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)")
    except Exception as e:
        logger.error(f"Failed to get view: {str(e)}")
        return error_response(f"Failed to get view: {str(e)}")


def insert_part_from_library_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    relative_path: str,
    include_screenshot: bool = True,
    view_name: str = "Isometric",
) -> ToolResponse:
    try:
        res = freecad.insert_part_from_library(relative_path)
        if res["success"]:
            response = text_response(f"Part inserted from library: {res['message']}")
        else:
            return error_response(f"Failed to insert part from library: {res['error']}")
        skip_screenshot = only_text_feedback or not include_screenshot
        screenshot = None if skip_screenshot else freecad.get_active_screenshot(view_name)
        return add_screenshot_if_available(response, screenshot, skip_screenshot)
    except Exception as e:
        logger.error(f"Failed to insert part from library: {str(e)}")
        return error_response(f"Failed to insert part from library: {str(e)}")


def get_objects_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    include_screenshot: bool = True,
    view_name: str = "Isometric",
) -> ToolResponse:
    try:
        response = json_response(freecad.get_objects(doc_name))
        skip_screenshot = only_text_feedback or not include_screenshot
        screenshot = None if skip_screenshot else freecad.get_active_screenshot(view_name)
        return add_screenshot_if_available(response, screenshot, skip_screenshot)
    except Exception as e:
        logger.error(f"Failed to get objects: {str(e)}")
        return error_response(f"Failed to get objects: {str(e)}")


def get_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    include_screenshot: bool = True,
    view_name: str = "Isometric",
) -> ToolResponse:
    try:
        response = json_response(freecad.get_object(doc_name, obj_name))
        skip_screenshot = only_text_feedback or not include_screenshot
        screenshot = None if skip_screenshot else freecad.get_active_screenshot(view_name)
        return add_screenshot_if_available(response, screenshot, skip_screenshot)
    except Exception as e:
        logger.error(f"Failed to get object: {str(e)}")
        return error_response(f"Failed to get object: {str(e)}")


def get_parts_list_operation(freecad: FreeCADConnection) -> ToolResponse:
    try:
        parts = freecad.get_parts_list()
    except Exception as e:
        logger.error(f"Failed to get parts list: {str(e)}")
        return error_response(f"Failed to get parts list: {str(e)}")
    if parts:
        return json_response(parts)
    return text_response("No parts found in the parts library. You must add parts_library addon.")


def list_documents_operation(freecad: FreeCADConnection) -> ToolResponse:
    return json_response(freecad.list_documents())


def get_rpc_status_operation(freecad: FreeCADConnection) -> ToolResponse:
    """Get bridge health through the GUI-independent RPC status method."""
    try:
        status = freecad.get_rpc_status()
        if isinstance(status, dict):
            status["version_check"] = addon_version_warning(status) or "ok"
        return json_response(status)
    except Exception as e:
        if is_missing_method_fault(e):
            return error_response(addon_version_warning(None))
        logger.error(f"Failed to get RPC status: {str(e)}")
        return error_response(f"Failed to get RPC status: {str(e)}")


def run_fem_analysis_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
    include_screenshot: bool = True,
    view_name: str = "Isometric",
) -> ToolResponse:
    try:
        res = freecad.run_fem_analysis(doc_name, analysis_name, timeout)
        if res.get("success"):
            def fmt(v, unit):
                return f"{v:.4g} {unit}" if isinstance(v, (int, float)) else f"unavailable ({unit})"
            skip_screenshot = only_text_feedback or not include_screenshot
            screenshot = None if skip_screenshot else freecad.get_active_screenshot(view_name)
            response = json_response({
                "summary": (
                    f"FEM analysis '{analysis_name}' solved. "
                    f"max von Mises = {fmt(res.get('max_von_mises_MPa'), 'MPa')}, "
                    f"max displacement = {fmt(res.get('max_displacement_mm'), 'mm')} "
                    f"({res.get('node_count')} nodes)."
                ),
                **res,
            })
            return add_screenshot_if_available(response, screenshot, skip_screenshot)
        return ErrorResponse(json_response({
            "summary": f"FEM analysis '{analysis_name}' failed: {res.get('error')}",
            **res,
        }))
    except Exception as e:
        logger.error(f"Failed to run FEM analysis: {str(e)}")
        return error_response(f"Failed to run FEM analysis: {str(e)}")


def reload_document_operation(
    freecad: FreeCADConnection,
    doc_name: str,
) -> ToolResponse:
    """Close and re-open a document so the GUI picks up external file
    changes (e.g. headless edits via `freecadcmd`).
    """
    try:
        res = freecad.reload_document(doc_name)
        if res.get("success"):
            name = res.get("document_name", doc_name)
            if name == doc_name:
                return text_response(f"Document '{doc_name}' reloaded from disk.")
            return text_response(
                f"Document '{doc_name}' was reopened by FreeCAD as '{name}'."
                f" Use '{name}' in later calls."
            )
        return error_response(f"Failed to reload document: {res.get('error')}")
    except Exception as e:
        logger.error(f"Failed to reload document: {str(e)}")
        return error_response(f"Failed to reload document: {str(e)}")
