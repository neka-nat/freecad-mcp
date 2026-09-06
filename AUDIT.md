# AUDIT.md - FreeCAD MCP x Codex

Scope: `CLAUDE.md`, `FDM_Reference.md`, `Workflows_Cookbook.md`, `SystemPrompt_FreeCAD_Agent_v3.md`, `ProjectMemory_FreeCAD_Agent.md`, `README.md`, repo code references, and Cortex memory reference at `C:\Users\AXIO\AXIO Model Improvement`.

Cortex baseline observed: compose service `axio-postgres`, container `axio-cortex-postgres`, image `pgvector/pgvector:pg16`, local bind `127.0.0.1:5432`, database `axio_cortex`, schema convention around `sessions`, `messages`, `memory_facts`, `memory_embeddings`, and ingestion/memory entry points through `MemoryManager`, `PostgresMemoryBackend`, `ModeMemorySession`, plus migration/seed scripts. Mirror this later; do not spawn a parallel Postgres.

## Top-5 CRIT

1. `Workflows_Cookbook.md:31` - Multiple recipe code blocks omit the mandatory final `doc.recompute()`.
2. `FDM_Reference.md:138` - The authoritative primitives snippet violates the recompute rule it defines.
3. `FDM_Reference.md:243` - The universal STL export snippet can export stale geometry because it does not recompute before export.
4. `Workflows_Cookbook.md:279` - The overhang-safe arch recipe ends after boolean setup without recomputing.
5. `ProjectMemory_FreeCAD_Agent.md:72` - Project memory still points agents to deprecated `FreeCAD_Python_Scripting_Reference.md`.

## Findings

[CRIT] Workflows_Cookbook.md:31  `new_parametric_part` creates a FreeCAD document in a code block that ends without `doc.recompute()`, conflicting with `SystemPrompt_FreeCAD_Agent_v3.md:36` and `FDM_Reference.md:133`.
  Fix: End the block with `doc.recompute()` or explicitly mark it as non-executable pseudocode; apply the same rule to recipe snippets at lines 41, 65, 74, 83, 177, 185, 233, 254, and 279.

[CRIT] FDM_Reference.md:138  The Part primitives snippet creates Box/Cylinder/Cone objects but ends at `cone.Height = 2.0` with no `doc.recompute()`.
  Fix: Add `doc.recompute()` at the end of the snippet so the single source of truth models its own mandatory pattern.

[CRIT] FDM_Reference.md:243  The universal STL export snippet exports `Final` and prints the path without recomputing first.
  Fix: Insert `doc.recompute()` immediately before `Mesh.export([final], output_path)`.

[CRIT] Workflows_Cookbook.md:279  `add_overhang_safe_arch` builds `ArchPeak`, `Wedge`, and `ChamferedPeak`, then stops after `cut.Base = peak; cut.Tool = wedge`.
  Fix: Add `doc.recompute()` and a `Final` assignment/export path, or state that this is only an intermediate fragment.

[CRIT] ProjectMemory_FreeCAD_Agent.md:72  Project memory still names `FreeCAD_Python_Scripting_Reference.md` as a key reference, while `FDM_Reference.md:4` says it was replaced.
  Fix: Remove the deprecated reference from active memory guidance and point future agents only to `FDM_Reference.md` and `Workflows_Cookbook.md`.

[WARN] Workflows_Cookbook.md:73  `MeshPart.meshToShape` is referenced outside `FDM_Reference.md` pitfall table, violating audit check A3 even though the sentence says to avoid it.
  Fix: Move this warning into the recipe pitfall section only, or phrase the step positively as "stay in mesh booleans".

[WARN] Workflows_Cookbook.md:101  A second `MeshPart.meshToShape()` reference appears outside the authoritative pitfalls table.
  Fix: Consolidate mesh conversion warnings in `FDM_Reference.md` section 13 and cross-reference that section from the cookbook.

[WARN] Workflows_Cookbook.md:15  Recipes are labeled "from real sessions" but individual recipes do not include verified session references.
  Fix: Add a `Verified session:` line to every recipe, using session id, date, artifact, or explicit "unverified" status until provenance is available.

[WARN] Workflows_Cookbook.md:38  Recipe 1 applies bore +0.2 and bolt-clearance +0.4 but omits hex flat-to-flat +0.3 from the same tolerance set.
  Fix: Add hex nut trap flat-to-flat +0.3 to the recipe tolerance step, citing `FDM_Reference.md` section 4.

[WARN] SystemPrompt_FreeCAD_Agent_v3.md:20  The system prompt says to add a new recipe whenever the cookbook does not cover a case, while the cookbook's `add_recipe` process at `Workflows_Cookbook.md:349` says to add recipes only for recurring patterns.
  Fix: Change the system prompt to "document a new recipe only when the pattern recurs or the user asks to persist it."

[WARN] SystemPrompt_FreeCAD_Agent_v3.md:45  The heading says "STANDARD WORKFLOW (5 STEPS)" but the workflow defines Step 1 through Step 6.
  Fix: Rename it to "6 STEPS" or merge export into verification.

[WARN] ProjectMemory_FreeCAD_Agent.md:9  Active memory hardcodes older Windows user paths (`C:\Users\Lenovo User\...`) and a second AXIO Desktop path.
  Fix: Replace path guidance with `os.path.expanduser("~")`-based conventions and mention machine-specific paths only as historical examples.

[WARN] Workflows_Cookbook.md:341  `file_transfer_fallbacks` tells the agent to generate scripts in `/home/claude`, which is Claude-specific and wrong for this Windows/Codex workspace.
  Fix: Replace with a Windows/Codex path convention such as repo-local scripts or `C:\Users\AXIO\Documents\freecad-mcp`.

[WARN] README.md:5  README frames the repository as "control FreeCAD from Claude Desktop" only, while this workspace is now being used through Codex too.
  Fix: Add a short Codex-compatible note that the MCP and docs apply to any agent using the same FreeCAD MCP tools.

[INFO] FDM_Reference.md:259  The only `mesh.translate(FreeCAD.Vector(...))` occurrence found is in the pitfalls table as a known error.
  Fix: Keep it there; do not introduce executable examples using `FreeCAD.Vector` for mesh translation.

[INFO] FDM_Reference.md:60  Bottom-edge guidance is aligned: chamfers are required and bottom fillets are prohibited.
  Fix: Preserve this rule when updating recipes or generated modeling plans.

[INFO] FDM_Reference.md:69  The authoritative tolerance table is internally consistent: clearance +0.2, bolt clearance +0.4, hex flat +0.3.
  Fix: Propagate the full tolerance set into every shortened checklist and recipe summary.

[INFO] CLAUDE.md:57  Cortex Step 0 was satisfied for audit context: the existing pattern is Docker Postgres + pgvector, not a new local memory stack.
  Fix: In the next phase, build `memory/` as an extension/override of the Cortex pattern, not as an independent database.

## A1-A10 Checklist

- A1: Partial pass. Main authority hierarchy is clear, but workflow count and recipe-add policy conflict.
- A2: Fail. Several FreeCAD code snippets do not end with `doc.recompute()`.
- A3: Fail by exact rule. `MeshPart.meshToShape` appears outside the pitfalls table, although as negative guidance.
- A4: Pass. No executable `mesh.translate(FreeCAD.Vector(...))` call found.
- A5: Pass. Bottom-edge fillet prohibition is present and cookbook arch recipe reinforces chamfer/stepped alternatives.
- A6: Partial pass. `FDM_Reference.md` is consistent, but shortened recipe/system summaries omit parts of the tolerance set.
- A7: Fail. Deprecated `FreeCAD_Python_Scripting_Reference.md` remains in active project memory.
- A8: Partial pass. Naming guidance exists, but some recipe fragments do not carry through to `Final`.
- A9: Partial pass. Export snippets mostly use `os.path.expanduser("~")`, but project memory and fallback docs still contain hardcoded/Claude-specific paths.
- A10: Fail. Cookbook recipes lack per-recipe verified session references.

## Stop Point

Per `CLAUDE.md`, stop after audit. Do not silently fix CRIT findings until the user gives go.

## Resolution Status - 2026-06-06

- Fixed CRIT recompute gaps in `FDM_Reference.md` and `Workflows_Cookbook.md`.
- Removed active deprecated-reference guidance from `ProjectMemory_FreeCAD_Agent.md`.
- Rephrased non-authoritative `MeshPart.meshToShape` mentions so the exact banned API remains only in `FDM_Reference.md` pitfalls.
- Added full tolerance set to shortened cookbook and system prompt summaries.
- Added `Verified session:` provenance to every cookbook recipe.
- Added Codex-compatible wording to `README.md`.
- Added repo guardrails in `tests/test_docs_audit.py`; current local run passes.
- Added Cortex-style `memory/` extension and tests in `tests/test_memory_module.py`; current local run passes.
- Created and committed local scaffold at `freecad-mcp-claude/` commit `e688fdb`.
