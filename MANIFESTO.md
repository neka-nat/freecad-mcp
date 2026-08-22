# MANIFESTO.md

## Premise

Natural-language CAD for FDM should be owned, local, inspectable, and tuned to the printer actually on the bench. This project turns FreeCAD plus MCP into a Bambu Lab A1-oriented modeling workflow where the agent follows FDM constraints, writes reproducible Python, exports local STL files, and learns from repeated failures without renting the design process from a cloud CAD platform.

## Principles

- Local-first: source files, memory, exports, and verification notes stay on the user's machine.
- FDM-tuned: geometry choices follow Bambu A1 constraints before aesthetics or generic CAD habits.
- Self-correcting: repeated errors become documented lessons and tests.
- Cross-session memory: sessions, events, lessons, and parts persist through the Cortex Postgres backend.
- Open: repo docs, scripts, and scaffold are plain files that another agent can audit.

## Non-goals

- Not a Fusion 360 replacement.
- No CAM.
- No cloud dependency.

## Versioning

Semver. Current version: `0.1.16` from `pyproject.toml`; no local git tag was present during the 2026-06-06 audit run.
