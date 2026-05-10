import FreeCAD
import FreeCADGui

import contextlib
import queue
import base64
import io
import os
import tempfile
import threading
from typing import Any

from PySide import QtCore

from .commands import register_commands, schedule_toggle_sync
from .fem_executor import run_fem_analysis as _run_fem_analysis
from .gui_dispatch import (
    process_gui_tasks,
    request_shutdown,
    rpc_request_queue,
    rpc_response_queue,
)
from .ip_filter import FilteredXMLRPCServer, validate_allowed_ips
from .object_factory import create_object_gui
from .parts_library import get_parts_list, insert_part_from_library
from .property_mapper import Object, set_object_property
from .serialize import serialize_object
from .settings import load_settings, save_settings
from .view_manager import save_active_screenshot

rpc_server_thread = None
rpc_server_instance = None


class FreeCADRPC:
    """RPC server for FreeCAD"""
    TIMEOUT = 10

    def ping(self):
        return True

    def create_document(self, name="New_Document"):
        rpc_request_queue.put(lambda: self._create_document_gui(name))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "document_name": name}
        else:
            return {"success": False, "error": res}

    def create_object(self, doc_name, obj_data: dict[str, Any]):
        obj = Object(
            name=obj_data.get("Name", "New_Object"),
            type=obj_data["Type"],
            analysis=obj_data.get("Analysis", None),
            properties=obj_data.get("Properties", {}),
        )
        rpc_request_queue.put(lambda: self._create_object_gui(doc_name, obj))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "object_name": obj.name}
        else:
            return {"success": False, "error": res}

    def edit_object(self, doc_name: str, obj_name: str, properties: dict[str, Any]) -> dict[str, Any]:
        obj = Object(
            name=obj_name,
            properties=properties.get("Properties", {}),
        )
        rpc_request_queue.put(lambda: self._edit_object_gui(doc_name, obj))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "object_name": obj.name}
        else:
            return {"success": False, "error": res}

    def delete_object(self, doc_name: str, obj_name: str):
        rpc_request_queue.put(lambda: self._delete_object_gui(doc_name, obj_name))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "object_name": obj_name}
        else:
            return {"success": False, "error": res}

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> dict[str, Any]:
        """Run the CalculiX solver on an existing Fem::FemAnalysis and return summary results."""
        try:
            timeout_s = int(timeout)
        except (TypeError, ValueError):
            return {"success": False, "error": f"invalid timeout: {timeout!r}"}
        rpc_request_queue.put(lambda: self._run_fem_analysis_gui(doc_name, analysis_name))
        try:
            res = rpc_response_queue.get(timeout=timeout_s)
        except queue.Empty:
            return {"success": False, "error": f"solver did not return within {timeout_s}s (still running on the GUI thread)"}
        if isinstance(res, dict):
            return res
        return {"success": False, "error": str(res)}

    def execute_code(self, code: str) -> dict[str, Any]:
        output_buffer = io.StringIO()
        def task():
            try:
                with contextlib.redirect_stdout(output_buffer):
                    exec(code, globals())
                FreeCAD.Console.PrintMessage("Python code executed successfully.\n")
                return True
            except Exception as e:
                FreeCAD.Console.PrintError(
                    f"Error executing Python code: {e}\n"
                )
                return f"Error executing Python code: {e}\n"

        rpc_request_queue.put(task)
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {
                "success": True,
                "message": "Python code execution scheduled. \nOutput: " + output_buffer.getvalue()
            }
        else:
            return {"success": False, "error": res}

    def get_objects(self, doc_name):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            return [serialize_object(obj) for obj in doc.Objects]
        else:
            return []

    def get_object(self, doc_name, obj_name):
        doc = FreeCAD.getDocument(doc_name)
        if doc:
            obj = doc.getObject(obj_name)
            if obj:
                return serialize_object(obj)
            else:
                return None
        else:
            return None

    def insert_part_from_library(self, relative_path):
        rpc_request_queue.put(lambda: self._insert_part_from_library(relative_path))
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            return {"success": True, "message": "Part inserted from library."}
        else:
            return {"success": False, "error": res}

    def list_documents(self):
        return list(FreeCAD.listDocuments().keys())

    def get_parts_list(self):
        return get_parts_list()

    def get_active_screenshot(self, view_name: str = "Isometric", width: int | None = None, height: int | None = None, focus_object: str | None = None) -> str:
        """Get a screenshot of the active view.
        
        Returns a base64-encoded string of the screenshot or None if a screenshot
        cannot be captured (e.g., when in TechDraw or Spreadsheet view).
        """
        # First check if the active view supports screenshots
        def check_view_supports_screenshots():
            try:
                active_view = FreeCADGui.ActiveDocument.ActiveView
                if active_view is None:
                    FreeCAD.Console.PrintWarning("No active view available\n")
                    return False
                
                view_type = type(active_view).__name__
                has_save_image = hasattr(active_view, 'saveImage')
                FreeCAD.Console.PrintMessage(f"View type: {view_type}, Has saveImage: {has_save_image}\n")
                return has_save_image
            except Exception as e:
                FreeCAD.Console.PrintError(f"Error checking view capabilities: {e}\n")
                return False
                
        rpc_request_queue.put(check_view_supports_screenshots)
        supports_screenshots = rpc_response_queue.get(timeout=self.TIMEOUT)
        
        if not supports_screenshots:
            FreeCAD.Console.PrintWarning("Current view does not support screenshots\n")
            return None
            
        # If view supports screenshots, proceed with capture
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        rpc_request_queue.put(
            lambda: self._save_active_screenshot(tmp_path, view_name, width, height, focus_object)
        )
        res = rpc_response_queue.get(timeout=self.TIMEOUT)
        if res is True:
            try:
                with open(tmp_path, "rb") as image_file:
                    image_bytes = image_file.read()
                    encoded = base64.b64encode(image_bytes).decode("utf-8")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            return encoded
        else:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            FreeCAD.Console.PrintWarning(f"Failed to capture screenshot: {res}\n")
            return None

    def _create_document_gui(self, name):
        doc = FreeCAD.newDocument(name)
        doc.recompute()
        FreeCAD.Console.PrintMessage(f"Document '{name}' created via RPC.\n")
        return True

    def _create_object_gui(self, doc_name, obj: Object):
        return create_object_gui(doc_name, obj)

    def _edit_object_gui(self, doc_name: str, obj: Object):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

        obj_ins = doc.getObject(obj.name)
        if not obj_ins:
            FreeCAD.Console.PrintError(f"Object '{obj.name}' not found in document '{doc_name}'.\n")
            return f"Object '{obj.name}' not found in document '{doc_name}'.\n"

        try:
            # For Fem::ConstraintFixed
            if hasattr(obj_ins, "References") and "References" in obj.properties:
                refs = []
                for ref_name, face in obj.properties["References"]:
                    ref_obj = doc.getObject(ref_name)
                    if ref_obj:
                        refs.append((ref_obj, face))
                    else:
                        raise ValueError(f"Referenced object '{ref_name}' not found.")
                obj_ins.References = refs
                FreeCAD.Console.PrintMessage(
                    f"References updated for '{obj.name}' in '{doc_name}'.\n"
                )
                # delete References from properties
                del obj.properties["References"]
            set_object_property(doc, obj_ins, obj.properties)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj.name}' updated via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _run_fem_analysis_gui(self, doc_name: str, analysis_name: str):
        # MUST always return a dict — process_gui_tasks treats None as no-response,
        # and the caller would block until its timeout. Keep the broad except.
        return _run_fem_analysis(doc_name, analysis_name)

    def _delete_object_gui(self, doc_name: str, obj_name: str):
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            FreeCAD.Console.PrintError(f"Document '{doc_name}' not found.\n")
            return f"Document '{doc_name}' not found.\n"

        try:
            doc.removeObject(obj_name)
            doc.recompute()
            FreeCAD.Console.PrintMessage(f"Object '{obj_name}' deleted via RPC.\n")
            return True
        except Exception as e:
            return str(e)

    def _insert_part_from_library(self, relative_path):
        try:
            insert_part_from_library(relative_path)
            return True
        except Exception as e:
            return str(e)

    def _save_active_screenshot(
        self,
        save_path: str,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
    ):
        return save_active_screenshot(save_path, view_name, width, height, focus_object)


def start_rpc_server(port=9875):
    global rpc_server_thread, rpc_server_instance

    if rpc_server_instance:
        return "RPC Server already running."

    settings = load_settings()
    remote_enabled = settings.get("remote_enabled", False)
    allowed_ips = settings.get("allowed_ips", "127.0.0.1")

    if remote_enabled:
        host = "0.0.0.0"
    else:
        host = "127.0.0.1"

    rpc_server_instance = FilteredXMLRPCServer(
        (host, port), allowed_ips_str=allowed_ips, allow_none=True, logRequests=False
    )
    rpc_server_instance.register_instance(FreeCADRPC())

    def server_loop():
        FreeCAD.Console.PrintMessage(f"RPC Server started at {host}:{port}\n")
        if remote_enabled:
            FreeCAD.Console.PrintMessage(f"Remote connections enabled. Allowed IPs: {allowed_ips}\n")
        rpc_server_instance.serve_forever()

    rpc_server_thread = threading.Thread(target=server_loop, daemon=True)
    rpc_server_thread.start()

    QtCore.QTimer.singleShot(500, process_gui_tasks)

    msg = f"RPC Server started at {host}:{port}."
    if remote_enabled:
        msg += f" Allowed IPs: {allowed_ips}"
    return msg


def stop_rpc_server():
    global rpc_server_instance, rpc_server_thread

    if rpc_server_instance:
        # Post the sentinel before shutting down the XML-RPC server so the
        # next QTimer tick exits process_gui_tasks cleanly without
        # rescheduling itself; otherwise a subsequent start_rpc_server would
        # leave two QTimer chains running.
        request_shutdown()
        rpc_server_instance.shutdown()
        rpc_server_thread.join()
        rpc_server_instance = None
        rpc_server_thread = None
        FreeCAD.Console.PrintMessage("RPC Server stopped.\n")
        return "RPC Server stopped."

    return "RPC Server was not running."


register_commands()
schedule_toggle_sync()
