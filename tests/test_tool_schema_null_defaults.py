"""Every tool argument that defaults to None must also accept null.

`obj_properties: dict[str, Any] = None` made the schema advertise
`"default": null` on a field typed `"type": "object"`, so a client that
sends the advertised default back failed validation before the tool ran.
"""

import asyncio

from freecad_mcp.server import mcp


def test_null_default_arguments_accept_null():
    rejecting = []
    for tool in asyncio.run(mcp.list_tools()):
        # mcp 2.x renamed Tool.inputSchema to input_schema
        schema = getattr(tool, "input_schema", None) or tool.inputSchema
        for name, prop in schema.get("properties", {}).items():
            if "default" not in prop or prop["default"] is not None:
                continue
            types = [prop.get("type")] + [s.get("type") for s in prop.get("anyOf", [])]
            if "null" not in types:
                rejecting.append(f"{tool.name}.{name}")
    assert rejecting == []
