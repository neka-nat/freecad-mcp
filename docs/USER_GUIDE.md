# FreeCAD MCP User Guide

Complete guide to using FreeCAD MCP with Claude Desktop.

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Basic Workflow](#basic-workflow)
4. [Advanced Features](#advanced-features)
5. [Assembly Workflow](#assembly-workflow)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

---

## Introduction

FreeCAD MCP enables you to control FreeCAD through Claude Desktop using natural language. Instead of learning complex CAD interfaces, simply describe what you want to create, and Claude will generate the appropriate FreeCAD commands.

### What You Can Do

- 📦 Create parametric 3D objects
- ✏️ Design with sketches and extrusions
- 🔧 Apply Boolean operations (union, cut, intersection)
- 🎨 Add finishing touches (fillets, chamfers, shells)
- 🔄 Transform and pattern objects
- 🏗️ Build assemblies with constraints
- ✈️ Design complex projects like aircraft

### System Architecture

```
Claude Desktop (User Interface)
    ↓ Natural Language
Model Context Protocol (MCP)
    ↓ Tool Calls
FreeCAD MCP Server
    ↓ XML-RPC
FreeCAD (CAD Engine)
```

---

## Getting Started

### Prerequisites

Before starting, ensure you have:
- ✅ FreeCAD 0.21+ installed
- ✅ Python 3.10+ installed
- ✅ Claude Desktop installed
- ✅ FreeCAD MCP addon installed
- ✅ Claude Desktop configured

See [Quick Start Guide](QUICKSTART.md) for installation instructions.

### First Steps

1. **Launch FreeCAD**
   - Open FreeCAD
   - Select "MCP Addon" workbench
   - Click "Start RPC Server"

2. **Open Claude Desktop**
   - You should see "freecad" in available tools
   - If not, restart Claude Desktop

3. **Try a Simple Command**
   ```
   "Create a box 100mm x 50mm x 30mm"
   ```

4. **Check FreeCAD**
   - You should see the box created
   - Screenshot should appear in Claude

---

## Basic Workflow

### Creating Simple Shapes

#### Box
```
"Create a rectangular box 100mm long, 50mm wide, 30mm high"
```

#### Cylinder
```
"Create a cylinder with radius 20mm and height 50mm"
```

#### Sphere
```
"Create a sphere with radius 30mm"
```

### Positioning Objects

#### Absolute Position
```
"Move Box001 to position x=100, y=50, z=0"
```

#### Relative Movement
```
"Move Cylinder001 10mm in the positive X direction"
```

### Modifying Objects

#### Change Dimensions
```
"Change the height of Cylinder001 to 75mm"
```

#### Change Color
```
"Make Box001 red"
```

### Deleting Objects

```
"Delete Cylinder001"
```

---

## Advanced Features

### Sketch-Based Modeling

This is the professional workflow for creating complex parts.

#### Step 1: Create Datum Plane

```
"Create a datum plane aligned with XY at the origin"
```

**Result:** Creates `base_plane` (Body with Origin)

#### Step 2: Create Sketch

```
"Create a sketch on base_plane"
```

**Result:** Creates `base_plane_sketch`

#### Step 3: Add Geometry

```
"Add a rectangle 100mm x 50mm to the sketch, starting at origin"
```

**Details:**
```json
{
  "geometry_elements": [
    {"type": "line", "start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}},
    {"type": "line", "start": {"x": 100, "y": 0}, "end": {"x": 100, "y": 50}},
    {"type": "line", "start": {"x": 100, "y": 50}, "end": {"x": 0, "y": 50}},
    {"type": "line", "start": {"x": 0, "y": 50}, "end": {"x": 0, "y": 0}}
  ]
}
```

#### Step 4: Extrude

```
"Extrude base_plane_sketch 20mm"
```

**Result:** Creates `base_plane_solid`

### Boolean Operations

#### Union (Fuse)

Combine multiple solids into one.

```
"Fuse Box001 and Cylinder001 together"
```

**Use Case:** Combining parts into single body

#### Cut (Subtract)

Remove one solid from another.

```
"Cut Cylinder001 from Box001 to create a hole"
```

**Use Case:** Creating holes, pockets, cutouts

#### Intersection

Keep only overlapping volume.

```
"Find the intersection between Sphere001 and Box001"
```

**Use Case:** Complex shape creation

### Finishing Operations

#### Fillets (Rounded Edges)

```
"Add a 5mm fillet to edges 1, 2, and 5 of Box001"
```

**Use Case:** Professional appearance, stress reduction

#### Chamfers (Beveled Edges)

```
"Add a 2mm chamfer to edge 3 of Box001"
```

**Use Case:** Sharp edge removal, assembly clearance

#### Shell (Hollow Out)

```
"Create a hollow shell from Box001 with 2mm wall thickness, removing the top face"
```

**Use Case:** Enclosures, containers, lightweight parts

### Transformations & Patterns

#### Mirror

Create symmetric parts instantly.

```
"Mirror Wing across the YZ plane and merge with original"
```

**Productivity:** 60% time saving for symmetric designs

#### Circular Pattern

Create radial arrays.

```
"Create a circular pattern of Cylinder001, 18 copies around the Z axis"
```

**Use Case:** Radial engines, bolt patterns, gears

#### Linear Pattern

Create rectangular arrays.

```
"Create a linear pattern of Hole001, 5 copies spaced 50mm apart in X direction"
```

**Use Case:** Repeated features, bolt holes, ventilation

### Advanced Modeling

#### Loft

Create organic shapes between profiles.

```
"Create a loft between Profile1, Profile2, and Profile3"
```

**Use Case:** Aircraft fuselages, boat hulls, bottles

#### Revolve

Create rotational parts.

```
"Revolve Profile001 360 degrees around the Z axis"
```

**Use Case:** Bottles, shafts, pulleys, bowls

#### Sweep

Sweep profile along path.

```
"Sweep Circle001 along Spline001"
```

**Use Case:** Pipes, cables, handrails

### Reference Geometry

#### Custom Planes

```
"Create a plane at Z=100 with normal tilted 10 degrees"
```

**Use Case:** Angled features, complex assemblies

#### NACA Airfoil Profiles

```
"Import NACA 2412 airfoil with 2000mm chord length"
```

**Use Case:** Aircraft wings, turbine blades, boat keels

#### DXF Import

```
"Import the DXF file from C:/drawings/part.dxf as a sketch"
```

**Use Case:** Professional CAD workflow integration

---

## Assembly Workflow

### Assembly3 (Constraint-Based)

Automatic positioning based on constraints.

#### Step 1: Create Assembly

```
"Create an Assembly3 container named MainAssembly"
```

#### Step 2: Add Parts

```
"Add Box001 to MainAssembly"
"Add Cylinder001 to MainAssembly"
```

#### Step 3: Add Constraints

```
"Add a PlaneCoincident constraint between Face6 of Box001 and Face1 of Cylinder001"
```

#### Step 4: Solve

```
"Solve the assembly constraints"
```

**Result:** Parts automatically position themselves

### Assembly4 (LCS-Based)

Manual positioning using coordinate systems.

#### Step 1: Create Assembly

```
"Create an Assembly4 container named MainAssembly"
```

#### Step 2: Create LCS

```
"Create an LCS named LCS_Base at origin in MainAssembly"
```

#### Step 3: Insert Parts

```
"Insert part from C:/parts/base.FCStd into MainAssembly, attach to LCS_Base"
```

### Bill of Materials

```
"Generate a BOM for MainAssembly in markdown format"
```

**Result:** Table with part counts, masses, materials

---

## Best Practices

### 1. Planning

**Before starting:**
- Sketch the design on paper
- Break down into components
- Identify symmetric features
- Plan assembly structure

### 2. Naming Conventions

**Use descriptive names:**
- ✅ `fuselage_main_body`
- ✅ `wing_left_outer`
- ❌ `Pad001`
- ❌ `Cut042`

### 3. Progressive Complexity

**Build incrementally:**
1. Start with simple shapes
2. Test basic operations
3. Add details gradually
4. Save frequently

### 4. Leverage Symmetry

**Use mirror for symmetric parts:**
```
"Create the right wing, then mirror it to create both wings"
```
**Saves 50%+ time**

### 5. Use Patterns

**Use patterns for repeated features:**
```
"Create one bolt hole, then use circular pattern for 6 holes"
```
**Much faster than individual holes**

### 6. Document As You Go

**In Claude, describe your steps:**
```
"Create fuselage base (will be 4000mm long, elliptical cross-section)"
```

### 7. Save Incrementally

**In FreeCAD:**
- File > Save As > `project_v1.FCStd`
- Make changes
- File > Save As > `project_v2.FCStd`

### 8. Verify Dimensions

**Check with screenshots:**
```
"Show me the top view"
"Show me the dimensions of Box001"
```

### 9. Organize Complex Projects

**Use hierarchy:**
```
Assembly
├── Fuselage
│   ├── Forward section
│   ├── Center section
│   └── Tail section
├── Wings
│   ├── Left wing
│   └── Right wing
└── Empennage
```

### 10. Test Before Complex Operations

**Try operations on simple geometry first:**
```
"Create a test box and try the fillet operation before applying to main part"
```

---

## Troubleshooting

### Common Issues

#### Issue: Claude doesn't see FreeCAD tools

**Symptoms:**
- Claude says "I don't have access to FreeCAD"
- No tools available

**Solutions:**
1. Restart Claude Desktop
2. Check `claude_desktop_config.json` syntax
3. Verify FreeCAD RPC server running
4. Check Claude Desktop logs

#### Issue: Connection Refused

**Symptoms:**
- Error: "Connection refused to localhost:9875"
- Tools fail to execute

**Solutions:**
1. Launch FreeCAD
2. Select "MCP Addon" workbench
3. Click "Start RPC Server"
4. Verify green indicator
5. Check firewall settings

#### Issue: No Screenshot

**Symptoms:**
- Operations succeed but no image
- "Screenshot unavailable" message

**Solutions:**
1. Switch to 3D view (not TechDraw/Spreadsheet)
2. Use `--only-text-feedback` if screenshots not needed
3. Check FreeCAD active document has 3D view

#### Issue: Object Not Found

**Symptoms:**
- Error: "Object 'Box001' not found"

**Solutions:**
1. List objects: `"Show me all objects in the document"`
2. Verify object name spelling
3. Check correct document is active
4. Refresh with `get_objects`

#### Issue: Boolean Operation Fails

**Symptoms:**
- Error during union/cut/intersection
- Invalid result

**Solutions:**
1. Verify objects are valid solids
2. Check objects actually overlap
3. Try `execute_code` to check geometry
4. Simplify geometry if complex

#### Issue: Assembly Constraints Not Solving

**Symptoms:**
- Constraints added but parts don't move
- Solver error

**Solutions:**
1. Check constraint types are appropriate
2. Verify references (faces/edges) exist
3. Check for conflicting constraints
4. Try Assembly4 LCS-based approach instead

### Getting Help

1. **Check Documentation**
   - [API Reference](API_REFERENCE.md)
   - [Quick Start](QUICKSTART.md)
   - [Corsair Workflow](CORSAIR_MODELING_WORKFLOW.md)

2. **FreeCAD Console**
   - View > Panels > Python console
   - Check for error messages

3. **GitHub Issues**
   - [Report bugs](https://github.com/neka-nat/freecad-mcp/issues)
   - Search existing issues

4. **FreeCAD Forum**
   - [FreeCAD Forum](https://forum.freecad.org/)
   - Ask FreeCAD-specific questions

---

## Example Projects

### Project 1: Simple Flange

```
1. "Create a cylinder 100mm diameter, 20mm thick"
2. "Add 6 holes, 10mm diameter, in a circular pattern at 80mm diameter"
3. "Add 5mm fillet to outer edges"
```

**Time:** ~2 minutes

### Project 2: Aircraft Wing

```
1. "Import NACA 2412 airfoil profile with 2000mm chord"
2. "Extrude 6000mm to create wing"
3. "Mirror across YZ plane to create both wings"
4. "Add 50mm fillet where wings meet fuselage"
```

**Time:** ~5 minutes

### Project 3: Radial Engine

```
1. "Create one cylinder 50mm diameter, 100mm long"
2. "Circular pattern, 18 copies around X axis"
3. "Add central crankcase, 150mm diameter sphere"
4. "Fuse all cylinders and crankcase"
```

**Time:** ~3 minutes

---

## Next Steps

### Continue Learning

- **[Corsair Workflow](CORSAIR_MODELING_WORKFLOW.md)** - Complete aircraft project (100+ hours → 40 hours)
- **[API Reference](API_REFERENCE.md)** - Detailed tool documentation
- **[Contributing](../CONTRIBUTING.md)** - Help improve FreeCAD MCP

### Advanced Topics

- Sheet metal design
- FEM analysis
- TechDraw documentation
- Animation
- Generative design

### Community

- Share your projects
- Report bugs
- Suggest features
- Contribute code

---

**Happy designing with FreeCAD MCP!** 🚀

