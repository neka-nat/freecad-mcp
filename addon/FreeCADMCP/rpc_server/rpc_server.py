import xmlrpc.server
import threading
import queue
import time
import traceback
import FreeCAD
import sys
from io import StringIO

# Global queue for thread-safe execution in FreeCAD's main thread
execution_queue = queue.Queue()
results = {}

class RPCServer:
    def ping(self):
        return True

    def execute_code(self, code):
        job_id = str(time.time())
        execution_queue.put((job_id, code))
        
        # Wait for result (timeout 30s)
        start = time.time()
        while time.time() - start < 30:
            if job_id in results:
                res = results.pop(job_id)
                return res
            time.sleep(0.1)
        return {"success": False, "error": "Timeout waiting for main thread execution"}

def process_queue():
    """This function must be called periodically from the FreeCAD main thread."""
    try:
        while not execution_queue.empty():
            job_id, code = execution_queue.get_nowait()
            try:
                # Redirect stdout to capture print statements
                old_stdout = sys.stdout
                redirected_output = StringIO()
                sys.stdout = redirected_output
                
                # Execute the code
                # We use the globals of the main module to ensure access to FreeCAD
                exec(code, globals())
                
                sys.stdout = old_stdout
                output = redirected_output.getvalue()
                
                results[job_id] = {"success": True, "message": output}
            except Exception as e:
                if 'old_stdout' in locals():
                    sys.stdout = old_stdout
                results[job_id] = {"success": False, "error": str(e), "traceback": traceback.format_exc()}
    except Exception as e:
        print(f"Error in process_queue: {e}")

def start_rpc_server():
    server = xmlrpc.server.SimpleXMLRPCServer(("0.0.0.0", 9875), allow_none=True, logRequests=False)
    server.register_instance(RPCServer())
    print("XML-RPC Server listening on port 9875...")
    server.serve_forever()

# Start XML-RPC server in a background thread
threading.Thread(target=start_rpc_server, daemon=True).start()

# Start the Qt Event Loop if we are in GUI mode (FreeCAD --cmd)
# In --cmd mode, we must manually process events or start an event loop
try:
    from PySide import QtCore, QtGui
    import FreeCADGui

    timer = QtCore.QTimer()
    timer.timeout.connect(process_queue)
    timer.start(100)
    print("Queue processor started via QTimer.")

    # If running via freecad --cmd, the application doesn't automatically enter the event loop
    # We check if a GUI application exists
    app = QtGui.qApp
    if app:
        print("Qt Application found, starting event loop...")
        # Note: app.exec_() will block. For FreeCAD, we might want to just process events.
        # But if we are a background server, blocking here is fine.
        app.exec_()
    else:
        print("No Qt Application found.")
except ImportError:
    print("PySide not found, fallback to manual polling...")
    while True:
        process_queue()
        time.sleep(0.1)
