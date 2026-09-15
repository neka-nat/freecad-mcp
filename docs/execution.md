# Code execution

[Back to README](../README.md) · [Tools](tools.md) · [Configuration](configuration.md)

## Choose an execution mode

| Tool | Use case |
| --- | --- |
| `execute_code` | Normal FreeCAD automation; the script runs on the GUI thread. |
| `execute_code_async` | Long background computations on independent geometry; hand document and view access to the GUI thread with `commit()`. |
| `execute_code_headless` | Heavy OCCT operations in a separate process, isolating native crashes from the GUI. |

## Shared script state

`execute_code` and `execute_code_async` share a persistent script namespace with
`FreeCAD`/`App` and `FreeCADGui`/`Gui` aliases. Script variables survive between
calls without overwriting the RPC server's own functions. This prevents accidental
name collisions; code execution still has FreeCAD's full privileges.

Concurrent scripts share live variables and must coordinate intentional writes
to the same data. Headless scripts run in a fresh process and do not share this
namespace.

## Background jobs

`execute_code_async` returns a `job_id`. `get_async_status(job_id)` reports
whether the job is `running`, `done`, or `failed`, and includes the exception and
traceback for failed jobs.

All running jobs and the 20 most recently completed jobs are retained in memory
until FreeCAD exits. `get_async_status()` lists this history; `get_rpc_status`
lists the IDs of jobs still running. Job status does not wait for GUI cleanup.
Script success does not certify geometry validity.

Install the updated addon to use job status. With an older addon, continue
polling a document status object and checking FreeCAD's Report View.

### Document and view access

Async code must keep document and view access on the GUI thread. Build
independent OCCT shapes in the worker, then use `commit(fn, timeout=120)` to apply
the result and recompute the document on the GUI thread. The helper returns
`fn`'s value or raises `RuntimeError` on failure.

`commit()` persists in the shared namespace so saved functions can reuse it in
later async calls. Calling it from `execute_code` or inside a GUI callback raises
immediately.

## Headless execution

`execute_code_headless` writes the script to a file and runs it with
`freecadcmd -c` in a separate process. Use it for OpenCascade work that may
segfault or block the GUI for minutes: `makeHelix` + `makePipeShell` threads,
lofts and sweeps, or booleans with many B-spline tools. A native crash only ends
the helper process; the tool reports the signal (e.g. `SIGSEGV`) together with
everything the script printed, and the GUI keeps its documents.

The script must import the modules it needs and open and save documents itself
(`FreeCAD.openDocument`, `doc.save()`, `doc.saveAs()`, or `Shape.exportBrep` for
shape export). After saving an `.FCStd` file that is open in the GUI, use
`reload_document(doc_name)` to refresh the GUI copy. Get the document name with
`list_documents`.

The executable runs on the machine hosting the MCP server; `--host` only selects
the GUI RPC host. Use file paths accessible on the MCP server machine. The
timeout must be positive and finite (default: 600 seconds). A timeout returns
partial stdout/stderr, and temporary scripts are removed on success, failure,
and timeout.

The executable is auto-detected (`freecadcmd` or Snap's `freecad.cmd` on PATH,
then the `org.freecad.FreeCAD` Flatpak). Override it with:

```bash
freecad-mcp --freecadcmd "flatpak run --command=freecadcmd org.freecad.FreeCAD"
```

## GUI dispatch timeouts

GUI-thread operations run one at a time in FIFO order. Calls have separate queue
and execution budgets: execution time counts from the moment a call starts on
the GUI thread, and waiting for an earlier operation does not consume that
budget. The queue budget defaults to the execution budget. If it expires before
a call starts, the call is cancelled and will not run later; this does not mark
dispatch as stuck.

| Operation | Queue budget | Execution budget | Bundled client socket timeout |
| --- | --- | --- | --- |
| `execute_code` | 90 seconds (or requested `timeout`) | 90 seconds (or requested `timeout`) | At least `2 * timeout + 30` seconds |
| `run_fem_analysis` | Requested `timeout` | Requested `timeout` | At least `2 * timeout + 30` seconds |

A GUI task cannot be cancelled once it has started, so a slower `execute_code`
call reports a timeout while the task keeps running, and its result is discarded
even though the work completes. Pass `timeout` (seconds, capped at 1800) for
work that genuinely has to run on the GUI thread and takes longer, such as
importing or exporting a large STEP assembly; the client widens its socket
timeout to match. For heavy pure-geometry work that touches neither the document
nor the GUI, prefer `execute_code_async`.

The client timeout covers both budgets plus a 30-second margin. Other clients
and MCP hosts must allow these response times in their own timeout settings.
Concurrent `execute_code` calls can be queued, but they still execute
sequentially, so total wall time includes each individual run.

### Recover from a stuck GUI operation

If a GUI-thread operation exceeds its execution budget after starting, the
bridge returns `GUI_DISPATCH_STUCK` and rejects later GUI operations immediately.
Calls that were already queued keep waiting, up to their queue timeout, and run
once the stuck operation returns.

Use `get_rpc_status` from a separate RPC client to identify the operation that
is still running. The RPC server handles connections concurrently, so
diagnostics do not wait for another request to finish. Document queries
(`get_object`, `get_objects`, and `list_documents`) run on the GUI thread
alongside modelling operations and report an RPC fault if dispatch times out or
is stuck.

FreeCAD GUI work cannot be force-cancelled safely. If status does not return to
`healthy` after the operation finishes, restart FreeCAD.

After an `execute_code` exception on a FreeCAD development build, inspect any
new `FeaturePython` object before mutating or deleting it. In particular, do
not continue with an object whose required `Proxy` was never installed, as
touching that broken object can wedge FreeCAD's GUI thread.
