import logging
import json
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.assembly_tools.assembly_common")


def list_assembly_parts(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
    assembly_type: str = "auto",
) -> list[TextContent | ImageContent]:
    """List all parts in an assembly.
    
    Works with both Assembly3 and Assembly4.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        assembly_type: Type of assembly - "auto", "assembly3", "assembly4"
        
    Returns:
        List of text/image content with result
    """
    try:
        code = f"""
import FreeCAD as App
import json

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document not found")
else:
    assembly = doc.getObject('{assembly_name}')
    if not assembly:
        print("ERROR: Assembly not found")
    else:
        parts_list = []
        
        # Detect assembly type if auto
        assembly_type = '{assembly_type}'
        if assembly_type == 'auto':
            if assembly.TypeId == 'Assembly::AssemblyObject':
                assembly_type = 'assembly3'
            elif assembly.TypeId == 'App::Part':
                assembly_type = 'assembly4'
        
        try:
            if assembly_type == 'assembly3':
                # List Assembly3 parts
                for obj in assembly.Group:
                    if hasattr(obj, 'Shape'):
                        parts_list.append({{
                            'name': obj.Name,
                            'label': obj.Label,
                            'type': obj.TypeId,
                            'visible': obj.ViewObject.Visibility if hasattr(obj, 'ViewObject') else True
                        }})
            
            elif assembly_type == 'assembly4':
                # List Assembly4 links
                for obj in assembly.Group:
                    if obj.TypeId == 'App::Link':
                        parts_list.append({{
                            'name': obj.Name,
                            'label': obj.Label,
                            'type': 'Link',
                            'linked_file': obj.LinkedObject.Document.FileName if hasattr(obj.LinkedObject, 'Document') else 'Unknown',
                            'visible': obj.ViewObject.Visibility if hasattr(obj, 'ViewObject') else True
                        }})
            
            print(f"SUCCESS: {{len(parts_list)}} parts found")
            print(f"PARTS_DATA: {{json.dumps(parts_list)}}")
        
        except Exception as e:
            print(f"ERROR: Failed to list parts: {{str(e)}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            message = res.get("message", "")
            
            # Extract parts data from message
            parts_data = []
            if "PARTS_DATA:" in message:
                try:
                    json_start = message.find("PARTS_DATA:") + len("PARTS_DATA:")
                    json_str = message[json_start:].strip()
                    parts_data = json.loads(json_str)
                except:
                    pass
            
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly '{assembly_name}' contains {len(parts_data)} parts:\n{json.dumps(parts_data, indent=2)}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to list assembly parts: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to list assembly parts: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to list assembly parts: {str(e)}")
        ]


def export_assembly(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
    export_path: str,
    export_format: str = "step",
) -> list[TextContent | ImageContent]:
    """Export an assembly to a file.
    
    Supported formats: step, iges, stl, obj, brep
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        export_path: Path for exported file
        export_format: Export format - "step", "iges", "stl", "obj", "brep"
        
    Returns:
        List of text/image content with result
    """
    try:
        export_path_escaped = export_path.replace("\\", "\\\\")
        
        code = f"""
import FreeCAD as App
import Import

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document not found")
else:
    assembly = doc.getObject('{assembly_name}')
    if not assembly:
        print("ERROR: Assembly not found")
    else:
        try:
            export_format = '{export_format}'.lower()
            export_path = "{export_path_escaped}"
            
            # Ensure correct file extension
            if not export_path.endswith(f'.{{export_format}}'):
                export_path += f'.{{export_format}}'
            
            # Export based on format
            if export_format == 'step':
                Import.export([assembly], export_path)
            elif export_format == 'iges':
                Import.export([assembly], export_path)
            elif export_format == 'stl':
                import Mesh
                Mesh.export([assembly], export_path)
            elif export_format == 'obj':
                import Mesh
                Mesh.export([assembly], export_path)
            elif export_format == 'brep':
                assembly.Shape.exportBrep(export_path)
            else:
                print(f"ERROR: Unsupported format '{{export_format}}'")
                raise ValueError(f"Unsupported format")
            
            print(f"SUCCESS: Assembly exported to '{{export_path}}'")
        
        except Exception as e:
            print(f"ERROR: Failed to export assembly: {{str(e)}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly '{assembly_name}' exported to '{export_path}' ({export_format.upper()} format)"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to export assembly: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to export assembly: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to export assembly: {str(e)}")
        ]


def calculate_assembly_mass(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """Calculate the total mass of an assembly.
    
    Requires parts to have material/density properties set.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        
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
    assembly = doc.getObject('{assembly_name}')
    if not assembly:
        print("ERROR: Assembly not found")
    else:
        try:
            total_mass = 0.0
            total_volume = 0.0
            parts_with_mass = 0
            parts_without_mass = 0
            
            # Iterate through parts
            for obj in assembly.Group:
                if hasattr(obj, 'Shape') and obj.Shape.Volume > 0:
                    volume_mm3 = obj.Shape.Volume  # mm³
                    volume_m3 = volume_mm3 / 1e9   # Convert to m³
                    total_volume += volume_mm3
                    
                    # Check if object has density/material
                    if hasattr(obj, 'Material') and hasattr(obj.Material, 'Density'):
                        density = obj.Material.Density  # kg/m³
                        mass = volume_m3 * density      # kg
                        total_mass += mass
                        parts_with_mass += 1
                    else:
                        parts_without_mass += 1
            
            print(f"SUCCESS: Assembly mass calculated")
            print(f"Total Mass: {{total_mass:.3f}} kg")
            print(f"Total Volume: {{total_volume:.0f}} mm³ ({{total_volume/1e9:.6f}} m³)")
            print(f"Parts with mass properties: {{parts_with_mass}}")
            print(f"Parts without mass properties: {{parts_without_mass}}")
            
            if parts_without_mass > 0:
                print(f"WARNING: {{parts_without_mass}} parts don't have material/density set")
        
        except Exception as e:
            print(f"ERROR: Failed to calculate mass: {{str(e)}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            message = res.get("message", "")
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly mass calculation:\n{message}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to calculate assembly mass: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to calculate assembly mass: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to calculate assembly mass: {str(e)}")
        ]










