import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.attachment_manager")


def attach_solid_to_plane(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    solid_body_name: str,
    target_plane_name: str,
    align_origin: bool = True,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    rotation_angle: float = 0.0,
    rotation_axis: str = "z",
) -> list[TextContent | ImageContent]:
    """Attach (position) a solid body to align with another datum plane.
    
    This function positions a solid body so that its base plane aligns with
    a target plane, optionally matching their origins and applying offsets.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        solid_body_name: Name of the Body containing the solid to position
        target_plane_name: Name of the target datum plane (Body) to align with
        align_origin: If True, align the origins of the planes
        offset_x: X offset from target plane origin
        offset_y: Y offset from target plane origin
        offset_z: Z offset from target plane origin
        rotation_angle: Rotation angle in degrees
        rotation_axis: Rotation axis ('x', 'y', or 'z')
        
    Returns:
        List of text/image content with result
    """
    try:
        axis_map = {
            "x": "(1, 0, 0)",
            "y": "(0, 1, 0)",
            "z": "(0, 0, 1)"
        }
        
        if rotation_axis.lower() not in axis_map:
            return [
                TextContent(
                    type="text",
                    text=f"Invalid rotation axis '{rotation_axis}'. Must be one of: x, y, z"
                )
            ]
        
        axis_vector = axis_map[rotation_axis.lower()]
        
        code = f"""
import FreeCAD as App
import math

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    solid_body = doc.getObject('{solid_body_name}')
    target_body = doc.getObject('{target_plane_name}')
    
    if not solid_body:
        print("ERROR: Body '{solid_body_name}' not found")
    elif not target_body:
        print("ERROR: Target plane (Body) '{target_plane_name}' not found")
    else:
        target_placement = target_body.Placement
        
        new_placement = App.Placement()
        
        if {align_origin}:
            new_placement.Base = target_placement.Base
        
        new_placement.Base.x += {offset_x}
        new_placement.Base.y += {offset_y}
        new_placement.Base.z += {offset_z}
        
        if {rotation_angle} != 0:
            rotation = App.Rotation(App.Vector{axis_vector}, {rotation_angle})
            new_placement.Rotation = rotation
        
        solid_body.Placement = new_placement
        
        doc.recompute()
        print(f"SUCCESS: Body '{{solid_body.Name}}' attached to plane '{target_plane_name}' with offsets (x:{offset_x}, y:{offset_y}, z:{offset_z})")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Body '{solid_body_name}' attached successfully to plane '{target_plane_name}'"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to attach solid: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to attach solid: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to attach solid: {str(e)}")
        ]


