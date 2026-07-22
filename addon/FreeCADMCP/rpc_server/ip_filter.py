"""IP-filtered, optionally token-authenticated XML-RPC server and helpers."""

import base64
import hmac
import ipaddress
import re
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

import FreeCAD


def authorization_ok(header_value: str, token: str) -> bool:
    """Check an ``Authorization`` header against the configured token.

    Accepts ``Bearer <token>`` and HTTP Basic (token in the password field,
    username ignored) so stdlib clients can use ``http://:token@host:port``
    URIs. Comparisons are constant-time.
    """
    if header_value.startswith("Bearer "):
        supplied = header_value[len("Bearer "):].strip()
        return hmac.compare_digest(supplied, token)
    if header_value.startswith("Basic "):
        try:
            decoded = base64.b64decode(header_value[len("Basic "):], validate=True).decode("utf-8")
        except Exception:
            return False
        _, _, password = decoded.partition(":")
        return hmac.compare_digest(password, token)
    return False


class TokenAuthRequestHandler(SimpleXMLRPCRequestHandler):
    """Request handler that enforces the server's auth token when one is set."""

    def parse_request(self):
        if not super().parse_request():
            return False
        token = getattr(self.server, "auth_token", "")
        if not token:
            return True  # authentication disabled
        if authorization_ok(self.headers.get("Authorization", ""), token):
            return True
        FreeCAD.Console.PrintWarning(
            f"MCP RPC: Rejected unauthenticated request from {self.client_address[0]}\n"
        )
        self.send_error(401, "Unauthorized: valid auth token required")
        return False


class FilteredXMLRPCServer(SimpleXMLRPCServer):
    """XML-RPC server that filters connections by allowed IP addresses/subnets
    and (when a token is configured) requires an Authorization header."""

    def __init__(self, addr, allowed_ips_str="127.0.0.1", auth_token="", **kwargs):
        self._allowed_networks = _parse_allowed_ips(allowed_ips_str)
        self.auth_token = auth_token or ""
        kwargs.setdefault("requestHandler", TokenAuthRequestHandler)
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
