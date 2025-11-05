def assembly_strategy() -> str:
    """Strategic guide for Assembly3 and Assembly4 workflows (2025-10-08)"""
    return """
# Assembly Strategy for FreeCAD MCP

## Overview

FreeCAD offers two powerful assembly workbenches, each with distinct approaches:

### Assembly3 - Constraint-Based Assembly
- **Philosophy**: Automatic positioning through constraints
- **Use Case**: Complex assemblies with precise relationships
- **Workflow**: Define constraints, let the solver position parts

### Assembly4 - LCS-Based Assembly
- **Philosophy**: Manual positioning using Local Coordinate Systems
- **Use Case**: Simple to medium assemblies, precise control
- **Workflow**: Create LCS, attach parts to LCS

---

## Assembly3 Workflow

### 1. Create Assembly
```json
{
    "tool": "create_assembly3_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly"
    }
}
```

### 2. Add Parts
From external file:
```json
{
    "tool": "add_part_to_assembly3_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "part_file": "C:/parts/base.FCStd",
        "part_name": "Base"
    }
}
```

From existing object:
```json
{
    "tool": "add_part_to_assembly3_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "part_object": "Box001"
    }
}
```

### 3. Add Constraints

**Common Constraint Types:**

**PlaneCoincident** - Align two planar faces:
```json
{
    "tool": "add_assembly3_constraint_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "constraint_type": "PlaneCoincident",
        "references": [
            {"object": "Base", "element": "Face6"},
            {"object": "Cover", "element": "Face1"}
        ]
    }
}
```

**Axial** - Align two cylindrical axes:
```json
{
    "tool": "add_assembly3_constraint_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "constraint_type": "Axial",
        "references": [
            {"object": "Shaft", "element": "Edge1"},
            {"object": "Bearing", "element": "Edge1"}
        ]
    }
}
```

**Distance** - Fixed distance between elements:
```json
{
    "tool": "add_assembly3_constraint_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "constraint_type": "Distance",
        "references": [
            {"object": "Part1", "element": "Face1"},
            {"object": "Part2", "element": "Face1"}
        ],
        "properties": {"Distance": 10.0}
    }
}
```

**Angle** - Fixed angle between elements:
```json
{
    "tool": "add_assembly3_constraint_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "constraint_type": "Angle",
        "references": [
            {"object": "Arm1", "element": "Face1"},
            {"object": "Arm2", "element": "Face1"}
        ],
        "properties": {"Angle": 90.0}
    }
}
```

**Lock** - Lock object in place:
```json
{
    "tool": "add_assembly3_constraint_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "constraint_type": "Lock",
        "references": [
            {"object": "Base", "element": ""}
        ]
    }
}
```

### 4. Solve Assembly
```json
{
    "tool": "solve_assembly3_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly"
    }
}
```

---

## Assembly4 Workflow

### 1. Create Assembly
```json
{
    "tool": "create_assembly4_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly"
    }
}
```
*Note: Automatically creates default LCS_Origin*

### 2. Create Additional LCS

**Basic LCS:**
```json
{
    "tool": "create_lcs_assembly4_tool",
    "params": {
        "doc_name": "MyDoc",
        "parent_name": "MainAssembly",
        "lcs_name": "LCS_Mount1",
        "position": {"x": 100, "y": 0, "z": 50}
    }
}
```

**LCS with Rotation:**
```json
{
    "tool": "create_lcs_assembly4_tool",
    "params": {
        "doc_name": "MyDoc",
        "parent_name": "MainAssembly",
        "lcs_name": "LCS_Mount2",
        "position": {"x": 200, "y": 0, "z": 50},
        "rotation": {
            "axis": {"x": 0, "y": 0, "z": 1},
            "angle": 90
        }
    }
}
```

### 3. Attach LCS to Geometry
```json
{
    "tool": "attach_lcs_to_geometry_tool",
    "params": {
        "doc_name": "MyDoc",
        "lcs_name": "LCS_Mount1",
        "target_object": "Base",
        "element": "Face6",
        "map_mode": "FlatFace"
    }
}
```

**Map Modes:**
- `FlatFace`: Align to planar face
- `ObjectXY`: Align to object's XY plane
- `ObjectXZ`: Align to object's XZ plane
- `ObjectYZ`: Align to object's YZ plane
- `NormalToEdge`: Perpendicular to edge

### 4. Insert Parts with LCS Attachment
```json
{
    "tool": "insert_part_assembly4_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "part_file": "C:/parts/motor.FCStd",
        "part_name": "Motor",
        "attach_lcs_part": "LCS_Origin",
        "attach_lcs_target": "LCS_Mount1",
        "offset": {"x": 0, "y": 0, "z": 5}
    }
}
```

---

## Common Operations

### List Assembly Parts
```json
{
    "tool": "list_assembly_parts_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "assembly_type": "auto"
    }
}
```

### Export Assembly
```json
{
    "tool": "export_assembly_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly",
        "export_path": "C:/exports/assembly.step",
        "export_format": "step"
    }
}
```

**Export Formats:**
- `step`: STEP format (recommended for CAD interchange)
- `iges`: IGES format
- `stl`: STL for 3D printing
- `obj`: OBJ format
- `brep`: BREP format

### Calculate Assembly Mass
```json
{
    "tool": "calculate_assembly_mass_tool",
    "params": {
        "doc_name": "MyDoc",
        "assembly_name": "MainAssembly"
    }
}
```
*Note: Requires material/density properties on parts*

---

## Best Practices

### When to Use Assembly3
✅ Complex mechanical assemblies
✅ Need automatic constraint solving
✅ Parametric relationships between parts
✅ Kinematic simulations

### When to Use Assembly4
✅ Simple assemblies
✅ Need precise manual control
✅ Working with pre-positioned parts
✅ Lightweight assemblies

### General Tips

1. **Always lock the base part** in Assembly3 to establish reference
2. **Use descriptive LCS names** in Assembly4 (e.g., LCS_Motor_Mount)
3. **Create LCS on faces** for easier attachment in Assembly4
4. **Start with fewer constraints** in Assembly3, add more as needed
5. **Use get_objects() first** to inspect current state
6. **List parts regularly** to verify assembly structure
7. **Set materials before mass calculation** for accurate results

### Common Patterns

**Assembly3 - Fixed Base with Rotating Arm:**
1. Lock base part
2. Add Axial constraint on rotation axis
3. Add Angle constraint for position
4. Solve assembly

**Assembly4 - Multi-Part Positioning:**
1. Create Assembly4
2. Create LCS at each mounting point
3. Attach LCS to base geometry
4. Insert parts attached to LCS
5. Adjust offsets as needed

---

## Troubleshooting

**Assembly3 won't solve:**
- Check for conflicting constraints
- Ensure base part is locked
- Verify all parts have valid geometry

**Assembly4 LCS not attaching:**
- Verify target element exists (Face1, Edge1, etc.)
- Check map_mode matches element type
- Ensure parent object contains target

**Mass calculation returns 0:**
- Set material properties on parts
- Ensure parts have valid solid geometry
- Check that Shape.Volume > 0

---

## Example: Complete Assembly3 Workflow

```json
// 1. Create assembly
{"tool": "create_assembly3_tool", "params": {"doc_name": "Motor", "assembly_name": "MotorAsm"}}

// 2. Add base part (lock it)
{"tool": "add_part_to_assembly3_tool", "params": {"doc_name": "Motor", "assembly_name": "MotorAsm", "part_object": "Base"}}
{"tool": "add_assembly3_constraint_tool", "params": {"doc_name": "Motor", "assembly_name": "MotorAsm", "constraint_type": "Lock", "references": [{"object": "Base", "element": ""}]}}

// 3. Add shaft
{"tool": "add_part_to_assembly3_tool", "params": {"doc_name": "Motor", "assembly_name": "MotorAsm", "part_object": "Shaft"}}

// 4. Align shaft to base
{"tool": "add_assembly3_constraint_tool", "params": {"doc_name": "Motor", "assembly_name": "MotorAsm", "constraint_type": "Axial", "references": [{"object": "Base", "element": "Edge1"}, {"object": "Shaft", "element": "Edge1"}]}}

// 5. Solve
{"tool": "solve_assembly3_tool", "params": {"doc_name": "Motor", "assembly_name": "MotorAsm"}}
```

## Example: Complete Assembly4 Workflow

```json
// 1. Create assembly (with default LCS)
{"tool": "create_assembly4_tool", "params": {"doc_name": "Robot", "assembly_name": "RobotAsm"}}

// 2. Create mounting LCS
{"tool": "create_lcs_assembly4_tool", "params": {"doc_name": "Robot", "parent_name": "RobotAsm", "lcs_name": "LCS_ArmMount", "position": {"x": 0, "y": 0, "z": 100}}}

// 3. Insert arm part
{"tool": "insert_part_assembly4_tool", "params": {"doc_name": "Robot", "assembly_name": "RobotAsm", "part_file": "C:/parts/arm.FCStd", "part_name": "Arm", "attach_lcs_part": "LCS_Origin", "attach_lcs_target": "LCS_ArmMount"}}

// 4. List parts to verify
{"tool": "list_assembly_parts_tool", "params": {"doc_name": "Robot", "assembly_name": "RobotAsm"}}
```

---

Remember: Use `get_objects()` before and after assembly operations to verify state!
"""










