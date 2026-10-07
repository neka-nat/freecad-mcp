"""Do not manipulate a hidden 3D view while a different tab is displayed."""

import base64
import importlib.util
from pathlib import Path
import sys
import threading
import types
from typing import Any
from unittest.mock import Mock

import pytest

from test_rpc_handlers import rpc_module


VIEW_PATH = Path(__file__).resolve().parents[1] / "addon/FreeCADMCP/rpc_server/view_manager.py"


@pytest.fixture
def view_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    hidden = Mock()
    shown = types.SimpleNamespace()
    gui = types.SimpleNamespace(
        ActiveDocument=types.SimpleNamespace(ActiveView=hidden),
        activeView=Mock(return_value=shown),
        Selection=Mock(), SendMsgToActiveView=Mock(), runCommand=Mock(),
    )
    freecad = types.SimpleNamespace(
        Console=types.SimpleNamespace(PrintWarning=Mock()),
        ActiveDocument=types.SimpleNamespace(getObject=lambda _name: object()),
    )
    flush = Mock()
    monkeypatch.setitem(sys.modules, "FreeCADGui", gui)
    monkeypatch.setitem(sys.modules, "FreeCAD", freecad)
    monkeypatch.setitem(sys.modules, "rpc_server.gui_dispatch", types.SimpleNamespace(_flush_gui_events=flush))
    spec = importlib.util.spec_from_file_location("_view_test", VIEW_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("active_view", ["other-tab", "no-view", "lookup-error"])
def test_hidden_3d_view_is_not_touched(
    view_module: types.ModuleType, tmp_path: Path, active_view: str,
) -> None:
    gui = view_module.FreeCADGui
    if active_view == "no-view":
        gui.activeView.return_value = None
    elif active_view == "lookup-error":
        gui.activeView.side_effect = RuntimeError("no active view")
    target = tmp_path / "hidden.png"
    result = view_module.save_active_screenshot(str(target), focus_object="Box")
    assert isinstance(result, str) and "not a 3D view" in result
    assert not target.exists()
    assert gui.ActiveDocument.ActiveView.mock_calls == []
    assert gui.Selection.mock_calls == []
    gui.SendMsgToActiveView.assert_not_called()
    gui.runCommand.assert_not_called()
    view_module._flush_gui_events.assert_not_called()


@pytest.mark.parametrize("focus", [None, "Box"])
@pytest.mark.parametrize("legacy_save", [False, True])
def test_displayed_3d_view_keeps_capture_and_framing(
    view_module: types.ModuleType, tmp_path: Path, focus: str | None, legacy_save: bool,
) -> None:
    gui = view_module.FreeCADGui
    shown = Mock()
    shown.getSize.return_value = (1600, 1200)

    def save(path: str, width: int, height: int, background: str, *method: str) -> None:
        if legacy_save and method:
            raise TypeError("legacy saveImage accepts four arguments")
        assert (width, height, background) == (800, 600, "Current")
        Path(path).write_bytes(b"screenshot")

    shown.saveImage.side_effect = save
    gui.activeView.return_value = shown
    target = tmp_path / "shown.png"
    assert view_module.save_active_screenshot(str(target), "Top", 800, 600, focus) is True
    assert target.read_bytes() == b"screenshot"
    shown.viewTop.assert_called_once()
    assert gui.ActiveDocument.ActiveView.mock_calls == []
    if focus:
        assert gui.SendMsgToActiveView.call_count == 2
    else:
        assert shown.fitAll.call_count == 2


@pytest.mark.parametrize("supported", [False, True])
def test_rpc_capture_runs_on_gui_and_cleans_temp_file(
    rpc_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path, supported: bool,
) -> None:
    caller = threading.get_ident()
    make_temp = rpc_module.tempfile.mkstemp
    monkeypatch.setattr(rpc_module.tempfile, "mkstemp", lambda **kwargs: make_temp(dir=tmp_path, **kwargs))
    calls: list[tuple[Any, ...]] = []

    def displayed() -> object | None:
        assert threading.get_ident() != caller
        return object() if supported else None

    def save(path: str, *args: Any) -> bool:
        assert threading.get_ident() != caller
        calls.append(args)
        Path(path).write_bytes(b"png payload")
        return True

    monkeypatch.setattr(rpc_module, "get_displayed_3d_view", displayed)
    monkeypatch.setattr(rpc_module, "save_active_screenshot", save)
    result = rpc_module.FreeCADRPC().get_active_screenshot("Top", 800, 600, "Box")
    if supported:
        assert result == base64.b64encode(b"png payload").decode()
        assert calls == [("Top", 800, 600, "Box")]
    else:
        assert result is None and calls == []
    assert list(tmp_path.iterdir()) == []
