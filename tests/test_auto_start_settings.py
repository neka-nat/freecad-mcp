"""Auto-start resolution for the addon (#127).

``FREECAD_MCP_AUTO_START`` lets a container entrypoint or a provisioning script
start the RPC server without opening FreeCAD's workbench menu, and overrides the
saved ``auto_start_rpc`` setting.
"""

import importlib.util
from pathlib import Path
import sys
import types
from typing import Iterator

import pytest


ADDON_DIR = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
SETTINGS_PATH = ADDON_DIR / "rpc_server" / "settings.py"
INIT_GUI_PATH = ADDON_DIR / "InitGui.py"


class FreeCADStub:
    """Minimal FreeCAD module: the addon only reads Console and the data dir."""

    def __init__(self) -> None:
        self.module = types.ModuleType("FreeCAD")
        self.warnings: list[str] = []
        self.messages: list[str] = []
        self.module.getUserAppDataDir = lambda: "/tmp"
        self.module.Console = types.SimpleNamespace(
            PrintMessage=self.messages.append,
            PrintWarning=self.warnings.append,
            PrintError=lambda _message: None,
        )


@pytest.fixture
def freecad(monkeypatch: pytest.MonkeyPatch) -> Iterator[FreeCADStub]:
    stub = FreeCADStub()
    monkeypatch.setitem(sys.modules, "FreeCAD", stub.module)
    yield stub


@pytest.fixture
def settings_module(freecad: FreeCADStub) -> types.ModuleType:
    """Load the real settings.py under the FreeCAD stub."""
    return _load_settings("_settings_test")


def _load_settings(module_name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, SETTINGS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def addon(
    monkeypatch: pytest.MonkeyPatch,
    freecad: FreeCADStub,
    settings_module: types.ModuleType,
) -> types.SimpleNamespace:
    """Run InitGui.py with FreeCAD/Qt stubbed and a recording rpc_server module.

    The real settings module is registered as ``rpc_server.settings``, so the hook
    is exercised against the actual auto-start resolution rather than a stand-in.
    """
    started: list[bool] = []

    rpc_server = types.ModuleType("rpc_server.rpc_server")
    rpc_server.start_rpc_server = lambda: started.append(True) or "started"
    rpc_server.load_settings = lambda: {}
    rpc_server_module = types.ModuleType("rpc_server")
    rpc_server_module.rpc_server = rpc_server
    rpc_server_module.load_settings = rpc_server.load_settings

    pyside = types.ModuleType("PySide")
    pyside.QtCore = types.SimpleNamespace(
        QTimer=types.SimpleNamespace(singleShot=lambda _delay, _callback: None)
    )

    monkeypatch.setitem(sys.modules, "PySide", pyside)
    monkeypatch.setitem(sys.modules, "rpc_server", rpc_server_module)
    monkeypatch.setitem(sys.modules, "rpc_server.rpc_server", rpc_server)
    monkeypatch.setitem(sys.modules, "rpc_server.settings", settings_module)

    # FreeCAD runs InitGui.py with these names already bound as globals.
    namespace: dict = {
        "__file__": str(INIT_GUI_PATH),
        "__name__": "_init_gui_test",
        "FreeCAD": freecad.module,
        "Workbench": object,
        "Gui": types.SimpleNamespace(addWorkbench=lambda _workbench: None),
    }
    code = compile(INIT_GUI_PATH.read_text(encoding="utf-8"), str(INIT_GUI_PATH), "exec")
    exec(code, namespace)
    return types.SimpleNamespace(
        auto_start=namespace["_auto_start_mcp"],
        settings=rpc_server_module,
        rpc_server=rpc_server,
        started=started,
        freecad=freecad,
    )


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on", " on "])
def test_env_var_enables_auto_start_over_the_saved_setting(
    settings_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch, value: str,
) -> None:
    monkeypatch.setenv(settings_module.AUTO_START_ENV_VAR, value)

    assert settings_module.auto_start_requested({"auto_start_rpc": False}) is True
    assert settings_module.auto_start_requested({}) is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no", "off", " off "])
def test_env_var_disables_auto_start_over_the_saved_setting(
    settings_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch, value: str,
) -> None:
    monkeypatch.setenv(settings_module.AUTO_START_ENV_VAR, value)

    assert settings_module.auto_start_requested({"auto_start_rpc": True}) is False


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_env_var_falls_back_to_the_saved_setting(
    settings_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch, value: str,
) -> None:
    monkeypatch.setenv(settings_module.AUTO_START_ENV_VAR, value)

    assert settings_module.auto_start_requested({"auto_start_rpc": True}) is True
    assert settings_module.auto_start_requested({"auto_start_rpc": False}) is False


def test_unset_env_var_falls_back_to_the_saved_setting(
    settings_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(settings_module.AUTO_START_ENV_VAR, raising=False)

    assert settings_module.auto_start_requested({"auto_start_rpc": True}) is True
    assert settings_module.auto_start_requested({"auto_start_rpc": False}) is False
    assert settings_module.auto_start_requested({}) is False


def test_unrecognised_env_var_warns_and_falls_back(
    freecad: FreeCADStub, monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_settings("_settings_warn_test")
    monkeypatch.setenv(module.AUTO_START_ENV_VAR, "ture")

    assert module.auto_start_requested({"auto_start_rpc": True}) is True
    assert freecad.warnings and "ture" in freecad.warnings[0]

    monkeypatch.setenv(module.AUTO_START_ENV_VAR, "1")
    assert module.auto_start_requested({"auto_start_rpc": False}) is True
    assert len(freecad.warnings) == 1


def test_auto_start_hook_consults_the_env_var(
    addon: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The env var must decide the launch path, not just the saved setting."""
    monkeypatch.setattr(addon.rpc_server, "load_settings", lambda: {"auto_start_rpc": False})
    monkeypatch.setenv("FREECAD_MCP_AUTO_START", "1")
    addon.auto_start()
    assert addon.started == [True]

    monkeypatch.setattr(addon.rpc_server, "load_settings", lambda: {"auto_start_rpc": True})
    monkeypatch.setenv("FREECAD_MCP_AUTO_START", "0")
    addon.started.clear()
    addon.auto_start()
    assert addon.started == []


def test_auto_start_hook_still_honours_the_saved_setting(
    addon: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FREECAD_MCP_AUTO_START", raising=False)

    monkeypatch.setattr(addon.rpc_server, "load_settings", lambda: {"auto_start_rpc": True})
    addon.auto_start()
    assert addon.started == [True]

    monkeypatch.setattr(addon.rpc_server, "load_settings", lambda: {"auto_start_rpc": False})
    addon.started.clear()
    addon.auto_start()
    assert addon.started == []


def test_auto_start_hook_reports_a_failed_start_without_raising(
    addon: types.SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing auto-start stays a warning: the hook runs at module import."""
    def fail() -> str:
        raise OSError("address already in use")

    monkeypatch.setattr(addon.rpc_server, "start_rpc_server", fail)
    monkeypatch.setattr(addon.rpc_server, "load_settings", lambda: {"auto_start_rpc": True})
    monkeypatch.delenv("FREECAD_MCP_AUTO_START", raising=False)

    addon.auto_start()

    assert any("Auto-start failed" in message for message in addon.freecad.warnings)
