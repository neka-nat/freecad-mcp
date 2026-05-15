#!/bin/bash

# Start Xvfb
Xvfb :99 -screen 0 1280x1024x24 &
export DISPLAY=:99

# Give Xvfb a moment to start
sleep 2

# Start FreeCAD in the background with a script to ensure RPC server starts
# We assume the addon is installed and configured to auto-start or we start it here
freecad --cmd "import rpc_server; rpc_server.start_rpc_server()" &

# Wait for RPC server to be ready
echo "Waiting for FreeCAD RPC server..."
for i in {1..30}; do
    if curl -s http://localhost:9875 > /dev/null; then
        echo "FreeCAD RPC server is ready!"
        break
    fi
    sleep 1
done

# Start the FastAPI web server
python3 app.py
