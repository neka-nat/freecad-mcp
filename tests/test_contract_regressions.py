"""Regression checks for the protocol-2 property, failure and concurrency contracts."""

import asyncio
import importlib.util
import math
from pathlib import Path
import sys
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock
from xmlrpc.client import Fault

import pytest

from freecad_mcp import server
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.headless import _clean
from freecad_mcp.operations.core import get_objects_operation, get_view_operation, execute_code_operation
from freecad_mcp.responses import ErrorResponse
from freecad_mcp.version import PROTOCOL_VERSION, is_missing_method_fault
from test_auth import token_server
from test_rpc_handlers import rpc_module
from test_rpc_command_feedback import commands
from test_serialize import load_serialize_module, make_freecad_module, FakeRotation


def test_rotations_dicts_nulls_and_links_keep_the_wire_contract() -> None:
    freecad = make_freecad_module()
    class Link:
        Name = "Box"
    freecad.DocumentObject = Link
    serialize = load_serialize_module(freecad)
    rotation = FakeRotation()
    rotation.Axis = NS(x=0, y=0, z=1)
    rotation.Angle = math.pi / 2
    assert serialize.serialize_value(rotation)["Angle"] == pytest.approx(90)
    assert serialize.serialize_value({"material": {"E": "210 GPa"}, "link": Link(), "empty": None}) == {
        "material": {"E": "210 GPa"}, "link": "Box", "empty": None,
    }


@pytest.mark.parametrize("method,args", [
    ("get_objects", ("Missing",)), ("get_object", ("Missing", "Box")),
    ("get_object", ("Doc", "Missing")),
])
def test_missing_queries_are_faults(rpc_module, method: str, args: tuple) -> None:
    with pytest.raises(Fault, match="not found"):
        getattr(rpc_module.FreeCADRPC(), method)(*args)


def test_sync_failure_preserves_output_in_rpc_and_mcp(rpc_module) -> None:
    rpc = rpc_module.FreeCADRPC()
    result = execute_code_operation(rpc, True, "print('before'); raise ValueError('failed')")
    assert isinstance(result, ErrorResponse)
    assert "before" in result[0].text and "failed" in result[0].text


def test_headless_does_not_filter_user_output() -> None:
    output = "FreeCAD 1.2 comparison\nPostprocessing result 42\nprogress 80%)\n\nfinal"
    assert _clean(output) == output


@pytest.mark.parametrize("timeout", [0, -1, True, 1.9, float("inf"), float("nan"), 2**31])
def test_fem_rejects_invalid_budgets_before_dispatch(rpc_module, monkeypatch, timeout) -> None:
    dispatch = Mock()
    monkeypatch.setattr(rpc_module, "dispatch_to_gui", dispatch)
    result = rpc_module.FreeCADRPC().run_fem_analysis("Doc", "Analysis", timeout)
    assert not result["success"]
    dispatch.assert_not_called()
    conn = FreeCADConnection()
    proxy = Mock()
    monkeypatch.setattr(conn, "_make_proxy", proxy)
    with pytest.raises(ValueError, match="timeout"):
        conn.run_fem_analysis("Doc", "Analysis", timeout)
    proxy.assert_not_called()


@pytest.mark.parametrize("tool,arguments", [
    ("execute_code", {"code": "pass", "timeout": True}),
    ("execute_code_headless", {"code": "pass", "timeout": True}),
    ("run_fem_analysis", {"doc_name": "Doc", "analysis_name": "A", "timeout": -1}),
])
def test_mcp_validation_rejects_bad_timeouts(monkeypatch, tool: str, arguments: dict) -> None:
    connect = Mock(side_effect=AssertionError("must validate before connecting"))
    monkeypatch.setattr(server, "get_freecad_connection", connect)
    headless = Mock(side_effect=AssertionError("must validate before spawning"))
    monkeypatch.setattr(server, "execute_code_headless_operation", headless)
    async def call() -> None:
        try:
            result = await server.mcp.call_tool(tool, arguments)
        except Exception as exc:
            assert "validation" in str(exc).lower()
        else:
            assert "validation" in str(result).lower()
    asyncio.run(call())
    connect.assert_not_called()
    headless.assert_not_called()


def test_status_does_not_wait_for_a_synchronous_tool(monkeypatch) -> None:
    entered = threading.Event()
    release = threading.Event()
    class Connection:
        def execute_code(self, *_args):
            entered.set()
            if not release.wait(3):
                raise TimeoutError("status was blocked by the tool")
            return {"success": True, "message": "done"}
        def get_rpc_status(self):
            assert entered.is_set()
            release.set()
            return {"protocol_version": PROTOCOL_VERSION}
    monkeypatch.setattr(server, "get_freecad_connection", lambda: Connection())
    async def call() -> None:
        work = asyncio.create_task(server.mcp.call_tool("execute_code", {"code": "pass", "include_screenshot": False}))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.01)
            assert entered.is_set()
            await asyncio.wait_for(server.mcp.call_tool("get_rpc_status", {}), 1)
            result = await work
            assert "done" in str(result)
        finally:
            release.set()
            await work
    asyncio.run(call())


def test_screenshot_transport_fault_keeps_its_diagnosis(monkeypatch) -> None:
    conn = FreeCADConnection()
    monkeypatch.setattr(conn, "_call", Mock(side_effect=TimeoutError("GUI_DISPATCH_STUCK")))
    result = get_view_operation(conn, "Top")
    assert isinstance(result, ErrorResponse)
    assert "GUI_DISPATCH_STUCK" in result[0].text
    assert "Spreadsheet" not in result[0].text


def test_optional_images_are_document_scoped() -> None:
    capture = Mock(return_value=None)
    conn = NS(get_objects=lambda name: [], get_active_screenshot=capture)
    result = get_objects_operation(conn, False, "OtherDocument")
    assert not isinstance(result, ErrorResponse)
    capture.assert_called_once_with("Isometric", doc_name="OtherDocument")


def test_document_capture_skips_other_active_document(rpc_module, monkeypatch) -> None:
    monkeypatch.setattr(rpc_module.FreeCAD, "ActiveDocument", NS(Name="Other"), raising=False)
    capture = Mock()
    monkeypatch.setattr(rpc_module, "save_active_screenshot", capture)
    assert rpc_module.FreeCADRPC().get_active_screenshot(doc_name="Doc") is None
    capture.assert_not_called()


def test_late_screenshot_cleans_its_own_file(rpc_module, monkeypatch, tmp_path: Path) -> None:
    original_dispatch = rpc_module.dispatch_to_gui
    monkeypatch.setattr(rpc_module, "dispatch_to_gui", lambda task, **kw: original_dispatch(task, timeout=.03, **kw))
    original_temp = rpc_module.tempfile.mkstemp
    monkeypatch.setattr(rpc_module.tempfile, "mkstemp", lambda **kw: original_temp(dir=tmp_path, **kw))
    monkeypatch.setattr(rpc_module, "get_displayed_3d_view", lambda: object())
    release = threading.Event()
    def capture(path: str, *_args) -> bool:
        assert release.wait(2)
        Path(path).write_bytes(b"late image")
        return True
    monkeypatch.setattr(rpc_module, "save_active_screenshot", capture)
    try:
        with pytest.raises(Fault, match="timed out"):
            rpc_module.FreeCADRPC().get_active_screenshot()
    finally:
        release.set()
    rpc_module.test_dispatch._waker.join()
    assert list(tmp_path.iterdir()) == []


def test_unicode_token_authenticates_over_the_real_client() -> None:
    with token_server("clé-秘密") as (_, port):
        assert FreeCADConnection("127.0.0.1", port, token="clé-秘密").ping()


def test_internal_unsupported_error_is_not_a_missing_method() -> None:
    assert not is_missing_method_fault(Fault(1, "ValueError: this document type is not supported"))
    assert is_missing_method_fault(Fault(1, '<class \'Exception\'>:method "get_rpc_status" is not supported'))


def test_ipv6_configuration_is_explicitly_rejected() -> None:
    import argparse
    from test_auth import ip_filter
    with pytest.raises(argparse.ArgumentTypeError, match="IPv6"):
        server._validate_host("::1")
    valid, errors = ip_filter().validate_allowed_ips("127.0.0.1, ::1")
    assert valid == ["127.0.0.1"] and "IPv6" in errors[0]


def test_failed_settings_write_preserves_previous_file(monkeypatch, tmp_path: Path) -> None:
    freecad = NS(getUserAppDataDir=lambda: str(tmp_path))
    monkeypatch.setitem(sys.modules, "FreeCAD", freecad)
    path = Path(__file__).resolve().parents[1] / "addon/FreeCADMCP/rpc_server/settings.py"
    spec = importlib.util.spec_from_file_location("_settings_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = tmp_path / "freecad_mcp_settings.json"
    original.write_text('{"auth_token": "previous"}')
    monkeypatch.setattr(module.os, "replace", Mock(side_effect=OSError("disk failure")))
    with pytest.raises(OSError, match="disk failure"):
        module.save_settings({"auth_token": "new"})
    assert original.read_text() == '{"auth_token": "previous"}'
    assert list(tmp_path.iterdir()) == [original]


def test_settings_command_reports_failed_save(commands, monkeypatch) -> None:
    module, _, console, status_bar = commands
    monkeypatch.setattr(module, "save_settings", Mock(side_effect=OSError("disk full")))
    assert module._persist_settings({"auto_start_rpc": True}) is False
    console.PrintMessage.assert_not_called()
    assert "not saved" in console.PrintError.call_args.args[0]
    assert "disk full" in status_bar.showMessage.call_args.args[0]
