"""#171: `reload_document` reports the name FreeCAD gave the reopened document.

FreeCAD names a reopened document after the file stem and sanitises it
("HandleConcept3D" saved as handle-concept-3d.FCStd comes back as
handle_concept_3d). The handler answered with the requested name, so the
call reported success and every follow-up call using that name failed with
"Document '<name>' is not loaded."
"""

from __future__ import annotations

import types
from pathlib import Path

import pytest

from test_rpc_handlers import rpc_module  # noqa: F401  (fixture)


@pytest.fixture
def reloadable(
    rpc_module: types.ModuleType, tmp_path: Path,
) -> tuple[types.SimpleNamespace, Path]:
    """Point the fixture's document at a real file and stub the reopen."""
    document = rpc_module.FreeCAD.listDocuments()["Doc"]
    file_path = tmp_path / "handle-concept-3d.FCStd"
    file_path.write_bytes(b"")
    document.FileName = str(file_path)
    return document, file_path


@pytest.mark.parametrize("reopened_name", ["handle_concept_3d", "handle_concept_3d001"])
def test_reload_reports_the_name_freecad_reopened_the_document_under(
    rpc_module: types.ModuleType,
    reloadable: tuple[types.SimpleNamespace, Path],
    reopened_name: str,
) -> None:
    document, file_path = reloadable
    reopened = types.SimpleNamespace(
        Name=reopened_name, Objects=document.Objects, getObject=document.getObject,
    )
    documents = {"Doc": document}
    seen: list[str] = []

    def open_document(path: str) -> types.SimpleNamespace:
        seen.append(path)
        documents[reopened.Name] = reopened
        return reopened

    def close_document(name: str) -> None:
        seen.append(name)
        del documents[name]

    rpc_module.FreeCAD.openDocument = open_document
    rpc_module.FreeCAD.closeDocument = close_document
    rpc_module.FreeCAD.getDocument = documents.__getitem__
    rpc_module.FreeCAD.listDocuments = lambda: documents

    rpc = rpc_module.FreeCADRPC()
    result = rpc.reload_document("Doc")

    assert result == {"success": True, "document_name": reopened_name}
    assert seen == ["Doc", str(file_path)]
    assert rpc.list_documents() == [reopened_name]
    assert rpc.get_object(result["document_name"], "Box") == {"Name": "Box"}


def test_reload_keeps_a_name_that_survives_the_reopen(
    rpc_module: types.ModuleType, reloadable: tuple[types.SimpleNamespace, Path],
) -> None:
    """Control: a document named after its stem keeps its name."""
    document, _file_path = reloadable
    rpc_module.FreeCAD.openDocument = lambda _path: types.SimpleNamespace(Name="Doc")

    result = rpc_module.FreeCADRPC().reload_document("Doc")

    assert result == {"success": True, "document_name": "Doc"}


def test_reload_still_fails_when_the_document_is_not_loaded(
    rpc_module: types.ModuleType
) -> None:
    result = rpc_module.FreeCADRPC().reload_document("Missing")

    assert result["success"] is False
    assert "not loaded" in result["error"]


def test_reload_without_a_file_on_disk_does_not_close_the_document(
    rpc_module: types.ModuleType, reloadable: tuple[types.SimpleNamespace, Path],
) -> None:
    document, _file_path = reloadable
    document.FileName = ""
    closed: list[str] = []
    rpc_module.FreeCAD.closeDocument = lambda name: closed.append(name)

    result = rpc_module.FreeCADRPC().reload_document("Doc")

    assert result["success"] is False
    assert "no file on disk" in result["error"]
    assert closed == []


def test_reload_missing_file_does_not_close_the_document(
    rpc_module: types.ModuleType, reloadable: tuple[types.SimpleNamespace, Path],
) -> None:
    _document, file_path = reloadable
    file_path.unlink()
    closed: list[str] = []
    rpc_module.FreeCAD.closeDocument = closed.append

    result = rpc_module.FreeCADRPC().reload_document("Doc")

    assert result["success"] is False
    assert "not found" in result["error"]
    assert closed == []
