# Changelog

All notable changes to this fork are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This is a fork of [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp). Versions up to
and including `0.1.21` are upstream's; `0.2.0` is the first release of this fork.

---

## [0.2.0] - 2026-08-05

First release of the fork. Every change was verified against a running FreeCAD 1.1.1.

### Fixed

- **One broken object no longer blinds the whole document.** `serialize_shape` read
  `shape.Volume` without a guard, so an object whose shape failed to compute raised
  `RuntimeError: shape is invalid`, which reached the client as an XML-RPC Fault and failed the
  **entire** `get_objects` call. Since the built-in prompt instructs the model to call
  `get_objects` before every task, a single broken feature left it permanently unable to inspect
  the document. Broken shapes now report `{"Valid": false, "Error": …}` and healthy output is
  unchanged.
- **`create_object` no longer reports success for objects that failed to compute.** A
  `PartDesign::Pad` created outside a Body returned `success: True` while sitting `Invalid` with
  a null shape, so the model would build on geometry that did not exist. Failures now carry
  FreeCAD's own reason via `getStatusString()`, plus the object name so the caller can repair or
  delete it instead of retrying. Applied to `edit_object` too — an edit can break a healthy
  object just as easily.
- **Auto-start and the remote-connections toggle now work.** Three independent causes: FreeCAD
  passes `checked=0` to `Activated()` in both directions, so the setting was pinned to `False`
  forever; `QtWidgets.QAction` does not exist on PySide6 (Qt6 moved it to `QtGui`) and the
  resulting `AttributeError` was swallowed, so the startup sync silently failed and the toolbar
  could show *Auto-Start ✓* while the settings file said `false`; and `setChecked()` re-entered
  the command, bouncing the state back.
- **The settings file can no longer be silently emptied.** Saving truncated the real file before
  writing, so a crash in that window left 0 bytes and every setting reverted to defaults. Writes
  now go to a temp file and are moved into place atomically; an unreadable file is preserved as
  `.bad` rather than overwritten.
- **`close_document` no longer discards unsaved work.** `Gui.Document.Modified` is the only
  trustworthy dirty flag on FreeCAD 1.1, and it is cleared solely by `Gui.Document.save()` —
  never by `App.Document.save()`. Saving through the GUI document keeps it accurate.

### Added

- **`create_sketch`** — build Sketcher geometry and constraints from plain JSON. Previously a
  sketch could only be made with `execute_code`, because `Part.LineSegment` cannot cross
  XML-RPC. Supports `polyline`, `rectangle`, `line`, `circle`, `arc`, `ellipse` and `point`, any
  of them construction, plus 17 constraint types. `polyline` and `rectangle` add their own
  coincident constraints, since an unclosed wire is the usual reason a Pad silently produces
  nothing. Returns `degrees_of_freedom`, `fully_constrained` and `closed_wires` so a usable
  profile can be told from a decorative one.
- **`body_name` on `create_object`** — creates a PartDesign feature *inside* a Body and advances
  its Tip. Body membership is a method call, not a property, so this was previously impossible
  over the wire and 71 PartDesign types were effectively unreachable. A PartDesign feature
  requested without a Body is now refused with an explanation rather than quietly producing
  nothing.
- **File tools** — `save_document`, `save_document_as`, `open_document`, `close_document`,
  `export_objects`, `import_file`. Format dispatch uses FreeCAD's own handler registry, so all
  ~53 registered formats work (STEP, IGES, BREP, STL, OBJ, PLY, 3MF, DXF, SVG …) with no
  hand-written extension table. Overwrites are refused unless explicitly requested.
- **TechDraw pages and spreadsheets can be captured.** `get_view` previously required
  `view.saveImage`, which a drawing page does not have, so drawings were invisible. Capture is
  now layered: the 3D view uses `saveImage`, a TechDraw page renders its scene (independent of
  zoom, scroll and window occlusion, and without disturbing the user's view), and anything else
  falls back to a widget grab.
- **A regression suite** — `docs/verify_gaps.py` runs against a live FreeCAD, builds real
  geometry, asserts the numbers and cleans up after itself.
- **Analysis documents** — `docs/mcp-gap-analysis.md` explains what was missing and why, and
  `docs/freecad-python-api-inventory.md` records FreeCAD 1.1.1's scriptable surface measured by
  introspection (352 object types, 76 FEM factories, 63 Draft factories, 53 export formats).

### Security

- **Capability gates.** Anything that could reach port 9875 previously got the whole RPC surface,
  including `execute_code` — arbitrary Python with FreeCAD's privileges. Five gates now sit on
  the RPC boundary, secure by default: only object editing is enabled; file import, file export,
  code execution and external solvers are opt-in. Inspection is never gated, so a refused call
  can still explain itself. Enforcement is in the addon rather than the MCP server, because the
  addon is the side that cannot be bypassed by another client, a script, or a remote machine.

### Changed

- **The FreeCAD toolbar was rebuilt** and is now visible from any workbench, not only the MCP
  one. A single **MCP On/Off** button replaces the always-enabled Start/Stop pair, with a status
  dot: red stopped, green running, amber shutting down. The amber state matters because the stop
  drains on a background thread — a two-state indicator would say "stopped" while the socket was
  still bound and invite a restart that fails with `EADDRINUSE`.
- **A settings dialog** (gear) consolidates auto-start, remote connections, allowed IPs and the
  capability gates, showing the live server status and bound address.
- **A document-location menu** (folder) lists the front document's path from filesystem root to
  file; clicking any level opens it in Finder, Explorer or your file manager.

### Known limitations

- A subtractive feature whose sketch sits below the material cuts into empty space. It reports
  success and is genuinely *valid* — it simply removes nothing — so neither the validity check
  nor the sketch validation catches it. Compare the body volume, or set `Reversed`.
- `view_name` applies only to the 3D view; it is ignored for drawings and spreadsheets, which
  have no 3D orientation.
- Sketch geometry is 2D by design. Attachment is limited to the three origin planes (`XY`, `XZ`,
  `YZ`); attaching to a face still needs `execute_code`.

---

## [0.1.21] and earlier

Upstream releases. See [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp).
