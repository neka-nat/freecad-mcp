"""Stdout capture isolates threads and preserves the surrounding console."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
from pathlib import Path
import sys
import threading

import pytest


PATH = Path(__file__).resolve().parents[1] / "addon/FreeCADMCP/rpc_server/stdout_capture.py"
spec = importlib.util.spec_from_file_location("_stdout_capture_test", PATH)
assert spec is not None and spec.loader is not None
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


def test_overlapping_threads_capture_only_their_own_output(monkeypatch: pytest.MonkeyPatch) -> None:
    console = io.StringIO()
    monkeypatch.setattr(sys, "stdout", console)
    barrier = threading.Barrier(3)
    first_finished = threading.Event()

    def worker(label: str) -> str:
        output = io.StringIO()
        with capture.capture_stdout(output):
            barrier.wait(3)
            for _ in range(50):
                print(label, flush=True)
            barrier.wait(3)
            if label == "second":
                assert first_finished.wait(3)
                print(label)
        if label == "first":
            first_finished.set()
        return output.getvalue()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker, "first")
        second = pool.submit(worker, "second")
        barrier.wait(3)
        print("console only", flush=True)
        barrier.wait(3)
        assert first.result() == "first\n" * 50
        assert second.result() == "second\n" * 51
    assert sys.stdout is console
    assert console.getvalue() == "console only\n"


def test_nested_capture_restores_outer_target_after_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    console, outer, inner = io.StringIO(), io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", console)
    with capture.capture_stdout(outer):
        print("before")
        with pytest.raises(KeyboardInterrupt), capture.capture_stdout(inner):
            print("inner")
            raise KeyboardInterrupt
        print("after")
    print("console")
    assert outer.getvalue() == "before\nafter\n"
    assert inner.getvalue() == "inner\n"
    assert console.getvalue() == "console\n"
    assert sys.stdout is console


def test_capture_restores_none_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", None)
    output = io.StringIO()
    with capture.capture_stdout(output):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(print, "uncaptured", flush=True).result()
        print("captured")
    assert output.getvalue() == "captured\n"
    assert sys.stdout is None


def test_does_not_overwrite_a_replacement_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    console, replacement = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", console)
    with capture.capture_stdout(io.StringIO()):
        sys.stdout = replacement
    assert sys.stdout is replacement


def test_uncaptured_threads_keep_console_methods(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    path = tmp_path / "console.txt"
    with path.open("w", encoding="utf-8") as console:
        monkeypatch.setattr(sys, "stdout", console)
        output = io.StringIO()

        def background() -> tuple[str, int, bool]:
            sys.stdout.writelines(["console\n"])
            sys.stdout.flush()
            return sys.stdout.encoding, sys.stdout.fileno(), sys.stdout.isatty()

        with capture.capture_stdout(output):
            sys.stdout.writelines(["captured\n"])
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert pool.submit(background).result() == ("utf-8", console.fileno(), False)
        assert sys.stdout is console
        assert output.getvalue() == "captured\n"
    assert path.read_text() == "console\n"
