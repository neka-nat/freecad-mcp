"""Nested property values sent as JSON strings reach the addon as objects (#156)."""

import json
from typing import Any

from freecad_mcp.operations import create_object_operation, edit_object_operation


PLACEMENT = {"Base": {"x": 30, "y": 30, "z": -5}}


class _RecordingConnection:
    def __init__(self) -> None:
        self.sent: dict[str, Any] = {}

    def create_object(self, doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        self.sent = obj_data
        return {"success": True, "object_name": obj_data["Name"]}

    def edit_object(
        self, doc_name: str, obj_name: str, obj_data: dict[str, Any]
    ) -> dict[str, Any]:
        self.sent = obj_data
        return {"success": True, "object_name": obj_name}


def _create(properties: dict[str, Any]) -> dict[str, Any]:
    conn = _RecordingConnection()
    create_object_operation(
        conn, True, "Doc", "Part::Cylinder", "Hole", None, properties
    )
    return conn.sent["Properties"]


def test_create_decodes_stringified_placement() -> None:
    sent = _create({"Radius": 8, "Placement": json.dumps(PLACEMENT)})

    assert sent == {"Radius": 8, "Placement": PLACEMENT}


def test_edit_decodes_stringified_placement() -> None:
    conn = _RecordingConnection()
    edit_object_operation(conn, True, "Doc", "Hole", {"Placement": json.dumps(PLACEMENT)})

    assert conn.sent["Properties"] == {"Placement": PLACEMENT}


def test_decodes_strings_nested_inside_decoded_values() -> None:
    sent = _create({
        "Placement": {"Base": json.dumps({"x": 1, "y": 2, "z": 3})},
        "References": json.dumps([{"object_name": "Box", "face": "Face1"}]),
        "ViewObject": json.dumps({"ShapeColor": "[0.5, 0.5, 0.5]"}),
    })

    assert sent == {
        "Placement": {"Base": {"x": 1, "y": 2, "z": 3}},
        "References": [{"object_name": "Box", "face": "Face1"}],
        "ViewObject": {"ShapeColor": [0.5, 0.5, 0.5]},
    }


def test_leaves_plain_strings_alone() -> None:
    properties = {
        "Base": "Box",
        "Label": "{not json",
        "Material": {"YoungModulus": "210 GPa"},
        "Text": '"quoted"',
        "Points": [{"x": 0, "y": 0, "z": 0}],
    }

    assert _create(properties) == properties
