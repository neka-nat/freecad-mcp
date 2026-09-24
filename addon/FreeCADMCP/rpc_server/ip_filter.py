"""IP-filtered XML-RPC server and helpers for parsing allowed IP/subnet lists.

The server also refuses requests a web page could have sent. The IP allowlist
cannot stop those: the browser runs on an allowed machine, so a malicious page
could otherwise call execute_code (CSRF, or DNS rebinding to read the reply).
"""

import ipaddress
import re
from email.message import Message
from socketserver import ThreadingMixIn
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

import FreeCAD


_XML_MEDIA_TYPES = frozenset({"text/xml", "application/xml"})


def _host_name(host_header: str) -> str:
    """Return the host of a Host header value, without port or brackets."""
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 literal, e.g. [::1]:9875
        return host[1:].split("]", 1)[0]
    return host.rsplit(":", 1)[0].rstrip(".")


def _is_loopback_name(name: str) -> bool:
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def browser_request_rejection(
    headers: Message, loopback_only: bool
) -> tuple[int, str] | None:
    """Return ``(status, reason)`` for a request to refuse, or None to accept it.

    Browsers attach Origin to every POST, and can send an XML body to another
    origin only after a CORS preflight, which this server never answers.
    xmlrpc.client sends text/xml without Origin, so MCP clients are unaffected.
    The Host check stops DNS rebinding where it is decidable: a server bound to
    loopback is only ever addressed as localhost.
    """
    if headers.get("Origin") is not None:
        return 403, "requests from web pages are not accepted"
    media_type = (headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if media_type not in _XML_MEDIA_TYPES:
        return 415, "XML-RPC requests must use Content-Type text/xml"
    host = headers.get("Host")
    if loopback_only and host is not None and not _is_loopback_name(_host_name(host)):
        return 403, "the local RPC server only accepts requests addressed to localhost"
    return None


class BrowserGuardRequestHandler(SimpleXMLRPCRequestHandler):
    """Refuse requests a web page could have sent before they are dispatched."""

    def do_POST(self) -> None:
        rejection = browser_request_rejection(self.headers, self.server.loopback_only)
        if rejection is None:
            super().do_POST()
            return
        status, reason = rejection
        FreeCAD.Console.PrintWarning(
            f"MCP RPC: Rejected request from {self.client_address[0]}: {reason}\n"
        )
        body = reason.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")  # the unread body must not be parsed as a request
        self.end_headers()
        self.wfile.write(body)


class FilteredXMLRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    """XML-RPC server that filters connections by allowed IP addresses/subnets.

    Threaded so get_rpc_status stays answerable while a wedged GUI task blocks
    another request. Document queries and synchronous modelling handlers
    serialise onto the GUI thread through dispatch_to_gui. The opt-in
    execute_code_async worker retains its existing background execution.

    daemon_threads must stay true — ThreadingMixIn.server_close() joins
    non-daemon request threads, which would make Stop wait out the stuck
    operation.
    """

    daemon_threads = True

    def __init__(self, addr, allowed_ips_str="127.0.0.1", **kwargs):
        self._allowed_networks = _parse_allowed_ips(allowed_ips_str)
        # Remote clients address the server by its LAN name or IP, so only a
        # loopback-bound server can require a localhost Host header.
        self.loopback_only = _is_loopback_name(str(addr[0]).lower())
        kwargs.setdefault("requestHandler", BrowserGuardRequestHandler)
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
