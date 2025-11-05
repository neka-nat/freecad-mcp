import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.contour_builder")


def add_contour_to_sketch(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    sketch_name: str,
    geometry_elements: list[dict[str, Any]],
    constraints: list[dict[str, Any]] | None = None,
    fix_first_point_to_origin: bool = True,
) -> list[TextContent | ImageContent]:
    """Add geometric contour elements and constraints to a sketch.
    
    Supported geometry types:
    - point: {type: "point", x: float, y: float}
    - line: {type: "line", start: {x, y}, end: {x, y}}
    - arc: {type: "arc", center: {x, y}, radius: float, start_angle: float, end_angle: float}
    - circle: {type: "circle", center: {x, y}, radius: float}
    - bspline: {type: "bspline", points: [{x, y}, ...], degree: int (default 3), closed: bool}
    - ellipse: {type: "ellipse", center: {x, y}, major_radius: float, minor_radius: float, angle: float}
    
    Supported constraints:
    - coincident: {type: "coincident", geo1: int, point1: int, geo2: int, point2: int}
    - tangent: {type: "tangent", geo1: int, geo2: int}
    - distance: {type: "distance", geo1: int, point1: int, geo2: int, point2: int, value: float}
    - horizontal: {type: "horizontal", geo: int}
    - vertical: {type: "vertical", geo: int}
    - angle: {type: "angle", geo1: int, geo2: int, value: float}
    - fix: {type: "fix", geo: int, point: int}
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        sketch_name: Sketch name
        geometry_elements: List of geometry elements to add
        constraints: List of constraints to apply
        fix_first_point_to_origin: If True, fixes the first point to sketch origin
        
    Returns:
        List of text/image content with result
    """
    try:
        if not geometry_elements:
            return [
                TextContent(
                    type="text",
                    text="No geometry elements provided"
                )
            ]
        
        constraints = constraints or []
        
        geometry_code = _generate_geometry_code(geometry_elements)
        constraint_code = _generate_constraint_code(constraints, fix_first_point_to_origin)
        
        code = f"""
import FreeCAD as App
import Part
import Sketcher

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    sketch = doc.getObject('{sketch_name}')
    if not sketch:
        print("ERROR: Sketch '{sketch_name}' not found")
    else:
        try:
            # Add geometry
{geometry_code}
            
            # Add constraints
{constraint_code}
            
            doc.recompute()
            print(f"SUCCESS: Added {{len(geometry_elements)}} geometry elements and {{len(constraints)}} constraints to sketch '{sketch_name}'")
        except Exception as e:
            print(f"ERROR: {{str(e)}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Added {len(geometry_elements)} geometry elements to sketch '{sketch_name}'"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to add contour: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to add contour: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to add contour: {str(e)}")
        ]


def _generate_geometry_code(geometry_elements: list[dict[str, Any]]) -> str:
    """Generate FreeCAD Python code for geometry elements."""
    lines = []
    lines.append("            geometry_elements = []")
    
    for idx, elem in enumerate(geometry_elements):
        elem_type = elem.get("type", "").lower()
        
        if elem_type == "point":
            x, y = elem.get("x", 0), elem.get("y", 0)
            lines.append(f"            geometry_elements.append(Part.Point(App.Vector({x}, {y}, 0)))")
            
        elif elem_type == "line":
            start = elem.get("start", {})
            end = elem.get("end", {})
            x1, y1 = start.get("x", 0), start.get("y", 0)
            x2, y2 = end.get("x", 0), end.get("y", 0)
            lines.append(f"            geometry_elements.append(Part.LineSegment(App.Vector({x1}, {y1}, 0), App.Vector({x2}, {y2}, 0)))")
            
        elif elem_type == "arc":
            center = elem.get("center", {})
            cx, cy = center.get("x", 0), center.get("y", 0)
            radius = elem.get("radius", 10)
            start_angle = elem.get("start_angle", 0)
            end_angle = elem.get("end_angle", 90)
            lines.append(f"            geometry_elements.append(Part.ArcOfCircle(Part.Circle(App.Vector({cx}, {cy}, 0), App.Vector(0, 0, 1), {radius}), {start_angle}, {end_angle}))")
            
        elif elem_type == "circle":
            center = elem.get("center", {})
            cx, cy = center.get("x", 0), center.get("y", 0)
            radius = elem.get("radius", 10)
            lines.append(f"            geometry_elements.append(Part.Circle(App.Vector({cx}, {cy}, 0), App.Vector(0, 0, 1), {radius}))")
            
        elif elem_type == "bspline":
            points = elem.get("points", [])
            degree = elem.get("degree", 3)
            closed = elem.get("closed", False)
            points_str = "[" + ", ".join([f"App.Vector({p.get('x', 0)}, {p.get('y', 0)}, 0)" for p in points]) + "]"
            lines.append(f"            geometry_elements.append(Part.BSplineCurve({points_str}, None, None, {closed}, {degree}, None, False))")
            
        elif elem_type == "ellipse":
            center = elem.get("center", {})
            cx, cy = center.get("x", 0), center.get("y", 0)
            major = elem.get("major_radius", 10)
            minor = elem.get("minor_radius", 5)
            angle = elem.get("angle", 0)
            lines.append(f"            geometry_elements.append(Part.Ellipse(App.Vector({cx}, {cy}, 0), {major}, {minor}))")
    
    lines.append("            sketch.addGeometry(geometry_elements, False)")
    return "\n".join(lines)


def _generate_constraint_code(constraints: list[dict[str, Any]], fix_first_point: bool) -> str:
    """Generate FreeCAD Python code for constraints."""
    lines = []
    
    if fix_first_point:
        lines.append("            # Fix first point to origin")
        lines.append("            sketch.addConstraint(Sketcher.Constraint('Coincident', 0, 1, -1, 1))")
    
    if not constraints:
        return "\n".join(lines)
    
    lines.append("            # User-defined constraints")
    lines.append("            constraint_list = []")
    
    for constraint in constraints:
        c_type = constraint.get("type", "").lower()
        
        if c_type == "coincident":
            geo1 = constraint.get("geo1", 0)
            point1 = constraint.get("point1", 1)
            geo2 = constraint.get("geo2", 1)
            point2 = constraint.get("point2", 1)
            lines.append(f"            constraint_list.append(Sketcher.Constraint('Coincident', {geo1}, {point1}, {geo2}, {point2}))")
            
        elif c_type == "tangent":
            geo1 = constraint.get("geo1", 0)
            geo2 = constraint.get("geo2", 1)
            lines.append(f"            constraint_list.append(Sketcher.Constraint('Tangent', {geo1}, {geo2}))")
            
        elif c_type == "distance":
            geo1 = constraint.get("geo1", 0)
            point1 = constraint.get("point1", 1)
            geo2 = constraint.get("geo2", 1)
            point2 = constraint.get("point2", 1)
            value = constraint.get("value", 10)
            lines.append(f"            constraint_list.append(Sketcher.Constraint('Distance', {geo1}, {point1}, {geo2}, {point2}, {value}))")
            
        elif c_type == "horizontal":
            geo = constraint.get("geo", 0)
            lines.append(f"            constraint_list.append(Sketcher.Constraint('Horizontal', {geo}))")
            
        elif c_type == "vertical":
            geo = constraint.get("geo", 0)
            lines.append(f"            constraint_list.append(Sketcher.Constraint('Vertical', {geo}))")
            
        elif c_type == "angle":
            geo1 = constraint.get("geo1", 0)
            geo2 = constraint.get("geo2", 1)
            value = constraint.get("value", 90)
            import math
            value_rad = math.radians(value)
            lines.append(f"            constraint_list.append(Sketcher.Constraint('Angle', {geo1}, {geo2}, {value_rad}))")
            
        elif c_type == "fix":
            geo = constraint.get("geo", 0)
            point = constraint.get("point", 1)
            lines.append(f"            constraint_list.append(Sketcher.Constraint('Block', {geo}))")
    
    lines.append("            if constraint_list:")
    lines.append("                sketch.addConstraint(constraint_list)")
    
    return "\n".join(lines)


