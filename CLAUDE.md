# CLAUDE.md - FreeCAD MCP

## Project Overview

FreeCAD MCP is a bridge between AI assistants (Claude Desktop, LangChain, Google ADK) and FreeCAD via the Model Context Protocol (MCP). It enables AI-powered CAD design automation through natural language.

**Architecture**: Two-process design connected via XML-RPC on port 9875:
- **MCP Server** (`src/freecad_mcp/server.py`) — runs as a standalone Python process, exposes MCP tools to AI clients
- **RPC Server** (`addon/FreeCADMCP/rpc_server/rpc_server.py`) — runs inside FreeCAD as a workbench addon, executes CAD operations

## Directory Structure

```
src/freecad_mcp/        # MCP server package (entry point: server.py:main)
addon/FreeCADMCP/       # FreeCAD workbench addon
  rpc_server/           # XML-RPC server + helpers (rpc_server.py, parts_library.py, serialize.py)
  InitGui.py            # GUI commands, menu registration, auto-start logic
  Init.py               # Empty module init
examples/               # Integration examples (Google ADK, LangChain)
assets/                 # Demo images and GIFs for README
```

## Tech Stack

- **Language**: Python 3.12+
- **Package manager**: [uv](https://docs.astral.sh/uv/)
- **Build system**: Hatchling
- **MCP framework**: `mcp[cli]>=1.12.2`
- **Dependencies**: `mcp[cli]`, `validators` (see `pyproject.toml`)
- **Lock file**: `uv.lock`
- **FreeCAD side**: PySide (Qt bindings), FreeCAD Python API

## Development Commands

```bash
# Install in dev mode
uv pip install -e .

# Run the MCP server
uv run freecad-mcp

# Run with options
uv run freecad-mcp --only-text-feedback    # skip screenshot data to save tokens
uv run freecad-mcp --host 192.168.1.100    # connect to remote FreeCAD
```

## Testing

There is no automated test suite. Testing is done manually by running the MCP server against a live FreeCAD instance with the addon installed.

## Code Conventions

- **Style**: Snake_case for functions/variables, PascalCase for classes
- **Type hints**: Used throughout (`dict[str, Any]`, `list[str]`, etc.)
- **Async**: MCP server uses async/await via the `mcp` framework
- **Threading**: RPC server uses queue-based communication between XML-RPC thread and FreeCAD's GUI thread (500ms polling)
- **Logging**: Standard `logging` module
- **No linter/formatter config**: No ruff, black, flake8, or mypy configuration present

## Key Files

| File | Purpose |
|------|---------|
| `src/freecad_mcp/server.py` | MCP server — defines all MCP tools, CLI arg parsing, XML-RPC client |
| `addon/FreeCADMCP/rpc_server/rpc_server.py` | RPC server — all FreeCAD operations (create/edit/delete objects, screenshots, FEM) |
| `addon/FreeCADMCP/rpc_server/serialize.py` | Serializes FreeCAD objects to dicts for transport |
| `addon/FreeCADMCP/rpc_server/parts_library.py` | Parts library integration |
| `addon/FreeCADMCP/InitGui.py` | FreeCAD GUI: workbench, menu commands, auto-start |
| `pyproject.toml` | Project metadata, dependencies, entry point |

## MCP Tools Exposed

The server exposes these tools to AI clients: `create_document`, `create_object`, `edit_object`, `delete_object`, `execute_code`, `get_view`, `insert_part_from_library`, `get_objects`, `get_object`, `get_parts_list`, `list_documents`.

Also provides an `asset_creation_strategy` prompt for CAD design guidance.

## Important Patterns

- **Settings persistence**: JSON file (`freecad_mcp_settings.json`) in FreeCAD's config directory stores auto-start, remote connection, and allowed IP settings
- **Remote connections**: IP filtering with CIDR subnet support via `validators` library
- **Screenshot handling**: Base64-encoded images, graceful fallback for unsupported view types (TechDraw, Spreadsheet)
- **FEM support**: Creates FEM analyses with constraints, materials, and Gmsh mesh generation
- **Object references**: FreeCAD objects are referenced by label (string name) across the RPC boundary

## CI/CD

No CI/CD pipeline is configured (no GitHub Actions or similar).

## Version

Current version: **0.1.16** (defined in `pyproject.toml`)
License: MIT
