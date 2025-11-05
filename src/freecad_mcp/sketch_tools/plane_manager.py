import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.plane_manager")


def create_datum_plane(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    plane_name: str,
    alignment: str = "xy",
    offset: float = 0.0,
) -> list[TextContent | ImageContent]:
    """Create a datum plane in FreeCAD aligned with the specified orientation.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        plane_name: Name for the datum plane
        alignment: Plane alignment ('xy', 'xz', 'yz')
        offset: Offset distance from origin
        
    Returns:
        List of text/image content with result
    """
    try:
        alignment_map = {"xy": "xy", "xz": "xz", "yz": "yz"}
        mapmode_map = {"xy": "ObjectXY", "xz": "ObjectXZ", "yz": "ObjectYZ"}
        
        if alignment.lower() not in alignment_map:
            return [
                TextContent(
                    type="text",
                    text=f"Invalid alignment '{alignment}'. Must be one of: xy, xz, yz"
                )
            ]
        
        mm = mapmode_map[alignment.lower()]
        code = f"""
import FreeCAD as App
doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    body = doc.addObject('PartDesign::Body', '{plane_name}')
    plane = doc.addObject('PartDesign::Plane', '{plane_name}_Datum')
    body.addObject(plane)
    plane.MapMode = 'Deactivated'
    off = plane.Placement
    if '{mm}' == 'ObjectXY':
        off.Base.z = {offset}
    elif '{mm}' == 'ObjectXZ':
        off.Base.y = {offset}
    else:
        off.Base.x = {offset}
    plane.Placement = off
    doc.recompute()
    print("SUCCESS: Datum plane '{plane_name}_Datum' created with alignment '{alignment}'")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Datum plane '{plane_name}' created successfully with alignment '{alignment}'"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create datum plane: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to create datum plane: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create datum plane: {str(e)}")
        ]


