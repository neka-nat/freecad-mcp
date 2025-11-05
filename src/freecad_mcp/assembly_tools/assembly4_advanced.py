"""Assembly4 Advanced Functions - Phase 2 (2025-10-08)"""

import logging
import json
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.assembly_tools.assembly4_advanced")


def list_assembly4_lcs(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    parent_name: str,
) -> list[TextContent | ImageContent]:
    """List all LCS (Local Coordinate Systems) in an Assembly4 or Part.
    
    Returns detailed information about each LCS including position, rotation, and attachment.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        parent_name: Parent object (Assembly or Part) name
        
    Returns:
        List of text/image content with LCS information
    """
    try:
        code = f"""
import FreeCAD as App
import json

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document not found")
else:
    parent = doc.getObject('{parent_name}')
    if not parent:
        print("ERROR: Parent object not found")
    else:
        try:
            lcs_list = []
            
            # Parcourir tous les objets du parent
            for obj in parent.Group:
                # Vérifier si c'est un LCS
                if obj.TypeId == 'PartDesign::CoordinateSystem':
                    lcs_info = {{
                        'name': obj.Name,
                        'label': obj.Label,
                        'position': {{
                            'x': float(obj.Placement.Base.x),
                            'y': float(obj.Placement.Base.y),
                            'z': float(obj.Placement.Base.z)
                        }},
                        'rotation': {{
                            'axis': {{
                                'x': float(obj.Placement.Rotation.Axis.x),
                                'y': float(obj.Placement.Rotation.Axis.y),
                                'z': float(obj.Placement.Rotation.Axis.z)
                            }},
                            'angle': float(obj.Placement.Rotation.Angle)
                        }},
                        'attached': False,
                        'attachment': None
                    }}
                    
                    # Vérifier attachement
                    if hasattr(obj, 'AttachmentSupport') and len(obj.AttachmentSupport) > 0:
                        lcs_info['attached'] = True
                        support = obj.AttachmentSupport[0]
                        lcs_info['attachment'] = {{
                            'object': support[0].Name if hasattr(support[0], 'Name') else str(support[0]),
                            'element': support[1] if len(support) > 1 else '',
                            'map_mode': obj.MapMode if hasattr(obj, 'MapMode') else 'Unknown'
                        }}
                    
                    lcs_list.append(lcs_info)
            
            print(f"SUCCESS: Found {{len(lcs_list)}} LCS")
            print(f"LCS_DATA: {{json.dumps(lcs_list)}}")
            
        except Exception as e:
            print(f"ERROR: Failed to list LCS: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            message = res.get("message", "")
            
            # Extract LCS data
            lcs_data = []
            if "LCS_DATA:" in message:
                try:
                    json_start = message.find("LCS_DATA:") + len("LCS_DATA:")
                    json_str = message[json_start:].strip()
                    lcs_data = json.loads(json_str)
                except Exception as e:
                    logger.error(f"Failed to parse LCS data: {e}")
            
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly4 '{parent_name}' contains {len(lcs_data)} LCS:\n{json.dumps(lcs_data, indent=2)}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to list Assembly4 LCS: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to list Assembly4 LCS: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to list LCS: {str(e)}")
        ]


def delete_lcs_assembly4(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    parent_name: str,
    lcs_name: str,
) -> list[TextContent | ImageContent]:
    """Delete an LCS from Assembly4.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        parent_name: Parent object (Assembly or Part) name
        lcs_name: LCS object name to delete
        
    Returns:
        List of text/image content with result
    """
    try:
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document not found")
else:
    parent = doc.getObject('{parent_name}')
    lcs = doc.getObject('{lcs_name}')
    
    if not parent:
        print("ERROR: Parent object not found")
    elif not lcs:
        print("ERROR: LCS not found")
    else:
        try:
            # Remove LCS from parent group
            if lcs in parent.Group:
                parent.removeObject(lcs)
            
            # Delete the LCS object
            doc.removeObject(lcs.Name)
            
            doc.recompute()
            print(f"SUCCESS: LCS '{{'{lcs_name}'}}' deleted")
        except Exception as e:
            print(f"ERROR: Failed to delete LCS: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"LCS '{lcs_name}' deleted from '{parent_name}'"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to delete LCS: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to delete LCS: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to delete LCS: {str(e)}")
        ]


def modify_lcs_assembly4(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    lcs_name: str,
    position: dict[str, float] | None = None,
    rotation: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Modify position and/or rotation of an LCS in Assembly4.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        lcs_name: LCS object name
        position: New position {"x": float, "y": float, "z": float} (optional)
        rotation: New rotation {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        
    Returns:
        List of text/image content with result
    """
    try:
        has_position = position is not None
        has_rotation = rotation is not None
        
        if has_position:
            pos_x = position.get("x", 0)
            pos_y = position.get("y", 0)
            pos_z = position.get("z", 0)
        else:
            pos_x = pos_y = pos_z = 0
        
        if has_rotation:
            axis = rotation.get("axis", {"x": 0, "y": 0, "z": 1})
            axis_x = axis.get("x", 0)
            axis_y = axis.get("y", 0)
            axis_z = axis.get("z", 1)
            angle = rotation.get("angle", 0)
        else:
            axis_x = axis_y = 0
            axis_z = 1
            angle = 0
        
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document not found")
else:
    lcs = doc.getObject('{lcs_name}')
    
    if not lcs:
        print("ERROR: LCS not found")
    else:
        try:
            if {has_position} or {has_rotation}:
                if {has_position} and {has_rotation}:
                    # Both position and rotation
                    position = App.Vector({pos_x}, {pos_y}, {pos_z})
                    rotation = App.Rotation(App.Vector({axis_x}, {axis_y}, {axis_z}), {angle})
                    lcs.Placement = App.Placement(position, rotation)
                elif {has_position}:
                    # Only position
                    lcs.Placement.Base = App.Vector({pos_x}, {pos_y}, {pos_z})
                else:
                    # Only rotation
                    rotation = App.Rotation(App.Vector({axis_x}, {axis_y}, {axis_z}), {angle})
                    lcs.Placement.Rotation = rotation
                
                doc.recompute()
                print(f"SUCCESS: LCS '{{lcs.Label}}' modified")
            else:
                print("ERROR: No position or rotation provided")
                
        except Exception as e:
            print(f"ERROR: Failed to modify LCS: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            changes = []
            if has_position:
                changes.append(f"position ({pos_x}, {pos_y}, {pos_z})")
            if has_rotation:
                changes.append(f"rotation ({angle}° around axis)")
            response = [
                TextContent(
                    type="text",
                    text=f"LCS '{lcs_name}' modified: {', '.join(changes)}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to modify LCS: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to modify LCS: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to modify LCS: {str(e)}")
        ]










