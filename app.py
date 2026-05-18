import os
import time
import xmlrpc.client
import socket
import re
import base64
from fastapi import FastAPI, Request, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Stlux")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("KING OF THE CADSTLE online.")
    yield

app = FastAPI(lifespan=lifespan)

API_KEY_NAME = "Authorization"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(header_key: str = Security(api_key_header)):
    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        # If no token set in environment, allow access (dev mode)
        return header_key

    if header_key and (header_key == f"Bearer {hf_token}" or header_key == hf_token):
        return header_key

    raise HTTPException(
        status_code=403, detail="Could not validate credentials"
    )

# Mount directories
os.makedirs("static", exist_ok=True)
os.makedirs("exports", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/exports", StaticFiles(directory="exports"), name="exports")

class CommandRequest(BaseModel):
    command: str

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = "static/index.html"
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>Stlux</h1><p>Static files not found.</p>", status_code=404)
    with open(index_path, "r") as f:
        return f.read()

@app.get("/health")
async def health_check():
    try:
        socket.setdefaulttimeout(5)
        client = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        if client.ping():
            return {"status": "healthy", "freecad": "connected"}
    except Exception as e:
        return {"status": "degraded", "freecad": "disconnected", "error": str(e)}
    return {"status": "degraded", "freecad": "unresponsive"}

@app.post("/execute")
async def execute_command(request: CommandRequest, api_key: str = Security(get_api_key)):
    return await _freecad_rpc(request.command, is_python=True)

@app.post("/agent")
async def agent_command(request: CommandRequest, api_key: str = Security(get_api_key)):
    """
    AI Operator endpoint.
    In a production HF Space, this would call an LLM (like Llama-3 or GPT-4)
    via an API key to translate NL to FreeCAD Python.
    Here, we provide a robust rule-based parametric engine as a baseline.
    """
    cmd = request.command.lower()
    logger.info(f"King Command: {cmd}")

    py_code = "import FreeCAD, os, Mesh, MeshPart, Part, math\n"
    py_code += "doc = FreeCAD.ActiveDocument if FreeCAD.ActiveDocument else FreeCAD.newDocument('StluxDoc')\n"

    # PARAMETRIC ENGINE
    if "gear" in cmd:
        teeth = 20
        match = re.search(r'(\d+)\s*(?:teeth|tooth)', cmd)
        if match: teeth = int(match.group(1))
        py_code += f"""
import InvoluteGear
gear = InvoluteGear.makeInvoluteGear('Gear')
gear.NumberOfTeeth = {teeth}
gear.Module = 2
doc.recompute()
"""
    elif "crown" in cmd:
        size = 50
        match = re.search(r'(\d+)', cmd)
        if match: size = int(match.group(1))
        py_code += f"""
b = doc.addObject("Part::Cylinder", "Base")
b.Radius = {size/2}
b.Height = {size/4}
for i in range(8):
    p = doc.addObject("Part::Box", "Point" + str(i))
    p.Length = {size/8}
    p.Width = {size/8}
    p.Height = {size/2}
    p.Placement = FreeCAD.Placement(FreeCAD.Vector({size/2.5}*math.cos(i*math.pi/4), {size/2.5}*math.sin(i*math.pi/4), {size/4}), FreeCAD.Rotation(FreeCAD.Vector(0,0,1), 45))
doc.recompute()
"""
    elif "box" in cmd or "cube" in cmd:
        size = 10
        match = re.search(r'(\d+)', cmd)
        if match: size = int(match.group(1))
        py_code += f"obj = doc.addObject('Part::Box', 'Box'); obj.Height = {size}; obj.Width = {size}; obj.Length = {size};\n"
    else:
        # Fallback: Treat as direct script if it contains 'FreeCAD' or 'doc'
        if "freecad" in cmd or "doc." in cmd or "import" in cmd:
            py_code += f"{request.command}\n"
        else:
            return {"status": "error", "message": "The King doesn't understand that command yet. Try 'Build a 30-tooth gear' or provide a Python script."}

    # POST-PROCESSING: SCREENSHOT -> REPAIR -> EXPORT
    filename = f"model_{int(time.time())}.stl"
    img_name = f"preview_{int(time.time())}.png"

    py_code += f"""
doc.recompute()
# Take Screenshot
import FreeCADGui
view = FreeCADGui.ActiveDocument.ActiveView
if view:
    view.viewIsometric()
    view.fitAll()
    view.saveImage(os.path.join('exports', '{img_name}'), 800, 600, 'Current')

# Export & Repair
objs = doc.Objects
if objs:
    mesh_list = []
    for o in objs:
        if hasattr(o, 'Shape'):
            mesh_list.append(MeshPart.meshFromShape(Shape=o.Shape, LinearDeflection=0.1, AngularDeflection=0.523599))
    if mesh_list:
        final_mesh = Mesh.Mesh()
        for m in mesh_list: final_mesh.addMesh(m)
        final_mesh.fixIdenticalPoints(); final_mesh.fixDegenerations(); final_mesh.removeDuplicatedFaces(); final_mesh.fillHoles()
        final_mesh.write(os.path.join('exports', '{filename}'))
        print(f"RESULT:{{'{filename}'}}:{{'{img_name}'}}")
"""

    result = await _freecad_rpc(py_code, is_python=True)
    msg = result.get("message", "")

    res_match = re.search(r'RESULT:(\S+):(\S+)', msg)
    if res_match:
        stl = res_match.group(1).replace("'", "")
        img = res_match.group(2).replace("'", "")
        return {
            "status": "success",
            "message": "The King has spoken! Your hyper-parametric design is ready.",
            "file": f"/exports/{stl}",
            "image": f"/exports/{img}"
        }

    return {"status": "success", "message": "Command executed.", "details": msg}

async def _freecad_rpc(command: str, is_python: bool = False):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            socket.setdefaulttimeout(60)
            client = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
            result = client.execute_code(command)
            if result.get("success"):
                return {"status": "success", "message": result.get("message", "Done")}
            else:
                return {"status": "error", "message": result.get("error", "Failed")}
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
