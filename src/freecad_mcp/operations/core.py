import logging
from typing import Any

from mcp.types import ImageContent

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, add_screenshot_if_available, json_response, text_response

logger = logging.getLogger("FreeCADMCPserver")


def create_document_operation(freecad: FreeCADConnection, name: str) -> ToolResponse:
    try:
        res = freecad.create_document(name)
        if res["success"]:
            return text_response(f"Document '{res['document_name']}' created successfully")
        return text_response(f"Failed to create document: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to create document: {str(e)}")
        return text_response(f"Failed to create document: {str(e)}")


def create_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] | None = None,
) -> ToolResponse:
    try:
        obj_data = {
            "Name": obj_name,
            "Type": obj_type,
            "Properties": obj_properties or {},
            "Analysis": analysis_name,
        }
        res = freecad.create_object(doc_name, obj_data)
        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' created successfully")
        else:
            return text_response(f"Failed to create object: {res['error']}")
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to create object: {str(e)}")
        return text_response(f"Failed to create object: {str(e)}")


def edit_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    obj_properties: dict[str, Any],
) -> ToolResponse:
    try:
        res = freecad.edit_object(doc_name, obj_name, {"Properties": obj_properties})
        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' edited successfully")
        else:
            return text_response(f"Failed to edit object: {res['error']}")
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to edit object: {str(e)}")
        return text_response(f"Failed to edit object: {str(e)}")


def delete_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    try:
        res = freecad.delete_object(doc_name, obj_name)
        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' deleted successfully")
        else:
            return text_response(f"Failed to delete object: {res['error']}")
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to delete object: {str(e)}")
        return text_response(f"Failed to delete object: {str(e)}")


def execute_code_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
) -> ToolResponse:
    try:
        res = freecad.execute_code(code)
        if res["success"]:
            response = text_response(f"Code executed successfully: {res['message']}")
            # Only attempt screenshot when code completed and screenshots are wanted.
            # Skipping on failure avoids a second hanging call while the worker thread
            # may still be running.
            screenshot = None if only_text_feedback else freecad.get_active_screenshot()
            return add_screenshot_if_available(response, screenshot, only_text_feedback)
        return text_response(f"Failed to execute code: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to execute code: {str(e)}")
        return text_response(f"Failed to execute code: {str(e)}")


def execute_code_async_operation(
    freecad: FreeCADConnection,
    code: str,
) -> ToolResponse:
    try:
        res = freecad.execute_code_async(code)
        if res["success"]:
            return text_response(
                "Code execution started in background.\n"
                "It runs on a separate thread and must not touch the FreeCAD "
                "document, GUI, selection, or recompute/save. "
                "Output (or any error) will appear in FreeCAD's Report View "
                "when it completes."
            )
        return text_response(f"Failed to start async execution: {res.get('error', 'unknown')}")
    except Exception as e:
        logger.error(f"Failed to start async code execution: {str(e)}")
        return text_response(f"Failed to start async code execution: {str(e)}")


def get_view_operation(
    freecad: FreeCADConnection,
    view_name: str,
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> ToolResponse:
    screenshot = freecad.get_active_screenshot(view_name, width, height, focus_object)
    if screenshot is not None:
        return [ImageContent(type="image", data=screenshot, mimeType="image/png")]
    return text_response("Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)")


def insert_part_from_library_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    relative_path: str,
) -> ToolResponse:
    try:
        res = freecad.insert_part_from_library(relative_path)
        if res["success"]:
            response = text_response(f"Part inserted from library: {res['message']}")
        else:
            return text_response(f"Failed to insert part from library: {res['error']}")
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to insert part from library: {str(e)}")
        return text_response(f"Failed to insert part from library: {str(e)}")


def get_objects_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    try:
        response = json_response(freecad.get_objects(doc_name))
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to get objects: {str(e)}")
        return text_response(f"Failed to get objects: {str(e)}")


def get_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    try:
        response = json_response(freecad.get_object(doc_name, obj_name))
        screenshot = None if only_text_feedback else freecad.get_active_screenshot()
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to get object: {str(e)}")
        return text_response(f"Failed to get object: {str(e)}")


def get_parts_list_operation(freecad: FreeCADConnection) -> ToolResponse:
    parts = freecad.get_parts_list()
    if parts:
        return json_response(parts)
    return text_response("No parts found in the parts library. You must add parts_library addon.")


def list_documents_operation(freecad: FreeCADConnection) -> ToolResponse:
    return json_response(freecad.list_documents())


def run_fem_analysis_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
) -> ToolResponse:
    try:
        res = freecad.run_fem_analysis(doc_name, analysis_name, timeout)
        if res.get("success"):
            def fmt(v, unit):
                return f"{v:.4g} {unit}" if isinstance(v, (int, float)) else f"unavailable ({unit})"
            screenshot = freecad.get_active_screenshot() if not only_text_feedback else None
            response = json_response({
                "summary": (
                    f"FEM analysis '{analysis_name}' solved. "
                    f"max von Mises = {fmt(res.get('max_von_mises_MPa'), 'MPa')}, "
                    f"max displacement = {fmt(res.get('max_displacement_mm'), 'mm')} "
                    f"({res.get('node_count')} nodes)."
                ),
                **res,
            })
            return add_screenshot_if_available(response, screenshot, only_text_feedback)
        return json_response({
            "summary": f"FEM analysis '{analysis_name}' failed: {res.get('error')}",
            **res,
        })
    except Exception as e:
        logger.error(f"Failed to run FEM analysis: {str(e)}")
        return text_response(f"Failed to run FEM analysis: {str(e)}")


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
            return text_response(
                f"Document '{res['document_name']}' reloaded from disk."
            )
        return text_response(f"Failed to reload document: {res.get('error')}")
    except Exception as e:
        logger.error(f"Failed to reload document: {str(e)}")
        return text_response(f"Failed to reload document: {str(e)}")

