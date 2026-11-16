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

Only one shared-namespace script is admitted at a time. An overlapping sync or
async call returns `SCRIPT_BUSY` with `mutation_outcome: not_started`; retry after
the current script finishes. Document tools, status queries, and async `commit()`
remain available. Scripts may still spawn their own threads; those threads must
coordinate their own state and follow FreeCAD's thread-safety rules.

Variables survive an RPC stop/start, but not a FreeCAD process restart. Failed
scripts preserve assignments and document changes made before the exception;
script execution is not a transaction. Headless scripts use a separate process.

Characters that XML-RPC cannot carry, such as ANSI colour codes or NUL bytes in
printed output or error messages, arrive as visible escapes (`\x1b`, `\x00`).

## Background jobs

`execute_code_async` returns a `job_id`. `get_async_status(job_id)` reports
whether the job is `running`, `done`, or `failed`, and includes the exception and
traceback for failed jobs. Synchronous script failures also return captured output
printed before the error.

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
`fn`'s value or raises `RuntimeError` on failure. A timeout does not stop an
already running callback; the exception includes its task ID for polling.

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
timeout must be positive and finite (default: 600 seconds). On timeout the runner
terminates its POSIX process group, or the Windows process tree with `taskkill /T`,
so ordinary child processes cannot continue writing after the timeout. Scripts
that deliberately detach children or use an external service are outside this
boundary; completed file writes are not rolled back. A timeout returns
partial stdout/stderr, and temporary scripts are removed on success, failure,
and timeout.

The executable is auto-detected (`freecadcmd` or Snap's `freecad.cmd` on PATH,
then the `org.freecad.FreeCAD` Flatpak). Override it with:

```bash
freecad-mcp --freecadcmd "flatpak run --command=freecadcmd org.freecad.FreeCAD"
```

An existing executable file can also be passed directly as the value of
`--freecadcmd`, including Windows paths with spaces and backslashes. In a shell,
quote the path so it reaches the server as one argument:

```powershell
freecad-mcp --freecadcmd "C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"
```

In an MCP JSON configuration's `args` array, use
`"C:\\Program Files\\FreeCAD 1.1\\bin\\FreeCADCmd.exe"` as the argument after
`"--freecadcmd"`; no embedded quote characters are needed. Command lines with
additional arguments still use shell-style splitting, so quote any executable
path containing spaces inside that command string.

Headless scripts receive closed standard input, so they cannot consume the MCP
protocol stream or wait for interactive input. Pass all inputs in the code or
files. Printed lines are flushed to preserve progress output on failure or timeout.
Output is not filtered by content; FreeCAD banners and progress text may appear.

## GUI dispatch timeouts

GUI-thread operations run one at a time in FIFO order. Calls have separate queue
and execution budgets: execution time counts from the moment a call starts on
the GUI thread, and waiting for an earlier operation does not consume that
budget. The queue budget defaults to the execution budget. If it expires before
a call starts, the call is cancelled and will not run later; this does not mark
dispatch as stuck.

| Operation | Queue budget | Execution budget | Bundled client socket timeout |
| --- | --- | --- | --- |
| `execute_code` | 90 seconds (or capped `timeout`) | 90 seconds (or capped `timeout`) | At least `2 * timeout + 30` seconds; 210 seconds by default |
| `run_fem_analysis` | Requested `timeout` | Requested `timeout` | At least `2 * timeout + 30` seconds |

A GUI task cannot be cancelled once it has started, so a slower `execute_code`
call reports a timeout while the task keeps running. Its response includes
`task_id` and `mutation_outcome: still_running`. Poll `get_task_status(task_id)`
for the eventual result before retrying. IDs are opaque strings that include a
process-specific namespace; an ID from a previous FreeCAD process cannot identify
new work after a restart. Pass `timeout` (positive finite seconds, capped at 1800) for
work that genuinely has to run on the GUI thread and takes longer, such as
importing or exporting a large STEP assembly; the client widens its socket
timeout to match the capped budget. Invalid values are rejected before execution.
Omitting `timeout` preserves the 90-second default and compatibility with older
addons; an explicit timeout requires an updated addon. For heavy pure-geometry work that touches neither the document
nor the GUI, prefer `execute_code_async`.

FEM timeouts must be integer seconds from 1 to 2147483647; script timeouts
must be positive finite numbers. Booleans are rejected at the MCP boundary.

The client timeout covers both budgets plus a 30-second margin. Other clients
and MCP hosts must allow these response times in their own timeout settings.
Document operations can queue behind one another. Shared-namespace scripts
use exclusive admission: overlapping script calls are rejected before execution.

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


## Listener, readiness, and operation outcomes

`get_rpc_status` separates the listener (`starting`, `running`, `stopping`,
`stopped`, `stop_failed`) from GUI dispatch (`healthy`, `queued`, `blocked`, `busy`, `stuck`,
`stopped`). Dispatch includes `accepting`, `ready`, queue counts, the last observed
UI blocker, heartbeat age, and a generation number. These are snapshots, not a
reservation of the GUI. An absent/stale heartbeat is visible even when no task
is currently executing. Status also reports the script owner, `quiescent`, a
listener `server_id`, and configuration fields requiring a restart. Tokens are
never included in status.

Stopping cancels work that has not started and drops queued cosmetic callbacks.
Running native operations and Python workers cannot be forcibly interrupted.
Restart is refused until running GUI work and the namespace owner finish. An
old worker's `commit()` and requests from the previous listener generation cannot
enter the new queue. Stopping the listener does not erase script variables or
job history.
If the shutdown worker cannot start, status reports `stop_failed` and retains
the listener so Stop can be retried. New document work remains disabled.

`get_task_status()` lists pending GUI tasks and the last 20 terminal tasks in
completion order. States are `queued`, `running`, `timed_out_running`, `done`,
`failed`, and `cancelled`. Terminal records contain the result; late script
failures include captured output. Results are JSON-safe snapshots, capped at
65,536 serialized characters with `result_truncated` set when needed. Arbitrary
native values returned from `commit()` are opaque in history. History is in
memory, survives listener restart, and disappears when FreeCAD exits. Unknown or
evicted task IDs return an error, never an assumed success. The history is shared
by authenticated clients, like the document and script namespace.

Failure responses carry `mutation_outcome` when known:

| Outcome | Meaning |
| --- | --- |
| `not_started` | Admission rejected or queued work cancelled; this operation did not run. |
| `still_running` | The caller timed out; poll the task before retrying. |
| `rolled_back` | The document transaction was aborted and creation cleanup completed, including changes to existing objects. |
| `retained_invalid` | Creation committed an invalid object for inspection; use the returned name. |
| `cleanup_incomplete` | Rollback/cleanup failed; inspect reported remaining objects and errors. |
| `partial_or_unknown` | Execution failed after it may have changed state; inspect before retrying. |
| `completed` | Execution finished; this alone does not certify arbitrary script output or geometry. |

FEM failure can leave a newly created solver, retained working directory, or
purged/changed results. Reload closes the old document before opening the file;
a reopen failure is not an automatic restoration. Screenshot capture changes
camera framing and can clear selection. These operations must not be retried
solely because a response indicates failure.

The MCP client refreshes compatibility and timeout budgets at each tool admission
so a cached client does not retain a previous listener's settings. A failed version
check reports `unknown`, distinct from `compatible`; changed warnings are delivered
once. Calls are not automatically replayed after transport failure.
