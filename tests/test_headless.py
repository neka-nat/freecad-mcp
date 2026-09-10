import sys

from freecad_mcp.headless import parse_command, run_headless
from freecad_mcp.operations.core import format_headless_result

PY = [sys.executable]  # stands in for freecadcmd: both accept `-c <code>`


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
    res = run_headless("import os, signal; print('before', flush=True); os.kill(os.getpid(), signal.SIGSEGV)", 30, PY)
    assert res["success"] is False and res["crashed"] is True
    assert "SIGSEGV" in res["error"] and "GUI is unaffected" in res["error"]
    assert res["output"] == "before"


def test_timeout_kills_the_process() -> None:
    res = run_headless("import time; time.sleep(30)", 1, PY)
    assert res["success"] is False and res["timed_out"] is True
    assert "did not finish within 1 s" in res["error"]


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


def test_args_become_sys_argv() -> None:
    res = run_headless("import sys; print(sys.argv[1:])", 30, PY, args=["a.FCStd", "K,L", "1.5"])
    assert res["success"] and res["output"] == "['a.FCStd', 'K,L', '1.5']"


def test_run_file_resolves_bundled_scripts(tmp_path) -> None:
    from freecad_mcp.headless import SCRIPTS_DIR, run_headless_file

    assert (SCRIPTS_DIR / "dfm_check.py").exists() and (SCRIPTS_DIR / "collisions.py").exists()
    script = tmp_path / "gen.py"
    script.write_text("import sys; print('gen', sys.argv[1])")
    res = run_headless_file(script, 30, PY, ["v3"])
    assert res["success"] and res["output"] == "gen v3"
    assert run_headless_file("nope.py", 30, PY)["error"] == "script not found: nope.py"
