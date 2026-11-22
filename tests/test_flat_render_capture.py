"""A real render with few colors must not be swapped for a blank framebuffer grab."""

from pathlib import Path
import sys
import types
from typing import Callable
from unittest.mock import Mock

import pytest

from test_displayed_view import view_module  # noqa: F401  (pytest fixture)


BACKGROUND = 0xFF202020
FLOOR = 0xFFD0D0D0
WALL = 0xFF1A1A1A


class _FakeImage:
    """Enough of QImage for the capture path: pixels to sample, and save() writes a payload."""

    def __init__(self, pixel: Callable[[int, int], int], payload: bytes = b"") -> None:
        self._pixel, self.payload = pixel, payload

    def isNull(self) -> bool:
        return False

    def width(self) -> int:
        return 640

    def height(self) -> int:
        return 330

    def pixel(self, x: int, y: int) -> int:
        return self._pixel(x, y)

    def scaled(self, *_args: object) -> "_FakeImage":
        return self

    def save(self, path: str, _fmt: str) -> bool:
        Path(path).write_bytes(self.payload)
        return True


def _blank_pixel(_x: int, _y: int) -> int:
    return BACKGROUND


def _plan_view_pixel(x: int, y: int) -> int:
    """A flat-shaded top-down floor plan: rooms on a dark background, walls as dark lines."""
    if not (40 <= x < 600 and 100 <= y < 230):
        return BACKGROUND
    if (x - 40) % 80 < 3 or (y - 100) % 65 < 3:
        return WALL
    return FLOOR


@pytest.fixture
def fake_images(monkeypatch: pytest.MonkeyPatch) -> dict[str, _FakeImage]:
    """Stand in for PySide6: QImage(path) returns the image stored under path."""
    store: dict[str, _FakeImage] = {}
    qt = types.SimpleNamespace(KeepAspectRatio=1, SmoothTransformation=1)
    modules = {
        "QtGui": types.SimpleNamespace(QImage=lambda path: store[path]),
        "QtCore": types.SimpleNamespace(Qt=qt),
        "QtWidgets": types.SimpleNamespace(QMdiArea=object()),
        "QtOpenGLWidgets": types.SimpleNamespace(QOpenGLWidget=object()),
    }
    monkeypatch.setitem(sys.modules, "PySide6", types.SimpleNamespace(**modules))
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, f"PySide6.{name}", module)
    return store


def test_blank_capture_is_flat(view_module: types.ModuleType, fake_images: dict) -> None:
    fake_images["blank.png"] = _FakeImage(_blank_pixel)
    assert view_module._image_is_flat_color("blank.png")


def test_speckled_blank_capture_is_flat(view_module: types.ModuleType, fake_images: dict) -> None:
    fake_images["speckled.png"] = _FakeImage(lambda x, y: WALL if (x, y) == (0, 0) else BACKGROUND)
    assert view_module._image_is_flat_color("speckled.png")


def test_flat_shaded_plan_view_is_not_flat(view_module: types.ModuleType, fake_images: dict) -> None:
    fake_images["plan.png"] = _FakeImage(_plan_view_pixel)
    assert not view_module._image_is_flat_color("plan.png")


class _ShownView:
    """The displayed 3D view: its offscreen render writes a known payload."""

    def viewTop(self) -> None:
        pass

    def fitAll(self) -> None:
        pass

    def getSize(self) -> tuple[int, int]:
        return 800, 600

    def saveImage(self, path: str, *_args: object) -> None:
        Path(path).write_bytes(b"RENDER")


def _capture(
    view_module: types.ModuleType,
    fake_images: dict,
    monkeypatch: pytest.MonkeyPatch,
    target: Path,
    render: _FakeImage,
    framebuffer: _FakeImage,
) -> bytes:
    """Run save_active_screenshot with the given offscreen render and live framebuffer."""
    monkeypatch.delenv("FREECAD_MCP_ALLOW_SCREEN_CAPTURE", raising=False)
    gl = Mock()
    gl.grabFramebuffer.return_value = framebuffer
    mdi = Mock()
    mdi.activeSubWindow.return_value.findChild.return_value = gl
    window = Mock()
    window.findChild.return_value = mdi
    gui = view_module.FreeCADGui
    gui.activeView.return_value = _ShownView()
    gui.getMainWindow = lambda: window
    view_module.FreeCAD.Console.PrintLog = Mock()
    fake_images[str(target)] = render

    assert view_module.save_active_screenshot(str(target), view_name="Top") is True
    return target.read_bytes()


def test_plan_view_render_is_kept(
    view_module: types.ModuleType, fake_images: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    shot = _capture(view_module, fake_images, monkeypatch, tmp_path / "shot.png",
                    render=_FakeImage(_plan_view_pixel), framebuffer=_FakeImage(_blank_pixel, b"BLANK"))
    assert shot == b"RENDER"


def test_blank_framebuffer_grab_never_replaces_the_render(
    view_module: types.ModuleType, fake_images: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    shot = _capture(view_module, fake_images, monkeypatch, tmp_path / "shot.png",
                    render=_FakeImage(_blank_pixel), framebuffer=_FakeImage(_blank_pixel, b"BLANK"))
    assert shot == b"RENDER"


def test_framebuffer_grab_replaces_a_blank_render(
    view_module: types.ModuleType, fake_images: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    shot = _capture(view_module, fake_images, monkeypatch, tmp_path / "shot.png",
                    render=_FakeImage(_blank_pixel), framebuffer=_FakeImage(_plan_view_pixel, b"GRAB"))
    assert shot == b"GRAB"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["shot.png"]
