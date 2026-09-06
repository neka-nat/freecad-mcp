from __future__ import annotations

import argparse
import os
from typing import Any


def build_context_preamble(
    sessions: list[dict[str, Any]],
    lessons: list[dict[str, Any]],
    max_chars: int = 4000,
) -> str:
    def clip(value: str, limit: int) -> str:
        value = value.strip()
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 3)].rstrip() + "..."

    session_limit = max(40, max_chars // 12)
    lesson_limit = max(60, max_chars // 8)
    lines = ["# FreeCAD MCP Memory Context", "", "## Recent sessions"]
    if sessions:
        for session in sessions[:5]:
            lines.append(f"- {clip(str(session.get('summary', '')), session_limit)}")
    else:
        lines.append("- None")

    lines.extend(["", "## Relevant lessons"])
    if lessons:
        for lesson in lessons[:10]:
            severity = lesson.get("severity", "INFO")
            title = lesson.get("title", "")
            body = lesson.get("body", "")
            lines.append(f"- [{severity}] {clip(str(title), lesson_limit)}: {clip(str(body), lesson_limit)}")
    else:
        lines.append("- None")

    preamble = "\n".join(lines).strip() + "\n"
    if len(preamble) <= max_chars:
        return preamble
    return preamble[: max(0, max_chars - len("\n[truncated]\n"))].rstrip() + "\n[truncated]\n"


def _connect():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("Install psycopg to retrieve FreeCAD MCP memory from Cortex Postgres.") from exc

    return psycopg.connect(
        host=os.getenv("AXIO_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("AXIO_DB_PORT", "5432")),
        dbname=os.getenv("AXIO_DB_NAME", "axio_cortex"),
        user=os.getenv("AXIO_DB_USER", "axio"),
        password=os.getenv("AXIO_DB_PASSWORD", "local-dev-password"),
        row_factory=dict_row,
    )


def retrieve_recent_context(limit_sessions: int = 5, limit_lessons: int = 10) -> str:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT summary
                FROM freecad_mcp.sessions
                ORDER BY COALESCE(ended_at, started_at) DESC
                LIMIT %s
                """,
                (limit_sessions,),
            )
            sessions = list(cur.fetchall())
            cur.execute(
                """
                SELECT title, body, severity
                FROM freecad_mcp.lessons
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit_lessons,),
            )
            lessons = list(cur.fetchall())
    return build_context_preamble(sessions, lessons)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieve a FreeCAD MCP memory preamble from AXIO Cortex.")
    parser.add_argument("--max-chars", type=int, default=4000)
    args = parser.parse_args(argv)
    print(retrieve_recent_context()[: args.max_chars])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
