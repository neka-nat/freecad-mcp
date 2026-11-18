"""Feedback that agents leave about this server, kept in a local JSONL file.

Each call appends one JSON object per line, so the file can be read with
``jq`` or loaded line by line. Nothing is sent anywhere: the file stays on
the machine running the MCP server.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .version import PROTOCOL_VERSION, __version__

FeedbackKind = Literal[
    "bug", "missing_feature", "confusing", "workaround", "docs", "praise", "other"
]
FeedbackSeverity = Literal["low", "medium", "high"]

FEEDBACK_FILE_ENV = "FREECAD_MCP_FEEDBACK_FILE"
MAX_SUMMARY_CHARS = 300
MAX_FIELD_CHARS = 20_000

_write_lock = threading.Lock()


def default_feedback_path() -> Path:
    """The feedback file: $FREECAD_MCP_FEEDBACK_FILE, else ~/.freecad-mcp/feedback.jsonl."""
    configured = os.environ.get(FEEDBACK_FILE_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".freecad-mcp" / "feedback.jsonl"


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def build_entry(
    kind: FeedbackKind,
    summary: str,
    details: str = "",
    tool_name: str | None = None,
    workaround: str = "",
    severity: FeedbackSeverity = "medium",
    client: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the record written for one piece of feedback."""
    entry: dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "severity": severity,
        "summary": _clip(summary, MAX_SUMMARY_CHARS),
        "server_version": __version__,
        "protocol_version": PROTOCOL_VERSION,
    }
    if tool_name:
        entry["tool"] = _clip(tool_name, 100)
    if details.strip():
        entry["details"] = _clip(details, MAX_FIELD_CHARS)
    if workaround.strip():
        entry["workaround"] = _clip(workaround, MAX_FIELD_CHARS)
    if client:
        entry["client"] = client
    return entry


def append_entry(entry: dict[str, Any], path: Path) -> None:
    """Append ``entry`` as one line of ``path``, creating its folder if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    with _write_lock, path.open("a", encoding="utf-8") as fp:
        fp.write(line)
