# CLAUDE.md — FreeCAD MCP × Claude · Audit & Build

## Context
- **Repo**: project root (this dir). Windows host.
- **Domain docs**: `FDM_Reference.md`, `Workflows_Cookbook.md`, system prompt v3.0.
- **Memory reference**: `C:\Users\AXIO\AXIO Model Improvement` (Cortex docker). Read first, mirror its pattern. Do not invent a parallel stack.
- **STL outputs**: `~/Desktop`. Paths: raw strings (`r"C:\..."`).

## Mission (in order)
1. Audit + debug
2. Wire self-training memory (Cortex-style)
3. Produce `TECH_STACK.md`, `MANIFESTO.md`, GitHub repo scaffold

---

## 1 · Audit
Scan repo. Emit `AUDIT.md`. Findings format:
```
[CRIT|WARN|INFO] <file>:<line>  <summary>
  Fix: <imperative>
```

Checks:

| # | Check |
|---|---|
| A1 | `FDM_Reference.md` vs `Workflows_Cookbook.md` vs system prompt — flag contradictions |
| A2 | Every `freecad:execute_code` snippet ends with `doc.recompute()` |
| A3 | Zero refs to `MeshPart.meshToShape` outside the pitfalls table |
| A4 | Zero `mesh.translate(FreeCAD.Vector(...))` calls (must be floats) |
| A5 | Bottom-edge fillets absent; chamfers used instead |
| A6 | Tolerances consistent: bore +0.2, bolt clearance +0.4, hex flat +0.3 |
| A7 | Dead refs to deprecated files (`Bambu_A1_FDM_Design_Rules.txt`, old `Design_Guide.pdf`, `FreeCAD_Python_Scripting_Reference.md`) |
| A8 | Naming: `PartName_vN.stl`, objects `Base`/`CutA`/`Final` |
| A9 | Hardcoded paths vs `os.path.expanduser("~")` |
| A10 | Every cookbook recipe has at least one verified session reference |

Stop after audit. Present top-5 CRIT. Wait for go.

---

## 2 · Debug
Trigger: CRIT finding OR user reports failed session.

1. Reproduce: pull failing block + inputs from session log
2. Match `FDM_Reference.md §13` (pitfalls). Known → patch with documented workaround
3. New → instrument, fix, append to §13 **and** memory `lessons`
4. Verify with `freecad:get_view`
5. Commit: `fix: <short>` body cites lesson id

Never: re-introduce `MeshPart.meshToShape`, fillets on bottom edges, skip `doc.recompute()`.

---

## 3 · Memory Module (self-training)

**Step 0**: read `C:\Users\AXIO\AXIO Model Improvement`. Identify Cortex container name, DB engine, schema convention, ingestion entry point. Mirror, don't fork.

**Assumed default if Cortex = Postgres + pgvector** (verify against actual; adjust):

Add namespace `freecad_mcp` in existing Cortex container. Schema:

```sql
sessions(id pk, started_at, ended_at, user, summary, tags text[])
events  (id pk, session_id fk, ts, kind, payload jsonb, embedding vector(1536))
lessons (id pk, created_at, title, body, severity, source_session, embedding vector(1536))
parts   (id pk, name, status, last_session, fcstd_path, stl_path, notes)
```
`kind` ∈ {prompt, tool_call, tool_result, error, fix, verify, export}

**Ingest loop** (end of every Code invocation):
1. Parse transcript → `events`
2. Diff vs prior sessions → detect repeated errors
3. Error repeated ≥2 sessions → auto-insert `lessons` (severity ≥ WARN)
4. Embed `lessons.body`
5. Update `parts` row for any part touched
6. Write `MEMORY_DELTA.md` (human-readable)

**Retrieve on next start**:
- Last 5 sessions for current user
- Top-10 nearest `lessons` by embedding of incoming prompt
- Inject as context preamble. Cap 4k tokens, drop oldest.

**Deliverable**: `memory/` containing `schema.sql`, `ingest.py`, `retrieve.py`, `docker-compose.override.yml`. Extend Cortex compose, do not spawn a second Postgres.

---

## 4 · `TECH_STACK.md`
One page. Table only:

| Layer | Tool | Version | Why | Replaceable with |
|---|---|---|---|---|

Layers: Runtime (Claude) · Orchestration (MCP) · CAD (FreeCAD) · Slicer (Bambu Studio) · Memory (Postgres+pgvector) · Storage (FS) · CI (GH Actions).

---

## 5 · `MANIFESTO.md`
≤1 page. Sections:
- **Premise** — 1 paragraph: natural-language CAD for FDM, owned not rented
- **Principles** — ≤5 bullets: local-first, FDM-tuned, self-correcting, cross-session memory, open
- **Non-goals** — 3 bullets: not Fusion replacement, no CAM, no cloud
- **Versioning** — semver, current from latest git tag

Tone: terse, technical. No marketing copy.

---

## 6 · GitHub repo scaffold
Build locally. Do **not** `git push` — leave remote to user.

```
freecad-mcp-claude/
├── README.md                  ← MANIFESTO excerpt + quickstart
├── TECH_STACK.md
├── MANIFESTO.md
├── AUDIT.md
├── LESSONS.md                 ← mirrors memory.lessons
├── docs/
│   ├── FDM_Reference.md
│   └── Workflows_Cookbook.md
├── prompts/system_prompt_v3.md
├── memory/
│   ├── schema.sql
│   ├── ingest.py
│   ├── retrieve.py
│   └── docker-compose.override.yml
├── examples/                  ← one .py per cookbook recipe
├── .github/workflows/audit.yml
└── LICENSE                    ← MIT default, confirm with user
```

Init:
```bash
git init && git add -A && git commit -m "chore: initial scaffold from audit"
```

---

## Conventions
- Spanish for user-facing prose; English for code, identifiers, commits
- Commits: Conventional Commits (`feat:`/`fix:`/`docs:`/`chore:`)
- Cite `FDM_Reference.md §<n>` whenever applying a rule
- Never silently fix CRIT — surface in audit, ask

## First-run sequence
1. Read repo + `C:\Users\AXIO\AXIO Model Improvement`
2. Emit `AUDIT.md`, present top-5 CRIT, **wait**
3. Debug pass after go
4. Build memory module; verify ingest+retrieve roundtrip
5. Generate `TECH_STACK.md`, `MANIFESTO.md`, repo scaffold
6. Write `MEMORY_DELTA.md` for this run
