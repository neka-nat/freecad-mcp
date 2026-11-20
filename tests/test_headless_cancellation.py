"""Cancellation joins headless processes; MCP startup does not require GUI RPC."""
import subprocess
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest

from freecad_mcp import headless, server
from freecad_mcp.server_state import ServerState


def test_registered_headless_cancellation_kills_process_and_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, late_write = tmp_path / "started", tmp_path / "late-write"
    child = (
        f"from pathlib import Path; import time; Path({str(started)!r}).touch(); "
        f"time.sleep(1); Path({str(late_write)!r}).touch()"
    )
    code = f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', {child!r}]); time.sleep(30)"
    processes: list[subprocess.Popen[Any]] = []
    original = headless.subprocess.Popen

    def record(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
        proc = original(*args, **kwargs)
        processes.append(proc)
        return proc

    monkeypatch.setattr(headless.subprocess, "Popen", record)
    monkeypatch.setattr(headless, "_script_dir", lambda: tmp_path)
    monkeypatch.setattr(server, "state", ServerState(freecadcmd=[sys.executable]))

    async def exercise() -> None:
        done = anyio.Event()
        scopes: list[anyio.CancelScope] = []

        async def call() -> None:
            with anyio.CancelScope() as scope:
                scopes.append(scope)
                tool = server.mcp._tool_manager.get_tool("execute_code_headless")
                await tool.run({"code": code, "timeout": 30}, context=None)
            done.set()

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(call)
            try:
                with anyio.fail_after(5):
                    while not started.exists():
                        await anyio.sleep(.01)
                scopes[0].cancel()
                with anyio.fail_after(3):
                    await done.wait()
                assert processes and all(p.poll() is not None for p in processes)
                assert not list(tmp_path.glob("*.py"))
                await anyio.sleep(1.1)
                assert not late_write.exists(), "A descendant survived cancellation"
            finally:
                # Ensure a regression cannot leave a test process behind.
                for proc in processes:
                    if proc.poll() is None:
                        headless._terminate_process_tree(proc)

    anyio.run(exercise)


def test_lifespan_and_headless_tools_do_not_connect_to_gui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden() -> None:
        pytest.fail("Startup attempted GUI RPC")

    monkeypatch.setattr(server, "state", ServerState())
    monkeypatch.setattr(server, "get_freecad_connection", forbidden)
    monkeypatch.setattr(server, "execute_code_headless_operation", lambda *_args: [])

    async def exercise() -> None:
        with anyio.fail_after(1):
            async with server.server_lifespan(server.mcp):
                tool = server.mcp._tool_manager.get_tool("execute_code_headless")
                assert await tool.run({"code": "pass"}, context=None) == []

    anyio.run(exercise)
