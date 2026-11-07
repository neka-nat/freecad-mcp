"""Fallback timers must not survive Stop or multiply after a restart."""

from collections.abc import Callable
import types

import pytest

from test_gui_dispatch import load_gui_dispatch


class PendingTimers:
    def __init__(self, dispatch: types.ModuleType) -> None:
        self.pending: list[Callable[[], None]] = []
        dispatch.QtCore.QTimer.singleShot = self.schedule

    def schedule(self, delay: int, callback: Callable[[], None]) -> None:
        assert delay == 500
        self.pending.append(callback)

    def tick(self) -> None:
        callbacks, self.pending = self.pending, []
        for callback in callbacks:
            callback()


def test_stop_kills_timer_when_immediate_wake_consumes_sentinel() -> None:
    with load_gui_dispatch() as dispatch:
        timers = PendingTimers(dispatch)
        dispatch.start_heartbeat()
        dispatch.request_shutdown()
        dispatch.process_gui_tasks()
        assert dispatch._rpc_request_queue.empty()
        timers.tick()
        assert timers.pending == []


def test_repeated_restarts_leave_one_chain_and_wakes_add_none() -> None:
    with load_gui_dispatch() as dispatch:
        timers = PendingTimers(dispatch)
        dispatch.start_heartbeat()
        for _ in range(20):
            dispatch.request_shutdown()
            dispatch.start_heartbeat()
        ran = []
        dispatch.post_to_gui(lambda: ran.append(True))
        timers.tick()
        assert ran == [True]  # old sentinels did not abandon the new queue
        for _ in range(3):
            dispatch._WakeSignal()._on_wake()
            assert len(timers.pending) == 1
            timers.tick()
            assert len(timers.pending) == 1
        dispatch.request_shutdown()
        timers.tick()
        assert not timers.pending


def test_stop_during_drain_does_not_reschedule_old_tick() -> None:
    with load_gui_dispatch() as dispatch:
        timers = PendingTimers(dispatch)
        dispatch.start_heartbeat()
        dispatch.post_to_gui(dispatch.request_shutdown)
        timers.tick()
        assert not timers.pending


def test_restart_during_drain_does_not_reschedule_old_generation() -> None:
    with load_gui_dispatch() as dispatch:
        timers = PendingTimers(dispatch)
        dispatch.start_heartbeat()

        def restart() -> None:
            dispatch.request_shutdown()
            dispatch.start_heartbeat()

        dispatch.post_to_gui(restart)
        timers.tick()
        assert len(timers.pending) == 1
        timers.tick()
        assert len(timers.pending) == 1


def test_unexpected_gui_failure_does_not_kill_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    with load_gui_dispatch() as dispatch:
        timers = PendingTimers(dispatch)
        ran = []
        dispatch.post_to_gui(lambda: ran.append(True))
        dispatch.start_heartbeat()

        def fail() -> int:
            raise RuntimeError("temporary GUI failure")

        with monkeypatch.context() as patch:
            patch.setattr(dispatch.QtWidgets.QApplication, "mouseButtons", fail)
            timers.tick()
        assert ran == []
        assert len(timers.pending) == 1
        timers.tick()
        assert ran == [True]
        assert len(timers.pending) == 1
