# Tools

[Back to README](../README.md) · [Configuration](configuration.md) · [Code execution](execution.md)

## Available tools

| Tool | Purpose |
| --- | --- |
| `create_document` | Create a new FreeCAD document. |
| `list_documents` | List open documents. |
| `reload_document` | Close and reopen a saved document to pick up external file changes, such as results from a headless script. |
| `create_object` | Create an object in a document. |
| `edit_object` | Edit an object's properties. |
| `delete_object` | Delete an object from a document. |
| `get_objects` | Get all objects in a document. |
| `get_object` | Get one object in a document. |
| `get_view` | Get a screenshot of the active view. |
| `execute_code` | Execute Python code on FreeCAD's GUI thread. |
| `execute_code_async` | Start a background computation and return its job ID; use `commit()` for document and view access. |
| `get_async_status` | Get background job state and failure tracebacks without using the GUI thread. |
| `execute_code_headless` | Run a script in a separate `freecadcmd` process and return its exit status and output. |
| `undo_last_edit` | Revert the last `execute_code` call, which runs as a single undo step. |
| `measure_probe` | Report the solid spans and open gaps a ray crosses in an object. |
| `measure_compare` | Probe several rays and, against a baseline, report which gained material. |
| `check_manufacturability` | Internal radii below the cutter, sharp inside corners, thin faces and short edges of one solid or STEP file. |
| `section_profile` | Outline of a shape in a plane, segment by segment, with short segments and steps flagged. |
| `shape_diff` | Solids present in one shape and absent from another, with volumes and bounding boxes. |
| `get_rpc_status` | Report RPC and GUI-dispatch health without using the GUI thread. |
| `insert_part_from_library` | Insert a part from the [FreeCAD parts library](https://github.com/FreeCAD/FreeCAD-library). |
| `get_parts_list` | List parts in the [FreeCAD parts library](https://github.com/FreeCAD/FreeCAD-library). |
| `run_fem_analysis` | Run CalculiX on an existing analysis and return summary results. |

See [code execution](execution.md) for execution modes, shared script state,
background job tracking, and timeout handling.

## Screenshot options

The following tools return optional screenshots: `create_object`, `edit_object`,
`delete_object`, `execute_code`, `insert_part_from_library`, `get_objects`,
`get_object`, and `run_fem_analysis`.

| Parameter | Default | Purpose |
| --- | --- | --- |
| `include_screenshot` | `true` | Set to `false` for text-only feedback, such as analytical scripts or intermediate steps. |
| `view_name` | `"Isometric"` | Orient the returned screenshot, for example `"Front"`, `"Top"`, or `"Right"`. |

The [`--only-text-feedback` flag](configuration.md#text-feedback-and-screenshots)
suppresses these optional screenshots regardless of `include_screenshot`.

Use `get_view` to request a screenshot explicitly; it is available even with
`--only-text-feedback`. It takes `view_name` and optional `width`, `height`, and
`focus_object` parameters. Supported views are `Isometric`, `Front`, `Top`,
`Right`, `Back`, `Left`, `Bottom`, `Dimetric`, and `Trimetric`.

## Checking an edit

A boolean that goes wrong usually still leaves a valid, single solid, so the
result looks fine and the mistake surfaces much later. Three things narrow that
gap.

`execute_code` and `execute_code_async` fingerprint every shape before the
script and re-check the ones that changed, reporting the result as
`shape_check`. Warnings cover an invalid shape, a solid that split into several,
a null shape, a removed object, and a bounding box that grew outward. Growth
matters because a cut can only shrink a solid: material outside the old bounds
means a fuse reached past the region it was meant to repair. The check is a
diagnostic and never fails the script on its own.

`shape_check` cannot see an edit that stays inside the old bounding box, such as
a fill box 0.5 mm wider than the wall it repairs. `measure_probe` catches those
by measuring along a ray: `spans` are the solid intervals, `gaps` the open ones,
so probing across a vented wall returns the ribs as spans and the slots as gaps.
Measurements are taken along the ray's dominant axis, so probe along X, Y or Z to
read a thickness directly. `measure_compare` runs several rays at once; pass a
previous call's `probes` back as `before` and each ray reports whether it `grew`.

`shape_check` also reports slivers on the shapes a script changed: faces
narrower than 0.3 mm and edges shorter than 0.1 mm. A fill box that overhangs
an arc by 0.04 mm, or a tab whose flat bottom is 0.14 mm wide, is valid, single
and invisible in a render; it is found on the shop floor by measuring.

`check_manufacturability` runs the fuller audit on one solid, or on a STEP file
so the check covers the exact file being sent out: concave cylindrical faces
below `r_min`, sharp concave edges between non-tangent faces of any surface
type (vertical ones by default), thin faces and short edges. `section_profile`
cuts the shape with a plane and returns the outline as ordered segments, with
short segments and steps (a short segment between nearly parallel neighbours)
listed separately. `shape_diff` returns the solids of A−B and B−A, which is the
quickest way to see what a rebuild changed or what a hand edit added.

Each `execute_code` call runs inside one undo transaction, so `undo_last_edit`
reverts it. Use it as soon as a check shows an edit went wrong: FreeCAD
overwrites the `.FCBak` file on the next save, so saving over a bad edit destroys
the only copy on disk.

## FEM analysis

`run_fem_analysis` runs the CalculiX solver on an existing `Fem::FemAnalysis`
container. It auto-creates a `SolverCcxTools` if the analysis has none and returns
max von Mises stress, max/min displacement, node count, and the solver's working
directory. The default `timeout` is 600 seconds.

See [`examples/cantilever_fem.py`](../examples/cantilever_fem.py) for an end-to-end
example, including geometry, material, mesh, constraints, and an analytical
comparison. For long analyses, configure the client to allow the
[queue and execution timeout budgets](execution.md#gui-dispatch-timeouts).
