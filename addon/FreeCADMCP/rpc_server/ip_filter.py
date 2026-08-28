"""IP-filtered XML-RPC server and helpers for parsing allowed IP/subnet lists."""

import ipaddress
import re
from socketserver import ThreadingMixIn
from xmlrpc.server import SimpleXMLRPCServer

import FreeCAD


class FilteredXMLRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    """XML-RPC server that filters connections by allowed IP addresses/subnets.

    Handles each request in its own thread. Serving requests one at a time
    defeated ``get_rpc_status``, which exists precisely to be answerable while
    the GUI thread is wedged: a blocked ``execute_code`` occupied the single
    accept loop, so the status call could not even reach the server until the
    operation it was meant to diagnose had finished.

    Concurrency is safe because every handler that touches FreeCAD funnels
    through ``dispatch_to_gui``, which owns a ``queue.Queue`` of tasks, a
    private response queue per call, and lock-guarded health state; the GUI
    thread therefore still executes tasks strictly one at a time, in order.

    ``daemon_threads`` must stay true: ``ThreadingMixIn.server_close()`` joins
    every non-daemon request thread, which would make Stop wait out a stuck
    ``execute_code`` — exactly the freeze this class is meant to avoid.

    Connections are still filtered before a thread is spawned: ``verify_request``
    runs in the accept loop, ahead of ``process_request``.
    """

    daemon_threads = True

    def __init__(self, addr, allowed_ips_str="127.0.0.1", **kwargs):
        self._allowed_networks = _parse_allowed_ips(allowed_ips_str)
        super().__init__(addr, **kwargs)

    def verify_request(self, request, client_address):
        client_ip = client_address[0]
        try:
            addr = ipaddress.ip_address(client_ip)
            for network in self._allowed_networks:
                if addr in network:
                    return True
        except ValueError:
            pass
        FreeCAD.Console.PrintWarning(
            f"MCP RPC: Rejected connection from {client_ip}\n"
        )
        return False


_COMMA_SEP_RE = re.compile(r"^\s*[^,\s]+(\s*,\s*[^,\s]+)*\s*$")


def validate_allowed_ips(allowed_ips_str):
    """Validate a comma-separated string of IP addresses/subnets.

    Returns a ``(valid, errors)`` tuple.  ``valid`` is a list of normalised
    entry strings that passed validation; ``errors`` is a list of
    human-readable error messages (empty when the input is fully valid).

    Checks performed:
    1. The overall string is well-formed comma-separated (no leading/trailing
       commas, no empty entries between commas, not blank).
    2. Each individual entry is a valid IPv4/IPv6 address or CIDR subnet
       (validated via the stdlib ``ipaddress`` module).
    """
    errors = []

    if not allowed_ips_str or not allowed_ips_str.strip():
        return [], ["Input must not be empty."]

    if not _COMMA_SEP_RE.match(allowed_ips_str):
        return [], [
            "Malformed list — check for leading/trailing commas, "
            "double commas, or missing separators."
        ]

    valid = []
    for entry in allowed_ips_str.split(","):
        entry = entry.strip()
        try:
            ipaddress.ip_network(entry, strict=False)
            valid.append(entry)
        except ValueError:
            errors.append(f"Invalid IP/subnet: '{entry}'")
    return valid, errors


def _parse_allowed_ips(allowed_ips_str):
    """Parse a comma-separated string of IPs/subnets into a list of ip_network objects."""
    valid, errors = validate_allowed_ips(allowed_ips_str)
    for msg in errors:
        FreeCAD.Console.PrintWarning(f"MCP RPC: {msg}, skipping\n")
    return [ipaddress.ip_network(entry, strict=False) for entry in valid]
