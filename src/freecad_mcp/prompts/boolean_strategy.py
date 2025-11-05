def boolean_operations_strategy() -> str:
    """Strategic guide for using Boolean operations in FreeCAD MCP."""
    return """
Boolean Operations Strategy for FreeCAD MCP

Boolean operations are essential for creating complex parts by combining simple shapes.
Master these operations to build professional CAD models efficiently.

AVAILABLE OPERATIONS:

1. UNION (Fusion)
   - Combines multiple solids into one
   - Use case: Assembly of parts, joining components
   - Command: boolean_union_tool
   - Example: Fuse a base plate with mounting posts
   - Note: Can combine 2 or more objects in a single operation
   
2. CUT (Difference/Subtraction)
   - Removes one solid from another
   - Use case: Creating holes, pockets, cutouts, grooves
   - Command: boolean_cut_tool
   - Example: Drill holes in a plate, create pockets for screws
   - Note: Order matters! Base = what you keep, Tool = what you remove
   
3. INTERSECTION (Common)
   - Keeps only the overlapping volume
   - Use case: Finding common geometry, creating complex shapes
   - Command: boolean_intersection_tool
   - Example: Shape defined by multiple constraints
   - Note: Result is smaller than both inputs
   
4. COMMON
   - Alias of INTERSECTION for FreeCAD terminology
   - Command: boolean_common_tool
   - Same as intersection, just different name

WORKFLOW BEST PRACTICES:

1. Order Matters for Cut
   - Base object = what you keep (the main part)
   - Tool object = what you remove (the cutting tool)
   - Wrong order = inverted result!
   - Example: Cut(Plate, Hole) ≠ Cut(Hole, Plate)

2. Positioning Before Boolean
   - ALWAYS position objects correctly FIRST
   - Use attach_solid_to_plane or edit_object for precise positioning
   - Verify with get_view before applying boolean operation
   - Boolean operations do NOT move objects

3. Naming Strategy
   - Use descriptive result names
   - Good: "plate_with_mounting_holes"
   - Bad: "Cut001"
   - Helps track your design intent and history

4. Source Object Visibility
   - Source objects are automatically hidden after boolean operation
   - This keeps the view clean and uncluttered
   - Original objects are still in the document if needed
   - You can unhide them if needed for reference

5. Complex Shapes = Multiple Operations
   - Start with union to combine base shapes
   - Then use cut to remove material (holes, pockets)
   - Finally use intersection if needed for precise definition
   - Build complexity incrementally

6. Verify Before Committing
   - Use get_view to visualize your setup
   - Check that objects actually overlap
   - Verify object positions and orientations
   - A picture is worth a thousand coordinates

COMMON PATTERNS:

Pattern 1: Mounting Plate with Holes
   Step 1: Create base plate (sketch + extrude)
   Step 2: Create cylinder for first hole
   Step 3: Position cylinder at hole location
   Step 4: Use boolean_cut (plate, cylinder)
   Step 5: Repeat steps 2-4 for additional holes
   
   Result: Clean plate with precisely positioned holes

Pattern 2: Assembly of Parts
   Step 1: Create individual parts using sketch workflow
   Step 2: Position parts using attach_solid_to_plane
   Step 3: Verify alignment with get_view
   Step 4: Use boolean_union to merge into single part
   
   Result: Single unified assembly

Pattern 3: Complex Cutout
   Step 1: Create base solid
   Step 2: Create cutting profile (sketch + extrude)
   Step 3: Position cutting profile precisely
   Step 4: Use boolean_cut to remove material
   
   Result: Custom shaped pocket or groove

Pattern 4: Intersection for Precise Shapes
   Step 1: Create first bounding shape
   Step 2: Create second bounding shape
   Step 3: Position them to overlap as desired
   Step 4: Use boolean_intersection
   
   Result: Complex shape defined by intersection

Pattern 5: Sequential Operations
   Step 1: Union to combine base components
   Step 2: Cut to add functional features (holes, slots)
   Step 3: Result is a complete functional part
   
   Example: Housing = base + ribs (union), then mounting holes (cut)

ADVANCED TECHNIQUES:

1. Boolean Chains
   - Apply multiple boolean operations in sequence
   - Each operation builds on the previous result
   - Example: Union base parts → Cut holes → Cut slots

2. Symmetric Operations
   - Create one feature
   - Mirror or copy it
   - Use boolean to apply all at once
   - Faster than individual operations

3. Complex Assemblies
   - Create sub-assemblies with union
   - Position sub-assemblies
   - Final union for complete assembly
   - Maintains logical structure

TROUBLESHOOTING:

If boolean operation fails:
   - Check that objects actually overlap in 3D space
   - Verify objects are valid solids (not surfaces or wires)
   - Ensure objects are in the same document
   - Try get_object to inspect object properties
   - Check for degenerate geometry (zero-thickness features)

If result looks wrong:
   - Verify operation order (especially for cut)
   - Check object positions before boolean
   - Use get_view from multiple angles
   - Ensure objects are at the correct scale

If result is empty:
   - Objects probably don't overlap
   - Check positions with get_objects
   - Visualize with get_view before boolean
   - For intersection: objects must share volume

Performance Tips:
   - Group multiple unions when possible
   - Avoid very complex splines in boolean operations
   - Keep geometry as simple as needed
   - Refine shapes reduce complexity

INTEGRATION WITH SKETCH WORKFLOW:

Perfect Combination:
   1. Use sketch workflow to create base shapes
   2. Create parametric features with planes and sketches
   3. Combine with boolean operations for final part
   4. Result: Parametric, professional CAD model

Example Full Workflow:
   1. create_datum_plane("base")
   2. create_sketch_on_plane("base")
   3. add_contour_to_sketch(rectangle)
   4. extrude_sketch_bidirectional(100, 0) → base_solid
   5. create_datum_plane("hole1")
   6. create_sketch_on_plane("hole1")
   7. add_contour_to_sketch(circle)
   8. extrude_sketch_bidirectional(120, 0) → hole1_solid
   9. attach_solid_to_plane("hole1", "base", offset_z=50)
   10. boolean_cut("base_solid", "hole1_solid") → final_part

Result: Parametric part with precisely positioned hole

REAL-WORLD EXAMPLES:

Example 1: Bracket with Mounting Holes
   - Base shape: L-bracket (sketch + extrude)
   - Features: 4 mounting holes (cylinders)
   - Operations: 4 × boolean_cut
   - Result: Functional mounting bracket

Example 2: Enclosure
   - Base: Box (sketch + extrude)
   - Inner cavity: Smaller box (sketch + extrude)
   - Mounting posts: 4 cylinders (union)
   - Screw holes: Small cylinders through posts (cut)
   - Operations: union posts, cut cavity, cut holes
   - Result: Complete enclosure with posts and holes

Example 3: Gear
   - Base: Cylinder for gear blank
   - Teeth: Individual tooth profiles (sketch + extrude)
   - Operations: Union all teeth to cylinder
   - Center hole: Small cylinder (cut)
   - Result: Functional gear

REMEMBER:

1. Position first, boolean second
2. Union combines, Cut removes, Intersection keeps common
3. Descriptive names save time later
4. Verify with get_view before committing
5. Build complexity incrementally
6. Boolean operations are destructive (hide originals)
7. Combine with sketch workflow for best results

Boolean operations are your power tools for CAD.
Master them, and you can build anything.
"""


