# FDM_Reference.md
## Single source of truth — Bambu Lab A1 + FreeCAD scripting

**Version 3.0 | Replaces:** Bambu_A1_FDM_Design_Rules.txt v1.0, Bambu_A1_FDM_Design_Guide.pdf, FreeCAD_Python_Scripting_Reference.md, and the embedded rules in System Prompt v2.0.

This document has two halves:
- **§1–§6**: Engineering rules (FDM design constraints for Bambu A1)
- **§7–§13**: FreeCAD Python scripting (verified patterns + pitfalls)

If the system prompt and this document disagree, **this document wins**.

---

# PART A — ENGINEERING RULES

## §1 BUILD VOLUME

| Spec | Value |
|---|---|
| Max X / Y / Z | 256 mm each |
| Practical design limit | 250 mm per axis (margin for brim/skirt) |

**Splitting parts > 256 mm**:
- Choose split plane perpendicular to the longest axis at a neutral point.
- Avoid splitting through holes, load-bearing features, or snap-fits.
- Add alignment pins: **Ø4 mm × 6 mm tall, +0.15 mm clearance** on the pin hole.
- Add a **0.5 mm wide glue channel** around the joint perimeter.
- Name parts `PartName_P1`, `PartName_P2`, etc.
- Verify the **diagonal** dimension for parts placed at an angle — a 200 mm × 200 mm part rotated 45° has a 283 mm diagonal.

## §2 WALL THICKNESS (0.4 mm nozzle)

| Use case | Minimum | Recommended |
|---|---|---|
| Decorative only | 0.8 mm | 1.0 mm |
| Functional (default) | **1.2 mm** | 1.6 mm |
| Strong functional | 1.6 mm | 2.0 mm |
| Load-bearing / structural | 2.4 mm | 3.2 mm |
| Thin pin / clip — flexible | 1.6 mm dia | — |
| Thin pin / clip — rigid | 2.4 mm dia | — |

**Never** model functional walls below 1.2 mm. Flag with `[WARN]` if dimensions provided force a violation, then propose a thicker alternative.

**Line width reference** (auto-calculated by Bambu Studio): outer 0.42 mm, inner 0.45 mm, first layer 0.50 mm. Walls should be a multiple of line width when possible.

## §3 OVERHANGS, BRIDGES, EDGE TREATMENT

| Angle from vertical | Behavior |
|---|---|
| 0° – 45° | Safe, no support |
| 45° – 50° | Borderline, test first |
| > 50° | Requires support OR redesign |

**Bridges (horizontal spans without support)**:
- Reliable: **20–30 mm**
- Maximum with perfect cooling: **50 mm**
- Over 50 mm → add midpoint support column or redesign

**Edge treatment** — this is where most parts fail:
- **Use 45° chamfers on bottom edges.**
- **NEVER use fillets on bottom edges** — fillets create progressive overhangs that fail on FDM.
- Fillets are fine on **top-facing** edges and **vertical** edges.
- Standard chamfer: **0.5–1.0 mm × 45°**.

## §4 HOLE & CLEARANCE TOLERANCES

| Fit type | Modeled diameter | Use case |
|---|---|---|
| Press fit | target **− 0.1 mm** | permanent assembly, no slip |
| Snug fit | target **+ 0.1 mm** | hand-press fit |
| **Clearance fit (default)** | target **+ 0.2 mm** | shafts, pins, alignment |
| Bolt clearance | nominal **+ 0.4 mm** | M-bolt through-holes |
| Hex nut trap | flat-to-flat **+ 0.3 mm** | embedded nut pocket |

**Bolt clearance quick lookup**:

| Bolt | Modeled hole |
|---|---|
| M3 | 3.4 mm |
| M4 | 4.4 mm |
| M5 | 5.4 mm |
| M6 | 6.4 mm |

**Orientation matters**:
- **Vertical holes** (axis along Z) print accurately — first choice for precision fits.
- **Horizontal holes < 5 mm** sag — add extra **+0.1 mm**.
- For best results, design so the precision feature ends up vertical when printed.

## §5 BASE & FIRST LAYER

- Every part must have at least one flat face for the build plate.
- If no natural flat face exists, add a **2 mm minimum flat pad** at the bottom.
- Orient the part so the **largest flat face** is on the build plate.
- Critical surfaces face **up** — top layers have the best finish and accuracy.
- Tall narrow parts (height > 3× base width) → enable brim in Bambu Studio.

**Elephant foot compensation**: first layer expands ~0.2–0.3 mm outward. For precision-fit bases:
- Subtract 0.2 mm from XY base dimensions, OR
- Add a **0.5 mm × 45°** chamfer on the bottom edge.

**First-layer rule**: do not place holes, slots, or critical features within the first **0.4 mm** of part height. Place these features 1–2 mm above the build plate.

## §6 LAYER HEIGHTS & PRINT SETTINGS

| Quality | Layer height | Use case |
|---|---|---|
| Draft | 0.28 mm | Fast prototypes, visible layers |
| Standard (default) | 0.20 mm | General use |
| Fine | 0.12 mm | Smooth finish, detailed parts |
| Ultra fine | 0.08 mm | Display parts only, very slow |

Wall count: **4 perimeters minimum** for functional parts. Infill: 20% default, **40%+ for structural / vibration loads**.

---

# PART B — FREECAD PYTHON PATTERNS (verified in this environment)

## §7 DOCUMENT SETUP

```python
import FreeCAD, Part, Mesh, os

# Create a new doc with explicit name
doc = FreeCAD.newDocument("PartName")

# Or get an already-active doc
doc = FreeCAD.ActiveDocument

# Or fetch by name (when resuming sessions)
doc = FreeCAD.getDocument("PartName")

# ALWAYS at the end of every code block:
doc.recompute()
```

## §8 PART PRIMITIVES (CSG approach)

```python
# Box
b = doc.addObject("Part::Box", "Base")
b.Length = 50.0; b.Width = 30.0; b.Height = 20.0

# Cylinder (default Z-axis)
c = doc.addObject("Part::Cylinder", "BoreZ")
c.Radius = 5.2          # target 5.0 + 0.2 clearance
c.Height = 25.0

# Cylinder along X-axis (rotate 90° around Y)
c.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 15, 10),
    FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)
)

# Cone (chamfer-like or tapered)
cone = doc.addObject("Part::Cone", "Cham")
cone.Radius1 = 5.0; cone.Radius2 = 3.0; cone.Height = 2.0

doc.recompute()
```

## §9 BOOLEAN OPERATIONS

```python
# Cut (subtract Tool from Base)
cut = doc.addObject("Part::Cut", "WithHole")
cut.Base = body; cut.Tool = bore

# Fuse (union)
fuse = doc.addObject("Part::Fuse", "Combined")
fuse.Base = part_a; fuse.Tool = part_b

# Common (intersection)
inter = doc.addObject("Part::Common", "Overlap")
inter.Base = part_a; inter.Tool = part_b

doc.recompute()
```

**Cutting rule**: the Tool must extend slightly past the Base on both ends — extend cylinders by 1 mm at each end so the cut surface is clean.

## §10 ROUNDED RECTANGLE (no native primitive)

FreeCAD has no rounded-box primitive. Use bounding box ∩ (4 corner cylinders fused). Function pattern:

```python
def make_rounded_box(doc, name, L, W, H, R):
    """Returns a Part::Common shape: rounded rect L×W×H with corner radius R."""
    box = doc.addObject("Part::Box", f"{name}_BB")
    box.Length = L; box.Width = W; box.Height = H

    corners = [(R,R), (L-R,R), (R,W-R), (L-R,W-R)]
    cyls = []
    for i, (cx, cy) in enumerate(corners):
        c = doc.addObject("Part::Cylinder", f"{name}_c{i}")
        c.Radius = R; c.Height = H
        c.Placement.Base = FreeCAD.Vector(cx, cy, 0)
        cyls.append(c)
    doc.recompute()

    f1 = doc.addObject("Part::Fuse", f"{name}_f1")
    f1.Base = cyls[0]; f1.Tool = cyls[1]
    f2 = doc.addObject("Part::Fuse", f"{name}_f2")
    f2.Base = cyls[2]; f2.Tool = cyls[3]
    f3 = doc.addObject("Part::Fuse", f"{name}_f3")
    f3.Base = f1; f3.Tool = f2
    doc.recompute()

    result = doc.addObject("Part::Common", f"{name}_Final")
    result.Base = box; result.Tool = f3
    doc.recompute()
    return result
```

## §11 MESH OPERATIONS (for STL files)

Imported STLs cannot be edited parametrically. Use mesh booleans directly.

```python
import Mesh

# Mesh primitives
box_m = Mesh.createBox(50.0, 30.0, 20.0)              # centered at origin
cyl_m = Mesh.createCylinder(r, h, closed=True, edges=1, segments=32)

# IMPORTANT: translate uses plain floats, NOT FreeCAD.Vector
box_m.translate(10.0, 0.0, 5.0)

# Boolean ops on meshes (mutate in place)
result = box_m.copy()
result.unite(cyl_m)         # union
# .intersect(other) and .difference(other) also available

# Add to document
mesh_obj = doc.addObject("Mesh::Feature", "Result")
mesh_obj.Mesh = result
doc.recompute()

# Export STL
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
Mesh.export([mesh_obj], os.path.join(desktop, "PartName_v1.stl"))
```

## §12 STL EXPORT (universal)

```python
import Mesh, os

desktop = os.path.join(os.path.expanduser("~"), "Desktop")
output_path = os.path.join(desktop, "PartName_v1.stl")

final = doc.getObject("Final")    # works for both Part and Mesh objects
doc.recompute()
Mesh.export([final], output_path)
print(f"Exported: {output_path}")
```

## §13 PITFALLS & WORKAROUNDS (lessons from real sessions)

| Symptom | Cause | Fix |
|---|---|---|
| Object appears but has no shape | Forgot to recompute | Call `doc.recompute()` after every change |
| `mesh.translate(FreeCAD.Vector(...))` errors | Wrong arg type | Use plain floats: `mesh.translate(x, y, z)` |
| `MeshPart.meshToShape()` times out / crashes | Mesh too complex | Don't use it — work with mesh booleans (`unite`, `difference`, `intersect`) |
| `Part.Shape.makeShapeFromMesh()` fails | Same as above | Same fix |
| Cut leaves a thin sliver | Tool didn't fully penetrate Base | Extend tool by 0.1–1 mm beyond Base on both ends |
| Cylinder oriented wrong | Default axis is Z | Set `Placement` with `FreeCAD.Rotation(axis, deg)` |
| Mesh stretch produced uneven base | Mesh vertex scaling deformed bottom | Don't stretch — **lift the mesh and add a flat slab** (see Cookbook recipe `mesh_thicken_base`) |
| Part shape comes out larger than expected | Boss/cylinder overhangs base | Compare bounding box against drawing; trim with `Part::Common` if needed |

## §14 NAMING & VERSIONING

```
Document:   DescriptivePart   e.g. WallBracket, DamperMount
Objects:    Base, CutA, CutB, BoreH, FuseAB, Final
STL export: PartName_vN.stl   on Desktop, bump N each successful build
FCStd:     PartName.FCStd   save in working folder
```

---

*Cross-reference: see `Workflows_Cookbook.md` for end-to-end recipes that combine these patterns.*
