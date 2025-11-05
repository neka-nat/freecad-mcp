def sketch_workflow_strategy() -> str:
    """Strategic guide for using the sketch-based workflow in FreeCAD MCP.
    
    This workflow provides a structured approach to creating parametric solids
    through datum planes, sketches, contours, and extrusion.
    """
    return """
Sketch-Based Workflow Strategy for FreeCAD MCP

This workflow enables precise, parametric solid creation through a structured process.
Always follow these steps in order for best results:

WORKFLOW STEPS:

1. CREATE DATUM PLANE
   Use: create_datum_plane()
   - Creates a reference plane aligned with XY, XZ, or YZ
   - Name the plane descriptively (e.g., "base_plane", "side_plane")
   - The plane serves as the foundation for sketching
   - Can be offset from origin if needed
   
   Example:
   {
     "doc_name": "MyDocument",
     "plane_name": "base_plane",
     "alignment": "xy",
     "offset": 0.0
   }

2. CREATE SKETCH ON PLANE
   Use: create_sketch_on_plane()
   - Creates a sketch attached to the datum plane
   - Sketch is automatically named: {plane_name}_sketch
   - The sketch inherits the plane's coordinate system
   
   Example:
   {
     "doc_name": "MyDocument",
     "plane_name": "base_plane"
   }
   
   This creates: "base_plane_sketch"

3. ADD CONTOUR TO SKETCH
   Use: add_contour_to_sketch()
   - Draw the 2D profile using geometric elements
   - Supported geometry:
     * Points
     * Lines
     * Arcs of circles
     * Full circles
     * B-Splines (for organic shapes)
     * Ellipses
   
   - Apply constraints to ensure geometry relationships:
     * Coincident: Make endpoints touch
     * Tangent: Smooth transitions between curves
     * Distance: Fixed distances
     * Horizontal/Vertical: Align with axes
     * Angle: Fixed angles between elements
     * Fix: Lock points in place
   
   - By default, the first point is fixed to the sketch origin
     This makes positioning the final solid predictable
   
   Example:
   {
     "doc_name": "MyDocument",
     "sketch_name": "base_plane_sketch",
     "geometry_elements": [
       {
         "type": "line",
         "start": {"x": 0, "y": 0},
         "end": {"x": 100, "y": 0}
       },
       {
         "type": "arc",
         "center": {"x": 100, "y": 50},
         "radius": 50,
         "start_angle": 270,
         "end_angle": 0
       },
       {
         "type": "line",
         "start": {"x": 100, "y": 100},
         "end": {"x": 0, "y": 100}
       }
     ],
     "constraints": [
       {
         "type": "coincident",
         "geo1": 0,
         "point1": 2,
         "geo2": 1,
         "point2": 1
       },
       {
         "type": "tangent",
         "geo1": 0,
         "geo2": 1
       }
     ],
     "fix_first_point_to_origin": true
   }

4. EXTRUDE SKETCH BIDIRECTIONALLY
   Use: extrude_sketch_bidirectional()
   - Creates a 3D solid from the 2D sketch
   - Solid is automatically named: {plane_name}_solid
   - Can extrude in both directions (forward and backward)
   - This creates volume from the contour
   
   Example:
   {
     "doc_name": "MyDocument",
     "sketch_name": "base_plane_sketch",
     "length_forward": 50.0,
     "length_backward": 25.0,
     "use_midplane": false
   }
   
   This creates: "base_plane_solid"

5. ATTACH SOLID TO ANOTHER PLANE (Optional, for assemblies)
   Use: attach_solid_to_plane()
   - Position the solid by aligning its base plane with another datum plane
   - Can align origins for precise positioning
   - Apply offsets and rotations as needed
   - Essential for creating multi-part assemblies
   
   Example:
   {
     "doc_name": "MyDocument",
     "solid_body_name": "base_plane",
     "target_plane_name": "mounting_plane",
     "align_origin": true,
     "offset_x": 0,
     "offset_y": 0,
     "offset_z": 10,
     "rotation_angle": 90,
     "rotation_axis": "z"
   }

NAMING CONVENTIONS:

The workflow uses consistent naming to track relationships:
- Datum plane: {custom_name}
- Sketch: {custom_name}_sketch
- Solid: {custom_name}_solid

This makes it easy to understand the hierarchy and dependencies.

BEST PRACTICES:

1. Start Simple
   - Begin with basic geometry (rectangles, simple curves)
   - Add complexity incrementally
   - Verify each step before proceeding

2. Use Constraints Wisely
   - Add coincident constraints to connect geometry endpoints
   - Use tangent constraints for smooth transitions
   - Fix critical points to maintain design intent

3. Check Geometry Before Extrusion
   - Ensure the sketch is fully closed (if creating a solid)
   - Verify no overlapping or intersecting geometry
   - Use get_object() to inspect the sketch if needed

4. Leverage the Origin Lock
   - The first point fixed to origin makes positioning predictable
   - When attaching solids, origins align precisely
   - This is crucial for assemblies and multi-part designs

5. Build Complex Shapes with Multiple Operations
   - Create multiple sketches on different planes
   - Combine using Boolean operations (future feature)
   - Think in terms of additive/subtractive features

GEOMETRY INDEXING:

When adding constraints, geometry is indexed starting from 0:
- First geometry element: index 0
- Second geometry element: index 1
- And so on...

Points on geometry are indexed:
- For lines: point 1 = start, point 2 = end
- For arcs: point 1 = start, point 2 = end, point 3 = center
- For circles: point 3 = center

COMMON PATTERNS:

Rectangle with rounded corners:
1. Four lines forming a square
2. Four arcs at corners
3. Coincident constraints connecting lines to arcs
4. Tangent constraints for smooth transitions

Organic shapes:
1. Create control points
2. Use B-Spline to connect them
3. Add constraints to control curvature

Symmetric profiles:
1. Draw half the profile
2. Use mirror constraints (future feature)
3. Or manually create mirrored geometry

TROUBLESHOOTING:

If sketch won't extrude:
- Verify sketch is closed (all endpoints connected)
- Check for self-intersections
- Ensure sketch is on a valid plane

If constraints fail:
- Check geometry indices are correct
- Verify point indices match geometry type
- Start with basic constraints, add complexity gradually

If attachment doesn't work:
- Confirm both bodies exist
- Check plane names match exactly
- Verify target plane has proper orientation

Remember: This workflow is designed for precision and repeatability.
Take time to set up datum planes and constraints properly, and the rest will follow naturally.
"""


