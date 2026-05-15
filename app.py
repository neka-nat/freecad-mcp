import os
import subprocess
import time
import asyncio
import xmlrpc.client
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Stlux")

app = FastAPI()

# Mount static files
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

class CommandRequest(BaseModel):
    command: str

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("static/index.html", "r") as f:
        return f.read()

def get_freecad_client():
    return xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)

@app.post("/execute")
async def execute_command(request: CommandRequest):
    logger.info(f"Executing command: {request.command}")

    try:
        client = get_freecad_client()
        # In a real integration, we might want to use LLM to translate
        # natural language to FreeCAD Python code.
        # For now, we'll treat the command as Python code if it starts with 'import'
        # or just try to execute it as a simple script.

        if request.command.startswith("import"):
            code = request.command
        else:
            # Wrap simple commands in a basic FreeCAD document creation if needed
            code = f"""
import FreeCAD
doc = FreeCAD.ActiveDocument if FreeCAD.ActiveDocument else FreeCAD.newDocument("StluxDoc")
{request.command}
doc.recompute()
"""

        result = client.execute_code(code)

        if result.get("success"):
            return {"status": "success", "message": result.get("message", "Executed successfully")}
        else:
            return {"status": "error", "message": result.get("error", "Unknown error")}

    except Exception as e:
        logger.error(f"Error communicating with FreeCAD: {e}")
        return {"status": "error", "message": str(e)}

@app.on_event("startup")
async def startup_event():
    logger.info("Stlux application starting...")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
