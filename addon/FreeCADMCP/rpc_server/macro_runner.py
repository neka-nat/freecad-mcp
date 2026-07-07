"""FreeCAD macro (.FCMacro) execution with proper __file__/sys.path context.

Plain-function module (macro path + exec globals in, plain dict out),
mirroring the fem_executor.py / step_io.py convention.
"""

import contextlib
import io
import os
import sys
import traceback


def run_macro(macro_path: str, exec_globals: dict) -> dict:
    """Execute a macro file on the caller's globals, with __file__ set to
    the macro's own path and its directory added to sys.path for the
    duration of the run.

    Unlike plain execute_code (exec(code, globals())), this sets up the
    context a macro run from FreeCAD's Macro menu would have: __file__
    pointing at itself (for relative resource loading) and its own
    directory importable (for sibling helper modules).
    """
    if not os.path.isfile(macro_path):
        return {"success": False, "error": f"Macro file not found: {macro_path}"}

    try:
        with open(macro_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        return {"success": False, "error": f"Could not read macro file: {type(e).__name__}: {e}"}

    macro_path = os.path.abspath(macro_path)
    macro_dir = os.path.dirname(macro_path)

    had_file = "__file__" in exec_globals
    original_file = exec_globals.get("__file__")
    exec_globals["__file__"] = macro_path

    path_inserted = macro_dir not in sys.path
    if path_inserted:
        sys.path.insert(0, macro_dir)

    output_buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(output_buffer):
            exec(compile(code, macro_path, "exec"), exec_globals)
        return {"success": True, "message": "Macro executed successfully.", "output": output_buffer.getvalue()}
    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "output": output_buffer.getvalue(),
        }
    finally:
        if path_inserted and macro_dir in sys.path:
            sys.path.remove(macro_dir)
        if had_file:
            exec_globals["__file__"] = original_file
        else:
            exec_globals.pop("__file__", None)
