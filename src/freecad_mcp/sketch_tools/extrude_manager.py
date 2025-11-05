import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.extrude_manager")


def extrude_sketch_bidirectional(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    sketch_name: str,
    length_forward: float,
    length_backward: float = 0.0,
    use_midplane: bool = False,
) -> list[TextContent | ImageContent]:
    """Extrude a sketch bidirectionally to create a solid.
    
    The solid will be automatically named based on the sketch name,
    replacing '_sketch' with '_solid'.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        sketch_name: Sketch name to extrude
        length_forward: Extrusion length in the forward direction (normal to sketch)
        length_backward: Extrusion length in the backward direction (default 0.0)
        use_midplane: If True, extrude symmetrically (length_forward is total, ignoring length_backward)
        
    Returns:
        List of text/image content with result
    """
    try:
        if "_sketch" in sketch_name:
            solid_name = sketch_name.replace("_sketch", "_solid")
        else:
            solid_name = f"{sketch_name}_solid"
        
        total_length = length_forward + length_backward
        
        code = f"""
import FreeCAD as App
import PartDesign

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    sketch = doc.getObject('{sketch_name}')
    if not sketch:
        print("ERROR: Sketch '{sketch_name}' not found")
    else:
        body = sketch.getParentGroup()
        if not body:
            print("ERROR: Sketch '{sketch_name}' is not in a Body")
        else:
            pad = body.newObject('PartDesign::Pad', '{solid_name}')
            pad.Profile = (sketch, [''])
            pad.Length = {length_forward}
            
            if {use_midplane}:
                pad.Midplane = True
                pad.Length = {total_length}
            elif {length_backward} > 0:
                pad.Type = 1
                pad.Length = {length_forward}
                pad.Length2 = {length_backward}
            else:
                pad.Type = 0
                pad.Length = {length_forward}
            
            pad.ReferenceAxis = (sketch, ['N_Axis'])
            sketch.Visibility = False
            
            doc.recompute()
            print(f"SUCCESS: Solid '{{pad.Name}}' created by extruding '{sketch_name}' (forward: {length_forward}, backward: {length_backward})")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Solid '{solid_name}' created successfully (forward: {length_forward}mm, backward: {length_backward}mm)"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to extrude sketch: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to extrude sketch: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to extrude sketch: {str(e)}")
        ]


