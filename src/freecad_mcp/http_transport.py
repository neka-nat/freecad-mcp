"""HTTP/SSE transport support with guards against accidental exposure.

The MCP server exposes ``execute_code``, which is arbitrary code execution in
FreeCAD, so network listeners are locked down by default:

* the listener binds to loopback unless told otherwise;
* binding to a non-loopback address is refused unless a bearer token is set;
* DNS-rebinding protection is always on, with an allow-list of Host headers.
"""

from __future__ import annotations

import hmac
import inspect
import ipaddress
import logging
from typing import Any, Literal, Sequence

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("FreeCADMCPserver")

HttpTransport = Literal["streamable-http", "sse"]

DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 8000
_LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1")


class UnsafeListenConfigError(ValueError):
    """Raised when the requested listener configuration would be unsafe."""


def is_loopback(host: str) -> bool:
    """Return True if *host* only accepts connections from this machine."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_listen_config(
    listen_host: str, token: str | None, allow_insecure_remote: bool = False
) -> None:
    """Refuse a non-loopback bind without a token, unless explicitly overridden.

    The override exists for containers, where the process must bind 0.0.0.0
    inside the container and the host's published port is what limits access.
    """
    if not is_loopback(listen_host) and not token:
        if allow_insecure_remote:
            logger.warning(
                "Listening on %s with NO token (--allow-insecure-remote). Anyone who can "
                "reach this port can run arbitrary code in FreeCAD.",
                listen_host,
            )
            return
        raise UnsafeListenConfigError(
            f"Refusing to listen on non-loopback address '{listen_host}' without "
            "a token. Set FREECAD_MCP_LISTEN_TOKEN (or --listen-token), or bind to "
            "127.0.0.1. In a container, pass --allow-insecure-remote and publish the "
            "port on the host's loopback only (-p 127.0.0.1:PORT:PORT)."
        )


def build_allowed_hosts(
    listen_host: str, listen_port: int, extra_hosts: Sequence[str] = ()
) -> list[str]:
    """Host header values accepted by DNS-rebinding protection.

    Loopback names are always accepted. A specific (non 0.0.0.0/::) listen
    address is added too. Anything else, such as a LAN name, must be passed
    explicitly via *extra_hosts*.
    """
    hosts = [f"localhost:{listen_port}", f"127.0.0.1:{listen_port}", f"[::1]:{listen_port}"]
    if listen_host not in ("0.0.0.0", "::") and not is_loopback(listen_host):
        hosts.append(f"[{listen_host}]:{listen_port}" if ":" in listen_host else f"{listen_host}:{listen_port}")
    for host in extra_hosts:
        hosts.append(host if ":" in host.rpartition("]")[2] else f"{host}:{listen_port}")
    return list(dict.fromkeys(hosts))


def build_allowed_origins(allowed_hosts: Sequence[str]) -> list[str]:
    """Browser Origin values matching *allowed_hosts*."""
    return [f"http://{host}" for host in allowed_hosts]


class BearerTokenMiddleware:
    """Pure ASGI middleware requiring ``Authorization: Bearer <token>``."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        auth = Headers(scope=scope).get("authorization", "")
        scheme, _, supplied = auth.partition(" ")
        if scheme.lower() == "bearer" and hmac.compare_digest(
            supplied.strip().encode(), self._token
        ):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http":
            response = PlainTextResponse(
                "Unauthorized", status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )
            await response(scope, receive, send)
        else:
            await send({"type": "websocket.close", "code": 1008})


def build_app(
    mcp: Any,
    transport: HttpTransport,
    listen_host: str,
    listen_port: int,
    token: str | None,
    extra_hosts: Sequence[str] = (),
    allow_insecure_remote: bool = False,
) -> ASGIApp:
    """Build the ASGI app for *mcp* with all exposure guards applied."""
    from mcp.server.transport_security import TransportSecuritySettings

    validate_listen_config(listen_host, token, allow_insecure_remote)
    allowed_hosts = build_allowed_hosts(listen_host, listen_port, extra_hosts)
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=build_allowed_origins(allowed_hosts),
    )
    builder = mcp.sse_app if transport == "sse" else mcp.streamable_http_app
    if "transport_security" in inspect.signature(builder).parameters:
        # mcp 2.x takes these as arguments.
        app: ASGIApp = builder(transport_security=security, host=listen_host)
    else:
        # mcp 1.x reads them from settings when the app is built.
        mcp.settings.host = listen_host
        mcp.settings.port = listen_port
        mcp.settings.transport_security = security
        app = builder()
    if token:
        app = BearerTokenMiddleware(app, token)
    return app


def run_http(
    mcp: Any,
    transport: HttpTransport,
    listen_host: str,
    listen_port: int,
    token: str | None,
    extra_hosts: Sequence[str] = (),
    allow_insecure_remote: bool = False,
) -> None:
    """Serve *mcp* over HTTP until interrupted."""
    import uvicorn

    app = build_app(
        mcp, transport, listen_host, listen_port, token, extra_hosts, allow_insecure_remote
    )
    logger.info(
        "Serving MCP over %s on %s:%s (bearer token %s)",
        transport,
        listen_host,
        listen_port,
        "required" if token else "not required",
    )
    uvicorn.run(app, host=listen_host, port=listen_port, log_level="info")
