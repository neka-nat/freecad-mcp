"""A shared MCP client must not share an in-flight HTTP connection (#160)."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading
from typing import Any

import pytest

from freecad_mcp import server
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.server_state import ServerState
from test_rpc_concurrency import running_server


# Include all ordinary RPC operations, not just the create that exposed the race.
CALLS = [
    ("ping", ()),
    ("create_document", ("NewDoc",)),
    ("create_object", ("Doc", {"Name": "Hole", "Properties": {}})),
    ("edit_object", ("Doc", "Plate", {"Properties": {"Length": 25}})),
    ("delete_object", ("Doc", "Old")),
    ("reload_document", ("Doc",)),
    ("insert_part_from_library", ("part.FCStd",)),
    ("execute_code_async", ("pass",)),
    ("get_active_screenshot", ("Top", 800, 600, "Plate")),
    ("get_objects", ("Doc",)),
    ("get_object", ("Doc", "Plate")),
    ("get_parts_list", ()),
    ("list_documents", ()),
]


@pytest.mark.parametrize(("method", "args"), CALLS)
def test_operations_do_not_share_a_blocked_create_connection(
    method: str, args: tuple[Any, ...],
) -> None:
    entered, release = threading.Event(), threading.Event()
    received: list[tuple[str, tuple[Any, ...]]] = []

    class Interface:
        def _dispatch(self, name: str, params: tuple[Any, ...]) -> dict[str, Any]:
            received.append((name, params))
            if name == "create_object" and params[1]["Name"] == "Plate":
                entered.set()
                assert release.wait(5)
            return {"method": name, "args": list(params)}

    with running_server(Interface()) as (host, port):
        connection = FreeCADConnection(host, port, timeout=2)
        with ThreadPoolExecutor(max_workers=1) as workers:
            first = workers.submit(connection.create_object, "Doc", {"Name": "Plate"})
            try:
                assert entered.wait(2)
                result = getattr(connection, method)(*args)
                assert result == {"method": method, "args": list(args)}
                assert not first.done()
            finally:
                release.set()
                connection.disconnect()
            assert first.result(timeout=2) == {
                "method": "create_object", "args": ["Doc", {"Name": "Plate"}],
            }
    assert received == [("create_object", ("Doc", {"Name": "Plate"})), (method, args)]


def test_registered_tools_create_both_objects_and_preserve_nested_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # SDK 1 runs sync tools inline; SDK 2 runs them concurrently in threads.
    # The CI SDK matrix must exercise the registered tools, not only functions.
    import time

    created: dict[str, dict[str, Any]] = {}

    class Interface:
        def create_object(self, doc: str, data: dict[str, Any]) -> dict[str, Any]:
            created[data["Name"]] = data["Properties"]
            time.sleep(0.1)
            return {"success": True, "object_name": data["Name"]}

    with running_server(Interface()) as (host, port):
        connection = FreeCADConnection(host, port, timeout=2)
        monkeypatch.setattr(server, "state", ServerState(
            freecad_connection=connection, only_text_feedback=True,
        ))
        tool = server.mcp._tool_manager.get_tool("create_object")
        assert tool is not None
        properties = {"Placement": {"Base": {"x": 30, "y": 30, "z": -5}}}

        async def create(name: str) -> list[Any]:
            return await tool.run({
                "doc_name": "Doc", "obj_type": "Part::Box", "obj_name": name,
                "obj_properties": properties, "include_screenshot": False,
            }, context=None)

        async def run() -> list[Any]:
            return await asyncio.gather(create("Plate"), create("Hole"))

        try:
            replies = asyncio.run(run())
            assert [reply[0].text for reply in replies] == [
                "Object 'Plate' created successfully", "Object 'Hole' created successfully",
            ]
            assert created == {"Plate": properties, "Hole": properties}
        finally:
            connection.disconnect()
