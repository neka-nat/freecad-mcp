from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import sys
import threading
import types
from xmlrpc.client import Fault

import pytest

from test_gui_dispatch import load_gui_dispatch, ThreadedWaker
from test_rpc_concurrency import client, running_server


RPC_PATH = (
    Path(__file__).resolve().parents[1]
    / "addon" / "FreeCADMCP" / "rpc_server" / "rpc_server.py"
)


@pytest.fixture
def rpc_module(monkeypatch: pytest.MonkeyPatch) -> Iterator[types.ModuleType]:
    """Exercise real RPC handlers and dispatch with only FreeCAD/Qt stubbed."""
    with load_gui_dispatch() as dispatch:
        freecad = dispatch.FreeCAD
        freecad.Console.PrintMessage = lambda _message: None
        freecad.Console.PrintWarning = lambda _message: None
        document = types.SimpleNamespace(
            Objects=[types.SimpleNamespace(Name="Box")],
            getObject=lambda name: types.SimpleNamespace(Name=name) if name == "Box" else None,
        )

        def get_document(name: str) -> object:
            if name != "Doc":
                raise NameError(name)
            return document

        freecad.getDocument = get_document
        freecad.listDocuments = lambda: {"Doc": document}
        stubs = {
            "gui_dispatch": dispatch,
            "commands": types.SimpleNamespace(
                register_commands=lambda: None, schedule_toggle_sync=lambda: None
            ),
            "fem_executor": types.SimpleNamespace(run_fem_analysis=lambda *_args: None),
            "object_factory": types.SimpleNamespace(
                create_object_gui=lambda *_args: None, edit_object_gui=lambda *_args: None
            ),
            "property_mapper": types.SimpleNamespace(Object=object),
            "parts_library": types.SimpleNamespace(
                get_parts_list=lambda: [], insert_part_from_library=lambda _path: None
            ),
            "serialize": types.SimpleNamespace(serialize_object=lambda obj: {"Name": obj.Name}),
            "settings": types.SimpleNamespace(load_settings=lambda: {}, save_settings=lambda _: None),
            "view_manager": types.SimpleNamespace(save_active_screenshot=lambda *_args: True),
        }
        with monkeypatch.context() as patch:
            for name, stub in stubs.items():
                patch.setitem(sys.modules, f"rpc_server.{name}", stub)
            spec = importlib.util.spec_from_file_location("_rpc_handler_test", RPC_PATH)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            waker = ThreadedWaker(dispatch)
            dispatch._waker = waker
            module.test_dispatch = dispatch
            try:
                yield module
            finally:
                waker.join()


def test_script_names_cannot_replace_rpc_internals(rpc_module: types.ModuleType) -> None:
    rpc = rpc_module.FreeCADRPC()
    original_dispatch = rpc_module.dispatch_to_gui
    original_serializer = rpc_module.serialize_object
    result = rpc.execute_code(
        "dispatch_to_gui = None\nserialize_object = None\n"
        "FreeCAD = None\nFreeCADGui = None\nshared_value = 41"
    )
    assert result["success"] is True
    assert rpc_module.dispatch_to_gui is original_dispatch
    assert rpc_module.serialize_object is original_serializer
    result = rpc.execute_code("print(shared_value + 1)")
    assert result["success"] is True
    assert result["message"].endswith("42\n")
    assert rpc.get_object("Doc", "Box") == {"Name": "Box"}


def test_async_scripts_share_variables_without_replacing_dispatch(
    rpc_module: types.ModuleType,
) -> None:
    rpc = rpc_module.FreeCADRPC()
    original_dispatch = rpc_module.dispatch_to_gui
    done = threading.Event()
    rpc_module.FreeCAD.async_done = done
    assert rpc.execute_code("shared_value = 40")["success"] is True
    assert rpc.execute_code_async(
        "dispatch_to_gui = None\nshared_value += 2\nFreeCAD.async_done.set()"
    )["success"] is True
    assert done.wait(2)
    assert rpc_module.dispatch_to_gui is original_dispatch
    result = rpc.execute_code(
        "assert App is FreeCAD\nassert Gui is FreeCADGui\nprint(shared_value)"
    )
    assert result["success"] is True
    assert result["message"].endswith("42\n")


@pytest.mark.parametrize(
    ("method", "args", "expected"),
    [
        ("list_documents", (), ["Doc"]),
        ("get_objects", ("Doc",), [{"Name": "Box"}]),
        ("get_objects", ("Missing",), []),
        ("get_object", ("Doc", "Box"), {"Name": "Box"}),
        ("get_object", ("Doc", "Missing"), None),
        ("get_object", ("Missing", "Box"), None),
    ],
)
def test_queries_use_gui_dispatch_and_keep_response_shapes(
    rpc_module: types.ModuleType, method: str, args: tuple, expected: object,
) -> None:
    dispatched: list[str] = []
    rpc = rpc_module.FreeCADRPC()
    original_dispatch = rpc_module.dispatch_to_gui

    def dispatch(task, **kwargs):
        dispatched.append(kwargs["operation_name"])
        return original_dispatch(task, **kwargs)

    rpc_module.dispatch_to_gui = dispatch
    assert getattr(rpc, method)(*args) == expected
    assert dispatched == [method]


@pytest.mark.parametrize(
    ("method", "args"),
    [("list_documents", ()), ("get_objects", ("Doc",)), ("get_object", ("Doc", "Box"))],
)
def test_queries_fail_without_touching_a_wedged_document(
    rpc_module: types.ModuleType, method: str, args: tuple,
) -> None:
    health = rpc_module.test_dispatch._dispatch_health
    health.start(100, "execute_code")
    health.mark_timed_out(100, 90)

    def unexpected_read(*_args):
        pytest.fail("Document was read while GUI dispatch was stuck")

    rpc_module.FreeCAD.getDocument = unexpected_read
    rpc_module.FreeCAD.listDocuments = unexpected_read
    with pytest.raises(Fault, match="GUI_DISPATCH_STUCK.*execute_code"):
        getattr(rpc_module.FreeCADRPC(), method)(*args)


def test_status_and_document_reads_during_real_dispatch(
    rpc_module: types.ModuleType,
) -> None:
    rpc = rpc_module.FreeCADRPC()
    rpc.EXECUTE_CODE_TIMEOUT = 0.5
    entered, release, read = threading.Event(), threading.Event(), threading.Event()
    rpc_module.FreeCAD.test_entered = entered
    rpc_module.FreeCAD.test_release = release
    rpc_module.FreeCAD.listDocuments = lambda: (read.set() or {"Doc": object()})
    with running_server(rpc) as (host, port), ThreadPoolExecutor(max_workers=2) as workers:
        def request(method: str, *args):
            with client(host, port, 5) as proxy:
                return getattr(proxy, method)(*args)

        execution = workers.submit(
            request, "execute_code",
            "FreeCAD.test_entered.set()\nFreeCAD.test_release.wait(5)",
        )
        try:
            assert entered.wait(2)
            status = request("get_rpc_status")
            assert status["gui_dispatch"]["state"] == "busy"
            assert status["gui_dispatch"]["operation"] == "execute_code"
            query = workers.submit(request, "list_documents")
            # The query must not inspect document state until execution ends.
            assert not read.wait(0.1)
            assert execution.result(timeout=2)["code"] == "GUI_DISPATCH_STUCK"
            assert request("get_rpc_status")["gui_dispatch"]["state"] == "stuck"
            with pytest.raises(Fault, match="GUI_DISPATCH_STUCK"):
                request("get_objects", "Doc")
            release.set()
            assert query.result(timeout=2) == ["Doc"]
            assert read.is_set()
            assert request("get_rpc_status")["gui_dispatch"]["state"] == "healthy"
            assert request("get_object", "Doc", "Box") == {"Name": "Box"}
        finally:
            release.set()
