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



class FreeCADConnection:
    # Keep the run budget in sync with the addon's FreeCADRPC constant.
    EXECUTE_CODE_TIMEOUT = 90
    RPC_TIMEOUT_MARGIN = 30

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

    def get_rpc_status(self) -> dict[str, Any]:
        with self._make_proxy(self._timeout) as proxy:
            return proxy.get_rpc_status()

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
        # The addon permits a full queue budget followed by a full run budget.
        timeout = max(self._timeout, 2 * self.EXECUTE_CODE_TIMEOUT + self.RPC_TIMEOUT_MARGIN)
        with self._make_proxy(timeout) as proxy:
            return proxy.execute_code(code)

    def execute_code_async(self, code: str) -> dict[str, Any]:
        return self.server.execute_code_async(code)

    def undo_last_edit(self, doc_name: str | None = None) -> dict[str, Any]:
        return self.server.undo_last_edit(doc_name)

    def measure_probe(
        self, doc_name: str, obj_name: str, start: list[float], end: list[float]
    ) -> dict[str, Any]:
        return self.server.measure_probe(doc_name, obj_name, start, end)

    def measure_compare(
        self,
        doc_name: str,
        obj_name: str,
        rays: list[dict[str, list[float]]],
        before: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self.server.measure_compare(doc_name, obj_name, rays, before)

    def check_manufacturability(
        self,
        doc_name: str = "",
        obj_name: str = "",
        file_path: str = "",
        r_min: float = 2.0,
        max_width: float = 0.3,
        min_edge: float = 0.1,
        vertical_only: bool = True,
    ) -> dict[str, Any]:
        return self.server.check_manufacturability(
            doc_name, obj_name, file_path, r_min, max_width, min_edge, vertical_only
        )

    def section_profile(
        self,
        doc_name: str,
        obj_name: str,
        axis: str,
        value: float,
        min_segment: float = 0.1,
        max_jog_deg: float = 2.0,
        file_path: str = "",
    ) -> dict[str, Any]:
        return self.server.section_profile(doc_name, obj_name, axis, value, min_segment, max_jog_deg, file_path)

    def shape_diff(
        self, doc_a: str, obj_a: str, doc_b: str, obj_b: str, file_a: str = "", file_b: str = ""
    ) -> dict[str, Any]:
        return self.server.shape_diff(doc_a, obj_a, doc_b, obj_b, file_a, file_b)

    def get_async_status(self, job_id: str = "") -> dict[str, Any]:
        # Polling must not share an HTTP connection with a blocked GUI request.
        with self._make_proxy(self._timeout) as proxy:
            return proxy.get_async_status(job_id)

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

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return self.server.get_objects(doc_name)

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.get_object(doc_name, obj_name)

    def get_parts_list(self) -> list[str]:
        return self.server.get_parts_list()

    def list_documents(self) -> list[str]:
        return self.server.list_documents()

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        # Both queueing and solving can consume `timeout` seconds each.
        socket_timeout = max(self._timeout, 2 * timeout + self.RPC_TIMEOUT_MARGIN)
        with self._make_proxy(socket_timeout) as proxy:
            return proxy.run_fem_analysis(doc_name, analysis_name, timeout)
