# Project Memory — FreeCAD Modeling Agent

## Purpose & context

Michael is building a workflow around FreeCAD + Claude via the Model Context Protocol (MCP), enabling natural language-driven 3D modeling without requiring deep CAD expertise. The primary output target is FDM printing on a **Bambu Lab A1** (256×256×256mm build volume). Projects span mechanical reverse engineering, organic/decorative modeling, and multi-material print preparation in Bambu Studio.

Michael has also framed the FreeCAD MCP × Claude integration itself as a project worth documenting and promoting — positioning it against commercial alternatives (e.g., Autodesk Fusion 360 MCP) on the basis of cost, data sovereignty, and FDM-specific optimization.

Michael works primarily in **Spanish**; code identifiers and comments follow English convention by established agreement. His machine runs Windows with FreeCAD; file paths use the format `C:\Users\Lenovo User\...` (Documents/3D Models or Desktop). A second machine associated with AXIO uses `C:\Users\AXIO\OneDrive\Desktop`.

---

## Current state

Active or recently paused projects:

- **Dolphin puzzle ("Delfín Rompecabezas"):** Reverse engineering a physical wooden leaping-dolphin puzzle (~190×137×30.6mm) for FDM recreation. Stage 1 (exterior silhouette using two open B-spline curves) was completed and saved as a standalone parametric Python script (`delfin_puzzle.py`) with editable profile point lists. Stage 2 (puzzle cuts: horizontal dolphin/wave split, vertical center cut, front/back slab split) is pending approval of Stage 1 proportions.
- **AXIO wall plaque:** Embedding the AXIO logo into a `.3mf` circular disc model for multi-color Bambu Studio printing. Mesh boolean difference failed silently; the project was paused when it was discovered the imported `.3mf` fuses all objects into a single mesh with a non-circular bottom outline. Unresolved.
- **Damper Bracket (PTT Mount):** Mechanical part reverse-engineered from `DamperBracket_9mmBase_ShaftFixed.FCStd`. A v2 was exported (`DamperBracket_v2.stl`) for verification in Bambu Studio; feedback on v2 is pending.

Recently completed:
- Alpine cabin, Layla Rustic Cabin (with full scene: pine trees, mountains, terrain, access path), and decorative strawberry — all modeled in FreeCAD via MCP.
- AXIO LinkedIn QR code embedded into a disc model via multi-material Bambu Studio workflow (QR STL as separate part + height range modifier for background color contrast).
- YZ125 FuelDumper (`FuelDumper_9mmBase.stl`) — completed and exported.
- Footpeg extension modeling — two iterations failed to match reference; paused pending better dimensional inputs and a PartDesign Sketch + Pad knowledge upgrade.

---

## On the horizon

- Dolphin puzzle Stage 2 (puzzle cuts) and Stage 3 (cavity + dowel holes)
- Resolution of AXIO wall plaque boolean embedding (requires alternative to mesh boolean difference)
- Damper Bracket v2 visual verification and potential v3 iteration
- Improving organic/curved part modeling via PartDesign Sketch + Pad workflow and fillet/loft knowledge

---

## Key learnings & principles

- **Geometric correctness first:** Michael quickly identifies Z-placement errors (e.g., roof at ground level, walls not starting from floor) and expects self-correction without lengthy explanation. Always verify that objects attach to adjacent geometry at the correct coordinate.
- **Mesh booleans are unreliable for large meshes:** `mesh.difference()` silently fails (facet count unchanged), and complex STL mesh-to-shape conversion is unavailable or crashes — pure mesh workflows or CSG `Part::` operations are the reliable paths.
- **Periodic B-splines fail on concave profiles:** For organic closed shapes with concavities (e.g., dolphin tail fork), use two open B-spline edges sharing endpoints + `Part.makeLine` sides assembled into a `Part.Wire`.
- **Boolean cut chaining:** For multiple openings in one wall, `Part::Cut` objects must chain (`cut2.Base = cut1`, not the original wall).
- **Revolution solids for organic bodies:** `Part.BSplineCurve().interpolate(pts)` + `face.revolve()` produces smoother organic profiles than `Part.makeLoft`.
- **Roof panels:** Compute perpendicular normal mathematically and extrude a 4-point polygon along the ridge axis — more robust than FreeCAD built-in primitives.
- **Mesh reverse engineering:** ASCII grid projection (point cloud onto 2D slices) is more reliable than statistical clustering for identifying holes, bores, and wall profiles.
- **Document hygiene:** Always call `freecad:list_documents` at session start; stale open documents cause version confusion. Intermediate objects still referenced by dependents must not be deleted (causes `-inf` bounding boxes); full document close + rebuild from scratch is the recovery pattern.
- **`doc.recompute()` is mandatory** after every code block; omitting it causes silent failures where objects exist in the tree but have no computed shape.
- **STL export:** `doc.saveCopy(filepath)` works on new documents; `doc.save(filepath)` throws errors. `Mesh.export([obj], filepath)` with Desktop path via `os.path.expanduser("~")` is reliable.
- **FreeCAD Python environment cannot access agent sandbox upload paths** — files must be referenced by Windows-visible paths.
- **Modeling is not for 3D printing** unless explicitly stated: avoid raising printing-specific considerations (supports, tolerances, etc.) when the task is purely decorative or modeling-focused.

---

## Approach & patterns

- **Iterative, feedback-driven:** Michael confirms at each stage with brief signals ("it worked, continue") and flags errors directly ("el techo en forma de A esta en piso"). He expects Claude to diagnose and self-correct rather than ask for extensive clarification.
- **Staged builds:** Complex projects are broken into labeled stages (Etapa 1, 2, 3) with explicit sign-off before proceeding.
- **Multiple `execute_code` blocks over one large script:** Splitting construction into phases (base → walls → cuts → colors) allows intermediate verification and is more reliable than monolithic scripts.
- **Progressive fuse chains:** Fusing pairs sequentially is more reliable than multi-fuse for 5+ objects.
- **Reusable/parametric scripts:** Where possible, deliverables are standalone Python scripts with editable parameter lists at the top (e.g., `delfin_puzzle.py`).
- **Re-run safety:** Scripts check for existing objects and remove them before rebuilding (idempotent pattern).

---

## Tools & resources

- **FreeCAD MCP:** `freecad:execute_code`, `freecad:list_documents`, `freecad:create_document`, `freecad:get_objects` — primary modeling environment
- **Bambu Studio:** Slicing, visual verification, multi-material AMS setup; Bambu Lab A1 printer
- **Figma MCP:** `Figma:generate_diagram` with Mermaid syntax (Starter plan — view only; write operations blocked; FigJam diagram creation works without edit seat)
- **Key file locations:** resolve Desktop and Documents with `os.path.expanduser("~")`; mention machine-specific absolute paths only when the user provides them.
- **FreeCAD Python patterns reference:** `FDM_Reference.md` and `Workflows_Cookbook.md` (v3.0 restructure)
