#!/bin/bash
set -e

echo "--- Starting Stlux Environment ---"
# Ensure Python output is unbuffered
export PYTHONUNBUFFERED=1

# Start Xvfb (Virtual Framebuffer)
echo "Starting Xvfb on display :99..."
Xvfb :99 -screen 0 1280x1024x24 &
export DISPLAY=:99

# Give Xvfb a moment to initialize
sleep 3

# Start FreeCAD in the background
# We ensure the rpc_server is in PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$HOME/.FreeCAD/Mod/FreeCADMCP/rpc_server
echo "Starting FreeCAD with MCP RPC server..."
# Use 'freecadcmd' for console mode or 'freecad --cmd' for GUI mode via Xvfb
# 'freecad' with --cmd still initializes the GUI which is often needed for some modules
freecad --cmd "import rpc_server" &

# Robust wait-for-service logic
echo "Waiting for FreeCAD RPC server (port 9875)..."
MAX_RETRIES=120
COUNT=0
# XML-RPC doesn't respond to GET, so we check if the port is open
while ! (exec 3<>/dev/tcp/127.0.0.1/9875) 2>/dev/null; do
    COUNT=$((COUNT+1))
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo "Error: FreeCAD RPC server failed to start within 120 seconds."
        # We continue anyway to let FastAPI show a disconnected state
        break
    fi
    sleep 1
    if [ $((COUNT % 10)) -eq 0 ]; then
        echo "Still waiting for FreeCAD RPC... ($COUNT/$MAX_RETRIES)"
    fi
done

if [ $COUNT -lt $MAX_RETRIES ]; then
    echo "FreeCAD RPC server is ready!"
fi

echo "Starting FastAPI web server on port 7860..."
# Use uvicorn with --log-level info
exec uvicorn app:app --host 0.0.0.0 --port 7860 --log-level info
