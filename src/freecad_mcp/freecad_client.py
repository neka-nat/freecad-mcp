import logging
import xmlrpc.client
from typing import Any


logger = logging.getLogger("FreeCADMCPserver")


class _TimeoutTransport(xmlrpc.client.Transport):
    """XML-RPC transport with a configurable socket timeout.

    The default Transport has no timeout, so a frozen FreeCAD GUI thread
    causes the MCP client to hang indefinitely (observed: 4+ minute waits).
    """
    def __init__(self, timeout: float = 30, **kwargs):
        super().__init__(**kwargs)
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn




def _normalize_envelope(res, fallback_error: str) -> dict:
    """Coerce an RPC reply into a dict carrying a ``success`` key.

    XML-RPC returns whatever the installed addon produces. The addon is copied
    into FreeCAD's ``Mod/`` directory by hand while the server is installed via
    pip, so the two halves can be out of step. Normalising here means a reply
    that is not the expected dict is reported as a failure the caller can read,
    rather than reaching ``res["success"]`` and raising a TypeError that points
    nowhere near the cause.
    """
    if isinstance(res, dict):
        if "success" in res:
            return res
        return {"success": True, **res}
    if isinstance(res, str) and res:
        return {"success": True, "image": res}
    return {"success": False, "error": fallback_error}


class FreeCADConnection:
    def __init__(self, host: str = "localhost", port: int = 9875, timeout: float = 150):
        self._uri = f"http://{host}:{port}"
        self._timeout = timeout
        self.server = self._make_proxy(timeout)

    def _make_proxy(self, timeout: float) -> xmlrpc.client.ServerProxy:
        return xmlrpc.client.ServerProxy(
            self._uri,
            allow_none=True,
            transport=_TimeoutTransport(timeout=timeout),
        )

    def disconnect(self) -> None:
        # Transport.close() clears cached HTTP connections if one was opened.
        transport = getattr(self.server, "_ServerProxy__transport", None)
        close = getattr(transport, "close", None)
        if callable(close):
            close()

    def ping(self) -> bool:
        return self.server.ping()

    def create_document(self, name: str) -> dict[str, Any]:
        return self.server.create_document(name)

    def create_object(self, doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.create_object(doc_name, obj_data)

    def edit_object(self, doc_name: str, obj_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.edit_object(doc_name, obj_name, obj_data)

    def delete_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.delete_object(doc_name, obj_name)


    def reload_document(self, doc_name: str) -> dict[str, Any]:
        return self.server.reload_document(doc_name)

    def insert_part_from_library(self, relative_path: str) -> dict[str, Any]:
        return self.server.insert_part_from_library(relative_path)

    def execute_code(self, code: str) -> dict[str, Any]:
        return self.server.execute_code(code)

    def execute_code_async(self, code: str) -> dict[str, Any]:
        return self.server.execute_code_async(code)

    def get_active_screenshot(
        self,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
    ) -> str | None:
        try:
            return self.server.get_active_screenshot(view_name, width, height, focus_object)
        except Exception as e:
            logger.error(f"Error getting screenshot: {e}")
            return None

    def get_page_screenshot(
        self,
        page_name: str,
        width: int | None = None,
        crop: list[float] | None = None,
        doc_name: str | None = None,
        save_to: str | None = None,
        include_image: bool = True,
    ) -> dict:
        try:
            res = self.server.get_page_screenshot(
                page_name, width, crop, doc_name, save_to, include_image
            )
        except Exception as e:
            # Covers transport failures and the arity error raised when a
            # stale addon is still installed and does not accept the newer
            # arguments.
            logger.error(f"Error getting page screenshot: {e}")
            return {"success": False, "error": f"RPC call failed: {e}"}
        return _normalize_envelope(
            res, "page render failed (no reason reported)"
        )

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return self.server.get_objects(doc_name)

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.get_object(doc_name, obj_name)

    def get_parts_list(self) -> list[str]:
        return self.server.get_parts_list()

    def list_documents(self) -> list[str]:
        return self.server.list_documents()

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        # The solver blocks the RPC response for up to `timeout` seconds, so the
        # socket must outlast it. The default 150 s transport timeout would abort
        # any solve longer than that even though the addon is still working.
        # Use a dedicated proxy whose socket timeout exceeds the solver timeout.
        proxy = self._make_proxy(max(self._timeout, timeout + 30))
        return proxy.run_fem_analysis(doc_name, analysis_name, timeout)
