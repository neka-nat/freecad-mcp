# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FreeCAD MCP (Model Context Protocol) server that lets an MCP client (e.g. Claude Desktop) drive FreeCAD. The system has **two halves that run in separate processes**:

1. **MCP server** (`src/freecad_mcp/`) — a stdio MCP server launched by the client via `uvx freecad-mcp`. It exposes MCP tools and forwards each one to FreeCAD over XML-RPC.
2. **FreeCAD addon** (`addon/FreeCADMCP/`) — a FreeCAD workbench that the user installs into FreeCAD's `Mod/` directory. It runs an XML-RPC server (default `localhost:9875`) inside the FreeCAD GUI process.

These halves only communicate over XML-RPC. There is no shared code or imports between `src/` and `addon/`; the wire contract is plain dicts/lists. When you change a tool's behavior you almost always have to edit **both** sides.

## Architecture

### Request flow

```
MCP client → server.py @mcp.tool → operations/core.py → freecad_client.py (XML-RPC client)
  → [process boundary] → rpc_server.py FreeCADRPC method → dispatch_to_gui → GUI-thread handler
```

- `server.py` — declares every `@mcp.tool()`. Tool functions are thin: they call `get_freecad_connection()` and delegate to an `*_operation` in `operations/core.py`. The extensive docstrings/examples here are the tool schemas the model sees, so keep them accurate.
- `operations/core.py` — one `*_operation` function per tool. Owns error handling (wraps the XML-RPC call in try/except, returns `text_response`/`json_response`) and the screenshot-on-success behavior gated by `only_text_feedback`.
- `freecad_client.py` — `FreeCADConnection`, a 1:1 wrapper over the XML-RPC methods. `_TimeoutTransport` gives every call a socket timeout so a frozen FreeCAD GUI can't hang the MCP client forever.
- `responses.py` — `ToolResponse` helpers. `add_screenshot_if_available` appends an `ImageContent` PNG unless `only_text_feedback` is set.
- `server_state.py` — `ServerState` singleton holding the live connection plus the `--only-text-feedback` / `--host` CLI flags.

### The GUI-thread dispatch model (most important addon concept)

The XML-RPC server runs in a **background thread**, but FreeCAD document and `FreeCADGui` APIs are **only safe on the main GUI thread**. `rpc_server/gui_dispatch.py` bridges this:

- Every handler that touches documents/GUI runs its work via `dispatch_to_gui(lambda: ...)`, which enqueues the callable, wakes the GUI thread with a Qt signal (`_WakeSignal`, queued connection), and blocks on a per-call response queue until the result comes back or it times out.
- `process_gui_tasks` drains the queue on the GUI thread. It guards against re-entrancy, defers while the mouse is held / a modal or popup is open (so MCP work never interrupts 3D navigation), and reschedules itself every 500 ms as a heartbeat fallback.
- Handler return contract: GUI-thread helpers return `True` on success or an **error string** on failure. `_ok()`/`_err()` in `rpc_server.py` convert that into the `{"success": bool, ...}` dict sent over the wire.

`execute_code` runs on the GUI thread (safe for document mutation, bounded by `EXECUTE_CODE_TIMEOUT`). `execute_code_async` runs on a **separate background thread** and must NOT touch documents/GUI — it's only for heavy pure-OCCT geometry. This distinction is load-bearing; preserve it when editing either tool.

### Addon module breakdown (`addon/FreeCADMCP/rpc_server/`)

- `rpc_server.py` — `FreeCADRPC` (all RPC methods) + `start_rpc_server`/`stop_rpc_server`. Binds `0.0.0.0` when remote is enabled, else `127.0.0.1`.
- `object_factory.py` — `create_object` dispatch: FEM mesh (Gmsh) vs generic `Fem::*` (`ObjectsFem.makeXxx`) vs arbitrary `doc.addObject`. Handles FreeCAD 0.x↔1.x property-name remapping (`Part`/`Shape`, `ElementSizeMax`/`CharacteristicLengthMax`).
- `property_mapper.py` — applies the JSON `Properties` dict onto a FreeCAD object (Placement, Vectors, colors, etc.).
- `serialize.py` — turns a FreeCAD object into the JSON dict returned by `get_object(s)`.
- `view_manager.py` — screenshot/camera handling for `get_active_screenshot`.
- `fem_executor.py` — CalculiX solver run for `run_fem_analysis`.
- `ip_filter.py` — `FilteredXMLRPCServer` + `validate_allowed_ips` enforcing the allow-list for remote connections.
- `settings.py` — JSON persistence (`freecad_mcp_settings.json` in FreeCAD's user app-data dir): `remote_enabled`, `allowed_ips`, `auto_start_rpc`.
- `commands.py` / `InitGui.py` — workbench toolbar/menu commands (Start/Stop/Auto-Start/Remote/Allowed-IPs) and auto-start wiring.

## Adding or changing a tool

A new MCP tool typically touches four files in this order:
1. `addon/FreeCADMCP/rpc_server/rpc_server.py` — add the `FreeCADRPC` method (wrap GUI work in `dispatch_to_gui`, return a result dict).
2. `src/freecad_mcp/freecad_client.py` — add the matching `self.server.<method>(...)` wrapper.
3. `src/freecad_mcp/operations/core.py` — add the `*_operation` (error handling + screenshot policy) and export it from `operations/__init__.py`.
4. `src/freecad_mcp/server.py` — add the `@mcp.tool()` with a thorough docstring/examples, and document it in `README.md`'s Tools list.

Because the addon installs as a copy in FreeCAD's `Mod/` dir, addon edits require reinstalling (re-copy) and restarting FreeCAD to take effect.

## Commands

This project uses **uv** (Python ≥ 3.12). There is no test suite, linter config, or build script checked in.

```bash
# Run the MCP server locally against a running FreeCAD addon
uv run freecad-mcp
uv run freecad-mcp --only-text-feedback     # skip screenshots, save tokens
uv run freecad-mcp --host 192.168.1.100      # connect to a remote FreeCAD

# Install the addon into FreeCAD (Linux Ubuntu/Debian example; see README for other OSes)
cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/
# then restart FreeCAD, switch to the "MCP Addon" workbench, run "Start RPC Server"

# Build the distributable package
uv build
```

The addon code cannot run outside FreeCAD (it imports `FreeCAD`, `FreeCADGui`, `PySide`, `ObjectsFem`), so iterate on it inside a running FreeCAD instance and watch its Report View / console for the `FreeCAD.Console.Print*` diagnostics the handlers emit.
