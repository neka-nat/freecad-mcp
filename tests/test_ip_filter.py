"""Tests for the addon's IP allow-list validation.

``validate_allowed_ips`` is security-critical (it gates who may connect to the
RPC server in remote mode) and is pure-stdlib logic. The module lives in the
FreeCAD addon and does ``import FreeCAD`` at top level, so we stub FreeCAD and
load the file directly rather than importing it as a package.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

_IP_FILTER_PATH = (
    Path(__file__).resolve().parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "ip_filter.py"
)


def _load_ip_filter():
    # FreeCAD only exists inside the running FreeCAD app; stub it so the pure
    # IP-validation helpers can be imported and exercised here.
    sys.modules.setdefault("FreeCAD", MagicMock())
    spec = importlib.util.spec_from_file_location("addon_ip_filter", _IP_FILTER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ip_filter = _load_ip_filter()
validate_allowed_ips = ip_filter.validate_allowed_ips


def test_single_valid_ip():
    valid, errors = validate_allowed_ips("127.0.0.1")
    assert valid == ["127.0.0.1"]
    assert errors == []


def test_multiple_entries_with_whitespace_and_cidr():
    valid, errors = validate_allowed_ips("192.168.1.100, 10.0.0.0/24")
    assert valid == ["192.168.1.100", "10.0.0.0/24"]
    assert errors == []


def test_ipv6_is_accepted():
    valid, errors = validate_allowed_ips("::1")
    assert valid == ["::1"]
    assert errors == []


def test_empty_string_is_rejected():
    valid, errors = validate_allowed_ips("")
    assert valid == []
    assert errors == ["Input must not be empty."]


def test_whitespace_only_is_rejected():
    valid, errors = validate_allowed_ips("   ")
    assert valid == []
    assert errors == ["Input must not be empty."]


def test_leading_comma_is_malformed():
    valid, errors = validate_allowed_ips(",127.0.0.1")
    assert valid == []
    assert len(errors) == 1
    assert "Malformed" in errors[0]


def test_double_comma_is_malformed():
    valid, errors = validate_allowed_ips("127.0.0.1,,10.0.0.1")
    assert valid == []
    assert "Malformed" in errors[0]


def test_invalid_entry_reported_but_valid_ones_kept():
    valid, errors = validate_allowed_ips("127.0.0.1, notanip")
    assert valid == ["127.0.0.1"]
    assert errors == ["Invalid IP/subnet: 'notanip'"]


def test_all_invalid_entries_yield_no_valid():
    valid, errors = validate_allowed_ips("999.999.999.999, nope")
    assert valid == []
    assert len(errors) == 2
