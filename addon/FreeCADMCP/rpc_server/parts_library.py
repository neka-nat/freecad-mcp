import os
from functools import cache

import FreeCAD
import FreeCADGui


def insert_part_from_library(relative_path: str) -> None:
    """Insert a part from the FreeCAD parts library.

    Args:
        relative_path: Relative path to the part file within the parts library.

    Raises:
        FileNotFoundError: If the part file does not exist.
        ValueError: If the path attempts to traverse outside the library directory.
    """
    parts_lib_path = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "parts_library")

    # Normalize and validate the path to prevent path traversal attacks
    part_path = os.path.normpath(os.path.join(parts_lib_path, relative_path))

    # Security check: Ensure the resolved path is within the parts library
    if not part_path.startswith(os.path.normpath(parts_lib_path) + os.sep):
        raise ValueError(f"Invalid path: Path traversal attempt detected in '{relative_path}'")

    # Ensure the file has the correct extension
    if not part_path.endswith(".FCStd"):
        raise ValueError(f"Invalid file type: Only .FCStd files are allowed, got '{relative_path}'")

    if not os.path.exists(part_path):
        raise FileNotFoundError(f"Not found: {part_path}")

    FreeCADGui.ActiveDocument.mergeProject(part_path)


@cache
def get_parts_list() -> list[str]:
    parts_lib_path = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "parts_library")

    if not os.path.exists(parts_lib_path):
        raise FileNotFoundError(f"Not found: {parts_lib_path}")

    parts = []

    for root, _, files in os.walk(parts_lib_path):
        for file in files:
            if file.endswith(".FCStd"):
                relative_path = os.path.relpath(os.path.join(root, file), parts_lib_path)
                parts.append(relative_path)

    return parts
