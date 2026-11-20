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
        def get_rpc_status(self):
            from freecad_mcp.version import PROTOCOL_VERSION
            return {"protocol_version": PROTOCOL_VERSION}

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


@pytest.mark.parametrize("phase", ["ping", "version"])
def test_slow_admission_does_not_block_completed_tool_reply(
    monkeypatch: pytest.MonkeyPatch, phase: str,
) -> None:
    entered, release = threading.Event(), threading.Event()

    class Connection:
        def ping(self) -> bool:
            if phase == "ping":
                entered.set()
                assert release.wait(5)
            return True

        def check_addon_version(self) -> None:
            if phase == "version":
                entered.set()
                assert release.wait(5)

    monkeypatch.setattr(server, "state", ServerState())
    monkeypatch.setattr(server, "FreeCADConnection", lambda **_kw: Connection())
    monkeypatch.setattr(server, "execute_code_headless_operation", lambda *_args: [])
    with ThreadPoolExecutor(max_workers=2) as workers:
        admission = workers.submit(server.get_freecad_connection)
        try:
            assert entered.wait(2)
            reply = workers.submit(server.execute_code_headless, None, "pass")
            assert reply.result(timeout=1) == []
            assert not admission.done()
        finally:
            release.set()
        admission.result(timeout=2)


def test_status_tool_remains_available_during_version_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = threading.Event(), threading.Event()

    class Connection:
        def check_addon_version(self) -> None:
            entered.set()
            assert release.wait(5)

        def get_rpc_status(self) -> dict[str, Any]:
            from freecad_mcp.version import PROTOCOL_VERSION
            return {"protocol_version": PROTOCOL_VERSION, "rpc_server": "running"}

    connection = Connection()
    monkeypatch.setattr(server, "state", ServerState(freecad_connection=connection))
    with ThreadPoolExecutor(max_workers=2) as workers:
        admission = workers.submit(server.get_freecad_connection)
        try:
            assert entered.wait(2)
            reply = workers.submit(server.get_rpc_status, None).result(timeout=1)
            assert '"rpc_server": "running"' in reply[0].text
            assert not admission.done()
        finally:
            release.set()
        assert admission.result(timeout=2) is connection


def test_concurrent_initial_callers_publish_one_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered, release = threading.Event(), threading.Event()
    created: list[Any] = []

    class Connection:
        def __init__(self, **_kwargs: Any) -> None:
            created.append(self)

        def ping(self) -> bool:
            entered.set()
            assert release.wait(5)
            return True

        def check_addon_version(self) -> None:
            return None

    monkeypatch.setattr(server, "state", ServerState())
    monkeypatch.setattr(server, "FreeCADConnection", Connection)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(server.get_freecad_connection)
        try:
            assert entered.wait(2)
            second = workers.submit(server.get_freecad_connection)
        finally:
            release.set()
        assert first.result(timeout=2) is second.result(timeout=2)
    assert len(created) == 1


def test_status_has_reserved_capacity_when_normal_and_heavy_workers_are_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import anyio

    release = threading.Event()
    lock = threading.Lock()
    counts = {"normal": 0, "heavy": 0}

    def block(kind: str) -> list[Any]:
        with lock:
            counts[kind] += 1
        assert release.wait(10)
        return []

    class Connection:
        def check_addon_version(self) -> None:
            return None

        def list_documents(self) -> list[Any]:
            return block("normal")

        def get_rpc_status(self) -> dict[str, Any]:
            from freecad_mcp.version import PROTOCOL_VERSION
            return {"protocol_version": PROTOCOL_VERSION, "rpc_server": "running"}

    monkeypatch.setattr(server, "state", ServerState(freecad_connection=Connection()))
    monkeypatch.setattr(server, "execute_code_headless_operation", lambda *_a: block("heavy"))

    async def exercise() -> None:
        default = anyio.to_thread.current_default_thread_limiter()
        previous = default.total_tokens
        default.total_tokens = 2
        async def call(name: str, args: dict[str, Any]) -> Any:
            return await server.mcp._tool_manager.get_tool(name).run(args, context=None)
        try:
            async with anyio.create_task_group() as group:
                for _ in range(2):
                    group.start_soon(call, "list_documents", {})
                for _ in range(6):
                    group.start_soon(call, "execute_code_headless", {"code": "pass"})
                try:
                    with anyio.fail_after(3):
                        while counts["normal"] != 2 or counts["heavy"] < 4:
                            await anyio.sleep(.01)
                        reply = await call("get_rpc_status", {})
                    assert '"rpc_server": "running"' in reply[0].text
                    assert counts["heavy"] == 4  # Remaining heavy calls are queued.
                finally:
                    release.set()
        finally:
            default.total_tokens = previous

    anyio.run(exercise)
