from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_KINDS = {"prompt", "tool_call", "tool_result", "error", "fix", "verify", "export"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_error(message: str) -> str:
    return re.sub(r"\s+", " ", message.strip().lower())


def parse_transcript_jsonl(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        record = json.loads(line)
        kind = record.get("kind") or record.get("type")
        if kind == "user":
            kind = "prompt"
        if kind == "assistant":
            kind = "verify"
        if kind not in SUPPORTED_KINDS:
            continue

        payload = dict(record.get("payload") or {})
        if "content" in record and "content" not in payload:
            payload["content"] = record["content"]
        if "message" in record and "message" not in payload:
            payload["message"] = record["message"]
        if "tool" in record and "tool" not in payload:
            payload["tool"] = record["tool"]

        events.append({
            "id": record.get("id") or str(uuid.uuid4()),
            "ts": record.get("ts") or _now_iso(),
            "kind": kind,
            "payload": payload,
        })
    return events


def detect_repeated_errors(
    events: Iterable[dict[str, Any]],
    prior_errors: dict[str, int] | None = None,
    threshold: int = 2,
) -> list[dict[str, str]]:
    counts = Counter(prior_errors or {})
    display = {}
    for event in events:
        if event.get("kind") != "error":
            continue
        message = str(event.get("payload", {}).get("message") or event.get("payload", {}).get("content") or "")
        key = normalize_error(message)
        if not key:
            continue
        counts[key] += 1
        display.setdefault(key, message.strip())

    lessons = []
    for key, count in counts.items():
        if count >= threshold and key in display:
            title = display[key]
            lessons.append({
                "id": f"lesson-{uuid.uuid4()}",
                "title": title,
                "body": f"Repeated FreeCAD MCP error seen {count} times: {title}. Patch the workflow and document the workaround in FDM_Reference.md section 13.",
                "severity": "WARN",
            })
    return lessons


def build_memory_delta(
    session_summary: str,
    lessons: list[dict[str, Any]],
    parts: list[dict[str, Any]],
) -> str:
    lines = [
        "# MEMORY_DELTA.md",
        "",
        f"Updated at: {_now_iso()}",
        "",
        "## Session Summary",
        session_summary or "No summary supplied.",
        "",
        "## Lessons",
    ]
    if lessons:
        for lesson in lessons:
            lines.append(f"- [{lesson.get('severity', 'INFO')}] {lesson.get('id')}: {lesson.get('title')}")
    else:
        lines.append("- None")

    lines.extend(["", "## Parts"])
    if parts:
        for part in parts:
            detail = part.get("stl_path") or part.get("fcstd_path") or part.get("notes") or ""
            lines.append(f"- {part.get('name')} ({part.get('status', 'unknown')}): {detail}")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _connect():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install psycopg to write FreeCAD MCP memory into Cortex Postgres.") from exc

    return psycopg.connect(
        host=os.getenv("AXIO_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("AXIO_DB_PORT", "5432")),
        dbname=os.getenv("AXIO_DB_NAME", "axio_cortex"),
        user=os.getenv("AXIO_DB_USER", "axio"),
        password=os.getenv("AXIO_DB_PASSWORD", "local-dev-password"),
    )


def write_session(
    session_id: str,
    user_name: str,
    summary: str,
    events: list[dict[str, Any]],
    lessons: list[dict[str, Any]],
    parts: list[dict[str, Any]],
) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO freecad_mcp.sessions (id, started_at, ended_at, user_name, summary, tags)
                VALUES (%s, now(), now(), %s, %s, ARRAY['freecad_mcp'])
                ON CONFLICT (id) DO UPDATE SET
                    ended_at = EXCLUDED.ended_at,
                    summary = EXCLUDED.summary
                """,
                (session_id, user_name, summary),
            )
            for event in events:
                cur.execute(
                    """
                    INSERT INTO freecad_mcp.events (id, session_id, ts, kind, payload)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (event["id"], session_id, event["ts"], event["kind"], json.dumps(event["payload"])),
                )
            for lesson in lessons:
                cur.execute(
                    """
                    INSERT INTO freecad_mcp.lessons (id, title, body, severity, source_session)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (lesson["id"], lesson["title"], lesson["body"], lesson["severity"], session_id),
                )
            for part in parts:
                cur.execute(
                    """
                    INSERT INTO freecad_mcp.parts (id, name, status, last_session, fcstd_path, stl_path, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                        status = EXCLUDED.status,
                        last_session = EXCLUDED.last_session,
                        fcstd_path = COALESCE(EXCLUDED.fcstd_path, freecad_mcp.parts.fcstd_path),
                        stl_path = COALESCE(EXCLUDED.stl_path, freecad_mcp.parts.stl_path),
                        notes = EXCLUDED.notes
                    """,
                    (
                        part.get("id") or str(uuid.uuid4()),
                        part["name"],
                        part.get("status", "unknown"),
                        session_id,
                        part.get("fcstd_path"),
                        part.get("stl_path"),
                        part.get("notes", ""),
                    ),
                )
        conn.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a FreeCAD MCP transcript into AXIO Cortex memory.")
    parser.add_argument("--transcript", required=True, help="Path to JSONL transcript.")
    parser.add_argument("--summary", default="", help="Human-readable session summary.")
    parser.add_argument("--user", default="AXIO", help="User name for the session row.")
    parser.add_argument("--session-id", default=None, help="Stable session id; defaults to a UUID.")
    parser.add_argument("--delta-out", default="MEMORY_DELTA.md", help="Markdown delta output path.")
    parser.add_argument("--dry-run", action="store_true", help="Write only MEMORY_DELTA.md, not Postgres.")
    args = parser.parse_args(argv)

    transcript = Path(args.transcript).read_text(encoding="utf-8-sig")
    events = parse_transcript_jsonl(transcript)
    lessons = detect_repeated_errors(events)
    parts: list[dict[str, Any]] = []
    session_id = args.session_id or str(uuid.uuid4())
    summary = args.summary or f"FreeCAD MCP session with {len(events)} captured events."

    Path(args.delta_out).write_text(build_memory_delta(summary, lessons, parts), encoding="utf-8")
    if not args.dry_run:
        write_session(session_id, args.user, summary, events, lessons, parts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
