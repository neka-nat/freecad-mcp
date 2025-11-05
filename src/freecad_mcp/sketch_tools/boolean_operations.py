import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.boolean_operations")


def boolean_union(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    base_object_name: str,
    tool_object_names: list[str],
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Fuse multiple solids into one using Boolean Union operation.
    
    This operation merges the base object with one or more tool objects,
    creating a single unified solid. The source objects are hidden by default.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        base_object_name: Name of the base object
        tool_object_names: List of object names to fuse with the base
        result_name: Name for the result (default: base_object_name + "_union")
        
    Returns:
        List of text/image content with result
    """
    try:
        if not tool_object_names:
            return [
                TextContent(
                    type="text",
                    text="Error: At least one tool object must be provided for union operation"
                )
            ]
        
        if result_name is None:
            result_name = f"{base_object_name}_union"
        
        tool_names_str = "[" + ", ".join([f"'{name}'" for name in tool_object_names]) + "]"
        
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    base = doc.getObject('{base_object_name}')
    if not base:
        print("ERROR: Base object '{base_object_name}' not found")
    else:
        tool_names = {tool_names_str}
        tools = []
        for name in tool_names:
            obj = doc.getObject(name)
            if obj:
                tools.append(obj)
            else:
                print(f"WARNING: Tool object '{{name}}' not found")
        
        if not tools:
            print("ERROR: No valid tool objects found")
        else:
            # Create union
            fusion = doc.addObject("Part::MultiFuse", "{result_name}")
            fusion.Shapes = [base] + tools
            doc.recompute()
            
            # Hide source objects
            base.ViewObject.Visibility = False
            for tool in tools:
                tool.ViewObject.Visibility = False
            
            print(f"SUCCESS: Union created as '{{fusion.Name}}' from {{len(tools) + 1}} objects")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Union '{result_name}' created successfully from {len(tool_object_names) + 1} objects"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create union: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to create union: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create union: {str(e)}")
        ]


def boolean_cut(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    base_object_name: str,
    tool_object_name: str,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Subtract one solid from another using Boolean Cut operation.
    
    This operation removes the volume of the tool object from the base object,
    useful for creating holes, pockets, and cutouts. The source objects are hidden by default.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        base_object_name: Name of the base object (what remains)
        tool_object_name: Name of the tool object (what is subtracted)
        result_name: Name for the result (default: base_object_name + "_cut")
        
    Returns:
        List of text/image content with result
    """
    try:
        if result_name is None:
            result_name = f"{base_object_name}_cut"
        
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    base = doc.getObject('{base_object_name}')
    tool = doc.getObject('{tool_object_name}')
    
    if not base:
        print("ERROR: Base object '{base_object_name}' not found")
    elif not tool:
        print("ERROR: Tool object '{tool_object_name}' not found")
    else:
        # Create cut
        cut = doc.addObject("Part::Cut", "{result_name}")
        cut.Base = base
        cut.Tool = tool
        doc.recompute()
        
        # Hide source objects
        base.ViewObject.Visibility = False
        tool.ViewObject.Visibility = False
        
        print(f"SUCCESS: Cut created as '{{cut.Name}}' ({{base.Name}} - {{tool.Name}})")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Cut '{result_name}' created successfully ({base_object_name} - {tool_object_name})"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create cut: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to create cut: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create cut: {str(e)}")
        ]


def boolean_intersection(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    object1_name: str,
    object2_name: str,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Keep only the common volume between two solids using Boolean Intersection.
    
    This operation creates a new solid containing only the volume that is common
    to both input objects. The source objects are hidden by default.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        object1_name: Name of the first object
        object2_name: Name of the second object
        result_name: Name for the result (default: object1_name + "_intersection")
        
    Returns:
        List of text/image content with result
    """
    try:
        if result_name is None:
            result_name = f"{object1_name}_intersection"
        
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    obj1 = doc.getObject('{object1_name}')
    obj2 = doc.getObject('{object2_name}')
    
    if not obj1:
        print("ERROR: Object '{object1_name}' not found")
    elif not obj2:
        print("ERROR: Object '{object2_name}' not found")
    else:
        # Create intersection
        common = doc.addObject("Part::MultiCommon", "{result_name}")
        common.Shapes = [obj1, obj2]
        doc.recompute()
        
        # Hide source objects
        obj1.ViewObject.Visibility = False
        obj2.ViewObject.Visibility = False
        
        print(f"SUCCESS: Intersection created as '{{common.Name}}' ({{obj1.Name}} ∩ {{obj2.Name}})")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Intersection '{result_name}' created successfully ({object1_name} ∩ {object2_name})"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create intersection: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to create intersection: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create intersection: {str(e)}")
        ]


def boolean_common(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    object1_name: str,
    object2_name: str,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Alias of boolean_intersection for FreeCAD terminology compatibility.
    
    Keep only the common volume between two solids.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        object1_name: Name of the first object
        object2_name: Name of the second object
        result_name: Name for the result (default: object1_name + "_common")
        
    Returns:
        List of text/image content with result
    """
    if result_name is None:
        result_name = f"{object1_name}_common"
    
    return boolean_intersection(ctx, freecad_connection, add_screenshot_helper, doc_name, object1_name, object2_name, result_name)


