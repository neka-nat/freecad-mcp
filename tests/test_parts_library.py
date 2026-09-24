import importlib.util
from pathlib import Path
import sys
import types
from contextlib import contextmanager
from typing import Iterator

import pytest

ADDON_DIR = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
PARTS_LIBRARY_PATH = ADDON_DIR / "rpc_server" / "parts_library.py"
if str(ADDON_DIR) not in sys.path:
    sys.path.insert(0, str(ADDON_DIR))


class FakeDocument:
    def __init__(self) -> None:
        self.merged: list[str] = []

    def mergeProject(self, part_path: str) -> None:
        self.merged.append(part_path)


@contextmanager
def load_parts_library(app_data_dir: str) -> Iterator[tuple[types.ModuleType, FakeDocument]]:
    module_names = ["FreeCAD", "FreeCADGui"]
    missing = object()
    saved = {name: sys.modules.get(name, missing) for name in module_names}

    freecad = types.ModuleType("FreeCAD")
    freecad.getUserAppDataDir = lambda: app_data_dir
    freecad.newDocument = lambda: None

    active_document = FakeDocument()
    freecad_gui = types.ModuleType("FreeCADGui")
    freecad_gui.ActiveDocument = active_document

    sys.modules["FreeCAD"] = freecad
    sys.modules["FreeCADGui"] = freecad_gui

    module_name = f"_parts_library_test_{id(app_data_dir)}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, PARTS_LIBRARY_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load parts_library from {PARTS_LIBRARY_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        yield module, active_document
    finally:
        sys.modules.pop(module_name, None)
        for name, value in saved.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def test_absolute_relative_path_is_rejected(tmp_path):
    app_data_dir = tmp_path / "AppData"
    parts_lib = app_data_dir / "Mod" / "parts_library"
    parts_lib.mkdir(parents=True)
    secret = tmp_path / "secret.FCStd"
    secret.write_text("not a real FCStd file")

    with load_parts_library(str(app_data_dir)) as (module, active_document):
        with pytest.raises(ValueError):
            module.insert_part_from_library(str(secret))
        assert active_document.merged == []


def test_dotdot_relative_path_is_rejected(tmp_path):
    app_data_dir = tmp_path / "AppData"
    parts_lib = app_data_dir / "Mod" / "parts_library"
    parts_lib.mkdir(parents=True)
    secret = tmp_path / "secret.FCStd"
    secret.write_text("not a real FCStd file")

    with load_parts_library(str(app_data_dir)) as (module, active_document):
        with pytest.raises(ValueError):
            module.insert_part_from_library("../../../secret.FCStd")
        assert active_document.merged == []


def test_relative_path_within_library_still_works(tmp_path):
    app_data_dir = tmp_path / "AppData"
    parts_lib = app_data_dir / "Mod" / "parts_library"
    (parts_lib / "bolts").mkdir(parents=True)
    part = parts_lib / "bolts" / "m3.FCStd"
    part.write_text("not a real FCStd file")

    with load_parts_library(str(app_data_dir)) as (module, active_document):
        module.insert_part_from_library("bolts/m3.FCStd")
        assert active_document.merged == [str(part)]
