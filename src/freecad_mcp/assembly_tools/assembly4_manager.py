import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.assembly_tools.assembly4_manager")


def create_assembly4(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str = "Assembly",
) -> list[TextContent | ImageContent]:
    """Create a new Assembly4 container.
    
    Assembly4 uses LCS (Local Coordinate Systems) for manual placement.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Name for the assembly (default: "Assembly")
        
    Returns:
        List of text/image content with result
    """
    try:
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    try:
        # Create Assembly4 container (App::Part with special properties)
        assembly = doc.addObject('App::Part', '{assembly_name}')
        assembly.Type = 'Assembly'
        
        # Add default LCS at origin
        lcs = assembly.newObject('PartDesign::CoordinateSystem', 'LCS_Origin')
        lcs.Placement = App.Placement(App.Vector(0, 0, 0), App.Rotation())
        
        doc.recompute()
        print(f"SUCCESS: Assembly4 '{{assembly.Name}}' created with default LCS")
    except Exception as e:
        print(f"ERROR: Failed to create Assembly4: {{str(e)}}")
        print("INFO: Make sure Assembly4 workbench is installed")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly4 '{assembly_name}' created successfully with default LCS"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create Assembly4: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to create Assembly4: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create Assembly4: {str(e)}")
        ]


def create_lcs_assembly4(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    parent_name: str,
    lcs_name: str,
    position: dict[str, float],
    rotation: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Create a Local Coordinate System (LCS) in Assembly4.
    
    LCS are used as attachment points for parts in Assembly4.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        parent_name: Parent object (Assembly or Part)
        lcs_name: Name for the LCS
        position: Position dict {"x": float, "y": float, "z": float}
        rotation: Rotation dict {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        
    Returns:
        List of text/image content with result
    """
    try:
        pos_x = position.get("x", 0)
        pos_y = position.get("y", 0)
        pos_z = position.get("z", 0)
        
        has_rotation = rotation is not None
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
    parent = doc.getObject('{parent_name}')
    if not parent:
        print("ERROR: Parent object '{parent_name}' not found")
    else:
        try:
            # Create LCS
            lcs = parent.newObject('PartDesign::CoordinateSystem', '{lcs_name}')
            
            # Set position
            position = App.Vector({pos_x}, {pos_y}, {pos_z})
            
            # Set rotation if provided
            if {has_rotation}:
                rotation = App.Rotation(App.Vector({axis_x}, {axis_y}, {axis_z}), {angle})
            else:
                rotation = App.Rotation()
            
            lcs.Placement = App.Placement(position, rotation)
            
            doc.recompute()
            print(f"SUCCESS: LCS '{{lcs.Name}}' created in '{{parent.Name}}'")
        except Exception as e:
            print(f"ERROR: Failed to create LCS: {{str(e)}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"LCS '{lcs_name}' created in '{parent_name}' at ({pos_x}, {pos_y}, {pos_z})"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create LCS: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to create LCS: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create LCS: {str(e)}")
        ]


def insert_part_assembly4(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
    part_file: str,
    part_name: str,
    attach_lcs_part: str | None = None,
    attach_lcs_target: str | None = None,
    offset: dict[str, float] | None = None,
) -> list[TextContent | ImageContent]:
    """Insert a part into Assembly4 using LCS attachment.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        part_file: Path to external part file
        part_name: Name for the inserted part
        attach_lcs_part: LCS name in the part to attach (optional)
        attach_lcs_target: LCS name in assembly to attach to (optional)
        offset: Optional offset dict {"x": float, "y": float, "z": float}
        
    Returns:
        List of text/image content with result
    """
    try:
        part_file_escaped = part_file.replace("\\", "\\\\")
        
        has_offset = offset is not None
        offset_x = offset.get("x", 0) if has_offset else 0
        offset_y = offset.get("y", 0) if has_offset else 0
        offset_z = offset.get("z", 0) if has_offset else 0
        
        has_attachment = attach_lcs_part and attach_lcs_target
        
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document not found")
else:
    assembly = doc.getObject('{assembly_name}')
    if not assembly:
        print("ERROR: Assembly not found")
    else:
        try:
            # Insert part as App::Link
            link = assembly.newObject('App::Link', '{part_name}')
            link.LinkedObject = App.openDocument("{part_file_escaped}").RootObjects[0]
            
            # Attach to LCS if specified
            if {has_attachment}:
                # Set attachment properties
                link.addProperty('App::PropertyString', 'AttachedBy', 'Assembly')
                link.addProperty('App::PropertyString', 'AttachedTo', 'Assembly')
                link.addProperty('App::PropertyPlacement', 'AttachmentOffset', 'Assembly')
                
                link.AttachedBy = '{attach_lcs_part}'
                link.AttachedTo = '{assembly_name}#{attach_lcs_target}'
                
                # Set offset if provided
                if {has_offset}:
                    offset_placement = App.Placement(
                        App.Vector({offset_x}, {offset_y}, {offset_z}),
                        App.Rotation()
                    )
                    link.AttachmentOffset = offset_placement
                else:
                    link.AttachmentOffset = App.Placement()
            
            doc.recompute()
            print(f"SUCCESS: Part '{{link.Name}}' inserted into assembly")
        except Exception as e:
            print(f"ERROR: Failed to insert part: {{str(e)}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            attach_info = f" with LCS attachment" if has_attachment else ""
            response = [
                TextContent(
                    type="text",
                    text=f"Part '{part_name}' inserted into Assembly4{attach_info}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to insert part: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to insert part into Assembly4: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to insert part: {str(e)}")
        ]


def attach_lcs_to_geometry(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    lcs_name: str,
    target_object: str,
    element: str,
    map_mode: str = "FlatFace",
) -> list[TextContent | ImageContent]:
    """Attach an LCS to a geometric element.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        lcs_name: LCS object name
        target_object: Target object name
        element: Element name (e.g., "Face1", "Edge1", "Vertex1")
        map_mode: Attachment mode - "FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"
        
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
    lcs = doc.getObject('{lcs_name}')
    target = doc.getObject('{target_object}')
    
    if not lcs:
        print("ERROR: LCS '{lcs_name}' not found")
    elif not target:
        print("ERROR: Target object '{target_object}' not found")
    else:
        try:
            # Attach LCS to geometry using FreeCAD attachment system
            # PartDesign::CoordinateSystem uses AttachmentSupport property
            if hasattr(lcs, 'AttachmentSupport'):
                lcs.AttachmentSupport = [(target, '{element}')]
                lcs.MapMode = '{map_mode}'
                lcs.recompute()
            else:
                # Fallback: try to set Support directly (older FreeCAD versions)
                lcs.Support = [(target, '{element}')]
                lcs.MapMode = '{map_mode}'
            
            doc.recompute()
            print(f"SUCCESS: LCS '{{lcs.Name}}' attached to '{{target.Name}}.{element}'")
        except Exception as e:
            print(f"ERROR: Failed to attach LCS: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"LCS '{lcs_name}' attached to '{target_object}.{element}' with mode '{map_mode}'"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to attach LCS: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to attach LCS to geometry: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to attach LCS: {str(e)}")
        ]

