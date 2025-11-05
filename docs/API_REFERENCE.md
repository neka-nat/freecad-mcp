# API Reference

Complete reference for all FreeCAD MCP tools.

## Table of Contents

- [Document Management](#document-management)
- [Basic Modeling](#basic-modeling)
- [Sketch Workflow](#sketch-workflow)
- [Boolean Operations](#boolean-operations)
- [Advanced Modeling](#advanced-modeling)
- [Transformations & Patterns](#transformations--patterns)
- [Reference Geometry](#reference-geometry)
- [Assembly Operations](#assembly-operations)
- [Visual Feedback](#visual-feedback)

---

## Document Management

### `create_document`

Create a new FreeCAD document.

**Parameters:**
- `name` (str): Document name

**Returns:**
- Success/error message

**Example:**
```json
{
  "name": "MyProject"
}
```

---

### `get_objects`

List all objects in a document.

**Parameters:**
- `doc_name` (str): Document name

**Returns:**
- List of objects with properties

**Example:**
```json
{
  "doc_name": "MyProject"
}
```

---

### `get_object`

Get detailed information about a specific object.

**Parameters:**
- `doc_name` (str): Document name
- `obj_name` (str): Object name

**Returns:**
- Object properties and details

**Example:**
```json
{
  "doc_name": "MyProject",
  "obj_name": "Box001"
}
```

---

## Basic Modeling

### `create_object`

Create a parametric object in FreeCAD.

**Parameters:**
- `doc_name` (str): Document name
- `obj_type` (str): Object type (e.g., "Part::Box", "Part::Cylinder")
- `obj_name` (str): Object name
- `obj_properties` (dict, optional): Object properties
- `analysis_name` (str, optional): FEM analysis name if applicable

**Supported Types:**
- `Part::Box` - Rectangular box
- `Part::Cylinder` - Cylinder
- `Part::Sphere` - Sphere
- `Part::Cone` - Cone
- `Part::Torus` - Torus
- `Draft::Circle` - 2D circle
- `PartDesign::Body` - Part Design body
- `Fem::AnalysisPython` - FEM analysis
- And many more...

**Example:**
```json
{
  "doc_name": "MyProject",
  "obj_name": "MyCylinder",
  "obj_type": "Part::Cylinder",
  "obj_properties": {
    "Height": 100,
    "Radius": 20,
    "Placement": {
      "Base": {"x": 0, "y": 0, "z": 0}
    }
  }
}
```

---

### `edit_object`

Modify properties of an existing object.

**Parameters:**
- `doc_name` (str): Document name
- `obj_name` (str): Object name
- `obj_properties` (dict): Properties to modify

**Example:**
```json
{
  "doc_name": "MyProject",
  "obj_name": "MyCylinder",
  "obj_properties": {
    "Height": 150,
    "Radius": 25
  }
}
```

---

### `delete_object`

Delete an object from the document.

**Parameters:**
- `doc_name` (str): Document name
- `obj_name` (str): Object name

**Example:**
```json
{
  "doc_name": "MyProject",
  "obj_name": "MyCylinder"
}
```

---

### `execute_code`

Execute arbitrary Python code in FreeCAD.

**Parameters:**
- `code` (str): Python code to execute

**Example:**
```json
{
  "code": "import FreeCAD\nFreeCAD.Console.PrintMessage('Hello from Claude!')"
}
```

---

## Sketch Workflow

### `create_datum_plane_tool`

Create a reference plane for sketching.

**Parameters:**
- `doc_name` (str): Document name
- `plane_name` (str): Plane name
- `alignment` (str): "xy", "xz", or "yz"
- `offset` (float): Offset from origin

**Example:**
```json
{
  "doc_name": "MyProject",
  "plane_name": "base_plane",
  "alignment": "xy",
  "offset": 0.0
}
```

---

### `create_sketch_on_plane_tool`

Create a sketch attached to a datum plane.

**Parameters:**
- `doc_name` (str): Document name
- `plane_name` (str): Datum plane name

**Example:**
```json
{
  "doc_name": "MyProject",
  "plane_name": "base_plane"
}
```

Creates: `base_plane_sketch`

---

### `add_contour_to_sketch_tool`

Add geometric elements to a sketch.

**Parameters:**
- `doc_name` (str): Document name
- `sketch_name` (str): Sketch name
- `geometry_elements` (list): List of geometry elements
- `constraints` (list, optional): List of constraints
- `fix_first_point_to_origin` (bool): Fix first point to origin

**Geometry Types:**
- `point`: `{"type": "point", "x": 0, "y": 0}`
- `line`: `{"type": "line", "start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}}`
- `arc`: `{"type": "arc", "center": {"x": 0, "y": 0}, "radius": 50, "start_angle": 0, "end_angle": 90}`
- `circle`: `{"type": "circle", "center": {"x": 0, "y": 0}, "radius": 25}`
- `bspline`: `{"type": "bspline", "points": [...], "degree": 3, "closed": false}`
- `ellipse`: `{"type": "ellipse", "center": {"x": 0, "y": 0}, "major_radius": 50, "minor_radius": 25, "angle": 0}`

**Constraint Types:**
- `coincident`: `{"type": "coincident", "geo1": 0, "point1": 2, "geo2": 1, "point2": 1}`
- `tangent`: `{"type": "tangent", "geo1": 0, "geo2": 1}`
- `distance`: `{"type": "distance", "geo1": 0, "point1": 1, "geo2": 0, "point2": 2, "value": 100}`
- `horizontal`: `{"type": "horizontal", "geo": 0}`
- `vertical`: `{"type": "vertical", "geo": 0}`
- `angle`: `{"type": "angle", "geo1": 0, "geo2": 1, "value": 90}`
- `fix`: `{"type": "fix", "geo": 0, "point": 1}`

**Example:**
```json
{
  "doc_name": "MyProject",
  "sketch_name": "base_plane_sketch",
  "geometry_elements": [
    {"type": "line", "start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}},
    {"type": "line", "start": {"x": 100, "y": 0}, "end": {"x": 100, "y": 50}},
    {"type": "line", "start": {"x": 100, "y": 50}, "end": {"x": 0, "y": 50}},
    {"type": "line", "start": {"x": 0, "y": 50}, "end": {"x": 0, "y": 0}}
  ],
  "constraints": [
    {"type": "horizontal", "geo": 0},
    {"type": "vertical", "geo": 1}
  ]
}
```

---

### `extrude_sketch_bidirectional_tool`

Extrude a sketch to create a 3D solid.

**Parameters:**
- `doc_name` (str): Document name
- `sketch_name` (str): Sketch name
- `length_forward` (float): Forward extrusion length
- `length_backward` (float): Backward extrusion length
- `use_midplane` (bool): Symmetric extrusion

**Example:**
```json
{
  "doc_name": "MyProject",
  "sketch_name": "base_plane_sketch",
  "length_forward": 50.0,
  "length_backward": 0.0,
  "use_midplane": false
}
```

Creates: `base_plane_solid`

---

## Boolean Operations

### `boolean_union_tool`

Fuse multiple solids into one.

**Parameters:**
- `doc_name` (str): Document name
- `base_object_name` (str): Base object
- `tool_object_names` (list): Objects to fuse
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "base_object_name": "Box001",
  "tool_object_names": ["Cylinder001", "Sphere001"],
  "result_name": "Combined"
}
```

---

### `boolean_cut_tool`

Subtract one solid from another.

**Parameters:**
- `doc_name` (str): Document name
- `base_object_name` (str): Base object
- `tool_object_name` (str): Object to subtract
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "base_object_name": "Box001",
  "tool_object_name": "Cylinder001",
  "result_name": "BoxWithHole"
}
```

---

### `boolean_intersection_tool`

Keep only common volume between two solids.

**Parameters:**
- `doc_name` (str): Document name
- `object1_name` (str): First object
- `object2_name` (str): Second object
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "object1_name": "Sphere001",
  "object2_name": "Box001",
  "result_name": "Common"
}
```

---

## Advanced Modeling

### `create_loft_tool`

Create a loft between multiple profiles.

**Parameters:**
- `doc_name` (str): Document name
- `sketch_names` (list): List of sketch names (profiles)
- `result_name` (str): Result name
- `solid` (bool): Create solid (default: True)
- `ruled` (bool): Ruled surface (default: False)

**Example:**
```json
{
  "doc_name": "MyProject",
  "sketch_names": ["Profile1", "Profile2", "Profile3"],
  "result_name": "Loft001",
  "solid": true,
  "ruled": false
}
```

---

### `create_revolve_tool`

Revolve a profile around an axis.

**Parameters:**
- `doc_name` (str): Document name
- `sketch_name` (str): Profile sketch name
- `axis` (dict): Axis definition
- `angle` (float): Rotation angle (default: 360)
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "sketch_name": "Profile",
  "axis": {
    "point": {"x": 0, "y": 0, "z": 0},
    "direction": {"x": 0, "y": 0, "z": 1}
  },
  "angle": 360,
  "result_name": "Revolve001"
}
```

---

### `create_sweep_tool`

Sweep a profile along a path.

**Parameters:**
- `doc_name` (str): Document name
- `profile_sketch` (str): Profile sketch name
- `path_sketch` (str): Path sketch name
- `result_name` (str): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "profile_sketch": "Circle",
  "path_sketch": "Spline",
  "result_name": "Sweep001"
}
```

---

### `add_fillet_tool`

Add rounded edges (fillets) to an object.

**Parameters:**
- `doc_name` (str): Document name
- `object_name` (str): Object name
- `edges` (list): List of edge names
- `radius` (float): Fillet radius
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "object_name": "Box001",
  "edges": ["Edge1", "Edge2", "Edge5"],
  "radius": 5.0,
  "result_name": "BoxRounded"
}
```

---

### `add_chamfer_tool`

Add beveled edges (chamfers) to an object.

**Parameters:**
- `doc_name` (str): Document name
- `object_name` (str): Object name
- `edges` (list): List of edge names
- `distance` (float): Chamfer distance
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "object_name": "Box001",
  "edges": ["Edge1", "Edge3"],
  "distance": 2.0,
  "result_name": "BoxChamfered"
}
```

---

### `shell_object_tool`

Create a hollow shell from a solid.

**Parameters:**
- `doc_name` (str): Document name
- `object_name` (str): Object name
- `thickness` (float): Wall thickness
- `faces_to_remove` (list, optional): Faces to remove (opens the shell)
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "object_name": "Box001",
  "thickness": 2.0,
  "faces_to_remove": ["Face6"],
  "result_name": "BoxShell"
}
```

---

## Transformations & Patterns

### `transform_object_tool`

Transform object with translation and/or rotation.

**Parameters:**
- `doc_name` (str): Document name
- `obj_name` (str): Object name
- `position` (dict, optional): Position {"x": 0, "y": 0, "z": 0}
- `rotation` (dict, optional): Rotation {"axis": {"x": 0, "y": 0, "z": 1}, "angle": 0}
- `relative` (bool): Relative transformation

**Example:**
```json
{
  "doc_name": "MyProject",
  "obj_name": "Cylinder001",
  "position": {"x": 100, "y": 50, "z": 20},
  "rotation": {"axis": {"x": 0, "y": 0, "z": 1}, "angle": 45},
  "relative": false
}
```

---

### `mirror_object_tool`

Mirror object across a plane.

**Parameters:**
- `doc_name` (str): Document name
- `source_obj` (str): Object to mirror
- `mirror_plane` (dict): Plane definition
- `result_name` (str, optional): Result name
- `merge` (bool): Merge with original

**Example:**
```json
{
  "doc_name": "MyProject",
  "source_obj": "Wing",
  "mirror_plane": {
    "base": {"x": 0, "y": 0, "z": 0},
    "normal": {"x": 1, "y": 0, "z": 0}
  },
  "merge": true,
  "result_name": "BothWings"
}
```

---

### `circular_pattern_tool`

Create circular pattern (polar array).

**Parameters:**
- `doc_name` (str): Document name
- `object_name` (str): Object to pattern
- `axis` (dict): Rotation axis
- `count` (int): Number of instances
- `angle` (float): Total angle
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "object_name": "Cylinder",
  "axis": {
    "point": {"x": 0, "y": 0, "z": 0},
    "direction": {"x": 0, "y": 0, "z": 1}
  },
  "count": 6,
  "angle": 360,
  "result_name": "CircularPattern"
}
```

---

### `linear_pattern_tool`

Create linear pattern (rectangular array).

**Parameters:**
- `doc_name` (str): Document name
- `object_name` (str): Object to pattern
- `direction` (dict): Pattern direction
- `spacing` (float): Distance between instances
- `count` (int): Number of instances
- `result_name` (str, optional): Result name

**Example:**
```json
{
  "doc_name": "MyProject",
  "object_name": "Hole",
  "direction": {"x": 1, "y": 0, "z": 0},
  "spacing": 50,
  "count": 5,
  "result_name": "HoleArray"
}
```

---

## Reference Geometry

### `create_reference_plane_tool`

Create a datum plane with various definition modes.

**Parameters:**
- `doc_name` (str): Document name
- `plane_name` (str): Plane name
- `definition` (dict): Plane definition

**Definition Modes:**
- Offset: `{"mode": "offset", "plane": "XY", "offset": 50}`
- 3 Points: `{"mode": "3points", "p1": {...}, "p2": {...}, "p3": {...}}`
- Point-Normal: `{"mode": "point_normal", "point": {...}, "normal": {...}}`

**Example:**
```json
{
  "doc_name": "MyProject",
  "plane_name": "CustomPlane",
  "definition": {
    "mode": "point_normal",
    "point": {"x": 0, "y": 0, "z": 100},
    "normal": {"x": 0.2, "y": 0, "z": 1}
  }
}
```

---

### `import_airfoil_profile_tool`

Import NACA airfoil profile.

**Parameters:**
- `doc_name` (str): Document name
- `sketch_name` (str): Sketch name
- `naca_code` (str): NACA code (e.g., "2412", "0012")
- `chord_length` (float): Chord length in mm
- `position` (dict, optional): Position

**Example:**
```json
{
  "doc_name": "MyProject",
  "sketch_name": "WingProfile",
  "naca_code": "2412",
  "chord_length": 2000,
  "position": {"x": 0, "y": 0, "z": 0}
}
```

---

### `import_dxf_tool`

Import DXF file into a sketch.

**Parameters:**
- `doc_name` (str): Document name
- `file_path` (str): DXF file path
- `sketch_name` (str): Sketch name
- `scale` (float): Scale factor

**Example:**
```json
{
  "doc_name": "MyProject",
  "file_path": "C:/drawings/part.dxf",
  "sketch_name": "ImportedProfile",
  "scale": 1.0
}
```

---

## Assembly Operations

See [ASSEMBLY.md](ASSEMBLY.md) for complete assembly documentation.

### Assembly3 Tools
- `create_assembly3_tool`
- `add_part_to_assembly3_tool`
- `add_assembly3_constraint_tool`
- `solve_assembly3_tool`
- `list_assembly3_constraints_tool`
- `delete_assembly3_constraint_tool`
- `modify_assembly3_constraint_tool`

### Assembly4 Tools
- `create_assembly4_tool`
- `create_lcs_assembly4_tool`
- `insert_part_assembly4_tool`
- `attach_lcs_to_geometry_tool`
- `list_assembly4_lcs_tool`
- `delete_lcs_assembly4_tool`
- `modify_lcs_assembly4_tool`

### Common Tools
- `list_assembly_parts_tool`
- `export_assembly_tool`
- `calculate_assembly_mass_tool`
- `generate_bom_tool`
- `get_assembly_properties_tool`

---

## Visual Feedback

### `get_view`

Get screenshot from specific view.

**Parameters:**
- `view_name` (str): "Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"

**Example:**
```json
{
  "view_name": "Isometric"
}
```

---

### `insert_part_from_library`

Insert part from FreeCAD parts library.

**Parameters:**
- `relative_path` (str): Relative path in library

**Example:**
```json
{
  "relative_path": "Fasteners/Bolts/ISO4017_M8x40.FCStd"
}
```

---

### `get_parts_list`

List available parts in library.

**Returns:**
- List of available parts

---

## Error Handling

All tools return consistent response format:

**Success:**
```json
{
  "success": true,
  "message": "Operation completed",
  "screenshot": "base64_image_data"
}
```

**Error:**
```json
{
  "success": false,
  "error": "Error description"
}
```

---

## Best Practices

1. **Always check object names** with `get_objects` before referencing
2. **Use descriptive names** for created objects
3. **Verify coordinates** with screenshots
4. **Save incrementally** in FreeCAD
5. **Test operations** with simple geometries first

---

**See Also:**
- [User Guide](USER_GUIDE.md) - Feature tutorials
- [Quick Start](QUICKSTART.md) - Setup guide
- [Corsair Workflow](CORSAIR_MODELING_WORKFLOW.md) - Real-world example

