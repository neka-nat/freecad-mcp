"""Macro authoring and execution for the RPC server.

FreeCAD macros are ordinary ``.FCMacro`` files (plain Python) living in the
user macro directory, so authoring them is file I/O and needs no GUI thread.
Execution is the awkward part and is deliberately kept separate --- see
``run_macro`` for why it cannot simply be run and awaited.
"""

import os
import re

import FreeCAD
import FreeCADGui
from PySide import QtCore

from rpc_server.gui_dispatch import dispatch_to_gui


MACRO_SUFFIX = ".FCMacro"

#: A macro name must be a plain file name. These helpers write files that
#: run_macro will later execute as Python, so a name escaping the macro
#: directory ("../../.bashrc") has to be impossible rather than unlikely.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$")

_DOCSTRING = re.compile(r'"""(.*?)"""|\'\'\'(.*?)\'\'\'', re.S)


def macro_dir() -> str:
    """The user macro directory FreeCAD itself lists macros from.

    Read from FreeCAD rather than configured here, so this works for any
    user. Note it is whatever the user pointed FreeCAD at, which may be a
    cloud-synced folder.
    """
    return FreeCAD.getUserMacroDir(True)


def _resolve(name: str) -> str:
    """Map a macro name to an absolute path inside the macro directory."""
    if not isinstance(name, str) or not _SAFE_NAME.match(name.strip()):
        raise ValueError(
            f"Invalid macro name {name!r}. Use letters, digits, spaces, "
            "'.', '_' or '-', starting with a letter or digit."
        )
    name = name.strip()
    if not name.endswith(MACRO_SUFFIX):
        name += MACRO_SUFFIX

    directory = os.path.realpath(macro_dir())
    path = os.path.realpath(os.path.join(directory, name))
    # Belt and braces: the regex already forbids separators, but resolve and
    # re-check so a symlink inside the macro dir cannot redirect a write out.
    if os.path.dirname(path) != directory:
        raise ValueError(f"Macro name {name!r} resolves outside the macro directory.")
    return path


def _summary(source: str) -> str:
    """First meaningful line of a macro's docstring, for listings."""
    match = _DOCSTRING.search(source[:4096])
    block = (match.group(1) or match.group(2)) if match else ""
    for line in block.splitlines():
        line = line.strip()
        if line:
            return line
    for line in source[:4096].splitlines():
        line = line.strip()
        if line.startswith("#") and not line.startswith("#!") and "coding" not in line:
            return line.lstrip("# ").strip()
    return ""


def list_macros() -> dict:
    """Every macro in the macro directory, with size and summary line."""
    directory = macro_dir()
    if not os.path.isdir(directory):
        return {"success": True, "macro_dir": directory, "macros": []}

    macros = []
    for entry in sorted(os.listdir(directory)):
        if not entry.endswith(MACRO_SUFFIX):
            continue
        path = os.path.join(directory, entry)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                head = fh.read(4096)
            size = os.path.getsize(path)
        except OSError as e:
            macros.append({"name": entry, "error": str(e)})
            continue
        macros.append(
            {
                "name": entry[: -len(MACRO_SUFFIX)],
                "file": entry,
                "bytes": size,
                "summary": _summary(head),
            }
        )
    return {"success": True, "macro_dir": directory, "macros": macros}


def get_macro(name: str) -> dict:
    """Full source of one macro."""
    path = _resolve(name)
    if not os.path.isfile(path):
        raise ValueError(f"Macro '{name}' not found in {macro_dir()}.")
    with open(path, encoding="utf-8") as fh:
        code = fh.read()
    return {"success": True, "name": os.path.basename(path), "path": path, "code": code}


def create_macro(name: str, code: str, overwrite: bool = False) -> dict:
    """Write a new macro file."""
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Macro code must be a non-empty string.")
    path = _resolve(name)
    if os.path.exists(path) and not overwrite:
        raise ValueError(
            f"Macro '{os.path.basename(path)}' already exists. "
            "Pass overwrite=True to replace it, or use edit_macro to change part of it."
        )
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    if not code.endswith("\n"):
        code += "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(code)
    FreeCAD.Console.PrintMessage(f"MCP: wrote macro {path}\n")
    return {
        "success": True,
        "name": os.path.basename(path),
        "path": path,
        "bytes": len(code.encode("utf-8")),
    }


def edit_macro(name: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """Replace an exact substring inside an existing macro.

    String replacement rather than whole-file rewrite: these files reach
    100 kB, and round-tripping one through a model to change a single value
    invites it to silently drop the parts it only half-remembers. A
    non-matching edit fails loudly instead of corrupting the macro.
    """
    if not isinstance(old_string, str) or old_string == "":
        raise ValueError("old_string must be a non-empty string.")
    if old_string == new_string:
        raise ValueError("old_string and new_string are identical; nothing to do.")

    path = _resolve(name)
    if not os.path.isfile(path):
        raise ValueError(f"Macro '{name}' not found in {macro_dir()}.")
    with open(path, encoding="utf-8") as fh:
        source = fh.read()

    count = source.count(old_string)
    if count == 0:
        raise ValueError(f"old_string not found in macro '{os.path.basename(path)}'.")
    if count > 1 and not replace_all:
        raise ValueError(
            f"old_string appears {count} times in '{os.path.basename(path)}'. "
            "Include surrounding lines to make it unique, or pass replace_all=True."
        )

    updated = source.replace(old_string, new_string)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(updated)
    FreeCAD.Console.PrintMessage(f"MCP: edited macro {path} ({count} replacement(s))\n")
    return {
        "success": True,
        "name": os.path.basename(path),
        "path": path,
        "replacements": count,
    }


def _execute(path: str) -> None:
    """Run a macro file the way FreeCAD's own macro runner does.

    ``__name__`` must be ``"__main__"``: the common macro idiom guards its
    entry point with ``if __name__ == '__main__'``, and without this the
    macro would load and do nothing at all.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        namespace = {"__name__": "__main__", "__file__": path, "__builtins__": __builtins__}
        exec(compile(source, path, "exec"), namespace)
    except Exception as e:
        import traceback

        FreeCAD.Console.PrintError(
            f"MCP: macro '{os.path.basename(path)}' raised "
            f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        )


def run_macro(name: str) -> dict:
    """Start a macro on the GUI thread and return without waiting for it.

    Detached on purpose, for a reason specific to this server. Macros
    routinely open a modal Qt dialog, and ``process_gui_tasks`` skips every
    tick while ``activeModalWidget()`` is set --- so awaiting a macro would
    stall the entire MCP dispatch loop until a human dismissed the dialog.
    Running it in a background thread instead is not an option either, since
    Qt widgets may only be constructed on the GUI thread.

    So: hop to the GUI thread (fast, returns at once) purely to arm a
    zero-delay timer. The macro then runs from the event loop after the
    dispatch task has finished, on the right thread, blocking nothing.

    The corollary is that this cannot report what the macro did. Anything
    the macro creates has to be observed afterwards with get_objects.
    """
    path = _resolve(name)
    if not os.path.isfile(path):
        raise ValueError(f"Macro '{name}' not found in {macro_dir()}.")
    if not FreeCAD.GuiUp:
        raise ValueError("Running macros requires the FreeCAD GUI.")

    res = dispatch_to_gui(lambda: QtCore.QTimer.singleShot(0, lambda: _execute(path)))
    if isinstance(res, dict) and not res.get("success", True):
        return res

    FreeCADGui.updateGui()
    return {
        "success": True,
        "name": os.path.basename(path),
        "path": path,
        "detached": True,
        "message": (
            "It runs detached, so this call cannot report its result; if it opens "
            "a dialog it is now waiting for input. Use get_objects to see what it "
            "created."
        ),
    }
