import logging
from typing import Any
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

logger = logging.getLogger("FreeCADMCPserver.sketch_tools.transform_manager")


def transform_object(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    obj_name: str,
    position: dict[str, float] | None = None,
    rotation: dict[str, Any] | None = None,
    relative: bool = False,
) -> list[TextContent | ImageContent]:
    """Transform an object with translation and/or rotation.
    
    This operation allows precise positioning and orientation of objects.
    Transformations can be absolute (set exact position/rotation) or 
    relative (add to current position/rotation).
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        obj_name: Name of the object to transform
        position: Position dict {"x": float, "y": float, "z": float} (optional)
        rotation: Rotation dict {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        relative: If True, transformation is relative to current placement
        
    Returns:
        List of text/image content with result
    """
    try:
        if position is None and rotation is None:
            return [
                TextContent(
                    type="text",
                    text="Error: At least position or rotation must be provided"
                )
            ]
        
        # Prepare position values
        has_position = position is not None
        if has_position:
            pos_x = position.get("x", 0)
            pos_y = position.get("y", 0)
            pos_z = position.get("z", 0)
        else:
            pos_x = pos_y = pos_z = 0
        
        # Prepare rotation values
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
    print("ERROR: Document '{doc_name}' not found")
else:
    obj = doc.getObject('{obj_name}')
    if not obj:
        print("ERROR: Object '{obj_name}' not found")
    else:
        if {relative}:
            # Transformation relative
            new_position = App.Vector({pos_x}, {pos_y}, {pos_z})
            new_rotation = App.Rotation(App.Vector({axis_x}, {axis_y}, {axis_z}), {angle})
            new_placement = App.Placement(new_position, new_rotation)
            obj.Placement = obj.Placement.multiply(new_placement)
            print(f"SUCCESS: Object '{{obj.Name}}' transformed relatively (pos: {{{has_position}}}, rot: {{{has_rotation}}})")
        else:
            # Transformation absolue
            if {has_position}:
                position = App.Vector({pos_x}, {pos_y}, {pos_z})
            else:
                position = obj.Placement.Base
            
            if {has_rotation}:
                rotation = App.Rotation(App.Vector({axis_x}, {axis_y}, {axis_z}), {angle})
            else:
                rotation = obj.Placement.Rotation
            
            obj.Placement = App.Placement(position, rotation)
            print(f"SUCCESS: Object '{{obj.Name}}' transformed absolutely (pos: {{{has_position}}}, rot: {{{has_rotation}}})")
        
        doc.recompute()
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            mode = "relatively" if relative else "absolutely"
            parts = []
            if has_position:
                parts.append(f"position ({pos_x}, {pos_y}, {pos_z})")
            if has_rotation:
                parts.append(f"rotation {angle}° around ({axis_x}, {axis_y}, {axis_z})")
            
            response = [
                TextContent(
                    type="text",
                    text=f"Object '{obj_name}' transformed {mode}: {', '.join(parts)}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to transform object: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to transform object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to transform object: {str(e)}")
        ]


def align_object(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    source_obj_name: str,
    target_obj_name: str,
    align_type: str = "both",
    offset: dict[str, float] | None = None,
) -> list[TextContent | ImageContent]:
    """Align one object to another (position, rotation, or both).
    
    This operation copies the placement (position and/or rotation) from 
    a target object to a source object, optionally with an offset.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        source_obj_name: Name of the object to move
        target_obj_name: Name of the reference object
        align_type: Type of alignment - "position", "rotation", or "both"
        offset: Optional offset dict {"x": float, "y": float, "z": float}
        
    Returns:
        List of text/image content with result
    """
    try:
        if align_type not in ["position", "rotation", "both"]:
            return [
                TextContent(
                    type="text",
                    text=f"Error: Invalid align_type '{align_type}'. Must be 'position', 'rotation', or 'both'"
                )
            ]
        
        has_offset = offset is not None
        offset_x = offset.get("x", 0) if has_offset else 0
        offset_y = offset.get("y", 0) if has_offset else 0
        offset_z = offset.get("z", 0) if has_offset else 0
        
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    source = doc.getObject('{source_obj_name}')
    target = doc.getObject('{target_obj_name}')
    
    if not source:
        print("ERROR: Source object '{source_obj_name}' not found")
    elif not target:
        print("ERROR: Target object '{target_obj_name}' not found")
    else:
        align_type = '{align_type}'
        
        if align_type in ['position', 'both']:
            # Copier la position
            source.Placement.Base = target.Placement.Base
            
            # Ajouter l'offset si présent
            if {has_offset}:
                offset = App.Vector({offset_x}, {offset_y}, {offset_z})
                source.Placement.Base = source.Placement.Base + offset
        
        if align_type in ['rotation', 'both']:
            # Copier la rotation
            source.Placement.Rotation = target.Placement.Rotation
        
        doc.recompute()
        offset_str = f" with offset ({{{offset_x}}}, {{{offset_y}}}, {{{offset_z}}})" if {has_offset} else ""
        print(f"SUCCESS: Object '{{source.Name}}' aligned to '{{target.Name}}' (type: {{align_type}}){{offset_str}}")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            offset_str = f" with offset ({offset_x}, {offset_y}, {offset_z})" if has_offset else ""
            response = [
                TextContent(
                    type="text",
                    text=f"Object '{source_obj_name}' aligned to '{target_obj_name}' ({align_type}){offset_str}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to align object: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to align object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to align object: {str(e)}")
        ]


def attach_to_face(
    ctx: Context,
    freecad_connection: Any,
    add_screenshot_helper: Any,
    doc_name: str,
    obj_name: str,
    target_obj_name: str,
    face_name: str,
    map_mode: str = "FlatFace",
    offset: dict[str, float] | None = None,
) -> list[TextContent | ImageContent]:
    """Attach an object to a face of another object.
    
    This operation attaches an object to a specific face of a target object,
    using FreeCAD's attachment system or positioning it at the face center.
    
    Args:
        ctx: MCP context
        freecad_connection: FreeCAD connection instance
        add_screenshot_helper: Helper function to add screenshots
        doc_name: Document name
        obj_name: Name of the object to attach
        target_obj_name: Name of the target face owner
        face_name: Face name (e.g., "Face1", "Face2", etc.)
        map_mode: Attachment mode - "FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"
        offset: Optional offset dict {"x": float, "y": float, "z": float}
        
    Returns:
        List of text/image content with result
    """
    try:
        valid_modes = ["FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"]
        if map_mode not in valid_modes:
            return [
                TextContent(
                    type="text",
                    text=f"Warning: MapMode '{map_mode}' might not be valid. Valid modes: {', '.join(valid_modes)}"
                )
            ]
        
        has_offset = offset is not None
        offset_x = offset.get("x", 0) if has_offset else 0
        offset_y = offset.get("y", 0) if has_offset else 0
        offset_z = offset.get("z", 0) if has_offset else 0
        
        code = f"""
import FreeCAD as App

doc = App.getDocument('{doc_name}')
if not doc:
    print("ERROR: Document '{doc_name}' not found")
else:
    obj = doc.getObject('{obj_name}')
    target = doc.getObject('{target_obj_name}')
    
    if not obj:
        print("ERROR: Object '{obj_name}' not found")
    elif not target:
        print("ERROR: Target object '{target_obj_name}' not found")
    else:
        # Vérifier si l'objet supporte l'attachement
        if hasattr(obj, 'Support') and hasattr(obj, 'MapMode'):
            # Méthode 1 : Attachement natif
            obj.Support = [(target, '{face_name}')]
            obj.MapMode = '{map_mode}'
            
            # Ajouter offset si présent
            if {has_offset} and hasattr(obj, 'AttachmentOffset'):
                offset = App.Placement(App.Vector({offset_x}, {offset_y}, {offset_z}), App.Rotation())
                obj.AttachmentOffset = offset
            
            doc.recompute()
            offset_str = f" with offset ({{{offset_x}}}, {{{offset_y}}}, {{{offset_z}}})" if {has_offset} else ""
            print(f"SUCCESS: Object '{{obj.Name}}' attached to '{{target.Name}}.{face_name}' (mode: {map_mode}){{offset_str}}")
        else:
            # Méthode 2 : Fallback - positionner manuellement sur la face
            print(f"INFO: Object '{{obj.Name}}' doesn't support native attachment, using fallback positioning")
            
            # Obtenir la face
            face_obj = None
            face_index = int('{face_name}'.replace('Face', '')) - 1 if '{face_name}'.startswith('Face') else -1
            
            if face_index >= 0 and hasattr(target, 'Shape') and face_index < len(target.Shape.Faces):
                face_obj = target.Shape.Faces[face_index]
                
                # Obtenir le centre de la face
                center = face_obj.CenterOfMass
                
                # Positionner l'objet au centre de la face
                obj.Placement.Base = center
                
                # Ajouter offset si présent
                if {has_offset}:
                    offset = App.Vector({offset_x}, {offset_y}, {offset_z})
                    obj.Placement.Base = obj.Placement.Base + offset
                
                doc.recompute()
                offset_str = f" with offset ({{{offset_x}}}, {{{offset_y}}}, {{{offset_z}}})" if {has_offset} else ""
                print(f"SUCCESS: Object '{{obj.Name}}' positioned on '{{target.Name}}.{face_name}' center{{offset_str}}")
            else:
                print("ERROR: Face '{face_name}' not found on target object")
"""
        
        res = freecad_connection.execute_code(code)
        screenshot = freecad_connection.get_active_screenshot()
        
        if res.get("success") and "SUCCESS:" in res.get("message", ""):
            offset_str = f" with offset ({offset_x}, {offset_y}, {offset_z})" if has_offset else ""
            response = [
                TextContent(
                    type="text",
                    text=f"Object '{obj_name}' attached to '{target_obj_name}.{face_name}'{offset_str}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
        else:
            error_msg = res.get("message", res.get("error", "Unknown error"))
            response = [
                TextContent(
                    type="text",
                    text=f"Failed to attach object: {error_msg}"
                )
            ]
            return add_screenshot_helper(response, screenshot)
            
    except Exception as e:
        logger.error(f"Failed to attach object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to attach object: {str(e)}")
        ]










