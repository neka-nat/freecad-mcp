"""BOM (Bill of Materials) and Assembly Properties Manager - Phase 2 (2025-10-08)"""

import logging
import json
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.assembly_tools.bom_manager")


def generate_bom(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
    format: str = "json",
) -> list[TextContent | ImageContent]:
    """Generate a Bill of Materials (BOM) for an assembly.
    
    Counts parts, calculates masses, and generates a formatted BOM.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        format: Output format - "json", "csv", or "markdown" (default: "json")
        
    Returns:
        List of text/image content with BOM
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
            bom = {{}}
            
            # Parcourir toutes les pièces
            for obj in assembly.Group:
                if hasattr(obj, 'Shape') and obj.Shape.Volume > 0:
                    # Identifier la pièce (par label)
                    part_id = obj.Label
                    
                    # Initialiser si nouvelle pièce
                    if part_id not in bom:
                        bom[part_id] = {{
                            'name': part_id,
                            'type': obj.TypeId,
                            'quantity': 0,
                            'mass_kg': 0.0,
                            'volume_mm3': 0.0,
                            'material': 'Unknown',
                            'description': obj.Label
                        }}
                    
                    # Incrémenter quantité
                    bom[part_id]['quantity'] += 1
                    
                    # Ajouter volume
                    bom[part_id]['volume_mm3'] += float(obj.Shape.Volume)
                    
                    # Calculer masse si matériau défini
                    if hasattr(obj, 'Material'):
                        if hasattr(obj.Material, 'Density'):
                            density = obj.Material.Density  # kg/m³
                            volume_m3 = obj.Shape.Volume / 1e9
                            mass = volume_m3 * density
                            bom[part_id]['mass_kg'] += mass
                            
                            if hasattr(obj.Material, 'Name'):
                                bom[part_id]['material'] = obj.Material.Name
                            else:
                                bom[part_id]['material'] = 'Defined'
            
            # Convertir en liste
            bom_list = list(bom.values())
            
            # Trier par nom
            bom_list.sort(key=lambda x: x['name'])
            
            print(f"SUCCESS: BOM generated with {{len(bom_list)}} unique parts")
            print(f"BOM_DATA: {{json.dumps(bom_list)}}")
            
        except Exception as e:
            print(f"ERROR: Failed to generate BOM: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            message = res.get("message", "")
            
            # Extract BOM data
            bom_data = []
            if "BOM_DATA:" in message:
                try:
                    json_start = message.find("BOM_DATA:") + len("BOM_DATA:")
                    json_str = message[json_start:].strip()
                    bom_data = json.loads(json_str)
                except Exception as e:
                    logger.error(f"Failed to parse BOM data: {e}")
            
            # Format selon le format demandé
            if format == "json":
                formatted_bom = json.dumps(bom_data, indent=2)
            elif format == "csv":
                formatted_bom = generate_csv_format(bom_data)
            elif format == "markdown":
                formatted_bom = generate_markdown_format(bom_data)
            else:
                formatted_bom = json.dumps(bom_data, indent=2)
            
            response = [
                TextContent(
                    type="text",
                    text=f"BOM for '{assembly_name}' ({len(bom_data)} unique parts):\n\n{formatted_bom}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to generate BOM: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to generate BOM: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to generate BOM: {str(e)}")
        ]


def generate_csv_format(bom_data: list[dict]) -> str:
    """Generate CSV format from BOM data"""
    csv_lines = ["Name,Quantity,Type,Mass (kg),Volume (mm³),Material,Description"]
    
    for item in bom_data:
        csv_lines.append(
            f"{item['name']},{item['quantity']},{item['type']},"
            f"{item['mass_kg']:.3f},{item['volume_mm3']:.0f},"
            f"{item['material']},{item['description']}"
        )
    
    return "\n".join(csv_lines)


def generate_markdown_format(bom_data: list[dict]) -> str:
    """Generate Markdown table format from BOM data"""
    md_lines = [
        "| # | Name | Qty | Type | Mass (kg) | Volume (mm³) | Material |",
        "|---|------|-----|------|-----------|--------------|----------|"
    ]
    
    for idx, item in enumerate(bom_data, 1):
        md_lines.append(
            f"| {idx} | {item['name']} | {item['quantity']} | {item['type']} | "
            f"{item['mass_kg']:.3f} | {item['volume_mm3']:.0f} | {item['material']} |"
        )
    
    # Add total
    total_mass = sum(item['mass_kg'] for item in bom_data)
    total_volume = sum(item['volume_mm3'] for item in bom_data)
    md_lines.append(
        f"| **TOTAL** | | | | **{total_mass:.3f}** | **{total_volume:.0f}** | |"
    )
    
    return "\n".join(md_lines)


def get_assembly_properties(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """Get detailed properties of an assembly.
    
    Returns mass, center of gravity, bounding box, and other properties.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        List of text/image content with properties
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
            properties = {{
                'name': assembly.Name,
                'label': assembly.Label,
                'type': assembly.TypeId,
                'num_parts': 0,
                'num_constraints': 0,
                'num_lcs': 0,
                'total_mass_kg': 0.0,
                'total_volume_mm3': 0.0,
                'bounding_box': None,
                'center_of_gravity': None
            }}
            
            # Compter pièces, contraintes, LCS
            for obj in assembly.Group:
                if hasattr(obj, 'Shape') and obj.Shape.Volume > 0:
                    properties['num_parts'] += 1
                    properties['total_volume_mm3'] += float(obj.Shape.Volume)
                    
                    # Masse si matériau défini
                    if hasattr(obj, 'Material') and hasattr(obj.Material, 'Density'):
                        volume_m3 = obj.Shape.Volume / 1e9
                        mass = volume_m3 * obj.Material.Density
                        properties['total_mass_kg'] += mass
                
                elif 'Constraint' in obj.TypeId:
                    properties['num_constraints'] += 1
                elif obj.TypeId == 'PartDesign::CoordinateSystem':
                    properties['num_lcs'] += 1
            
            # Bounding box de l'assembly (si possible)
            try:
                if hasattr(assembly, 'Shape') and assembly.Shape:
                    bb = assembly.Shape.BoundBox
                    properties['bounding_box'] = {{
                        'x_min': float(bb.XMin),
                        'x_max': float(bb.XMax),
                        'y_min': float(bb.YMin),
                        'y_max': float(bb.YMax),
                        'z_min': float(bb.ZMin),
                        'z_max': float(bb.ZMax),
                        'x_length': float(bb.XLength),
                        'y_length': float(bb.YLength),
                        'z_length': float(bb.ZLength)
                    }}
                    
                    # Centre de masse
                    cog = assembly.Shape.CenterOfMass
                    properties['center_of_gravity'] = {{
                        'x': float(cog.x),
                        'y': float(cog.y),
                        'z': float(cog.z)
                    }}
            except Exception as e:
                print(f"WARNING: Could not compute shape properties: {{str(e)}}")
            
            print(f"SUCCESS: Assembly properties computed")
            print(f"PROPERTIES_DATA: {{json.dumps(properties)}}")
            
        except Exception as e:
            print(f"ERROR: Failed to get assembly properties: {{str(e)}}")
            import traceback
            print(f"TRACE: {{traceback.format_exc()}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            message = res.get("message", "")
            
            # Extract properties data
            properties_data = {}
            if "PROPERTIES_DATA:" in message:
                try:
                    json_start = message.find("PROPERTIES_DATA:") + len("PROPERTIES_DATA:")
                    json_str = message[json_start:].strip()
                    properties_data = json.loads(json_str)
                except Exception as e:
                    logger.error(f"Failed to parse properties data: {e}")
            
            response = [
                TextContent(
                    type="text",
                    text=f"Assembly '{assembly_name}' properties:\n{json.dumps(properties_data, indent=2)}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to get assembly properties: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to get assembly properties: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to get properties: {str(e)}")
        ]










