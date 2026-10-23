"""#171: `reload_document` reports the name FreeCAD gave the reopened document.

FreeCAD names a reopened document after the file stem and sanitises it
("HandleConcept3D" saved as handle-concept-3d.FCStd comes back as
handle_concept_3d). The handler answered with the requested name, so the
call reported success and every follow-up call using that name failed with
"Document '<name>' is not loaded."
"""

from __future__ import annotations

import types

import pytest

from test_rpc_handlers import rpc_module  # noqa: F401  (fixture)
from test_rpc_handlers import wait_for_job  # noqa: F401


@pytest.fixture
def reloadable(rpc_module: types.ModuleType, tmp_path):
    """Point the fixture's document at a real file and stub the reopen."""
    document = rpc_module.FreeCAD.listDocuments()["Doc"]
    file_path = tmp_path / "handle-concept-3d.FCStd"
    file_path.write_bytes(b"")
    document.FileName = str(file_path)
    return document, file_path


def test_reload_reports_the_name_freecad_reopened_the_document_under(
    rpc_module: types.ModuleType, reloadable
) -> None:
    document, file_path = reloadable
    reopened = types.SimpleNamespace(Name="handle_concept_3d")
    seen = []

    def open_document(path: str):
        seen.append(path)
        return reopened

    rpc_module.FreeCAD.openDocument = open_document
    rpc_module.FreeCAD.closeDocument = lambda name: seen.append(name)

    result = rpc_module.FreeCADRPC().reload_document("Doc")

    assert result == {"success": True, "document_name": "handle_concept_3d"}
    assert seen == ["Doc", str(file_path)]


def test_reload_keeps_a_name_that_survives_the_reopen(
    rpc_module: types.ModuleType, reloadable
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
    rpc_module: types.ModuleType, reloadable
) -> None:
    document, _file_path = reloadable
    document.FileName = ""
    closed = []
    rpc_module.FreeCAD.closeDocument = lambda name: closed.append(name)

    result = rpc_module.FreeCADRPC().reload_document("Doc")

    assert result["success"] is False
    assert "no file on disk" in result["error"]
    assert closed == []
