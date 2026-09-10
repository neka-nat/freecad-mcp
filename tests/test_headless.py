import sys
from pathlib import Path

import pytest

import freecad_mcp.headless as headless

from freecad_mcp.headless import parse_command, run_headless
from freecad_mcp.operations.core import format_headless_result

PY = [sys.executable]  # stands in for freecadcmd: both accept `-c <code>`


@pytest.fixture(autouse=True)
def temporary_scripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(headless, "_script_dir", lambda: tmp_path)


def test_success_returns_output() -> None:
    res = run_headless("print('built'); print('  (50 %)')", 30, PY)
    assert res["success"] is True and res["returncode"] == 0
    assert res["output"] == "built"  # progress noise filtered
    text = format_headless_result(res)
    assert text.startswith("Headless FreeCAD script finished") and "reload_document" in text


def test_exception_reports_exit_code_and_traceback() -> None:
    res = run_headless("print('step 1')\nraise ValueError('Null shape')", 30, PY)
    assert res["success"] is False and res["returncode"] == 1
    assert "step 1" in res["output"] and "ValueError: Null shape" in res["output"]
    assert format_headless_result(res).startswith("Headless FreeCAD script FAILED: script failed (exit code 1)")


def test_native_crash_is_reported_not_propagated() -> None:
    if sys.platform == "win32":
        pytest.skip("POSIX signal exit status")
    res = run_headless("import os, resource, signal; resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); print('before', flush=True); os.kill(os.getpid(), signal.SIGSEGV)", 30, PY)
    assert res["success"] is False and res["crashed"] is True
    assert "SIGSEGV" in res["error"] and "GUI is unaffected" in res["error"]
    assert res["output"] == "before"


def test_timeout_kills_the_process() -> None:
    res = run_headless("import time; time.sleep(30)", 1, PY)
    assert res["success"] is False and res["timed_out"] is True
    assert "did not finish within 1 s" in res["error"]


@pytest.mark.parametrize(
    ("output_code", "expected"),
    [
        ("print('started', flush=True)", "started"),
        ("print('warning', file=sys.stderr, flush=True)", "warning"),
        ("print('started', flush=True); print('warning', file=sys.stderr, flush=True)", "started\nwarning"),
        ("sys.stdout.buffer.write(b'progress \\xe3\\x81'); sys.stdout.flush()", "progress \ufffd"),
    ],
)
def test_timeout_preserves_partial_output_and_removes_script(
    tmp_path: Path, output_code: str, expected: str,
) -> None:
    result = run_headless(f"import sys, time\n{output_code}\ntime.sleep(30)", 0.5, PY)
    assert result["success"] is False and result["timed_out"] is True
    assert result["output"] == expected
    assert "within 0.5 s" in result["error"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_never_launches_code(tmp_path: Path, timeout: float) -> None:
    result = run_headless("raise AssertionError('must not run')", timeout, PY)
    assert result["success"] is False
    assert "positive finite" in result["error"]
    assert list(tmp_path.iterdir()) == []


def test_start_failure_is_reported_and_removes_script(tmp_path: Path) -> None:
    result = run_headless("pass", 5, [str(tmp_path / "missing-freecadcmd")])
    assert result["success"] is False
    assert "could not start" in result["error"]
    assert list(tmp_path.iterdir()) == []


def test_snap_command_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(headless.shutil, "which", lambda name: "/snap/bin/freecad.cmd" if name == "freecad.cmd" else None)
    assert headless.detect_freecadcmd() == ["/snap/bin/freecad.cmd"]


def test_missing_command_is_a_clear_error(monkeypatch) -> None:
    import freecad_mcp.headless as h

    monkeypatch.setattr(h, "detect_freecadcmd", lambda: None)
    res = run_headless("print(1)", 5, None)
    assert res["success"] is False and "freecadcmd not found" in res["error"]


def test_parse_command() -> None:
    assert parse_command(None) is None
    assert parse_command("flatpak run --command=freecadcmd org.freecad.FreeCAD") == [
        "flatpak", "run", "--command=freecadcmd", "org.freecad.FreeCAD",
    ]
