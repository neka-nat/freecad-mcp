"""Operations backing the macro authoring and execution tools.

Kept out of ``core`` because macros are a self-contained capability: they
touch files in the user macro directory rather than the document tree, and
none of them need a screenshot.
"""

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, json_response, text_response


logger = logging.getLogger("FreeCADMCPserver")


def _failed(action: str, res: object) -> ToolResponse | None:
    """Render a failure result, or None when the call succeeded."""
    if isinstance(res, dict) and res.get("success"):
        return None
    error = res.get("error", res) if isinstance(res, dict) else res
    return text_response(f"Failed to {action}: {error}")


def list_macros_operation(freecad: FreeCADConnection) -> ToolResponse:
    try:
        res = freecad.list_macros()
        if (failure := _failed("list macros", res)) is not None:
            return failure
        return json_response(
            {"macro_dir": res.get("macro_dir"), "macros": res.get("macros", [])}
        )
    except Exception as e:
        logger.error(f"Failed to list macros: {str(e)}")
        return text_response(f"Failed to list macros: {str(e)}")


def get_macro_operation(freecad: FreeCADConnection, name: str) -> ToolResponse:
    try:
        res = freecad.get_macro(name)
        if (failure := _failed(f"read macro '{name}'", res)) is not None:
            return failure
        return text_response(res["code"])
    except Exception as e:
        logger.error(f"Failed to read macro: {str(e)}")
        return text_response(f"Failed to read macro '{name}': {str(e)}")


def create_macro_operation(
    freecad: FreeCADConnection, name: str, code: str, overwrite: bool = False
) -> ToolResponse:
    try:
        res = freecad.create_macro(name, code, overwrite)
        if (failure := _failed(f"create macro '{name}'", res)) is not None:
            return failure
        return text_response(
            f"Macro '{res['name']}' written ({res['bytes']} bytes) to {res['path']}"
        )
    except Exception as e:
        logger.error(f"Failed to create macro: {str(e)}")
        return text_response(f"Failed to create macro '{name}': {str(e)}")


def edit_macro_operation(
    freecad: FreeCADConnection,
    name: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> ToolResponse:
    try:
        res = freecad.edit_macro(name, old_string, new_string, replace_all)
        if (failure := _failed(f"edit macro '{name}'", res)) is not None:
            return failure
        return text_response(
            f"Macro '{res['name']}' edited ({res['replacements']} replacement(s))"
        )
    except Exception as e:
        logger.error(f"Failed to edit macro: {str(e)}")
        return text_response(f"Failed to edit macro '{name}': {str(e)}")


def run_macro_operation(freecad: FreeCADConnection, name: str) -> ToolResponse:
    try:
        res = freecad.run_macro(name)
        if (failure := _failed(f"run macro '{name}'", res)) is not None:
            return failure
        return text_response(f"Macro '{res['name']}' started. {res['message']}")
    except Exception as e:
        logger.error(f"Failed to run macro: {str(e)}")
        return text_response(f"Failed to run macro '{name}': {str(e)}")
