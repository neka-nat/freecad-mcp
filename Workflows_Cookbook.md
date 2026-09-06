# Workflows_Cookbook.md
## End-to-end recipes from real sessions

**Version 3.0** | These recipes capture patterns the agent has redeveloped multiple times across sessions. Always check this cookbook before improvising — the patterns here are tested in this exact environment.

Each recipe follows the format:
- **When to use** (trigger conditions)
- **Inputs** (what the user provides)
- **Steps** (numbered actions, with code)
- **Verify** (how to confirm success)
- **Pitfalls** (specific failures to avoid)

---

## Recipe 1 — `new_parametric_part`
### Build a part from scratch using dimensioned drawings

**Verified session:** Project memory `Damper Bracket (PTT Mount)` rebuild from `DamperBracket_9mmBase_ShaftFixed.FCStd`; current verification pending in Bambu Studio.

**When to use**: User uploads a dimensioned drawing or describes a part with explicit dimensions, and there is no source STL.

**Inputs**: Drawing/photo with dimensions OR text description with all key measurements.

**Steps**:

1. **Analyze geometry** — list every dimension, identify the primitives (boxes, cylinders, cones), and identify all features (bores, bosses, mounting holes, ribs).

2. **Run FDM checklist** (see `FDM_Reference.md` §1–§5). Output the `[OK] / [WARN]` table.

3. **Show modeling plan** to the user before executing. Wait for confirmation if any feature is ambiguous (especially overhang treatment, hole positions, or symmetry).

4. **Create the document**:
```python
import FreeCAD, Part
doc = FreeCAD.newDocument("PartName")
doc.recompute()
```

5. **Build base body**, then add features one logical block at a time. Recompute and `freecad:get_view` after each block.

6. **Apply tolerances**: every bore +0.2 mm, every bolt-clearance +0.4 mm, every hex nut trap flat-to-flat +0.3 mm.

7. **Final fuse and export**:
```python
import Mesh, os
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
final = doc.getObject("Final")
doc.recompute()
Mesh.export([final], os.path.join(desktop, "PartName_v1.stl"))
```

**Verify**: bounding box matches target ± tolerance, get_view shows expected silhouette, no `[WARN]` left unaddressed.

**Pitfalls**:
- Don't forget tolerances — modeled bore should always be larger than drawing.
- A boss (Ø42 boss on a 64×64 base) can overhang the base — verify XY bounding box matches the drawing, not the base alone.

---

## Recipe 2 — `modify_imported_stl`
### Add geometry to an existing STL (mesh-based, no parametric edits)

**Verified session:** Project memory `YZ125 FuelDumper` mesh modification and export as `FuelDumper_9mmBase.stl`.

**When to use**: User uploads an STL or has one already loaded in FreeCAD as a `Mesh::Feature`, and wants to add a feature (collar, boss, ear, bracket extension).

**Inputs**: STL file or already-imported Mesh object + description of what to add + dimensions.

**Steps**:

1. **Inspect the mesh**:
```python
mesh_obj = doc.getObject("YZ125_Fuel_Dumper_final_v1")
bb = mesh_obj.Mesh.BoundBox
print(f"X: {bb.XMin:.2f}→{bb.XMax:.2f} ({bb.XLength:.2f})")
print(f"Y: {bb.YMin:.2f}→{bb.YMax:.2f} ({bb.YLength:.2f})")
print(f"Z: {bb.ZMin:.2f}→{bb.ZMax:.2f} ({bb.ZLength:.2f})")
```

2. **Build the new feature as a mesh** (NOT as Part::Cylinder, because we'll fuse meshes directly and avoid complex STL mesh-to-shape conversion timeouts):
```python
import Mesh
collar = Mesh.createCylinder(outer_r, height, True, 1, 32)
bore = Mesh.createCylinder(inner_r + 0.1, height + 2, True, 1, 32)
collar.difference(bore)
collar.translate(cx, cy, z_start)   # plain floats
```

3. **Unite with the original**:
```python
new_mesh = mesh_obj.Mesh.copy()
new_mesh.unite(collar)
```

4. **Add as new mesh object, hide original**:
```python
result = doc.addObject("Mesh::Feature", "PartName_Modified")
result.Mesh = new_mesh
mesh_obj.Visibility = False
doc.recompute()
```

5. **Export STL** (see Recipe 1 step 7).

**Verify**: bounding box reflects the addition, get_view shows feature in correct position, no holes in the mesh.

**Pitfalls**:
- **Never convert a complex STL mesh into a Part shape** — it times out or crashes. Stay in mesh-land.
- Use plain floats with `mesh.translate(x, y, z)` — `FreeCAD.Vector` will fail.
- Build the feature as a mesh with `Mesh.createCylinder` / `Mesh.createBox`, not as `Part::*` — converting Part→Mesh works, but mesh→Part doesn't.

---

## Recipe 3 — `mesh_thicken_base`
### Make the bottom face thicker without deforming the rest of the part

**Verified session:** Project memory `YZ125 FuelDumper` base-thickness correction; Bambu Studio verified slab-and-lift behavior after vertex stretching produced the wrong thickness.

**When to use**: User wants to add Z-thickness to the base of an STL (e.g. "add 3 mm to the bottom" or "make the base 9 mm").

**This is a high-failure-rate request** — vertex stretching produces uneven bases. Use the slab-and-lift method below instead.

**Inputs**: Loaded mesh + target base thickness (mm) OR delta thickness to add.

**Steps**:

1. **Inspect mesh** (Recipe 2 step 1).

2. **DO NOT stretch vertices**. Stretching deforms the bottom and the verified result in Bambu Studio is wrong (e.g. 5.6 mm instead of 9 mm requested).

3. **Lift the entire mesh up by the slab thickness, then add a flat slab below**:
```python
import Mesh

TARGET_SLAB = 9.0   # desired base thickness

# Lift the original mesh upward
new_mesh = mesh_obj.Mesh.copy()
new_mesh.translate(0.0, 0.0, TARGET_SLAB)

# Build a flat slab covering the full XY footprint
bb = mesh_obj.Mesh.BoundBox
slab = Mesh.createBox(bb.XLength, bb.YLength, TARGET_SLAB)
cx = bb.XMin + bb.XLength / 2
cy = bb.YMin + bb.YLength / 2
slab.translate(cx, cy, TARGET_SLAB / 2)   # slab spans Z=0 to Z=TARGET_SLAB

# Unite — flat 9 mm slab welded under the original mesh
new_mesh.unite(slab)

result = doc.addObject("Mesh::Feature", "PartName_thickBase")
result.Mesh = new_mesh
mesh_obj.Visibility = False
doc.recompute()
```

4. **Export and verify in Bambu Studio**.

**Verify**: in Bambu Studio, measure the distance from the bottom face to the original geometry — it must equal `TARGET_SLAB` exactly. If it doesn't, the original mesh had an uneven bottom (very common for reverse-engineered STLs).

**Pitfalls**:
- The slab must be **at least as wide as the original mesh's XY bounding box**, otherwise edges will hang off.
- If the original mesh's bottom is uneven, this method produces a **flat new bottom** at Z=0 — that's the desired behavior, but tell the user.

---

## Recipe 4 — `reverse_engineer_from_fcstd`
### Open a reference FCStd file and extract its dimensions to rebuild a clean parametric version

**Verified session:** Project memory `Damper Bracket (PTT Mount)` reverse-engineered from `DamperBracket_9mmBase_ShaftFixed.FCStd`.

**When to use**: User uploads a reference `.FCStd` file (often a previous mesh-based version) and asks to rebuild it parametrically or to compare against a current model.

**Inputs**: Path to FCStd file (often on Desktop or in `~/Documents/3D Models/`).

**Steps**:

1. **Locate the file** — try common upload locations:
```python
import os
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
docs_3d = os.path.join(os.path.expanduser("~"), "Documents", "3D Models")
print("Desktop:", os.listdir(desktop))
# also check Downloads, AppData/Local/Temp/uploads
```

2. **Open and list objects**:
```python
import FreeCAD
ref_doc = FreeCAD.openDocument(file_path)
for obj in ref_doc.Objects:
    print(f"  [{obj.TypeId}] {obj.Name} — Label: {obj.Label}")
```

3. **Extract bounding box** of the main mesh/part:
```python
main = ref_doc.getObject("MainObjectName")
if hasattr(main, "Mesh"):
    bb = main.Mesh.BoundBox
elif hasattr(main, "Shape"):
    bb = main.Shape.BoundBox
print(f"X: {bb.XLength:.2f}, Y: {bb.YLength:.2f}, Z: {bb.ZLength:.2f}")
```

4. **For mesh references**, sample features by slicing — find holes by counting facets per Z-level, find walls by looking at the mesh outline at known Z-heights.

5. **Build a gap analysis** (table comparing reference vs current model). Show the user the gaps before deciding what to rebuild.

6. **Rebuild parametrically using Recipe 1** — this gives a clean editable version.

**Verify**: bounding boxes within ± 0.5 mm; key features (bores, bolt circles, total height) match within tolerance.

**Pitfalls**:
- Reference FCStd may contain multiple closed/open documents — close everything else first to avoid collisions.
- Mesh objects in old FCStds often have non-flat bottoms — use `Recipe 3` to fix before reusing.

---

## Recipe 5 — `resume_session`
### Continue from a part that was left mid-execution

**Verified session:** Project memory `Damper Bracket (PTT Mount)` paused after `DamperBracket_v2.stl` export, with feedback pending.

**When to use**: Session opens with project memory mentioning an in-progress part (e.g. "Damper Bracket through-bore cut still in progress").

**Steps**:

1. **List documents first** — never assume:
```python
freecad:list_documents
```

2. **Inspect each named candidate**:
```python
freecad:get_objects   # doc_name: from list_documents output
```

3. **Triage: resume vs rebuild**:
   - **Resume** if doc has clean intermediate objects and the last operation is identifiable.
   - **Rebuild** (recommended) if doc has artifacts, broken booleans, or multiple half-finished versions (`DamperBracket`, `HolderDamper`, `DamperV3` all open is a rebuild signal).

4. **Show the user a 1-line status and ask**:
> "DamperV3 has the boss ring and arch shell, central bore not cut yet — resume or rebuild from scratch?"

5. **If rebuilding**, close stale docs:
```python
import FreeCAD
for name in list(FreeCAD.listDocuments().keys()):
    if name != "KeepThisOne":
        FreeCAD.closeDocument(name)
```

6. **Proceed with Recipe 1** for the rebuild.

**Pitfalls**:
- Don't auto-rebuild without user confirmation — they may have intentional in-progress work.
- Don't try to fix broken booleans — clean rebuild is faster than debugging stale CSG trees.

---

## Recipe 6 — `multi_doc_cleanup`
### Reset FreeCAD when too many half-finished docs are open

**Verified session:** Project memory document-hygiene lesson: stale open documents caused version confusion; full close + rebuild is the recovery pattern.

**When to use**: `freecad:list_documents` returns 3+ docs and the user wants a fresh start.

**Steps**:
```python
import FreeCAD

# Close everything
for name in list(FreeCAD.listDocuments().keys()):
    FreeCAD.closeDocument(name)

print("All documents closed.")
```

Then create a fresh doc with Recipe 1.

**Pitfall**: this loses unsaved work — confirm with the user first.

---

## Recipe 7 — `add_overhang_safe_arch`
### Replace a curved arch (>45° overhang) with a chamfered or stepped version

**Verified session:** Project memory `Damper Bracket (PTT Mount)` arch-shell work and FDM overhang corrections for Bambu Lab A1.

**When to use**: User's design has an arch, dome, or curved overhang that exceeds 45° from vertical (the most common Bambu A1 violation).

**Two FDM-safe alternatives**:

### 7a — Chamfered peak (fastest)
Replace the curve with a triangular peak:
```python
# Build the peak as a wedge: full-width box cut by a 45° wedge
peak = doc.addObject("Part::Box", "ArchPeak")
peak.Length = arch_w; peak.Width = arch_d; peak.Height = peak_h

# Diagonal cut — wedge of length ≥ peak_h to make 45° face
wedge = doc.addObject("Part::Box", "Wedge")
wedge.Length = peak_h * 1.5; wedge.Width = arch_d + 2; wedge.Height = peak_h * 1.5
wedge.Placement = FreeCAD.Placement(
    FreeCAD.Vector(arch_w, -1, 0),
    FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), -45)
)

cut = doc.addObject("Part::Cut", "ChamferedPeak")
cut.Base = peak; cut.Tool = wedge
doc.recompute()
```

### 7b — Stepped overhang
Build the curve as a stack of boxes, each stepping in by ≤ layer height. Each step prints clean as a horizontal layer.

**Verify**: visually confirm in `freecad:get_view` that no face exceeds 45° from vertical.

**Pitfall**: Do not use a fillet on the bottom edge to "soften" the chamfer — fillets on bottom edges are an FDM failure mode.

---

## Recipe 8 — `verify_with_bambu_studio`
### Workflow for confirming exported STL matches expectations

**Verified session:** Project memory `DamperBracket_v2.stl` verification handoff and `FuelDumper_9mmBase.stl` Bambu Studio base-thickness measurement workflow.

**When to use**: After every successful export.

**Steps to give the user**:
1. Open exported STL in Bambu Studio (drag onto build plate).
2. Use the **Measure tool** (M key) to confirm:
   - Total bounding box (X, Y, Z)
   - Critical bore diameters (use Measure → Distance between parallel faces)
   - Critical hole positions (Measure → Distance between centers)
   - Base thickness (Measure → distance from bottom face to first internal feature)
3. If any measurement deviates by more than tolerance, report back to the agent with the actual reading (e.g. "Bambu shows 5.6 mm but should be 9 mm").
4. Agent applies the appropriate fix recipe (most often Recipe 3 for base issues).

**Pitfall**: Don't trust FreeCAD's bounding box for the slab thickness — the original mesh might have an uneven bottom that FreeCAD reports as a clean number.

---

## Recipe 9 — `file_transfer_fallbacks`
### When file transfer between agent environment and FreeCAD fails

**Verified session:** Project memory file-access lesson: FreeCAD Python could not access agent sandbox upload paths and needed Windows-visible paths.

**When to use**: Chrome MCP is offline, file uploads aren't visible to FreeCAD, or `bash_tool` can't write to the user's local disk.

**Order of fallbacks**:

1. **User uploads file directly to FreeCAD's Documents folder** — most reliable, ask the user to do this.

2. **Use FreeCAD's Python download** (works if user's machine has internet):
```python
import urllib.request
url = "https://example.com/path/to/file.stl"
local = os.path.join(desktop, "downloaded.stl")
urllib.request.urlretrieve(url, local)
```

3. **Generate a repo-local Python script under `C:\Users\AXIO\Documents\freecad-mcp\examples\` and ask the user to paste or run it in FreeCAD's Python Console** — useful when the script is small but the data is local.

4. **Last resort**: instruct the user to run a one-line PowerShell or shell command to move the file.

**Pitfall**: don't try base64-pasting STL files into `execute_code` — they're typically several MB and will crash the prompt.

---

## Recipe 10 — `add_recipe`
### How to add a new recipe to this cookbook

**Verified session:** `AUDIT.md` 2026-06-06 finding A10 required every cookbook recipe to carry session provenance.

When a session reveals a new recurring pattern:

1. Identify the trigger condition (when would the agent need this?).
2. Document Inputs / Steps / Verify / Pitfalls in the same format.
3. Append to this file at the bottom — keep recipes ordered chronologically by date added.
4. Update `Workflows_Cookbook.md` reference in the system prompt only if a major reorganization happens.

---

*Cross-reference: see `FDM_Reference.md` for engineering rules and Python primitives. The system prompt orchestrates which recipe to apply when.*
