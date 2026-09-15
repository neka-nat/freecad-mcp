"""Run a FreeCAD script in a separate ``freecadcmd`` process.

Heavy OCCT work (helical sweeps, lofts, many-tool booleans) can segfault
OpenCascade. Inside the GUI process that kills FreeCAD together with every
unsaved document; here it only kills the helper process, and the caller gets
the exit status and the script's output back.
"""

import logging
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("FreeCADMCPserver")

FLATPAK_APP = "org.freecad.FreeCAD"
_NOISE = ("%)", "Importing project files", "Postprocessing", "FreeCAD 1.", "(C) 2001", "LGPL")


def detect_freecadcmd() -> list[str] | None:
    """Find a headless FreeCAD executable: PATH first, then the Flatpak."""
    for name in ("freecadcmd", "FreeCADCmd", "freecadcmd.exe", "freecad.cmd"):
        path = shutil.which(name)
        if path:
            return [path]
    flatpak = shutil.which("flatpak")
    if flatpak:
        try:
            probe = subprocess.run(
                [flatpak, "info", FLATPAK_APP], capture_output=True, timeout=30
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if probe.returncode == 0:
            return [flatpak, "run", f"--command=freecadcmd", FLATPAK_APP]
    return None


def parse_command(value: str | None) -> list[str] | None:
    return shlex.split(value) if value else None


def _script_dir() -> Path:
    # Flatpak sandboxes usually see $HOME but not /tmp, so keep scripts under HOME.
    d = Path.home() / ".cache" / "freecad-mcp" / "headless"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clean(output: str | bytes | None) -> str:
    # TimeoutExpired retains captured bytes even when run(text=True) is used.
    # A timeout can also cut a multibyte character in half.
    if output is None:
        return ""
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="replace")
    lines = [ln for ln in output.splitlines() if ln.strip() and not any(n in ln for n in _NOISE)]
    return "\n".join(lines)


def run_headless(code: str, timeout: float, command: list[str] | None) -> dict[str, Any]:
    """Execute ``code`` with ``command -c "exec(open(script).read())"``.

    Returns ``success``, ``returncode``, ``output`` (stdout+stderr, noise
    filtered), and flags ``crashed`` (killed by a signal) / ``timed_out``.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        return {"success": False, "error": "timeout must be a positive finite number"}
    command = command or detect_freecadcmd()
    if not command:
        return {
            "success": False,
            "error": "freecadcmd not found: install FreeCAD, or pass --freecadcmd to freecad-mcp",
        }
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", dir=_script_dir(), delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        script = f.name
    argv = command + ["-c", f"exec(open({script!r}, encoding='utf-8').read())"]
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        out = "\n".join(part for part in (_clean(e.stdout), _clean(e.stderr)) if part)
        return {
            "success": False,
            "timed_out": True,
            "error": f"headless FreeCAD did not finish within {timeout:g} s",
            "output": out,
        }
    except OSError as e:
        return {"success": False, "error": f"could not start headless FreeCAD: {e}"}
    finally:
        try:
            os.unlink(script)
        except OSError:
            pass
    output = _clean(proc.stdout + "\n" + proc.stderr)
    result: dict[str, Any] = {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "output": output,
    }
    if proc.returncode < 0:
        sig = -proc.returncode
        try:
            name = signal.Signals(sig).name
        except ValueError:
            name = str(sig)
        result["crashed"] = True
        result["error"] = f"headless FreeCAD crashed with {name} (OCCT native crash; the GUI is unaffected)"
    elif proc.returncode != 0:
        # FreeCAD's own signal handler can print a native backtrace and exit 1,
        # hiding the signal from the OS exit status. Label this as a report
        # from FreeCAD, distinct from an OS-observed negative return code.
        crash = re.search(r"(?m)^Program received signal (SIG[A-Z0-9]+),", output)
        if crash:
            result["crashed"] = True
            result["error"] = (
                f"headless FreeCAD reported a crash with {crash.group(1)} "
                f"(exit code {proc.returncode}; the GUI is unaffected)"
            )
        else:
            result["error"] = f"script failed (exit code {proc.returncode})"
    return result
