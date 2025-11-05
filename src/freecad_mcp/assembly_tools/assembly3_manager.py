import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.assembly_tools.assembly3_manager")


def create_assembly3(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str = "Assembly",
) -> list[TextContent | ImageContent]:
    """Create a new Assembly3 object.
    
    Assembly3 uses constraint-based assembly with automatic solver.
    
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
        # Create Assembly3 object
        assembly = doc.addObject("Assembly::AssemblyObject", "{assembly_name}")
        doc.recompute()
        print(f"SUCCESS: Assembly3 '{{assembly.Name}}' created successfully")
    except Exception as e:
        print(f"ERROR: Failed to create Assembly3: {{str(e)}}")
        print("INFO: Make sure Assembly3 workbench is installed")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly3 '{assembly_name}' created successfully"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to create Assembly3: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to create Assembly3: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create Assembly3: {str(e)}")
        ]


def add_part_to_assembly3(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
    part_file: str | None = None,
    part_object: str | None = None,
    part_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Add a part to an Assembly3.
    
    Can import from external file or use existing object in document.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        part_file: Path to external part file (optional)
        part_object: Existing object name in document (optional)
        part_name: Name for the imported part (optional)
        
    Returns:
        List of text/image content with result
    """
    try:
        if not part_file and not part_object:
            return [
                TextContent(
                    type="text",
                    text="Error: Either part_file or part_object must be provided"
                )
            ]
        
        if part_file:
            # Import external part
            part_file_escaped = part_file.replace("\\", "\\\\")
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
            # Import part from file
            part_name = '{part_name}' if '{part_name}' else None
            imported = assembly.importPart("{part_file_escaped}", part_name)
            doc.recompute()
            print(f"SUCCESS: Part imported from file")
        except Exception as e:
            print(f"ERROR: Failed to import part: {{str(e)}}")
"""
        else:
            # Use existing object
            code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document not found")
else:
    assembly = doc.getObject('{assembly_name}')
    part = doc.getObject('{part_object}')
    
    if not assembly:
        print("ERROR: Assembly not found")
    elif not part:
        print("ERROR: Part object '{part_object}' not found")
    else:
        try:
            assembly.addObject(part)
            doc.recompute()
            print(f"SUCCESS: Part '{{part.Name}}' added to assembly")
        except Exception as e:
            print(f"ERROR: Failed to add part: {{str(e)}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            source = f"file '{part_file}'" if part_file else f"object '{part_object}'"
            response = [
                TextContent(
                    type="text",
                    text=f"Part added to Assembly3 from {source}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to add part: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to add part to Assembly3: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to add part: {str(e)}")
        ]


def add_assembly3_constraint(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
    constraint_type: str,
    references: list[dict[str, str]],
    constraint_name: str | None = None,
    properties: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Add a constraint to Assembly3.
    
    Supported constraint types:
    - PlaneCoincident: Align two planar faces
    - Axial: Align two cylindrical axes
    - PointsCoincident: Make two points coincident
    - PointOnLine: Point on an edge
    - PointOnPlane: Point on a plane
    - SameOrientation: Same orientation for two faces
    - MultiParallel: Make elements parallel
    - Angle: Fixed angle between elements
    - Distance: Fixed distance
    - Lock: Lock object in place
    - Perpendicular: Perpendicular elements
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        constraint_type: Type of constraint
        references: List of {"object": "PartName", "element": "Face1"}
        constraint_name: Optional constraint name
        properties: Optional properties (Angle, Distance, etc.)
        
    Returns:
        List of text/image content with result
    """
    try:
        # Generate references code
        refs_code = []
        for ref in references:
            obj_name = ref.get("object", "")
            element = ref.get("element", "")
            refs_code.append(f"(doc.getObject('{obj_name}'), '{element}')")
        
        refs_str = "[" + ", ".join(refs_code) + "]"
        
        # Generate properties code if present
        props_code = ""
        if properties:
            for key, value in properties.items():
                if isinstance(value, str):
                    props_code += f"\n        constraint.{key} = '{value}'"
                else:
                    props_code += f"\n        constraint.{key} = {value}"
        
        constraint_name_str = constraint_name if constraint_name else f"{constraint_type}_auto"
        
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
            # Create constraint using Assembly3 API
            # Assembly3 uses 'asm3::Constraint<Type>' format (lowercase asm3)
            constraint_obj_type = 'asm3::Constraint{constraint_type}'
            constraint = doc.addObject(constraint_obj_type, '{constraint_name_str}')
            
            if constraint:
                # Add constraint to assembly group
                assembly.addObject(constraint)
                
                # Set constraint label
                constraint.Label = '{constraint_name_str}'
                
                # Set references (list of tuples: (object, subelement))
                constraint.References = {refs_str}{props_code}
                
                doc.recompute()
                print(f"SUCCESS: Constraint '{{constraint.Label}}' of type '{constraint_type}' added")
            else:
                print("ERROR: Failed to create constraint object")
        except Exception as e:
            print(f"ERROR: Failed to add constraint: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Constraint '{constraint_type}' added to Assembly3"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to add constraint: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to add Assembly3 constraint: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to add constraint: {str(e)}")
        ]


def solve_assembly3(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """Solve the Assembly3 constraints.
    
    This updates all part positions based on the defined constraints.
    
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
            # Solve the assembly
            assembly.solve()
            doc.recompute()
            print(f"SUCCESS: Assembly3 '{{assembly.Name}}' solved successfully")
        except Exception as e:
            print(f"ERROR: Failed to solve assembly: {{str(e)}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly3 '{assembly_name}' solved successfully"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to solve Assembly3: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to solve Assembly3: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to solve Assembly3: {str(e)}")
        ]

