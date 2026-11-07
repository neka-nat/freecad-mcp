"""Every tool argument that defaults to None must also accept null.

`obj_properties: dict[str, Any] = None` made the schema advertise
`"default": null` on a field typed `"type": "object"`, so a client that
sends the advertised default back failed validation before the tool ran.
"""

import asyncio
from typing import Any

import pytest

from freecad_mcp import server
from freecad_mcp.server import mcp


def test_null_default_arguments_accept_null() -> None:
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


@pytest.mark.parametrize("properties", [None, {}, {"Length": 12}, "omitted"])
def test_create_object_accepts_null_omitted_and_object_properties(
    monkeypatch: pytest.MonkeyPatch, properties: Any,
) -> None:
    sent = []

    class Connection:
        def create_object(self, doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
            sent.append(obj_data)
            return {"success": True, "object_name": obj_data["Name"]}

    monkeypatch.setattr(server, "get_freecad_connection", lambda: Connection())
    arguments = {
        "doc_name": "Doc", "obj_type": "Part::Box", "obj_name": "Box",
        "include_screenshot": False,
    }
    if properties != "omitted":
        arguments["obj_properties"] = properties
    asyncio.run(mcp.call_tool("create_object", arguments))
    assert len(sent) == 1
    expected = {} if properties == "omitted" else properties or {}
    assert sent[0]["Properties"] == expected
