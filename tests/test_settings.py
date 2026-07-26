import json
import sys

import pytest

from rpc_server import settings as settings_mod
from rpc_server.settings import _DEFAULT_SETTINGS, load_settings, save_settings


@pytest.fixture
def settings_dir(tmp_path, monkeypatch):
    """Point the FreeCAD stub's user app data dir at a temp directory."""
    monkeypatch.setattr(
        sys.modules["FreeCAD"], "getUserAppDataDir", lambda: str(tmp_path)
    )
    return tmp_path


class TestLoadSettings:
    def test_missing_file_returns_defaults(self, settings_dir):
        assert load_settings() == _DEFAULT_SETTINGS

    def test_missing_file_returns_copy_not_shared_dict(self, settings_dir):
        settings = load_settings()
        settings["remote_enabled"] = True
        assert _DEFAULT_SETTINGS["remote_enabled"] is False

    def test_corrupt_file_returns_defaults(self, settings_dir):
        (settings_dir / "freecad_mcp_settings.json").write_text("{not json!", encoding="utf-8")
        assert load_settings() == _DEFAULT_SETTINGS

    def test_partial_file_merged_with_defaults(self, settings_dir):
        (settings_dir / "freecad_mcp_settings.json").write_text(
            json.dumps({"remote_enabled": True}), encoding="utf-8"
        )
        settings = load_settings()
        assert settings["remote_enabled"] is True
        assert settings["allowed_ips"] == _DEFAULT_SETTINGS["allowed_ips"]
        assert settings["auto_start_rpc"] == _DEFAULT_SETTINGS["auto_start_rpc"]

    def test_unknown_keys_preserved(self, settings_dir):
        (settings_dir / "freecad_mcp_settings.json").write_text(
            json.dumps({"future_key": 123}), encoding="utf-8"
        )
        assert load_settings()["future_key"] == 123


class TestSaveSettings:
    def test_roundtrip(self, settings_dir):
        settings = dict(_DEFAULT_SETTINGS)
        settings["allowed_ips"] = "192.168.1.0/24"
        save_settings(settings)
        assert load_settings() == settings

    def test_writes_expected_filename(self, settings_dir):
        save_settings(dict(_DEFAULT_SETTINGS))
        assert (settings_dir / "freecad_mcp_settings.json").exists()
