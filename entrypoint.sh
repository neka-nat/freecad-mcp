#!/bin/bash
set -e

echo "--- Starting Stlux Environment ---"

# Start Xvfb (Virtual Framebuffer)
echo "Starting Xvfb on display :99..."
Xvfb :99 -screen 0 1280x1024x24 &
export DISPLAY=:99

# Give Xvfb a moment to initialize
sleep 3

# Start FreeCAD in the background
# We ensure the rpc_server is in PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)/addon/FreeCADMCP/rpc_server
echo "Starting FreeCAD with MCP RPC server..."
# The rpc_server.py starts itself and the timer upon import
freecad-cmd --cmd "import rpc_server" &

# Robust wait-for-service logic
echo "Waiting for FreeCAD RPC server (port 9875)..."
MAX_RETRIES=60
COUNT=0
while ! curl -s http://localhost:9875 > /dev/null; do
    COUNT=$((COUNT+1))
    if [ $COUNT -ge $MAX_RETRIES ]; then
        echo "Error: FreeCAD RPC server failed to start within 60 seconds."
        # We continue anyway to let FastAPI show a disconnected state
        break
    fi
    sleep 1
    if [ $((COUNT % 10)) -eq 0 ]; then
        echo "Still waiting... ($COUNT/60)"
    fi
done

if [ $COUNT -lt $MAX_RETRIES ]; then
    echo "FreeCAD RPC server is ready!"
fi

echo "Starting FastAPI web server on port 7860..."
# Use uvicorn directly to ensure it catches signals properly in the container
exec uvicorn app:app --host 0.0.0.0 --port 7860
