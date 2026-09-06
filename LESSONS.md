# LESSONS.md

- [WARN] Always end mutating FreeCAD Python snippets with `doc.recompute()` before exporting or verifying.
- [WARN] Keep complex STL work in mesh-land; avoid mesh-to-shape conversion except as a documented pitfall.
- [WARN] Use full FDM tolerance language everywhere: bore +0.2 mm, bolt clearance +0.4 mm, hex flat-to-flat +0.3 mm.
- [WARN] Use repo-local or Windows-visible paths for FreeCAD scripts; do not refer to agent sandbox paths as runnable FreeCAD locations.
- [INFO] Mirror AXIO Cortex Postgres + pgvector with schema `freecad_mcp`; do not spawn a second Postgres stack.
