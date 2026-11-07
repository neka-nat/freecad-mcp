"""Opt-in native FreeCAD checks, also run by the Windows CI job."""

import asyncio
import json
import os
from pathlib import Path
import sys

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from freecad_mcp.headless import run_headless

COMMAND = json.loads(os.environ.get("FREECAD_TEST_COMMAND", "null"))
pytestmark = pytest.mark.skipif(COMMAND is None, reason="set FREECAD_TEST_COMMAND to a JSON argv")


def test_native_headless_through_an_open_stdio_session() -> None:
    async def exercise() -> None:
        # A real MCP pipe remains open while FreeCADCmd runs, as in #179.
        script = (
            "from freecad_mcp import server; "
            f"server.state.freecadcmd = {COMMAND!r}; server.mcp.run()"
        )
        params = StdioServerParameters(command=sys.executable, args=["-c", script], env=dict(os.environ))
        with anyio.fail_after(90):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    reply = await session.call_tool("execute_code_headless", {
                        "code": "import FreeCAD, Part; print('VOLUME', Part.makeCylinder(5, 10).Volume)",
                        "timeout": 30,
                    })
                    assert not reply.isError, reply
                    assert "785.398" in str(reply), reply
    asyncio.run(exercise())


def test_native_headless_preserves_partial_output() -> None:
    reply = run_headless("print('BEFORE_FAILURE'); raise ValueError('native test')", 30, COMMAND)
    assert not reply["success"], reply
    assert "BEFORE_FAILURE" in reply["output"] and "ValueError" in reply["output"]


def test_native_fem_repeated_solve_and_atomic_creation() -> None:
    ccx = os.environ.get("FREECAD_TEST_CCX")
    if not ccx:
        pytest.skip("set FREECAD_TEST_CCX to the CalculiX executable")
    root = Path(__file__).resolve().parents[1]
    scenario = root / "tests/native/fem_scenario.py"
    code = (
        f"import runpy; runpy.run_path({str(scenario)!r}, init_globals="
        f"{{'ADDON_PATH': {str(root / 'addon/FreeCADMCP')!r}, 'CCX_PATH': {ccx!r}}})"
    )
    reply = run_headless(code, 120, COMMAND)
    assert reply["success"], reply
    assert "NATIVE_FEM_OK" in reply["output"], reply
