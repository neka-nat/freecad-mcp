"""Release updates must preserve addon metadata and reject partial edits."""

from datetime import date
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bump_version.py"
spec = importlib.util.spec_from_file_location("bump_version", SCRIPT)
assert spec is not None and spec.loader is not None
bump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bump)

XML = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<package format="1" xmlns="https://wiki.freecad.org/Package_Metadata">
  <version>1.2.3</version>
  <date>2025-01-02</date>
  <!-- Keep the workbench loader instructions. -->
  <description>Control FreeCAD — MCP</description>
</package>
'''


@pytest.fixture
def metadata(tmp_path: Path) -> Path:
    path = tmp_path / "package.xml"
    path.write_text(XML, encoding="utf-8")
    return path


def test_bump_preserves_unrelated_metadata(metadata: Path) -> None:
    before_mode = metadata.stat().st_mode
    assert bump.bump_version(metadata, "1.2.4", date(2026, 10, 13)) == "1.2.3"
    assert metadata.read_text(encoding="utf-8") == XML.replace(
        "1.2.3", "1.2.4"
    ).replace("2025-01-02", "2026-10-13")
    assert bump.read_version(metadata) == "1.2.4"
    assert metadata.stat().st_mode == before_mode


def test_repeating_version_does_not_change_date_or_file(metadata: Path) -> None:
    before = metadata.stat().st_mtime_ns
    bump.bump_version(metadata, "1.2.3", date(2026, 10, 13))
    assert metadata.read_text(encoding="utf-8") == XML
    assert metadata.stat().st_mtime_ns == before


@pytest.mark.parametrize("version", ["v1.2.4", "01.2.4", "1.2", "1.2.4rc1", "<x>", "1.2.2"])
def test_invalid_or_older_version_leaves_file_untouched(metadata: Path, version: str) -> None:
    with pytest.raises(ValueError):
        bump.bump_version(metadata, version, date(2026, 10, 13))
    assert metadata.read_text(encoding="utf-8") == XML


@pytest.mark.parametrize("dates", ["", "<date>2025-01-02</date>" * 2])
def test_bad_date_field_does_not_partially_update_version(metadata: Path, dates: str) -> None:
    text = XML.replace("<date>2025-01-02</date>", dates)
    metadata.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one <date>"):
        bump.bump_version(metadata, "1.2.4", date(2026, 10, 13))
    assert metadata.read_text(encoding="utf-8") == text


def test_failed_replace_keeps_original_and_cleans_temporary(
    metadata: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_replace(self: Path, target: Path) -> None:
        raise OSError("replacement failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        bump.bump_version(metadata, "1.2.4", date(2026, 10, 13))
    assert metadata.read_text(encoding="utf-8") == XML
    assert list(metadata.parent.iterdir()) == [metadata]


def test_check_rejects_installed_version_mismatch(
    metadata: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(bump, "METADATA", metadata)
    monkeypatch.setattr(bump, "installed_version", lambda name: "1.2.2")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check"])
    with pytest.raises(SystemExit) as error:
        bump.main()
    assert error.value.code == 1
    assert "Installed version 1.2.2 != package.xml version 1.2.3" in capsys.readouterr().err
    assert metadata.read_text(encoding="utf-8") == XML


def test_bump_cli_works_outside_checkout(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / SCRIPT.name
    script.parent.mkdir()
    script.write_bytes(SCRIPT.read_bytes())
    metadata = tmp_path / "addon" / "FreeCADMCP" / "package.xml"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(XML, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(script), "1.2.4"],
        cwd=tmp_path.parent, capture_output=True, text=True, check=True,
    )
    assert "1.2.3 -> 1.2.4" in result.stdout
    assert bump.read_version(metadata) == "1.2.4"
