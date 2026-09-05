"""Smoke test for FreeCAD MCP spatial comments.

Prereqs:
- FreeCAD is running with the FreeCADMCP addon loaded.
- RPC server is started from the FreeCAD MCP toolbar or auto-start is enabled.
"""

import sys
import xmlrpc.client
from typing import cast

HOST = "localhost"
PORT = 9875
DOC = "MCPSpatialComments"

server = xmlrpc.client.ServerProxy(f"http://{HOST}:{PORT}", allow_none=True)
if not server.ping():
    print("RPC server is not responding.")
    sys.exit(2)

documents = cast(list[str], server.list_documents())
if DOC in documents:
    server.execute_code(f"import FreeCAD; FreeCAD.closeDocument('{DOC}')")

print(server.create_document(DOC))
print(
    server.create_object(
        DOC,
        {
            "Name": "Body",
            "Type": "Part::Box",
            "Properties": {"Length": 20, "Width": 10, "Height": 10},
        },
    )
)

comment = server.create_spatial_comment(
    DOC,
    {
        "text": "Make the top face more oval.",
        "kind": "edit_request",
        "author": "user",
        "anchor": {
            "type": "subelement",
            "object_name": "Body",
            "subelement": "Face6",
            "position": {"x": 10, "y": 5, "z": 10},
        },
    },
)
print(comment)
print(server.list_spatial_comments(DOC, {}))
