| Layer | Tool | Version | Why | Replaceable with |
|---|---|---|---|---|
| Runtime | Codex / Claude-compatible MCP client | Current local desktop session | Agent executes FreeCAD MCP workflows from natural language | Any MCP client that can call `freecad:*` tools |
| Orchestration | MCP | `mcp[cli]>=1.12.2` | Standard tool boundary between agent and FreeCAD | Direct FreeCAD Python console for manual fallback |
| CAD | FreeCAD + FreeCADMCP addon | User-installed FreeCAD, repo addon | Local parametric/mesh modeling with Python automation | Blender Python for mesh-only work |
| Slicer | Bambu Studio | User-installed | Bambu A1 measurement, slicing, AMS/multi-material verification | OrcaSlicer for compatible FDM checks |
| Memory | Postgres + pgvector | `pgvector/pgvector:pg16`, vector(768) | Mirrors AXIO Cortex local-first memory and semantic lessons | JSON files for offline fallback |
| Storage | Local filesystem | Windows workspace + Desktop exports | Keeps `.FCStd`, `.stl`, docs, and deltas owned locally | NAS or encrypted local volume |
| CI | GitHub Actions | `ubuntu-latest`, Python 3.12 | Runs repository and documentation audit checks | Local `python -m unittest discover tests -v` |
