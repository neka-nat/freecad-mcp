# What's missing from the MCP server — and what it costs to add

Companion to [`freecad-python-api-inventory.md`](freecad-python-api-inventory.md). Every claim about FreeCAD here was verified by introspection against FreeCAD 1.1.1 on this machine; every claim about the MCP server comes from reading `src/freecad_mcp/` and `addon/FreeCADMCP/`.

## The honest framing

`execute_code` runs **arbitrary Python on FreeCAD's GUI thread**. Nothing in FreeCAD is unreachable. So "missing" does not mean "impossible" — it means one of three things, and they are not equally serious:

| Class | Meaning | Why it hurts |
|---|---|---|
| **A. Blind spot** | The model cannot *see* the result | Breaks the feedback loop — the model works blind and cannot self-correct |
| **B. No first-class tool** | Works, but only via hand-written Python | Model must know FreeCAD's API from memory; no schema, no validation, silent version drift |
| **C. Trap** | Reports success, produces a broken model | Worst class — the model believes it succeeded and builds on sand |

The tool surface today is **14 tools**: `create_document`, `create_object`, `edit_object`, `delete_object`, `execute_code`, `execute_code_async`, `get_view`, `get_objects`, `get_object`, `get_parts_list`, `insert_part_from_library`, `list_documents`, `reload_document`, `run_fem_analysis`.

Against 352 creatable object types, 76 FEM factories, 63 Draft factories, and 53 file formats.

---

## Difficulty scale

Adding any tool means touching the 5 layers in `CLAUDE.md` § *Adding a tool*. That baseline is ~60 lines and is assumed in every rating below.

| | Meaning |
|---|---|
| **S** | Plumbing only. FreeCAD side is 1–3 calls. Half a day. |
| **M** | Needs a new JSON schema, dispatch logic, or GUI-thread care. 1–3 days. |
| **L** | Needs a designed data model or protocol. About a week. |
| **XL** | Architectural change to how the two halves talk. |

---

# Class C — Traps (fix these first)

These are defects, not absences. They cost nothing to hit and produce confidently wrong work.

> **All of Class C and A1 were verified live** against a running FreeCAD 1.1.1 + RPC server on 2026-08-05. Transcript in §*Live verification*. Re-run with `python3 docs/verify_gaps.py`.

## C0. One invalid object makes `get_objects` throw for the whole document — ✅ **FIXED** (`30738ca`)

> **Fixed 2026-08-05** in `addon-dev/FreeCADMCP/rpc_server/serialize.py`.
> `serialize_shape` now returns `{"Valid": false, "Error": ...}` for a null or unreadable
> shape instead of propagating; healthy output is unchanged. Added `safe_attr()` because
> `getattr(obj, name, None)` only swallows `AttributeError` — a `RuntimeError` from reading
> `.Shape` went straight through the three-argument form.
> Verified headlessly: healthy `Part::Box` serialises identically, the broken Pad returns the
> diagnostic dict, a full-document pass completes. See [`version_history.md`](version_history.md).

Original analysis follows.

### The bug — **S, and it was the worst here**

`serialize.serialize_shape()` reads `shape.Volume` with no guard. On an object whose shape failed to compute, FreeCAD raises `RuntimeError: shape is invalid`, which escapes `serialize_object` and comes back to the client as an **XML-RPC Fault that kills the entire call**.

**Measured live:**

```
create_object PartDesign::Pad     -> {'success': True, 'object_name': 'Pad2'}
get_object(doc, 'Pad')            -> Fault 1: <class 'RuntimeError'>:shape is invalid
get_objects(doc)                  -> Fault 1: <class 'RuntimeError'>:shape is invalid   <-- whole document
get_object(doc, 'Box')            -> OK        (healthy object still fine)
execute_code: p.Shape.isNull()    -> True ;  p.Shape.Volume -> RuntimeError
```

Why this is the priority: `prompt_text.ASSET_CREATION_STRATEGY` opens with *"Before starting any task, always use get_objects() to confirm the current state of the document."* So the model is instructed to call, first and on every task, the exact tool that a single broken object disables. It then cannot inspect the document, cannot see what went wrong, and cannot recover — while `create_object` keeps cheerfully returning `success: True`.

C0 and C1 compound: C1 creates the broken object, C0 makes it undiagnosable.

**Fix:** wrap the body of `serialize_shape` in try/except and return `{"error": "invalid shape"}` for that object instead of propagating. Three lines. Also worth guarding `serialize_value`'s `getattr` loop the same way — it already catches per-property, but `Shape` is read outside that loop.

`serialize.py` is **byte-identical between the repo and the deployed addon**, so this is current code, not a stale-deployment artifact.

## C1. `create_object` reports success on objects that are broken — ✅ **FIXED** (`bddf445`)

> **Fixed 2026-08-05** in `object_factory.py` (`validity_error()`) and applied to **both** the
> create and edit paths — an edit can break a healthy object just as easily.
>
> The discriminator is **`obj.isValid()`, not the presence of a shape.** Measured on 1.1.1, a
> shape-based test would have wrongly failed every empty `Body` and geometry-less `Sketch` —
> normal intermediate states in any PartDesign workflow:
>
> | Object | State | `isValid()` | Shape |
> |---|---|---|---|
> | `Part::Box` healthy | `Up-to-date` | True | solid |
> | empty `Body` / `Sketch` | `Up-to-date` | True | **null** |
> | Analysis / Group / Sheet | `Up-to-date` | True | **none** |
> | bodyless `Pad` | `Touched, Invalid` | **False** | null |
> | linkless `Part::Cut` | `Touched, Invalid` | **False** | null |
>
> The failure now carries **`obj.getStatusString()`** — FreeCAD's own reason, e.g.
> *"Linked shape object is empty"* — which otherwise only reaches the Report View and is
> invisible to a remote caller. That partly compensates for A2 until a log tool exists.
> `object_name` is returned on failure too, so the caller can delete or repair rather than
> retry and accumulate `Pad001, Pad002, …`
> Verified headlessly: 8/8 cases, no false positives on the six legitimate types.

Original analysis follows.

### The bug — **S**

`object_factory.create_object_gui()` ends with `doc.recompute()` then unconditionally `return {"success": True, ...}`. It never checks whether the object actually computed.

**Measured:** creating `PartDesign::Pad`, setting `Profile` and `Length` by property, then recomputing leaves the object in state `['Touched', 'Invalid']` with `pad.Shape.isNull() == True`, while FreeCAD logs *"Link(s) to object(s) 'Sk' go out of the allowed scope"*. The MCP returns **`success: True`**. The model then pads, fillets and exports a shape that does not exist.

**Fix:** after recompute, check `obj.State` for `Invalid`/`Error`/`Touched`, and surface `doc.recompute()`'s returned error count. Return a failure — or at minimum a warning field — with the object name.

> Highest value-per-line change in this list. It converts an entire class of silent corruption into a visible error.

## C2. PartDesign features cannot be assembled through the property interface — **M**

Body membership is `body.addObject(feature)` — a **method**. `property_mapper.set_object_property` only does `setattr`, and it name-resolves strings to objects for exactly four properties: `Base`, `Tool`, `Source`, `Profile`.

**Measured live** — trying to express body membership the only way the wire allows:

```
edit_object(doc, 'Body', {'Group': ['Sk']})
  -> {'success': False,
      'error': "Failed to set property: Group: Type must be App.DocumentObject or None, not str"}
```

Credit where due: the MCP **reports this honestly** rather than failing silently — my earlier prediction that it would silently no-op was wrong. But the outcome is the same: there is *no expressible way* to put a feature into a Body. The Pad is then created outside any body, computes to nothing, and `create_object` still returns `success: True` (C1), after which the document can no longer be inspected (C0).

**Consequence:** the entire PartDesign workflow — 71 object types, the *normal* way to do parametric CAD in FreeCAD — is unreachable except through `execute_code`.

**Fix:** a body-aware branch in `object_factory` mirroring the existing `Fem::` branch: create the feature, call `body.addObject()`, set `Tip`, recompute, validate. Add an optional `body_name` argument alongside the existing `analysis_name`.

## C3. Sketch geometry cannot cross the wire — ✅ **FIXED** (`86a17a9`)

> **Fixed 2026-08-05.** `create_sketch` takes JSON geometry and constraints and rebuilds them
> addon-side. `polyline`/`rectangle` auto-stitch their coincident constraints. PointPos measured
> as `1=start, 2=end, 3=centre`.
>
> Validation is a **safety gate**: an unknown constraint type or wrong argument count is not
> reliably catchable — the identical call raised `TypeError` in one script and killed the
> FreeCAD process in another — so type, arity and indices are checked before construction.
>
> Proven by rebuilding the L-bracket with no hand-written geometry: DoF 0, fully constrained,
> final volume 15492.04 mm³ against 15492.05 predicted.

Original analysis follows.

### The gap — **L**

This is the structural one. `sketch.Geometry = [...]` *is* a settable property (verified), so FreeCAD is not the obstacle. **XML-RPC is.**

**Measured:** `xmlrpc.client.dumps((Part.LineSegment(...),))` → `TypeError: cannot marshal <class 'builtin_function_or_method'> objects`. XML-RPC carries only ints, floats, strings, bools, arrays, structs, dates, base64. A `Part.LineSegment` cannot be sent, and `property_mapper` has no deserializer that would rebuild one.

**Consequence:** sketches — the foundation of parametric modelling — can only be built with `execute_code`. Since PartDesign consumes sketches, C2 and C3 compound: the model must drop to raw Python for essentially all real CAD work.

**Fix:** design a JSON geometry + constraint schema and a deserializer in `property_mapper`, e.g.

```json
{"geometry": [{"type": "LineSegment", "start": [0,0], "end": [10,0]},
              {"type": "Arc", "center": [10,5], "radius": 5, "start_angle": -90, "end_angle": 90}],
 "constraints": [{"type": "Coincident", "first": 0, "first_pos": 2, "second": 1, "second_pos": 1},
                 {"type": "DistanceX", "first": 0, "value": 10}]}
```

Then a `create_sketch` / `add_sketch_geometry` tool that calls `addGeometry`/`addConstraint`. Budget a week: ~15 geometry types and ~20 constraint types, and constraint indices are fiddly. **Highest-value large item on this list.**

---

# Class A — Blind spots (the model cannot see its work)

## A1. TechDraw pages and Spreadsheets are invisible — ✅ **FIXED** (`a7ade77`)

> **Fixed 2026-08-05** in `view_manager.py`. Capture is now layered, cheapest-correct first:
>
> | View | Class | Path |
> |---|---|---|
> | 3D | `View3DInventorPy` | `saveImage` — the only one that can re-orient and resize |
> | TechDraw | `MDIViewPagePy` | `QGraphicsScene.render()` over `itemsBoundingRect()` |
> | Spreadsheet | `SheetViewPy` | `QWidget.grab()` fallback |
>
> All three verified **by opening the images**, not by return code — which mattered: the first
> attempt grabbed the outer `QMainWindow` and produced an all-white PNG that returned `True`
> and looked like success.
>
> The scene path renders content rather than screen pixels, so it is immune to zoom, scroll and
> window occlusion, and never disturbs the user's view (a zoom-to-fit would). The `grab()`
> fallback means any *future* view type is captured rather than refused.
>
> Two limits: `view_name` only applies to the 3D path (nothing to orient on a drawing), and the
> `grab()` fallback is still zoom/scroll dependent — a sheet scrolled to row 500 captures row 500.

Original analysis follows.

### The gap — **M**

You raised this one, and it is real and total. `rpc_server.get_active_screenshot` gates on `hasattr(active_view, "saveImage")`.

**Measured live** — page built, opened as the active MDI view via `page.ViewObject.doubleClicked()`:

```
active view type: MDIViewPagePy
has saveImage:    False
get_active_screenshot(...) -> None
```

so `get_view` replies *"Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)."* The concrete class is **`MDIViewPagePy`**, not a 3D `View3DInventorPy`.

So the model can *build* a drawing — 45 `TechDraw::` object types are creatable — and then has **no way to look at it**. It is working blind on exactly the deliverable a drawing is meant to be.

Three routes, in ascending quality:

1. **`QWidget.grab()` on the MDI sub-window** — *S–M*. Qt can rasterise any widget regardless of type. One generic fallback fixes TechDraw **and** Spreadsheet **and** any future view type. Must run on the GUI thread (already the case). Recommended first move.
2. **`TechDrawGui.exportPageAsSvg(page, path)`** — *M*. Verified present in the installed `TechDrawGui.so`. Returns true vector output. Either rasterise with `QSvgRenderer` (PySide is already a dependency) or return the SVG source as text — an LLM reads SVG directly, though it is token-hungry.
3. **`exportPageAsPdf`** — *M*, needs an external rasteriser (poppler). Best fidelity, worst dependency story.

Do (1) as a general `view_type` fallback in `view_manager`, then (2) as a dedicated `export_techdraw_page` tool.

## A2. FreeCAD's Report View is not readable — **M**

Addon-side errors are printed with `FreeCAD.Console.PrintError` and `dispatch_to_gui` catches task exceptions and prints tracebacks there. All of it is visible only to a human sitting in front of FreeCAD. When a recompute emits *"Wire is not closed"*, the model never learns.

**Fix:** install a `FreeCAD.Console` observer (or redirect via `FreeCAD.Console.SetStatus`/a logging handler) into a bounded ring buffer, and expose `get_console_log(lines=50, level="error")`. Pairs naturally with C1 — the validity check says *something broke*, the log says *what*.

## A3. No selection / user-context awareness — **S–M**

`FreeCADGui.Selection` is fully scriptable (`getSelection`, `getSelectionEx`, `addSelection`, `clearSelection`) and `view_manager` already uses it internally for `focus_object`. Nothing exposes it as a tool, so the model cannot answer "what is the user pointing at?" — which is the natural way to say *"fillet this edge"*.

**Fix:** `get_selection` (returning object names + sub-element names like `Face3`/`Edge7`) and `set_selection`. Cheap, and it unlocks conversational editing.

---

# Class B — No first-class tool

## B1. No file I/O at all — ✅ **FIXED** (`8d84766`)

> **Fixed 2026-08-05.** `save_document`, `save_document_as`, `open_document`, `close_document`,
> `export_objects`, `import_file`, behind the import/export capability gates. Format dispatch
> uses FreeCAD's own `getExportType`/`getImportType` registry, so all ~53 formats are covered
> without a hand-written table.

Original analysis follows.

### The gap — **S each, high value**

FreeCAD registers **53 export formats**. The MCP exposes **zero**. There is no `save_document`, no `open_document`, no `export`, no `import`.

Note the sharp edge: `reload_document` exists and is documented for picking up external edits — but it *requires a file on disk*, and nothing in the MCP can put one there. `doc.save()`, `doc.saveAs()`, `FreeCAD.openDocument()`, `FreeCAD.closeDocument()` are all one-liners.

Practical impact: a user asking *"export this as STL for printing"* — the single most common FreeCAD endgame — requires `execute_code`.

**Fix:** `save_document`, `save_document_as`, `open_document`, `close_document`, `export_objects(doc, [names], path, format=None)`, `import_file(path, doc)`. Format dispatch across `Import.export` / `Mesh.export` / `Part.export` is the only wrinkle; extension-based dispatch matches what FreeCAD's own GUI does.

## B2. No undo / transaction support — **S, and it is a safety feature**

`openTransaction`, `commitTransaction`, `abortTransaction`, `undo`, `redo` all verified callable. None exposed.

Right now an LLM mistake is permanent unless the human intervenes. Worse, a multi-step tool call that fails halfway leaves a half-built document with no clean rollback.

**Fix:** wrap each mutating RPC handler in `openTransaction(tool_name)` / `commitTransaction`, `abortTransaction` on failure — this alone makes every LLM action individually undoable from FreeCAD's own Ctrl-Z. Then expose `undo`/`redo` tools. Small change, large safety gain.

## B3. Draft: 63 factories, none exposed — **M**

2D drafting, arrays (`make_ortho_array`, `make_polar_array`, `make_path_array`), `make_clone`, `make_shapestring`, dimensions. Arrays especially are a common ask ("put 12 of these on a bolt circle") that currently needs scripting.

Most take `Vector`/object arguments, so they need the same JSON→FreeCAD coercion `property_mapper` already does for `Placement`. Moderate, mechanical work.

## B4. Mesh workflow unexposed — **S–M**

`MeshPart.meshFromShape` (solid → mesh), `Mesh.export` (STL/OBJ/PLY/3MF), mesh repair/analysis, `minimumVolumeOrientedBox`. This is the 3D-printing path and it is entirely absent.

## B5. Spreadsheet cells unreachable — **S**

`sheet.set("A1", "42")` is a method. Measured: `A1` is **not** in `PropertiesList` before the write and **is** after. So `edit_object` can modify a cell that already exists but can never create one — a confusing partial capability.

Combined with FreeCAD's expression engine (`ExpressionEngine` is a property on every object), spreadsheet-driven parametric models are a major FreeCAD idiom that is effectively closed off.

**Fix:** `set_cells(doc, sheet, {"A1": "42", "B2": "=A1*2"})` and `get_cells`. Genuinely small.

## B6. Assembly (1.0+) unexposed — **L**

`UtilsAssembly` offers `activeAssembly`, `createPart`, `getAssemblyShapes`, `getBomGroup`, `findPlacement`, placement maths. But joints — the actual point of the workbench — are the hard part, and the solver API is not a stable documented surface. Treat as research, not plumbing.

## B7. FEM breadth — **S–M per item**

`run_fem_analysis` is genuinely good, but it is CalculiX-only. Unexposed: **four other solvers** (Elmer, Mystran, Z88, plain CalculiX), Netgen meshing, 10 Elmer equation types, all 17 post-processing/VTK filter factories, mesh regions and boundary layers.

The `Fem::` branch in `object_factory` already routes to `ObjectsFem.makeXxx` generically, so many of these *partly* work today via `create_object` — the gap is mostly that nothing tells the model they exist, and the result-extraction path in `fem_executor` is CalculiX-shaped.

---

# Class D — Scaling and ergonomics

## D1. `get_objects` has no filter or pagination — **M**

`serialize_object` dumps **every** property of **every** object, plus full `Placement`, `Shape` summary and `ViewObject`. Measured property counts: `Part::Box` 18, `PartDesign::Body` 14, `Sketcher::SketchObject` 26 — before values. On a real assembly this is a large payload on every call, and the screenshot rides along by default.

**Fix:** `properties=["Length","Placement"]` filter, `include_shape=False`, a names-only mode, and pagination. The `--only-text-feedback` flag and per-call `include_screenshot` show the project already takes token cost seriously; this is the same idea applied to the JSON side.

## D2. `execute_code_async` has no completion channel — **M**

It returns immediately and the docstring tells the model to poll a document object's `Label` for status — a convention the model must invent and maintain by hand. There is no job id, no status tool, no result retrieval. Output goes to the Report View, which per A2 is unreadable.

**Fix:** return a job id; keep a small job table in the addon; add `get_job_status(job_id)`. Fixing A2 also helps here.

## D3. `execute_code` is capped at 90 s on the GUI thread — **inherent**

`EXECUTE_CODE_TIMEOUT = 90`. Correct design — a longer GUI-thread block freezes FreeCAD — but it means genuinely long OCCT work must go async, which lands in D2. Worth documenting to the model rather than "fixing".

## D4. No measurement tools — **S**

FreeCAD 1.0 added a `Measure::` namespace (9 types), and `Part.Shape` exposes `Volume`, `Area`, `BoundBox`, `CenterOfMass`, `Inertia`. `serialize_shape` already returns Volume/Area/counts, but there is no tool for "how far apart are these two faces?" — a routine engineering question.

---

# Suggested order of work

| # | Item | Class | Effort | Status |
|---|---|---|---|---|
| 0 | Guard `serialize_shape` (C0) | Trap | **S** | ✅ **done** `30738ca` |
| 1 | Validity check after create/edit (C1) | Trap | **S** | ✅ **done** `bddf445` |
| 2 | Transactions + undo (B2) | Missing | **S** | open — makes every LLM action reversible; safety net for all later work |
| 3 | Save / open / export / import (B1) | Missing | **S** | open — unblocks STL/STEP export, the most common real endgame |
| 4 | Generic `QWidget.grab()` view capture (A1) | Blind | **S–M** | open — one change makes TechDraw *and* Spreadsheet visible |
| 5 | Console log tool (A2) | Blind | **M** | open — turns "it failed" into "here is why" (C1 now covers part of this) |
| 6 | Selection tools (A3) | Blind | **S–M** | open — enables "fillet *this* edge" conversational editing |
| 7 | Spreadsheet cells (B5) | Missing | **S** | open — small, unlocks expression-driven models |
| 8 | Body-aware PartDesign (C2) | Trap | **M** | open — opens 71 object types properly |
| 9 | Sketch geometry schema (C3) | Trap | **L** | open — biggest unlock; do it once C2 exists to consume it |
| 10 | `get_objects` filtering (D1) | Scaling | **M** | open — do when payload size starts to bite |

Items 0 and 1 are done and verified headlessly; both still want a live-path confirmation
(`python3 docs/verify_gaps.py` after a FreeCAD restart). Change log in
[`version_history.md`](version_history.md).

Items 1–3 are roughly one focused day together and remove the most dangerous behaviour. Items 8–9 together are the real project: they are what turn this from "an LLM that scripts FreeCAD" into "an LLM that models in FreeCAD".

---

## Live verification

Run against FreeCAD 1.1.1 + the RPC server on **2026-08-05**, driving XML-RPC on `localhost:9875` directly. Reproduce with `python3 docs/verify_gaps.py`.

| Check | Result |
|---|---|
| `ping` | OK |
| `create_object Part::Box` | `{'success': True, 'object_name': 'Box'}` |
| screenshot of 3D view | OK — 51,896 b64 chars (~39 KB PNG) |
| `edit_object Body.Group=['Sk']` | `success: False` — *"Type must be App.DocumentObject or None, not str"* (**C2**) |
| `create_object PartDesign::Pad` (no body) | `{'success': True, 'object_name': 'Pad2'}` — object is `['Touched','Invalid']`, `Shape.isNull()==True` (**C1**) |
| `get_object(doc,'Pad')` | **Fault** — `RuntimeError: shape is invalid` (**C0**) |
| `get_objects(doc)` | **Fault** — whole document unreadable (**C0**) |
| `get_object(doc,'Box')` | OK — healthy objects unaffected |
| TechDraw page as active view | `MDIViewPagePy`, `hasattr(saveImage)==False` (**A1**) |
| `get_active_screenshot` w/ page active | `None` — page invisible (**A1**) |
| `get_objects` payload | 2,719 chars for 4 objects (~680 chars/object) (**D1**) |
| `system.listMethods` | not registered — no introspection endpoint |

### Caveat on the deployed addon

The addon deployed at `~/Library/Application Support/FreeCAD/v1-1/Mod/FreeCADMCP` is dated **10 July**, while the repo is **1 August**. Five files differ: `rpc_server.py`, `object_factory.py`, `view_manager.py`, `gui_dispatch.py`, `fem_executor.py`. Tests above therefore ran against the *older* build.

This does not weaken the findings:

- **C0** — `serialize.py` is **byte-identical** in both. The bug is in current repo code.
- **C1** — the deployed `create_object_gui` returns bare `True`; the repo version returns `{"success": True, "object_name": created.Name}`. Both return success unconditionally after `doc.recompute()` with no validity check, so the trap is present in both. The repo version is otherwise an improvement (it reports real object names).
- **C2 / A1** — `property_mapper.py` is identical in both; the `saveImage` gate is unchanged in substance.

Re-run `verify_gaps.py` after deploying the repo build to confirm.

## One caution on Class B generally

Adding a first-class tool is not purely a win. Every tool is permanently in the model's context and competes for attention with `execute_code`, which can already do the job. The tools worth adding are the ones where a schema buys **validation and discoverability** the model cannot get from raw Python — sketches, PartDesign bodies, exports — not thin wrappers over calls the model can already write correctly from memory.
