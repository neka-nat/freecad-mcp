"""Version handshake between the MCP server and the FreeCAD addon (#145)."""

import importlib.util
import json
from pathlib import Path
import time
import tomllib
import types
import xml.etree.ElementTree as ET

import pytest

from freecad_mcp import server
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.operations import get_rpc_status_operation
from freecad_mcp.server_state import ServerState
from freecad_mcp.version import PROTOCOL_VERSION, addon_version_warning
from test_rpc_concurrency import running_server
from test_rpc_handlers import rpc_module


ROOT = Path(__file__).resolve().parents[1]
ADDON_VERSION_PATH = ROOT / "addon" / "FreeCADMCP" / "rpc_server" / "version.py"


def load_addon_version() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("_addon_version_test", ADDON_VERSION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def matching_status(**overrides) -> dict:
    return {
        "success": True,
        "addon_version": "0.1.24",
        "protocol_version": PROTOCOL_VERSION,
        "execute_code_timeout": 90,
        "max_execute_code_timeout": 1800,
        **overrides,
    }


class OldestAddon:
    """Predates get_rpc_status entirely."""

    def ping(self) -> bool:
        return True


class UnversionedAddon(OldestAddon):
    def get_rpc_status(self) -> dict:
        return {"success": True, "rpc_server": "running"}


class VersionedAddon(OldestAddon):
    def __init__(self, status: dict) -> None:
        self.status = status

    def get_rpc_status(self) -> dict:
        return self.status


class BrokenStatusAddon(OldestAddon):
    """Has get_rpc_status, but the method fails."""

    def get_rpc_status(self) -> dict:
        raise RuntimeError("status exploded")


def check(interface: object) -> tuple[str | None, FreeCADConnection]:
    with running_server(interface) as (host, port):
        connection = FreeCADConnection(host, port, timeout=2)
        try:
            return connection.check_addon_version(), connection
        finally:
            connection.disconnect()


def test_addon_and_server_share_protocol_and_package_version() -> None:
    addon = load_addon_version()
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert addon.PROTOCOL_VERSION == PROTOCOL_VERSION
    assert addon.__version__ == pyproject["project"]["version"]


def test_package_xml_version_matches_when_present() -> None:
    # Addon Manager metadata (#94, #104) would be one more copy of the version.
    expected = load_addon_version().__version__
    for path in (ROOT / "package.xml", ROOT / "addon" / "FreeCADMCP" / "package.xml"):
        if path.exists():
            root = ET.parse(path).getroot()
            found = root.findtext("{https://wiki.freecad.org/Package_Metadata}version")
            assert found == expected, f"{path.relative_to(ROOT)}: {found} != {expected}"


def test_matching_addon_gives_no_warning() -> None:
    assert addon_version_warning(matching_status()) is None


def test_addon_without_get_rpc_status_is_reported_as_old() -> None:
    warning, _ = check(OldestAddon())
    assert warning is not None
    assert "no get_rpc_status" in warning
    assert "Update the addon" in warning


def test_addon_without_version_fields_is_reported_as_old() -> None:
    warning, _ = check(UnversionedAddon())
    assert warning is not None
    assert "does not report a version" in warning
    assert "Update the addon" in warning


def test_failing_get_rpc_status_is_not_reported_as_an_old_addon() -> None:
    warning, connection = check(BrokenStatusAddon())
    assert warning is None
    assert connection.EXECUTE_CODE_TIMEOUT == 90


def rpc_status_tool_text(interface: object) -> str:
    with running_server(interface) as (host, port):
        connection = FreeCADConnection(host, port, timeout=2)
        try:
            return get_rpc_status_operation(connection)[0].text
        finally:
            connection.disconnect()


def test_rpc_status_tool_tells_an_old_addon_from_a_failing_one() -> None:
    assert "no get_rpc_status" in rpc_status_tool_text(OldestAddon())
    failing = rpc_status_tool_text(BrokenStatusAddon())
    assert "Failed to get RPC status" in failing
    assert "status exploded" in failing
    assert "no get_rpc_status" not in failing


@pytest.mark.parametrize(
    ("protocol", "fix"),
    [(PROTOCOL_VERSION - 1, "Update the addon"), (PROTOCOL_VERSION + 1, "Update the MCP server")],
)
def test_protocol_mismatch_names_the_side_to_update(protocol: int, fix: str) -> None:
    warning, _ = check(VersionedAddon(matching_status(addon_version="9.9.9", protocol_version=protocol)))
    assert warning is not None
    assert f"FreeCAD addon 9.9.9 (protocol {protocol}) does not match" in warning
    assert fix in warning


def test_boolean_protocol_is_not_a_version() -> None:
    assert "does not report a version" in addon_version_warning(matching_status(protocol_version=True))


def test_client_adopts_the_addons_budgets() -> None:
    warning, connection = check(
        VersionedAddon(matching_status(execute_code_timeout=45, max_execute_code_timeout=600))
    )
    assert warning is None
    assert connection.EXECUTE_CODE_TIMEOUT == 45
    assert connection.MAX_EXECUTE_CODE_TIMEOUT == 600
    # Class defaults stay intact for other connections.
    assert FreeCADConnection.EXECUTE_CODE_TIMEOUT == 90


@pytest.mark.parametrize(
    "bad", [0, -5, True, "90", float("inf"), float("nan"), None, 1801, 1e9, 1e308]
)
def test_client_ignores_invalid_budgets(bad: object) -> None:
    _, connection = check(
        VersionedAddon(matching_status(execute_code_timeout=bad, max_execute_code_timeout=bad))
    )
    assert connection.EXECUTE_CODE_TIMEOUT == 90
    assert connection.MAX_EXECUTE_CODE_TIMEOUT == 1800


def test_client_adopts_a_budget_up_to_its_own_ceiling() -> None:
    _, connection = check(VersionedAddon(matching_status(execute_code_timeout=1800)))
    assert connection.EXECUTE_CODE_TIMEOUT == 1800


def test_unreachable_addon_does_not_block_the_check() -> None:
    connection = FreeCADConnection("127.0.0.1", 9, timeout=0.5)
    try:
        assert connection.check_addon_version() is None
    finally:
        connection.disconnect()


class HungStatusAddon(VersionedAddon):
    def get_rpc_status(self) -> dict:
        time.sleep(1.0)
        return super().get_rpc_status()


def test_hung_addon_cannot_hold_up_the_check() -> None:
    with running_server(HungStatusAddon(matching_status())) as (host, port):
        # The connection timeout stays long; only the check is short.
        connection = FreeCADConnection(host, port, timeout=150)
        connection.VERSION_CHECK_TIMEOUT = 0.2
        started = time.monotonic()
        try:
            assert connection.check_addon_version() is None
        finally:
            connection.disconnect()
        assert time.monotonic() - started < 0.9


def test_real_addon_reports_version_and_budgets(rpc_module: types.ModuleType) -> None:
    rpc = rpc_module.FreeCADRPC()
    rpc.EXECUTE_CODE_TIMEOUT = 42
    status = rpc.get_rpc_status()
    assert status["addon_version"] == load_addon_version().__version__
    assert status["protocol_version"] == PROTOCOL_VERSION
    assert status["execute_code_timeout"] == 42
    assert status["max_execute_code_timeout"] == rpc.MAX_EXECUTE_CODE_TIMEOUT

    warning, connection = check(rpc)
    assert warning is None
    assert connection.EXECUTE_CODE_TIMEOUT == 42


def test_rpc_status_tool_reports_version_check() -> None:
    class Connection:
        def __init__(self, status: dict) -> None:
            self.status = status

        def get_rpc_status(self) -> dict:
            return dict(self.status)

    ok = json.loads(get_rpc_status_operation(Connection(matching_status()))[0].text)
    assert ok["version_check"] == "ok"
    old = json.loads(get_rpc_status_operation(Connection({"success": True}))[0].text)
    assert "does not report a version" in old["version_check"]


def test_warning_is_shown_once_in_the_next_tool_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    class Connection:
        def ping(self) -> bool:
            return True

        def check_addon_version(self) -> str:
            return "addon is old"

        def list_documents(self) -> list[str]:
            return ["Doc"]

    monkeypatch.setattr(server, "state", ServerState())
    monkeypatch.setattr(server, "FreeCADConnection", lambda **_kwargs: Connection())

    first = server.list_documents(None)
    assert first[0].text == "Warning: addon is old"
    assert json.loads(first[1].text) == ["Doc"]

    second = server.list_documents(None)
    assert len(second) == 1
    assert json.loads(second[0].text) == ["Doc"]


def test_version_is_checked_when_freecad_starts_after_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # MCP clients usually launch the server before FreeCAD is open.
    freecad_running = False
    checks: list[str] = []

    class Connection:
        def ping(self) -> bool:
            if not freecad_running:
                raise ConnectionRefusedError(111, "Connection refused")
            return True

        def check_addon_version(self) -> str:
            checks.append("checked")
            return "addon is old"

        def list_documents(self) -> list[str]:
            return ["Doc"]

        def disconnect(self) -> None:
            pass

    monkeypatch.setattr(server, "state", ServerState())
    monkeypatch.setattr(server, "FreeCADConnection", lambda **_kwargs: Connection())

    with pytest.raises(Exception, match="Failed to connect to FreeCAD"):
        server.list_documents(None)
    assert server.state.freecad_connection is None
    assert checks == []

    freecad_running = True
    reply = server.list_documents(None)
    assert reply[0].text == "Warning: addon is old"
    assert json.loads(reply[1].text) == ["Doc"]
    assert checks == ["checked"]
    assert server.state.freecad_connection is not None
