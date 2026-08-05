# FreeCAD Python API — measured inventory

Everything below was **measured by introspection against the FreeCAD installed on this machine**, not taken from documentation:

| | |
|---|---|
| Build | FreeCAD **1.1.1**, libs 1.1.1R20260414 (Git shallow) |
| Bundled Python | **3.11.14** |
| App bundle | `/Users/jeanyves/ CAO/Freecad/FreeCAD.app` |
| Headless binary | `Contents/Resources/bin/freecadcmd` |

Reproduce with:

```bash
"/Users/jeanyves/ CAO/Freecad/FreeCAD.app/Contents/Resources/bin/freecadcmd" script.py
```

---

## 1. Document object types — 352 total

`doc.supportedTypes()` returns 38 types on a bare interpreter and **352 once the workbench modules are imported**. Every one of these is a legal first argument to `doc.addObject(type, name)` — which is exactly what the MCP's `create_object` calls in its generic branch.

| Namespace | Types | Namespace | Types |
|---|---:|---|---:|
| `PartDesign::` | 71 | `Measure::` | 9 |
| `Part::` | 63 | `Assembly::` | 7 |
| `Fem::` | 57 | `Surface::` | 7 |
| `TechDraw::` | 45 | `Points::` | 5 |
| `App::` | 38 | `Robot::` | 5 |
| `Mesh::` | 27 | `Sketcher::` | 3 |
| `Path::` (CAM) | 10 | `Inspection::` / `Spreadsheet::` | 2 each |

Full list: regenerate with the probe script in §8.

**Caveat that matters:** being *creatable* is not the same as being *usable*. Most `PartDesign::` and `Sketcher::` types produce an `Invalid` object when created bare — see the gap analysis for proof.

## 2. Workbenches importable headlessly

Loaded successfully in `freecadcmd`: `Part`, `PartDesign`, `Sketcher`, `Draft`, `Fem`, `ObjectsFem`, `Mesh`, `MeshPart`, `TechDraw`, `Import`, `Spreadsheet`, `Points`, `Surface`, `Path`, `CAM`, `Arch`, `BIM`, `Assembly`, `Material`/`Materials`, `Measure`, `OpenSCAD`, `ReverseEngineering`, `Inspection`, `importDXF`, `importSVG`, `Robot`, `Plot`, `Show`.

Failed headlessly: `Idf` (*"Cannot load Gui module in console application"*) — GUI-dependent modules exist but need the full GUI process. Inside the MCP addon you are always in the GUI process, so these are available there.

## 3. Part — solid modelling core

- **Module factories (30):** `makeBox`, `makeCylinder`, `makeSphere`, `makeCone`, `makeTorus`, `makeWedge`, `makeHelix`, `makeLongHelix`, `makeThread`, `makeTube`, `makeLoft`, `makeRevolution`, `makeShell`, `makeSolid`, `makeCompound`, `makeFace`, `makeFilledFace`, `makeFilledSurface`, `makeRuledSurface`, `makeSweepSurface`, `makeSplitShape`, `makeShellFromWires`, `makePlane`, `makePolygon`, `makeCircle`, `makeLine`, `makeWireString`, plus `read`/`export`/`show`/`cast_to_shape`.
- **`Part.Shape` — 137 methods.** Booleans (`cut`, `fuse`, `common`, `section`), `extrude`, `revolve`, `slice`/`slices`, `mirror`, `scale`/`scaled`, `transformGeometry`/`transformShape`/`transformed`, `tessellate`, healing (`check`, `fix`, `fixTolerance`, `removeSplitter`, `removeInternalWires`, `removeShape`, `replaceShape`).
- Fillet/chamfer are on the shape and on `Part::Fillet`/`Part::Chamfer` document objects.

## 4. FEM — the deepest scripted area (76 factories)

`ObjectsFem` exposes 76 `make*` functions. Categories:

- **Analysis/solvers:** `makeAnalysis`, `makeSolverCalculiX`, `makeSolverCalculiXCcxTools`, `makeSolverElmer`, `makeSolverMystran`, `makeSolverZ88` — **five** solver back-ends.
- **Meshing:** `makeMeshGmsh`, `makeMeshNetgen`, `makeMeshNetgenLegacy`, `makeMeshRegion`, `makeMeshBoundaryLayer`, `makeMeshGroup`, `makeMeshResult`.
- **Constraints (29):** `Fixed`, `Force`, `Pressure`, `Displacement`, `Contact`, `Spring`, `Temperature`, `Heatflux`, `BodyHeatSource`, `SelfWeight`, `Centrif`, `Tie`, `Transform`, `RigidBody`, `SectionPrint`, `PlaneRotation`, `Bearing`, `Gear`, `Pulley`, `FlowVelocity`, `InitialFlowVelocity`, `InitialPressure`, `InitialTemperature`, `FluidBoundary`, `ElectrostaticPotential`, `ElectricChargeDensity`, `CurrentDensity`, `Magnetization`, `ConstantVacuumPermittivity`.
- **Materials:** `makeMaterialSolid`, `makeMaterialFluid`, `makeMaterialMechanicalNonlinear`, `makeMaterialReinforced`.
- **Elmer equations (10):** `Heat`, `Flow`, `Flux`, `Elasticity`, `Deformation`, `Electrostatic`, `Electricforce`, `StaticCurrent`, `Magnetodynamic`, `Magnetodynamic2D`.
- **Post-processing (17):** `makePostVtkResult`, VTK filters (`ClipRegion`, `ClipScalar`, `Contours`, `CutFunction`, `Warp`), plus `makePostLineplot`, `makePostHistogram`, `makePostTable` and their `FieldData`/`IndexOverFrames` variants.

## 5. Draft — 63 factory functions

Legacy `makeXxx` and modern `make_xxx` names coexist. Notables beyond primitives: `make_ortho_array`, `make_polar_array`, `make_circular_array`, `make_path_array`, `make_path_twisted_array`, `make_point_array`, `make_clone`, `make_fillet`, `make_hatch`, `make_layer`, `make_shapestring`, `make_sketch`, `make_shape2dview`, `make_linear_dimension`, `make_angular_dimension`, `make_radial_dimension_obj`, `make_facebinder`, `make_workingplaneproxy`.

## 6. TechDraw, Import/Export, Mesh, Assembly, Materials

- **TechDraw module:** `project`, `projectEx`, `projectToSVG`, `projectToDXF`, `viewPartAsSvg`, `viewPartAsDxf`, `writeDXFPage`, `writeDXFView`, `makeDistanceDim`, `makeDistanceDim3d`, `makeExtentDim`, `makeGeomHatch`, `makeLeader`, `findOuterWire`, `findShapeOutline`, `findCentroid`, `edgeWalker`.
- **`TechDrawGui` (GUI process only) — verified present in `TechDrawGui.so`:**
  `exportPageAsPdf(DrawPageObject, FilePath)` and `exportPageAsSvg(DrawPageObject, FilePath)`. This is the documented escape route for getting a drawing page out of FreeCAD — see gap #9.
- **`Import`:** `open`, `insert`, `export`, `readDXF`, `writeDXFObject`, `writeDXFShape`, `StepShape`.
- **`Mesh`:** `open`, `insert`, `read`, `export`, `show`, primitives (`createBox`, `createSphere`, `createCylinder`, `createCone`, `createTorus`, `createEllipsoid`, `createPlane`), analysis (`minimumVolumeOrientedBox`, `calculateEigenTransform`, `polynomialFit`).
- **`MeshPart`:** `meshFromShape`, `wireFromMesh`, `wireFromSegment`, `projectShapeOnMesh`, `projectPointsOnMesh`, `loftOnCurve`, `findSectionParameters`.
- **Assembly (1.0+):** the `Assembly` module itself only re-exports `AssemblyApp`; the real Python surface is **`UtilsAssembly`** — `activeAssembly`, `createPart`, `getAssemblyShapes`, `getBomGroup`, `findPlacement`, `applyOffsetToPlacement`, `applyRotationToPlacementAlongAxis`, `getCenterOfMass`, `getCenterOfBoundingBox`, `arePlacementSameDir`, `flipPlacement`, and more.
- **`Materials` (new 1.0 system):** `MaterialManager`, `MaterialLibrary`, `MaterialFilter`, `Material`, `Model`, `ModelManager`, `MaterialProperty`, `Array2D`/`Array3D`, `UUIDs`.

## 7. File formats — 53 registered export extensions

```
3mf amf asc ast bdf bms brep brp csg dae dat dwg dxf glb gltf html ifc ifcJSON
iges igs inp json med meshjson meshpy meshyaml obj oca off pcd ply poly scad smf
step stl stp stpZ stpz svg txt unv vti vtk vtm vtp vtr vts vtu xdmf xml yaml z88
```

Covers STEP/IGES/BREP (CAD interchange), STL/OBJ/PLY/3MF/AMF/OFF/glTF/DAE (mesh & 3D print), DXF/DWG/SVG (2D), IFC (BIM), INP/UNV/MED/Z88/BDF (FEA), VTK family (post-processing), SCAD (OpenSCAD).

## 8. Core services confirmed present

- **Persistence:** `doc.save()`, `doc.saveAs(path)`, `FreeCAD.openDocument`, `FreeCAD.closeDocument`.
- **Undo/transactions:** `doc.openTransaction`, `commitTransaction`, `abortTransaction`, `undo`, `redo` — all callable.
- **Spreadsheet:** `sheet.set(addr, value)` / `sheet.get(addr)` are **methods**; a cell only appears in `PropertiesList` *after* it has been written.
- **Sketcher:** `sketch.addGeometry(geo, construction)` and `sketch.addConstraint(c)` are **methods**; `Geometry` is also a settable property.

### Probe script used

```python
import FreeCAD, json
for m in ["Part","PartDesign","Sketcher","Draft","Fem","ObjectsFem","Mesh","MeshPart",
          "TechDraw","Import","Spreadsheet","Points","Surface","Path","CAM","Arch",
          "BIM","Assembly","Material","Measure","OpenSCAD","ReverseEngineering",
          "Inspection","importDXF","importSVG","Robot","Plot","Show"]:
    try: __import__(m)
    except Exception as e: print("FAIL", m, e)
d = FreeCAD.newDocument("Probe")
types = sorted(d.supportedTypes())
groups = {}
for t in types: groups.setdefault(t.split("::")[0], []).append(t)
print(len(types), {k: len(v) for k, v in groups.items()})
print(sorted(FreeCAD.getExportType().keys()))
```
