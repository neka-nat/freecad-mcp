"""Tests for the response-formatting helpers."""

import json

from mcp.types import ImageContent, TextContent

from freecad_mcp.responses import add_screenshot_if_available, json_response, text_response


def test_text_response_wraps_message():
    res = text_response("hello")
    assert res == [TextContent(type="text", text="hello")]


def test_json_response_serializes_and_is_unicode_safe():
    res = json_response({"name": "café", "n": 1})
    assert isinstance(res[0], TextContent)
    parsed = json.loads(res[0].text)
    assert parsed == {"name": "café", "n": 1}


def test_json_response_falls_back_to_str_for_unserializable():
    class Weird:
        def __str__(self):
            return "weird-value"

    res = json_response({"obj": Weird()})
    assert "weird-value" in res[0].text


def test_add_screenshot_appends_image():
    base = text_response("ok")
    res = add_screenshot_if_available(base, "BASE64", only_text_feedback=False)
    assert len(res) == 2
    assert isinstance(res[1], ImageContent)
    assert res[1].data == "BASE64"


def test_add_screenshot_skipped_when_only_text_feedback():
    base = text_response("ok")
    res = add_screenshot_if_available(base, "BASE64", only_text_feedback=True)
    assert res == base


def test_add_screenshot_skipped_when_none():
    base = text_response("ok")
    res = add_screenshot_if_available(base, None, only_text_feedback=False)
    assert res == base
