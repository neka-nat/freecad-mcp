"""Screen capture must not select a browser or ignore an overlay."""
import importlib.util
from pathlib import Path
import types
from unittest.mock import Mock

import pytest
from test_displayed_view import view_module

PATH = Path(__file__).resolve().parents[1] / "addon/FreeCADMCP/rpc_server/screencopy.py"


@pytest.fixture
def capture(monkeypatch):
    spec = importlib.util.spec_from_file_location("_screencopy", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    window = {"pid": 123, "class": "org.freecad.FreeCAD", "title": "FreeCAD", "address": "0x123",
              "at": [1000, 800], "size": [100, 100], "mapped": True, "hidden": False}
    browser = {**window, "pid": 456, "class": "firefox", "title": "freecad-mcp - GitHub",
               "address": "0x456", "at": [0, 0]}
    replies = {"clients": [browser, window], "activewindow": window,
               "layers": {"monitor": {"levels": {"2": [], "3": []}}}}
    monkeypatch.setattr(module, "_query", lambda name: replies[name])
    runner = Mock(return_value=types.SimpleNamespace(returncode=0))
    monkeypatch.setattr(module.subprocess, "run", runner)
    return module, replies, runner


def test_capture_uses_pid_and_class_not_browser_title(capture) -> None:
    module, _, runner = capture
    image = types.SimpleNamespace(isNull=lambda: False)
    assert module.capture_viewport(123, (10, 10, 80, 80), (100, 100), lambda _: image) is image
    assert runner.call_args.args[0][2] == "1010,810 80x80"


@pytest.mark.parametrize("problem", ["wrong_pid", "wrong_class", "duplicate", "wrong_focus", "overlap", "overlay", "malformed"])
def test_unsafe_or_unknown_target_never_runs_grim(capture, problem: str) -> None:
    module, replies, runner = capture
    window = replies["clients"][1]
    if problem == "wrong_pid": window["pid"] = 999
    elif problem == "wrong_class": window["class"] = "firefox"
    elif problem == "duplicate": replies["clients"].append({**window, "address": "0x789"})
    elif problem == "wrong_focus": replies["activewindow"] = replies["clients"][0]
    elif problem == "overlap": replies["clients"][0]["at"] = [1010, 810]
    elif problem == "overlay": replies["layers"]["monitor"]["levels"]["3"] = [{"x":1010,"y":810,"w":40,"h":40}]
    elif problem == "malformed": del window["size"]
    assert module.capture_viewport(123, (10, 10, 80, 80), (100, 100), Mock()) is None
    runner.assert_not_called()


def test_window_change_during_capture_discards_image(capture) -> None:
    module, replies, runner = capture
    runner.side_effect = lambda *_a, **_kw: replies["clients"][1].update(at=[2000, 800])
    image = Mock()
    assert module.capture_viewport(123, (10, 10, 80, 80), (100, 100), image) is None
    image.assert_not_called()


def test_desktop_capture_requires_explicit_opt_in(view_module, monkeypatch) -> None:
    monkeypatch.delenv("FREECAD_MCP_ALLOW_SCREEN_CAPTURE", raising=False)
    assert view_module._grab_compositor_viewport("unused.png", 100, 100) is False


def test_framebuffer_uses_only_active_subwindow(view_module, monkeypatch) -> None:
    import sys
    active_gl = object()
    active_sub = types.SimpleNamespace(findChild=lambda _: active_gl)
    mdi = types.SimpleNamespace(activeSubWindow=lambda: active_sub, currentSubWindow=lambda: None)
    view_module.FreeCADGui.getMainWindow = lambda: types.SimpleNamespace(findChild=lambda _: mdi)
    monkeypatch.setitem(sys.modules, "PySide6", types.SimpleNamespace(
        QtOpenGLWidgets=types.SimpleNamespace(QOpenGLWidget=object),
        QtWidgets=types.SimpleNamespace(QMdiArea=object)))
    assert view_module._find_active_gl_widget() is active_gl
    active_sub.findChild = lambda _: None
    assert view_module._find_active_gl_widget() is None
