import json
import unittest

from memory.ingest import (
    build_memory_delta,
    detect_repeated_errors,
    parse_transcript_jsonl,
)
from memory.retrieve import build_context_preamble


class MemoryModuleTests(unittest.TestCase):
    def test_parse_transcript_jsonl_normalizes_supported_events(self):
        transcript = "\n".join(
            [
                json.dumps({"type": "user", "content": "make a bracket"}),
                json.dumps({"type": "tool_call", "tool": "freecad:execute_code", "payload": {"code": "doc.recompute()"}}),
                json.dumps({"type": "tool_result", "tool": "freecad:get_view", "content": "ok"}),
                json.dumps({"type": "error", "message": "Mesh conversion timed out"}),
            ]
        )

        events = parse_transcript_jsonl(transcript)

        self.assertEqual(["prompt", "tool_call", "tool_result", "error"], [event["kind"] for event in events])
        self.assertEqual("make a bracket", events[0]["payload"]["content"])
        self.assertEqual("freecad:execute_code", events[1]["payload"]["tool"])

    def test_parse_transcript_jsonl_accepts_utf8_bom(self):
        transcript = "\ufeff" + json.dumps({"type": "user", "content": "make a bracket"})

        events = parse_transcript_jsonl(transcript)

        self.assertEqual("prompt", events[0]["kind"])

    def test_detect_repeated_errors_promotes_lesson_at_threshold(self):
        events = [
            {"kind": "error", "payload": {"message": "Mesh conversion timed out"}},
            {"kind": "error", "payload": {"message": "mesh conversion timed out"}},
        ]
        prior_errors = {"mesh conversion timed out": 1}

        lessons = detect_repeated_errors(events, prior_errors=prior_errors, threshold=2)

        self.assertEqual(1, len(lessons))
        self.assertEqual("WARN", lessons[0]["severity"])
        self.assertIn("Mesh conversion timed out", lessons[0]["title"])

    def test_build_memory_delta_lists_lessons_and_parts(self):
        delta = build_memory_delta(
            session_summary="Patched recompute guidance.",
            lessons=[{"id": "lesson-1", "title": "Always recompute", "severity": "WARN"}],
            parts=[{"name": "Bracket", "status": "exported", "stl_path": r"C:\Users\AXIO\Desktop\Bracket_v1.stl"}],
        )

        self.assertIn("Patched recompute guidance.", delta)
        self.assertIn("lesson-1", delta)
        self.assertIn("Bracket", delta)

    def test_build_context_preamble_caps_text_and_orders_sections(self):
        sessions = [{"summary": "Session " + ("x" * 500)} for _ in range(5)]
        lessons = [{"title": "Lesson", "body": "Use doc.recompute().", "severity": "WARN"}]

        preamble = build_context_preamble(sessions, lessons, max_chars=700)

        self.assertLessEqual(len(preamble), 700)
        self.assertLess(preamble.index("Recent sessions"), preamble.index("Relevant lessons"))


if __name__ == "__main__":
    unittest.main()
