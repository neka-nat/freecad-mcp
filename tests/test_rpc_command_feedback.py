import importlib.util
from pathlib import Path
import sys
import types
from unittest.mock import MagicMock

import pytest

from test_rpc_handlers import rpc_module


@pytest.fixture
def commands(
    rpc_module: types.ModuleType, monkeypatch: pytest.MonkeyPatch,
) -> tuple[types.ModuleType, types.ModuleType, types.SimpleNamespace, MagicMock]:
    path = Path(__file__).resolve().parents[1] / "addon/FreeCADMCP/rpc_server/commands.py"
    spec = importlib.util.spec_from_file_location("rpc_server._commands_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys.modules["rpc_server"], "rpc_server", rpc_module, raising=False)
    console = types.SimpleNamespace(PrintMessage=MagicMock(), PrintError=MagicMock())
    monkeypatch.setattr(module.FreeCAD, "Console", console)
    window = MagicMock()
    monkeypatch.setattr(module.FreeCADGui, "getMainWindow", lambda: window)
    return module, rpc_module, console, window.statusBar.return_value


@pytest.mark.parametrize("command_name,method", [
    ("StartRPCServerCommand", "start_rpc_server"),
    ("StopRPCServerCommand", "stop_rpc_server"),
])
def test_success_reaches_console_and_status_bar(
    commands: tuple, monkeypatch: pytest.MonkeyPatch, command_name: str, method: str,
) -> None:
    module, rpc, console, status_bar = commands
    monkeypatch.setattr(rpc, method, lambda: "RPC status feedback")
    getattr(module, command_name)().Activated(0)
    console.PrintMessage.assert_called_once_with("RPC status feedback\n")
    status_bar.showMessage.assert_called_once_with("RPC status feedback", 15000)


@pytest.mark.parametrize("command_name,method", [
    ("StartRPCServerCommand", "start_rpc_server"),
    ("StopRPCServerCommand", "stop_rpc_server"),
])
def test_failure_is_visible_and_does_not_escape_callback(
    commands: tuple, monkeypatch: pytest.MonkeyPatch, command_name: str, method: str,
) -> None:
    module, rpc, console, status_bar = commands

    def fail() -> None:
        raise OSError("address already in use")

    monkeypatch.setattr(rpc, method, fail)
    getattr(module, command_name)().Activated()
    message = console.PrintError.call_args.args[0]
    assert "OSError: address already in use" in message
    assert "failed to" in message
    status_bar.showMessage.assert_called_once_with(message.rstrip(), 15000)
    console.PrintMessage.assert_not_called()
