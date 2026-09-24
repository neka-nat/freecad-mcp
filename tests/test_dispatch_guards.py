"""Tick guards may delay GUI tasks, but must not wedge dispatch or hide why."""

import time

from test_gui_dispatch import FakeApplication, ThreadedWaker, load_gui_dispatch


class HeldMouse(FakeApplication):
    @staticmethod
    def mouseButtons() -> int:
        return 1


class PopupOpen(FakeApplication):
    @staticmethod
    def activePopupWidget() -> object:
        return object()


class ModalOpen(FakeApplication):
    @staticmethod
    def activeModalWidget() -> object:
        return object()


def test_mouse_guard_defers_a_drag_only_until_the_cap() -> None:
    with load_gui_dispatch() as gui_dispatch:
        cap = gui_dispatch.MOUSE_DEFER_MAX_S
        should_defer = gui_dispatch._mouse_guard_should_defer
        # 0.0 is a valid monotonic time and must arm the guard like any other.
        assert should_defer(True, 0.0) is True
        assert should_defer(True, cap - 0.1) is True
        assert should_defer(True, cap) is False
        assert should_defer(True, cap + 10) is False
        # A release ends the episode, so the next press is a new drag.
        assert should_defer(False, cap + 11) is False
        assert should_defer(True, cap + 12) is True


def test_stale_mouse_state_cannot_wedge_dispatch() -> None:
    with load_gui_dispatch() as gui_dispatch:
        warnings: list[str] = []
        gui_dispatch.FreeCAD.Console.PrintWarning = warnings.append
        gui_dispatch.QtWidgets.QApplication = HeldMouse
        ran: list[int] = []

        gui_dispatch._rpc_request_queue.put(lambda: ran.append(1))
        gui_dispatch.process_gui_tasks(reschedule=False)
        assert ran == []  # a fresh press is treated as a drag

        gui_dispatch._mouse_defer_since -= gui_dispatch.MOUSE_DEFER_MAX_S
        gui_dispatch.process_gui_tasks(reschedule=False)
        assert ran == [1]

        gui_dispatch._rpc_request_queue.put(lambda: ran.append(2))
        gui_dispatch.process_gui_tasks(reschedule=False)
        assert ran == [1, 2]
        assert len(warnings) == 1  # once per stuck-button episode


def test_queue_timeout_names_the_guard_that_held_the_call() -> None:
    with load_gui_dispatch() as gui_dispatch:
        gui_dispatch.QtWidgets.QApplication = ModalOpen
        waker = ThreadedWaker(gui_dispatch)
        gui_dispatch._waker = waker
        ran: list[bool] = []

        result = gui_dispatch.dispatch_to_gui(
            lambda: ran.append(True), timeout=0.2, operation_name="execute_code"
        )
        waker.join()

        assert result["success"] is False
        assert "waiting for 'execute_code' to start" in result["error"]
        assert "a modal dialog is open in FreeCAD" in result["error"]
        assert ran == []


def test_queue_timeout_ignores_a_guard_that_only_held_an_earlier_call() -> None:
    with load_gui_dispatch() as gui_dispatch:
        gui_dispatch.QtWidgets.QApplication = PopupOpen
        gui_dispatch._rpc_request_queue.put(lambda: None)
        gui_dispatch.process_gui_tasks(reschedule=False)
        time.sleep(0.01)  # the popup was seen strictly before the next call

        # No tick runs for this call (no waker), so nothing is known about
        # why it did not start; the earlier popup must not be blamed.
        result = gui_dispatch.dispatch_to_gui(
            lambda: None, timeout=0.05, operation_name="list_documents"
        )

        assert "waiting for 'list_documents' to start" in result["error"]
        assert "popup" not in result["error"]
