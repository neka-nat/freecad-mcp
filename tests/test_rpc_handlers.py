from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import sys
import threading
import time
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
            # Real module; must re-import so it binds this test's FreeCAD stub.
            # ``from rpc_server import shape_check`` reuses the package attribute
            # when present, so the attribute has to go along with the module.
            patch.delitem(sys.modules, "rpc_server.shape_check", raising=False)
            if "rpc_server" in sys.modules:
                patch.delattr(sys.modules["rpc_server"], "shape_check", raising=False)
            spec = importlib.util.spec_from_file_location("_rpc_handler_test", RPC_PATH)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            waker = ThreadedWaker(dispatch)
            dispatch._waker = waker
            module.test_dispatch = dispatch
            async_threads: list[threading.Thread] = []

            def worker_thread(*args, **kwargs) -> threading.Thread:
                thread = threading.Thread(*args, **kwargs)
                async_threads.append(thread)
                return thread

            module.threading = types.SimpleNamespace(Thread=worker_thread)
            try:
                yield module
            finally:
                for thread in async_threads:
                    thread.join(timeout=2)
                    assert not thread.is_alive()
                waker.join()


def test_execute_code_failure_reports_script_line_and_partial_output(
    rpc_module: types.ModuleType,
) -> None:
    rpc = rpc_module.FreeCADRPC()
    rpc_module.FreeCAD.Console.PrintError = lambda _message: None
    result = rpc.execute_code(
        "print('step 1 ok')\n"
        "value = 41\n"
        "raise ValueError('Null shape')\n"
        "print('never')"
    )
    assert result["success"] is False
    assert result["error"] == "ValueError: Null shape"
    assert result["traceback"] == "Script line 3: raise ValueError('Null shape')"
    assert result["output"] == "step 1 ok\n"


def test_execute_code_failure_inside_function_names_the_frame(
    rpc_module: types.ModuleType,
) -> None:
    rpc = rpc_module.FreeCADRPC()
    rpc_module.FreeCAD.Console.PrintError = lambda _message: None
    result = rpc.execute_code("def f():\n    return 1 / 0\nf()")
    assert result["success"] is False
    assert result["error"].startswith("ZeroDivisionError")
    assert result["traceback"] == "Script line 3: f()\nScript line 2 in f: return 1 / 0"


def test_execute_code_syntax_error_points_at_line(rpc_module: types.ModuleType) -> None:
    rpc = rpc_module.FreeCADRPC()
    rpc_module.FreeCAD.Console.PrintError = lambda _message: None
    result = rpc.execute_code("x = 1\ny = (\n")
    assert result["success"] is False
    assert result["error"].startswith("SyntaxError")
    assert result["traceback"].startswith("Script line ")


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


def test_async_commit_runs_document_writes_on_the_gui_thread(
    rpc_module: types.ModuleType,
) -> None:
    """Document writes must land on the GUI thread, not the worker thread."""
    rpc = rpc_module.FreeCADRPC()
    done = threading.Event()
    rpc_module.FreeCAD.async_done = done
    rpc_module.FreeCAD.test_threads = {}
    assert rpc.execute_code_async(
        "import threading\n"
        "FreeCAD.test_threads['worker'] = threading.current_thread().name\n"
        "def apply():\n"
        "    FreeCAD.test_threads['commit'] = threading.current_thread().name\n"
        "    return 'applied'\n"
        "FreeCAD.test_threads['result'] = commit(apply)\n"
        "FreeCAD.async_done.set()"
    )["success"] is True
    assert done.wait(2)
    threads = rpc_module.FreeCAD.test_threads
    assert threads["result"] == "applied"
    # The worker runs off-thread; commit hands the write to the dispatch thread.
    assert threads["commit"] != threads["worker"]


def test_async_commit_reports_dispatch_failure_to_the_script(
    rpc_module: types.ModuleType,
) -> None:
    """A wedged GUI thread surfaces as a RuntimeError instead of a silent write."""
    rpc = rpc_module.FreeCADRPC()
    health = rpc_module.test_dispatch._dispatch_health
    health.start(200, "execute_code")
    health.mark_timed_out(200, 90)
    done = threading.Event()
    rpc_module.FreeCAD.async_done = done
    rpc_module.FreeCAD.test_error = None
    assert rpc.execute_code_async(
        "try:\n"
        "    commit(lambda: 'never runs')\n"
        "except RuntimeError as exc:\n"
        "    FreeCAD.test_error = str(exc)\n"
        "FreeCAD.async_done.set()"
    )["success"] is True
    assert done.wait(2)
    error = rpc_module.FreeCAD.test_error
    assert error is not None and "commit() failed" in error
    assert "'execute_code' timed out" in error


def test_saved_functions_can_commit_in_later_async_scripts(
    rpc_module: types.ModuleType,
) -> None:
    rpc = rpc_module.FreeCADRPC()
    done = threading.Event()
    rpc_module.FreeCAD.async_done = done
    assert rpc.execute_code_async(
        "shared_value = 7\n"
        "def apply_later():\n"
        "    return commit(lambda: shared_value)\n"
        "FreeCAD.async_done.set()"
    )["success"] is True
    assert done.wait(2)
    assert rpc.execute_code("shared_value = 99")["success"] is True
    done.clear()
    assert rpc.execute_code_async(
        "FreeCAD.test_result = apply_later()\nFreeCAD.async_done.set()"
    )["success"] is True
    assert done.wait(2)
    assert rpc_module.FreeCAD.test_result == 99


def test_async_completion_preserves_concurrent_writes_and_deletions(
    rpc_module: types.ModuleType,
) -> None:
    rpc = rpc_module.FreeCADRPC()
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    rpc_module.FreeCAD.test_entered = entered
    rpc_module.FreeCAD.test_release = release
    rpc_module.FreeCAD.Console.PrintMessage = (
        lambda message: done.set() if message == "Async code execution completed.\n" else None
    )
    assert rpc.execute_code("shared_value = 1\nobsolete = True")["success"] is True
    assert rpc.execute_code_async(
        "FreeCAD.test_entered.set()\nFreeCAD.test_release.wait(2)\n"
        "del obsolete\nasync_value = 42"
    )["success"] is True
    try:
        assert entered.wait(2)
        assert rpc.execute_code("shared_value = 99")["success"] is True
    finally:
        release.set()
    assert done.wait(2)
    result = rpc.execute_code(
        "assert shared_value == 99\nassert 'obsolete' not in globals()\nassert async_value == 42"
    )
    assert result["success"] is True, result


def test_async_exception_preserves_completed_assignments(
    rpc_module: types.ModuleType,
) -> None:
    done = threading.Event()
    rpc_module.FreeCAD.Console.PrintError = lambda _message: done.set()
    rpc = rpc_module.FreeCADRPC()
    assert rpc.execute_code_async("partial_result = 42\nraise ValueError('failed')")["success"]
    assert done.wait(2)
    assert rpc.execute_code("print(partial_result)")["message"].endswith("42\n")


@pytest.mark.parametrize("code", ["commit(lambda: 7)", "commit(lambda: commit(lambda: 7))"])
def test_commit_rejects_gui_thread_use_without_dispatching(
    rpc_module: types.ModuleType, code: str,
) -> None:
    rpc = rpc_module.FreeCADRPC()
    if code == "commit(lambda: 7)":
        # Synchronous scripts already run on the GUI thread.
        result = rpc.execute_code(code)
        assert result["success"] is False
        assert "only available inside execute_code_async" in result["error"]
    else:
        done = threading.Event()
        errors: list[str] = []
        rpc_module.FreeCAD.Console.PrintError = lambda message: (errors.append(message), done.set())
        assert rpc.execute_code_async(code)["success"]
        assert done.wait(2)
        assert any("only available inside execute_code_async" in error for error in errors)


@pytest.mark.parametrize("value", [None, "error-looking text", {"success": False, "error": "data"}])
def test_commit_preserves_callback_return_values(
    rpc_module: types.ModuleType, value: object,
) -> None:
    done = threading.Event()
    rpc_module.FreeCAD.test_value = value
    rpc_module.FreeCAD.async_done = done
    assert rpc_module.FreeCADRPC().execute_code_async(
        "FreeCAD.test_result = commit(lambda: FreeCAD.test_value)\nFreeCAD.async_done.set()"
    )["success"]
    assert done.wait(2)
    assert rpc_module.FreeCAD.test_result == value


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
    entered, release = threading.Event(), threading.Event()
    reads: list[float] = []  # execute_code's own shape snapshot reads before the script runs
    rpc_module.FreeCAD.test_entered = entered
    rpc_module.FreeCAD.test_release = release
    rpc_module.FreeCAD.listDocuments = lambda: (reads.append(time.monotonic()) or {"Doc": object()})
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
            reads_before_query = len(reads)
            query = workers.submit(request, "list_documents")
            # The query must not inspect document state until execution ends.
            time.sleep(0.1)
            assert len(reads) == reads_before_query
            assert execution.result(timeout=2)["code"] == "GUI_DISPATCH_STUCK"
            assert request("get_rpc_status")["gui_dispatch"]["state"] == "stuck"
            with pytest.raises(Fault, match="GUI_DISPATCH_STUCK"):
                request("get_objects", "Doc")
            release.set()
            assert query.result(timeout=2) == ["Doc"]
            assert len(reads) > reads_before_query
            assert request("get_rpc_status")["gui_dispatch"]["state"] == "healthy"
            assert request("get_object", "Doc", "Box") == {"Name": "Box"}
        finally:
            release.set()


def test_async_failure_is_readable_through_get_async_status(
    rpc_module: types.ModuleType,
) -> None:
    done = threading.Event()
    rpc_module.FreeCAD.Console.PrintError = lambda _message: done.set()
    rpc_module.FreeCAD.Console.PrintWarning = lambda _message: None
    rpc = rpc_module.FreeCADRPC()
    started = rpc.execute_code_async("partial = 1\nraise ValueError('Null shape')")
    job_id = started["job_id"]
    assert started["success"] is True and job_id
    assert done.wait(2)
    for _ in range(50):
        job = rpc.get_async_status(job_id)["job"]
        if job["state"] != "running":
            break
        threading.Event().wait(0.02)
    assert job["state"] == "failed"
    assert job["error"] == "ValueError: Null shape"
    assert 'line 2, in <module>' in job["traceback"]
    assert job["shape_check"] == {"changed": [], "warnings": []}
    assert rpc.get_async_status("nope") == {"success": False, "error": "unknown async job: nope"}
    assert [j["id"] for j in rpc.get_async_status()["jobs"]] == [job_id]
    assert rpc.get_rpc_status()["async_jobs_running"] == []


def test_execute_code_reports_shapes_the_script_broke(
    rpc_module: types.ModuleType,
) -> None:
    from test_shape_check import FakeShape

    lid = FakeShape(volume=10.0)
    doc = types.SimpleNamespace(Objects=[types.SimpleNamespace(Name="Lid", Shape=lid)])
    rpc_module.FreeCAD.listDocuments = lambda: {"Doc": doc}
    rpc_module.FreeCAD.test_lid = lid
    warned: list[str] = []
    rpc_module.FreeCAD.Console.PrintWarning = warned.append
    rpc = rpc_module.FreeCADRPC()
    result = rpc.execute_code("print('ok')")
    assert result["success"] is True
    assert result["shape_check"] == {"changed": [], "warnings": []}
    result = rpc.execute_code("FreeCAD.test_lid.volume = 9.0\nFreeCAD.test_lid.valid = False")
    assert result["success"] is True
    assert result["message"].endswith("Output: ")
    assert result["shape_check"]["warnings"] == ["Doc.Lid: shape is INVALID"]
    assert result["shape_check"]["changed"][0]["was"]["volume"] == 10.0
    assert warned == ["Shape check: Doc.Lid: shape is INVALID\n"]
