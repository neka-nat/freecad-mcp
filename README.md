[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/neka-nat-freecad-mcp-badge.png)](https://mseep.ai/app/neka-nat-freecad-mcp)

# FreeCAD MCP

This repository is a FreeCAD MCP that allows you to control FreeCAD from Claude Desktop.

## Demo

### Design a flange

![demo](./assets/freecad_mcp4.gif)

### Design a toy car

![demo](./assets/make_toycar4.gif)

### Design a part from 2D drawing

#### Input 2D drawing

![input](./assets/b9-1.png)

#### Demo

![demo](./assets/from_2ddrawing.gif)

This is the conversation history.
https://claude.ai/share/7b48fd60-68ba-46fb-bb21-2fbb17399b48

## Install addon

FreeCAD Addon directory is
* Windows: `%APPDATA%\FreeCAD\Mod\`
* Mac:
  * FreeCAD 1.1: `~/Library/Application\ Support/FreeCAD/v1-1/Mod/`
  * FreeCAD 1.0: `~/Library/Application\ Support/FreeCAD/v1-0/Mod/`
* Linux:
  * Ubuntu: `~/.FreeCAD/Mod/` or `~/snap/freecad/common/Mod/` (if you install FreeCAD from snap)
  * Debian: `~/.local/share/FreeCAD/Mod`
  * Arch / CachyOS (FreeCAD 1.1 from `extra/freecad`): `~/.local/share/FreeCAD/v1-1/Mod/`
  * Flatpak: `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/`

Please put `addon/FreeCADMCP` directory to the addon directory.

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
cd freecad-mcp

# For Linux (Ubuntu/Debian)
mkdir -p ~/.FreeCAD/Mod/
cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/

# For Linux (Arch/CachyOS, FreeCAD 1.1 from extra/freecad)
mkdir -p ~/.local/share/FreeCAD/v1-1/Mod/
cp -r addon/FreeCADMCP ~/.local/share/FreeCAD/v1-1/Mod/

# For Linux (Flatpak)
mkdir -p ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/
cp -r addon/FreeCADMCP ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/

# For macOS (FreeCAD 1.1)
mkdir -p ~/Library/Application\ Support/FreeCAD/v1-1/Mod/
cp -r addon/FreeCADMCP ~/Library/Application\ Support/FreeCAD/v1-1/Mod/
```

When you install addon, you need to restart FreeCAD.
You can select "MCP Addon" from Workbench list and use it.

![workbench_list](./assets/workbench_list.png)

And you can start RPC server by "Start RPC Server" command in "FreeCAD MCP" toolbar.

![start_rpc_server](./assets/start_rpc_server.png)

### Auto-Start RPC Server

By default, the RPC server must be started manually each time FreeCAD opens. To start it automatically:

1. Open the **FreeCAD MCP** menu (switch to the MCP Addon workbench first)
2. Check **Auto-Start Server**

The setting is saved to `freecad_mcp_settings.json` and persists across sessions. On the next FreeCAD launch, the RPC server will start automatically once the application finishes loading.

You can disable it at any time by unchecking **Auto-Start Server** in the same menu.

## Setting up Claude Desktop

Pre-installation of the [uvx](https://docs.astral.sh/uv/guides/tools/) is required.

And you need to edit Claude Desktop config file, `claude_desktop_config.json`.

For user.

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp"
      ]
    }
  }
}
```

If you want to save token, you can set `only_text_feedback` to `true` and use only text feedback.

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp",
        "--only-text-feedback"
      ]
    }
  }
}
```

Screenshots can also be controlled per tool call instead of globally: every tool that returns a screenshot accepts an optional `include_screenshot` parameter (pass `false` to get text-only feedback, e.g. for analytical scripts or intermediate steps) and an optional `view_name` parameter to orient the screenshot ("Isometric" by default, or "Front", "Top", "Right", etc.). The `--only-text-feedback` flag always wins: when it is set, no screenshots are returned regardless of `include_screenshot`.


For developer.
First, you need clone this repository.

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
```

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/freecad-mcp/",
        "run",
        "freecad-mcp"
      ]
    }
  }
}
```

## Remote Connections

By default the RPC server does not accept remote connections and listens on `localhost`. To control FreeCAD from another machine on your network:

### 1. Enable remote connections in FreeCAD

In the **FreeCAD MCP** toolbar:

1. Check **Remote Connections** — the RPC server will bind to `0.0.0.0` (all interfaces) on the next restart. For security reasons, it only accepts connections from the IP addresses or CIDR subnets specified in the **Allowed IPs** field. By default this is `127.0.0.1`.
2. Click **Configure Allowed IPs** and enter a comma-separated list of IP addresses or CIDR subnets that are allowed to connect, e.g.:

   ```
   192.168.1.100, 10.0.0.0/24
   ```

   `127.0.0.1` is always the default. Invalid entries are rejected with an error dialog. Restart the RPC server after changing these settings.

### 2. Point the MCP server at the remote host

Pass the `--host` flag with the IP address or hostname of the machine running FreeCAD:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": [
        "freecad-mcp",
        "--host", "192.168.1.100"
      ]
    }
  }
}
```

The `--host` value is validated on startup — it must be a valid IPv4/IPv6 address or hostname.

## Tools

* `create_document`: Create a new document in FreeCAD.
* `create_object`: Create a new object in FreeCAD.
* `edit_object`: Edit an object in FreeCAD.
* `delete_object`: Delete an object in FreeCAD.
* `execute_code`: Execute arbitrary Python code in FreeCAD.
* `execute_code_headless`: Run a FreeCAD script in a separate `freecadcmd` process (crash-safe for heavy OCCT work such as helical threads, lofts, big booleans); returns exit status and output. Pair with `reload_document`.
* `check_manufacturability`: Headless DFM audit of saved solids for 3-axis milling: internal radii below the shop minimum (grouped by radius and axis) and sharp concave vertical edges.
* `check_collisions`: Headless pairwise intersection report (volume and bounding box of each interfering region) for objects of a saved document.
* `insert_part_from_library`: Insert a part from the [parts library](https://github.com/FreeCAD/FreeCAD-library).
* `get_view`: Get a screenshot of the active view.
* `get_objects`: Get all objects in a document.
* `get_object`: Get an object in a document.
* `get_parts_list`: Get the list of parts in the [parts library](https://github.com/FreeCAD/FreeCAD-library).
* `get_rpc_status`: Report RPC and GUI-dispatch health without using the FreeCAD GUI thread.
* `get_async_status`: Report background jobs started by `execute_code_async` (state, error traceback, shape check) without using the GUI thread.
* `run_fem_analysis`: Run the CalculiX solver on an existing `Fem::FemAnalysis` and return summary results (max von Mises stress, max displacement, node count, working directory). Auto-creates a `SolverCcxTools` if the analysis has none. See [`examples/cantilever_fem.py`](examples/cantilever_fem.py) for an end-to-end usage example.

Tools that return a screenshot (`create_object`, `edit_object`, `delete_object`, `execute_code`, `insert_part_from_library`, `get_objects`, `get_object`, `run_fem_analysis`) accept optional `include_screenshot` (default `true`) and `view_name` (default `"Isometric"`) parameters to suppress or reorient the returned image per call.

### GUI dispatch timeouts

GUI calls have separate queue and execution budgets. The queue budget defaults
to the execution budget; a call cancelled before it starts will not run later.
`execute_code` allows 90 seconds in the queue and 90 seconds after GUI execution
starts. The bundled client's socket timeout covers both plus a 30-second margin
(210 seconds total). FEM calls use the requested `timeout` for each budget, with
a client socket timeout of at least `2 * timeout + 30` seconds. Other clients
and MCP hosts must allow these response times in their own timeout settings.

GUI-thread operations run one at a time in FIFO order. An operation's timeout
counts from the moment it starts on the GUI thread, not from when it was
queued: a call that arrives while another operation is still running waits
for its turn without spending its own budget. The wait itself is bounded by a
separate queue timeout (defaults to the same value); when it expires the task
is dropped before it starts without marking dispatch as stuck. Concurrent
`execute_code` calls are therefore safe to issue, but they still execute
sequentially, so total wall time is the sum of the individual runs.

If a GUI-thread operation exceeds its timeout after it has started, the bridge
returns `GUI_DISPATCH_STUCK` and rejects later GUI operations immediately.
Calls that were already queued keep waiting (up to their queue timeout) and run
once the stuck operation returns. Use
`get_rpc_status` from a separate RPC client to identify the operation that is
still running. The RPC server handles connections concurrently, so diagnostics
do not wait for another request to finish. Document queries (`get_object`,
`get_objects`, and `list_documents`) run on the GUI thread alongside modelling
operations and report an RPC fault if dispatch times out or is stuck. FreeCAD GUI
work cannot be force-cancelled safely; if the status does not return to
`healthy` after the operation finishes, restart FreeCAD.

When a script passed to `execute_code` raises, the tool reports the exception
together with the failing script line (`Script line N: <source>`, with the
function name for nested frames) and everything the script printed before it
failed. Multi-step scripts can therefore be debugged from a single failed call
instead of re-running them piecewise.

`execute_code` and `execute_code_async` share a persistent script namespace with
`FreeCAD`/`App` and `FreeCADGui`/`Gui` aliases. Script variables survive between
calls without overwriting the RPC server's own functions. This prevents accidental
name collisions; code execution still has FreeCAD's full privileges.

Async code must keep document and view access on the GUI thread. Build independent
OCCT shapes in the worker, then use `commit(fn, timeout=120)` to apply the result
and recompute the document on the GUI thread. The helper returns `fn`'s value or
raises `RuntimeError` on failure. It persists in the shared namespace so saved
functions can reuse it in later async calls; calling it from `execute_code` or
inside a GUI callback raises immediately. Concurrent scripts share live variables
and must coordinate any intentional writes to the same data.

After an `execute_code` exception on a FreeCAD development build, inspect any
new `FeaturePython` object before mutating or deleting it. In particular, do
not continue with an object whose required `Proxy` was never installed, as
touching that broken object can wedge FreeCAD's GUI thread.

### Shape check after every script

`execute_code` fingerprints every object that has a `Shape` before the script
runs and compares afterwards. Objects whose shape changed are validated and the
result is appended to the tool output, e.g.
`Shape check: 1 shape(s) changed (Doc.Lid); all valid.` or
`WARNING: Doc.Lid: shape is INVALID`. Warnings cover invalid shapes, null
shapes, a change in the number of solids, and removed objects. Unchanged shapes
are not validated, so the check stays cheap on large documents.

### Background jobs

`execute_code_async` returns a `job_id`. `get_async_status(job_id)` reports
whether the job is `running`, `done` or `failed`, and for failed jobs the
exception and traceback that previously reached only FreeCAD's Report View.
Finished jobs also carry the shape check for everything the job committed to
the document. `get_rpc_status` lists the ids of jobs still running.
### Headless execution

`execute_code_headless` writes the script to a file and runs it with
`freecadcmd -c` in a separate process. Use it for OpenCascade work that may
segfault or block the GUI for minutes: `makeHelix` + `makePipeShell` threads,
lofts and sweeps, booleans with many B-spline tools. A native crash only ends
the helper process; the tool reports the signal (e.g. `SIGSEGV`) together with
everything the script printed, and the GUI keeps its documents. The script
must open and save documents itself (`FreeCAD.openDocument`, `doc.save()`,
`Shape.exportBrep`); afterwards `reload_document` refreshes the GUI copy.

The executable is auto-detected (`freecadcmd` on PATH, then the
`org.freecad.FreeCAD` Flatpak). Override with
`freecad-mcp --freecadcmd "flatpak run --command=freecadcmd org.freecad.FreeCAD"`.


`execute_code_headless` also accepts `script_path` (run a generator script
from disk) and `args` (exposed as `sys.argv[1:]`). Two bundled scripts are
wrapped as tools: `check_manufacturability(file_path, objects,
min_internal_radius)` and `check_collisions(file_path, objects)`. Both read
the saved `.FCStd`, so save the document first.

## Contributors

<a href="https://github.com/neka-nat/freecad-mcp/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=neka-nat/freecad-mcp" />
</a>

Made with [contrib.rocks](https://contrib.rocks).
