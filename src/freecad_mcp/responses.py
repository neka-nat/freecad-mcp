import json

from mcp.types import ImageContent, TextContent

type ToolResponse = list[TextContent | ImageContent]


def text_response(message: str) -> ToolResponse:
    return [TextContent(type="text", text=message)]


def json_response(data: object) -> ToolResponse:
    return text_response(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def add_screenshot_if_available(
    response: ToolResponse,
    screenshot: str | None,
    only_text_feedback: bool,
) -> ToolResponse:
    if only_text_feedback or screenshot is None:
        return response
    return [*response, ImageContent(type="image", data=screenshot, mimeType="image/png")]
