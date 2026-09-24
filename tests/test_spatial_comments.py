import importlib.util
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

ADDON_DIR = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
COMMENTS_PATH = ADDON_DIR / "rpc_server" / "comments.py"


class FakeVector:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = x
        self.y = y
        self.z = z


class FakeFaceSurface:
    @staticmethod
    def parameter(_center: FakeVector) -> tuple[int, int]:
        return 0, 0


class FakeFace:
    CenterOfMass = FakeVector(10.0, 20.0, 30.0)
    Surface = FakeFaceSurface()
    Area = 42.0

    @staticmethod
    def normalAt(_u: int, _v: int) -> FakeVector:
        return FakeVector(0.0, 0.0, 1.0)


class FakeShape:
    BoundBox = types.SimpleNamespace(Center=FakeVector(1.0, 2.0, 3.0))

    @staticmethod
    def getElement(name: str) -> FakeFace:
        if name != "Face1":
            raise ValueError(name)
        return FakeFace()


class FakeObject:
    Name = "Body"
    Label = "case"
    TypeId = "PartDesign::Body"
    Shape = FakeShape()
    Placement = types.SimpleNamespace(Base=FakeVector(4.0, 5.0, 6.0))


class FakeDocument:
    def __init__(self, file_name: Path) -> None:
        self.Name = "Doc"
        self.FileName = str(file_name)
        self.objects = {"Body": FakeObject()}

    def getObject(self, name: str) -> object | None:
        return self.objects.get(name)


@contextmanager
def load_comments_module(app_data_dir: Path) -> Iterator[types.ModuleType]:
    module_names = ["FreeCAD", "FreeCADGui"]
    missing = object()
    saved = {name: sys.modules.get(name, missing) for name in module_names}

    warnings: list[str] = []
    freecad = types.ModuleType("FreeCAD")
    freecad.Console = types.SimpleNamespace(
        PrintWarning=warnings.append,
        PrintMessage=lambda _message: None,
    )
    freecad.getUserAppDataDir = lambda: str(app_data_dir)
    freecad.Vector = FakeVector

    freecad_gui = types.ModuleType("FreeCADGui")
    freecad_gui.Selection = types.SimpleNamespace(getSelectionEx=lambda _doc_name: [])

    sys.modules["FreeCAD"] = freecad
    sys.modules["FreeCADGui"] = freecad_gui

    module_name = f"_comments_test_{id(app_data_dir)}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, COMMENTS_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load comments from {COMMENTS_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        module._test_warnings = warnings
        yield module
    finally:
        sys.modules.pop(module_name, None)
        for name, value in saved.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def test_create_comment_enriches_subelement_anchor_and_persists(tmp_path: Path) -> None:
    doc = FakeDocument(tmp_path / "model.FCStd")
    with load_comments_module(tmp_path) as comments:
        comment = comments.create_comment(
            doc,
            {
                "id": "comment-1",
                "text": "Round this face for finger comfort.",
                "anchor": {
                    "type": "subelement",
                    "object_name": "Body",
                    "subelement": "Face1",
                    "position": {"x": 9.0, "y": 8.0, "z": 7.0},
                },
            },
        )

        assert comment["id"] == "comment-1"
        assert comment["thread_id"] == "comment-1"
        assert comment["status"] == "open"
        assert comment["anchor"]["type"] == "subelement"
        signature = comment["anchor"]["geometry_signature"]
        assert signature["object_name"] == "Body"
        assert signature["object_type"] == "PartDesign::Body"
        assert signature["center"] == {"x": 10.0, "y": 20.0, "z": 30.0}
        assert signature["normal"] == {"x": 0.0, "y": 0.0, "z": 1.0}
        assert signature["measure"] == 42.0

        store = comments.load_comment_store(doc)
        assert store["comments"][0]["id"] == "comment-1"
        assert Path(store["sidecar_path"]).name == "model.FCStd.comments.json"


def test_missing_anchor_object_fails_clearly(tmp_path: Path) -> None:
    doc = FakeDocument(tmp_path / "model.FCStd")
    with (
        load_comments_module(tmp_path) as comments,
        pytest.raises(ValueError, match="Missing"),
    ):
        comments.create_comment(
            doc,
            {
                "text": "Attach to missing object.",
                "anchor": {"type": "object", "object_name": "Missing"},
            },
        )


def test_update_can_propose_but_not_confirm_resolution(tmp_path: Path) -> None:
    doc = FakeDocument(tmp_path / "model.FCStd")
    with load_comments_module(tmp_path) as comments:
        comments.create_comment(
            doc,
            {
                "id": "comment-1",
                "text": "Needs review.",
                "anchor": {"type": "object", "object_name": "Body"},
            },
        )

        with pytest.raises(ValueError, match="Final resolution"):
            comments.update_comment(doc, "comment-1", {"status": "resolved"})

        proposed = comments.update_comment(
            doc,
            "comment-1",
            {"status": "resolution_proposed", "resolution_note": "Done."},
        )
        assert proposed["status"] == "resolution_proposed"

        resolved = comments.confirm_comment_resolution(doc, "comment-1", "Accepted.")
        assert resolved["status"] == "resolved"
        assert resolved["resolution_note"] == "Accepted."
        assert comments.list_comments(doc) == []
        assert len(comments.list_comments(doc, {"include_resolved": True})) == 1


def test_corrupt_sidecar_is_quarantined(tmp_path: Path) -> None:
    doc = FakeDocument(tmp_path / "model.FCStd")
    sidecar = tmp_path / "model.FCStd.comments.json"
    sidecar.write_text("not-json", encoding="utf-8")

    with load_comments_module(tmp_path) as comments:
        store = comments.load_comment_store(doc)

        assert store["comments"] == []
        assert "load_error" in store
        assert not sidecar.exists()
        assert sidecar.with_suffix(".json.corrupt").exists()
        assert comments._test_warnings
