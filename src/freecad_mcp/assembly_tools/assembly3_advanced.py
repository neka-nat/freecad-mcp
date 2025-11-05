"""Assembly3 Advanced Functions - Phase 2 (2025-10-08)"""

import logging
import json
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.assembly_tools.assembly3_advanced")


def list_assembly3_constraints(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """List all constraints in an Assembly3.
    
    Returns detailed information about each constraint including type, references, and properties.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        List of text/image content with constraints information
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
        try:
            constraints = []
            
            # Parcourir tous les objets de l'assembly
            for obj in assembly.Group:
                # Vérifier si c'est une contrainte
                if 'Constraint' in obj.TypeId:
                    constraint_info = {{
                        'name': obj.Name,
                        'label': obj.Label,
                        'type': obj.TypeId,
                        'references': [],
                        'enabled': True,
                        'properties': {{}}
                    }}
                    
                    # Extraire les références
                    if hasattr(obj, 'References'):
                        for ref in obj.References:
                            if ref and len(ref) >= 2:
                                ref_obj = ref[0]
                                ref_element = ref[1] if len(ref) > 1 else ''
                                constraint_info['references'].append({{
                                    'object': ref_obj.Name if hasattr(ref_obj, 'Name') else str(ref_obj),
                                    'element': ref_element
                                }})
                    
                    # Extraire propriétés spécifiques
                    if hasattr(obj, 'Enabled'):
                        constraint_info['enabled'] = obj.Enabled
                    if hasattr(obj, 'Distance'):
                        constraint_info['properties']['Distance'] = float(obj.Distance)
                    if hasattr(obj, 'Angle'):
                        constraint_info['properties']['Angle'] = float(obj.Angle)
                    if hasattr(obj, 'LockRotation'):
                        constraint_info['properties']['LockRotation'] = obj.LockRotation
                    if hasattr(obj, 'LockPosition'):
                        constraint_info['properties']['LockPosition'] = obj.LockPosition
                    
                    constraints.append(constraint_info)
            
            print(f"SUCCESS: Found {{len(constraints)}} constraints")
            print(f"CONSTRAINTS_DATA: {{json.dumps(constraints)}}")
            
        except Exception as e:
            print(f"ERROR: Failed to list constraints: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            message = res.get("message", "")
            
            # Extract constraints data
            constraints_data = []
            if "CONSTRAINTS_DATA:" in message:
                try:
                    json_start = message.find("CONSTRAINTS_DATA:") + len("CONSTRAINTS_DATA:")
                    json_str = message[json_start:].strip()
                    constraints_data = json.loads(json_str)
                except Exception as e:
                    logger.error(f"Failed to parse constraints data: {e}")
            
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly3 '{assembly_name}' contains {len(constraints_data)} constraints:\n{json.dumps(constraints_data, indent=2)}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to list Assembly3 constraints: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to list Assembly3 constraints: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to list constraints: {str(e)}")
        ]


def delete_assembly3_constraint(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
    constraint_name: str,
) -> list[TextContent | ImageContent]:
    """Delete a constraint from Assembly3.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        constraint_name: Constraint object name to delete
        
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
    constraint = doc.getObject('{constraint_name}')
    
    if not assembly:
        print("ERROR: Assembly not found")
    elif not constraint:
        print("ERROR: Constraint not found")
    else:
        try:
            # Remove constraint from assembly group
            if constraint in assembly.Group:
                assembly.removeObject(constraint)
            
            # Delete the constraint object
            doc.removeObject(constraint.Name)
            
            doc.recompute()
            print(f"SUCCESS: Constraint '{{'{constraint_name}'}}' deleted")
        except Exception as e:
            print(f"ERROR: Failed to delete constraint: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Constraint '{constraint_name}' deleted from Assembly3 '{assembly_name}'"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to delete constraint: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to delete Assembly3 constraint: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to delete constraint: {str(e)}")
        ]


def modify_assembly3_constraint(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    constraint_name: str,
    properties: dict[str, Any],
) -> list[TextContent | ImageContent]:
    """Modify properties of an Assembly3 constraint.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        constraint_name: Constraint object name
        properties: Properties to modify (e.g., {"Distance": 10.0, "Enabled": False})
        
    Returns:
        List of text/image content with result
    """
    try:
        # Generate properties code
        props_code = ""
        for key, value in properties.items():
            if isinstance(value, str):
                props_code += f"\n            constraint.{key} = '{value}'"
            elif isinstance(value, bool):
                props_code += f"\n            constraint.{key} = {str(value)}"
            else:
                props_code += f"\n            constraint.{key} = {value}"
        
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document not found")
else:
    constraint = doc.getObject('{constraint_name}')
    
    if not constraint:
        print("ERROR: Constraint not found")
    else:
        try:
            # Modify properties{props_code}
            
            doc.recompute()
            print(f"SUCCESS: Constraint '{{constraint.Label}}' modified")
        except Exception as e:
            print(f"ERROR: Failed to modify constraint: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Constraint '{constraint_name}' modified: {properties}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to modify constraint: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to modify Assembly3 constraint: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to modify constraint: {str(e)}")
        ]










