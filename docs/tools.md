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
| `execute_guarded` | Run an edit and keep it only if the audit passes; a rejected one is rolled back. |
| `create_checkpoint` | Copy the shapes and their face colours, so a later edit can be undone exactly. |
| `list_checkpoints` | List the checkpoints available to restore. |
| `restore_checkpoint` | Put every shape and its colours back the way a checkpoint recorded them. |
| `audit_shapes` | Report a document's defects and which ones an edit introduced. |
| `measure_probe` | Report the solid spans and open gaps a ray crosses in an object. |
| `measure_sweep` | Scan a wall with parallel rays to find where a feature starts and stops. |
| `measure_compare` | Probe several rays and, against a baseline, report which gained material. |
| `check_clearance` | Measure the gap between two parts the whole way along an axis, against an expected figure. |
| `compare_section` | Two parts' cross-sections on one plane side by side, with the clearance between. |
| `find_gaps` | Thin slots of air inside a part, where an edit fell short of what it was meant to meet. |
| `find_islands` | The separate pieces a part is actually made of. |
| `check_cutter` | What a cutting block would remove, and what it would reach that it should not. |
| `cut_pocket` | Cut a pocket the way a mill does, with the corner radii a cutter leaves. |
| `cut_slot` | Cut a slot along a path, with the rounded ends a cutter leaves. |
| `pick_pixel` | Name the face drawn at a pixel of the last screenshot. |
| `pick_region` | List every face drawn inside a rectangle of the last screenshot. |
| `locate_point` | Say where a 3D point appears in the current view. |
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

## Rejecting an edit instead of reporting it

The checks above describe an edit after it has been applied, which leaves the
damaged shape in the document until somebody reads the warnings. `execute_guarded`
decides instead: it takes a checkpoint, runs the code, audits the result, and
restores the checkpoint when the verdict is `reject`. What comes back names the
defect and where it is, which is the input for the next attempt rather than a
reason to guess.

The audit rejects an invalid shape, a changed solid count, a part left in more
pieces than it started in, a bounding box that grew, and new slivers or sharp
inside corners beyond the allowed number. Each threshold can be relaxed per call
through `policy` — `{"forbid_bbox_growth": false}` for an edit meant to add
material, `{"max_new_sharp_concave": 6}` where a pocket's own floor edges are
expected.

It does not check for hairline gaps: a scan coarse enough to run on every
checkpoint misses them, and one that does not is too slow to be in the way of
every edit. Run `find_gaps` over the region an edit touched, or `check_clearance`
on the candidate before fusing it.

`create_checkpoint` and `restore_checkpoint` are the same mechanism by hand.
They hold their own copies of the shapes and their `DiffuseColor`, so a restore
returns both: GUI undo is a stack the user also drives and silently does nothing
once its depth runs out, and putting an old shape back under the current colour
list scatters the colours across the wrong faces.

## Checking a fit before committing to it

A clearance holds where it was checked and nowhere else unless somebody looks.
`check_clearance` walks the overlap of two parts and measures the gap at every
stop; with `expect` set it says whether that figure holds all the way along and
names the stops that disagree. Run it on a candidate shape before fusing, not
after. `compare_section` is the same question on one plane, with both parts'
spans side by side.

`find_gaps` catches what a fuse leaves when it falls short of what it was meant
to meet: a parallel slot of air a fraction of a millimetre wide. The body stays
one valid solid, `shape_check` sees nothing, and the piece hangs free in the
render. `find_islands` reports the separate pieces a part is made of, counting
per solid first and then per connected face group, which catches a shell joined
to a body OCCT still counts as single.

## Cutting features a mill could make

A pocket assembled from boxes and cylinders comes out with notches where the
primitives cross, and the geometry is wrong from the first operation: a round
cutter cannot produce a square inside corner. `cut_pocket` and `cut_slot` cut
the region a cutter sweeps, so inside corners are arcs of `tool_radius` because
nothing else can be there. A pocket the cutter does not fit is refused rather
than approximated. Both run inside the same checkpoint-and-audit cycle as a
guarded edit.

## Placing a cutting block

`cut_pocket` and `cut_slot` cover features a mill makes. Trimming something
already modelled is still a hand-placed block and a boolean, and that block is
placed from remembered numbers: the height of a rim, where a face ends. A block
a tenth too tall or half a millimetre too far along cuts to a valid single
solid, reports no warning, and leaves a sliver on a face that was never part of
the edit. The audit finds it afterwards without being able to say which edit
made it, so the search starts from scratch.

`check_cutter` answers before the cut. It reports the volume the block would
remove and the box that volume occupies; given `within`, the region the cut is
allowed to touch, it reports everything outside it as `strays` with position and
volume; given `avoid`, it names any part the block reaches that it should not.
A block that intersects nothing is reported too, because cutting nothing looks
exactly like a cut that worked.

Run it on the block, correct the block, then cut. Correcting the block is a
change of six numbers; repairing the result is a new defect each time.

## Reading a screenshot

A screenshot shows a defect; the geometry that has to change is named by face
and coordinate. `pick_pixel` and `pick_region` resolve a pixel of the current
view to the face that drew it; `locate_point` goes the other way, for a defect
an audit reported by coordinate, and names what is actually visible at that
pixel rather than claiming the point is.

Screenshots are scaled down before they reach the caller, so pass the image's
own size as `image_width` and `image_height` whenever it differs from the
`view_size` in the reply. Without it the pixel lands somewhere else entirely and
the answer is a confident hit on the wrong face.

## FEM analysis

`run_fem_analysis` runs the CalculiX solver on an existing `Fem::FemAnalysis`
container. It auto-creates a `SolverCcxTools` if the analysis has none and returns
max von Mises stress, max/min displacement, node count, and the solver's working
directory. The default `timeout` is 600 seconds.

See [`examples/cantilever_fem.py`](../examples/cantilever_fem.py) for an end-to-end
example, including geometry, material, mesh, constraints, and an analytical
comparison. For long analyses, configure the client to allow the
[queue and execution timeout budgets](execution.md#gui-dispatch-timeouts).
