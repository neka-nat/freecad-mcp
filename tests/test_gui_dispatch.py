from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
import threading
import time
import types
from typing import Iterator


ADDON_DIR = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP"
GUI_DISPATCH_PATH = ADDON_DIR / "rpc_server" / "gui_dispatch.py"
if str(ADDON_DIR) not in sys.path:
    sys.path.insert(0, str(ADDON_DIR))


class FakeSignal:
    def __init__(self) -> None:
        self.callback = None

    def connect(self, callback, *_args) -> None:
        self.callback = callback

    def emit(self) -> None:
        if self.callback is not None:
            self.callback()


class FakeStatusBar:
    def showMessage(self, _message: str) -> None:
        pass

    def clearMessage(self) -> None:
        pass


class FakeApplication:
    @staticmethod
    def mouseButtons() -> int:
        return 0

    @staticmethod
    def activePopupWidget() -> None:
        return None

    @staticmethod
    def activeModalWidget() -> None:
        return None

    @staticmethod
    def instance() -> "FakeApplication":
        return FakeApplication()

    def setOverrideCursor(self, _cursor) -> None:
        pass

    def restoreOverrideCursor(self) -> None:
        pass


@contextmanager
def load_gui_dispatch() -> Iterator[types.ModuleType]:
    module_names = ["FreeCAD", "FreeCADGui", "PySide"]
    missing = object()
    saved = {name: sys.modules.get(name, missing) for name in module_names}

    freecad = types.ModuleType("FreeCAD")
    freecad.Console = types.SimpleNamespace(PrintError=lambda _message: None)

    status_bar = FakeStatusBar()
    freecad_gui = types.ModuleType("FreeCADGui")
    freecad_gui.updateGui = lambda: None
    freecad_gui.getMainWindow = lambda: types.SimpleNamespace(
        statusBar=lambda: status_bar
    )

    qt_core = types.SimpleNamespace(
        QObject=object,
        Signal=FakeSignal,
        Qt=types.SimpleNamespace(
            QueuedConnection=0,
            NoButton=0,
            WaitCursor=0,
        ),
        QEventLoop=types.SimpleNamespace(
            ExcludeUserInputEvents=1,
            ExcludeSocketNotifiers=2,
        ),
        QThread=types.SimpleNamespace(msleep=lambda _delay: None),
        QTimer=types.SimpleNamespace(singleShot=lambda _delay, _callback: None),
    )
    qt_widgets = types.SimpleNamespace(QApplication=FakeApplication)
    pyside = types.ModuleType("PySide")
    pyside.QtCore = qt_core
    pyside.QtWidgets = qt_widgets

    sys.modules["FreeCAD"] = freecad
    sys.modules["FreeCADGui"] = freecad_gui
    sys.modules["PySide"] = pyside

    module_name = f"_gui_dispatch_test_{time.monotonic_ns()}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, GUI_DISPATCH_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load gui_dispatch from {GUI_DISPATCH_PATH}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(module_name, None)
        for name, value in saved.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class ThreadedWaker:
    def __init__(self, gui_dispatch: types.ModuleType):
        self.gui_dispatch = gui_dispatch
        self.threads: list[threading.Thread] = []

    def wake(self) -> None:
        thread = threading.Thread(
            target=lambda: self.gui_dispatch.process_gui_tasks(reschedule=False),
            daemon=True,
        )
        self.threads.append(thread)
        thread.start()

    def join(self) -> None:
        for thread in self.threads:
            thread.join(timeout=1.0)


def test_running_timeout_blocks_followups_until_task_finishes() -> None:
    with load_gui_dispatch() as gui_dispatch:
        waker = ThreadedWaker(gui_dispatch)
        gui_dispatch._waker = waker
        started = threading.Event()
        release = threading.Event()

        def blocked_task() -> bool:
            started.set()
            release.wait(timeout=1.0)
            return True

        first = gui_dispatch.dispatch_to_gui(
            blocked_task,
            timeout=0.05,
            operation_name="remove_broken_feature",
        )
        assert started.is_set()
        assert first["code"] == "GUI_DISPATCH_STUCK"

        before = time.monotonic()
        second = gui_dispatch.dispatch_to_gui(
            lambda: True,
            timeout=1.0,
            operation_name="list_documents",
        )
        elapsed = time.monotonic() - before

        assert second["code"] == "GUI_DISPATCH_STUCK"
        assert elapsed < 0.1
        assert gui_dispatch.get_dispatch_status()["state"] == "stuck"

        release.set()
        waker.join()
        assert gui_dispatch.get_dispatch_status()["state"] == "healthy"

        third = gui_dispatch.dispatch_to_gui(
            lambda: "recovered",
            timeout=0.5,
            operation_name="recovered_call",
        )
        waker.join()

        assert third == "recovered"


def test_queued_timeout_cancels_task_without_marking_dispatch_stuck() -> None:
    with load_gui_dispatch() as gui_dispatch:
        ran = threading.Event()

        result = gui_dispatch.dispatch_to_gui(
            lambda: ran.set(),
            timeout=0.01,
            operation_name="stale_call",
        )
        gui_dispatch.process_gui_tasks(reschedule=False)

        assert result["success"] is False
        assert "code" not in result
        assert not ran.is_set()
        assert gui_dispatch.get_dispatch_status()["state"] == "healthy"
