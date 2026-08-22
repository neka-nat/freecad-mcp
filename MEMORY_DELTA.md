# MEMORY_DELTA.md

Updated at: 2026-06-07

## Session Summary — 2026-06-07

Verified all 5 CRIT fixes in source docs. Confirmed FreeCAD MCP operational via `execute_code` + `get_view` (VerifyTest box rendered). Synced corrected `FDM_Reference.md`, `Workflows_Cookbook.md`, `SystemPrompt_FreeCAD_Agent_v3.md`, and `AUDIT.md` into `freecad-mcp-claude/` scaffold.

## Session Summary — 2026-06-06

Executed the `CLAUDE.md` flow after user approval: audit findings were corrected, documentation guardrails were added, a Cortex-style `freecad_mcp` memory module was built, root manifesto/tech-stack artifacts were generated, and a local GitHub-style scaffold was created under `freecad-mcp-claude/`.

## Lessons

- [WARN] Mutating FreeCAD snippets must include `doc.recompute()` before verification/export; enforced by `tests/test_docs_audit.py`.
- [WARN] Keep exact `MeshPart.meshToShape` mentions only in the authoritative pitfalls table; other docs should say "complex STL mesh-to-shape conversion".
- [WARN] Short tolerance summaries must include the full set: bore +0.2 mm, bolt clearance +0.4 mm, hex flat-to-flat +0.3 mm.
- [INFO] The memory module mirrors AXIO Cortex with schema `freecad_mcp` on the existing `axio-postgres` service and vector(768), not a second database. The schema was applied to the live local DB and ingest/retrieve roundtrip returned session `DB roundtrip verification`.
- [INFO] `freecad:get_view` verification could not be executed in this Codex session because no FreeCAD MCP server/tools were available; `mcp_find freecad` returned no catalog matches.

## Parts

- None touched.

## Artifacts

- `AUDIT.md`
- `TECH_STACK.md`
- `MANIFESTO.md`
- `LESSONS.md`
- `memory/schema.sql`
- `memory/ingest.py`
- `memory/retrieve.py`
- `memory/docker-compose.override.yml`
- `tests/test_docs_audit.py`
- `tests/test_memory_module.py`
- `freecad-mcp-claude/` local scaffold commit `e688fdb`
