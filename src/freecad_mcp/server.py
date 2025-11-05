import json
import logging
import xmlrpc.client
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, Literal

from mcp.server.fastmcp import FastMCP, Context
from mcp.types import TextContent, ImageContent
# Advanced modeling implementations
from .modeling_tools import (
    create_loft as _create_loft,
    create_revolve as _create_revolve,
    create_sweep as _create_sweep,
    create_spline_3d as _create_spline_3d,
)

# Advanced modeling Phase 3-5: Corsair features (2025-10-08)
from .modeling_tools_advanced import (
    add_fillet as _add_fillet,
    add_chamfer as _add_chamfer,
    shell_object as _shell_object,
    mirror_object as _mirror_object,
    circular_pattern as _circular_pattern,
    linear_pattern as _linear_pattern,
    create_reference_plane as _create_reference_plane,
    create_reference_axis as _create_reference_axis,
    import_airfoil_profile as _import_airfoil_profile,
    import_dxf as _import_dxf,
)

# Import new sketch workflow tools (2025-10-08)
from .sketch_tools.plane_manager import create_datum_plane as _create_datum_plane
from .sketch_tools.sketch_manager import create_sketch_on_plane as _create_sketch_on_plane
from .sketch_tools.contour_builder import add_contour_to_sketch as _add_contour_to_sketch
from .sketch_tools.extrude_manager import extrude_sketch_bidirectional as _extrude_sketch_bidirectional
from .sketch_tools.attachment_manager import attach_solid_to_plane as _attach_solid_to_plane
from .prompts.sketch_strategy import sketch_workflow_strategy

# Import boolean operations (2025-10-08)
from .sketch_tools.boolean_operations import (
    boolean_union as _boolean_union,
    boolean_cut as _boolean_cut,
    boolean_intersection as _boolean_intersection,
    boolean_common as _boolean_common,
)
from .prompts.boolean_strategy import boolean_operations_strategy
from .prompts.assembly_strategy import assembly_strategy

# Import transform and alignment tools (2025-10-08)
from .sketch_tools.transform_manager import (
    transform_object as _transform_object,
    align_object as _align_object,
    attach_to_face as _attach_to_face,
)

# Import assembly tools (2025-10-08)
from .assembly_tools.assembly3_manager import (
    create_assembly3 as _create_assembly3,
    add_part_to_assembly3 as _add_part_to_assembly3,
    add_assembly3_constraint as _add_assembly3_constraint,
    solve_assembly3 as _solve_assembly3,
)
from .assembly_tools.assembly4_manager import (
    create_assembly4 as _create_assembly4,
    create_lcs_assembly4 as _create_lcs_assembly4,
    insert_part_assembly4 as _insert_part_assembly4,
    attach_lcs_to_geometry as _attach_lcs_to_geometry,
)
from .assembly_tools.assembly_common import (
    list_assembly_parts as _list_assembly_parts,
    export_assembly as _export_assembly,
    calculate_assembly_mass as _calculate_assembly_mass,
)
# Import assembly Phase 2 - Advanced (2025-10-08)
from .assembly_tools.assembly3_advanced import (
    list_assembly3_constraints as _list_assembly3_constraints,
    delete_assembly3_constraint as _delete_assembly3_constraint,
    modify_assembly3_constraint as _modify_assembly3_constraint,
)
from .assembly_tools.assembly4_advanced import (
    list_assembly4_lcs as _list_assembly4_lcs,
    delete_lcs_assembly4 as _delete_lcs_assembly4,
    modify_lcs_assembly4 as _modify_lcs_assembly4,
)
from .assembly_tools.bom_manager import (
    generate_bom as _generate_bom,
    get_assembly_properties as _get_assembly_properties,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FreeCADMCPserver")


_only_text_feedback = False


class FreeCADConnection:
    def __init__(self, host: str = "localhost", port: int = 9875):
        self.server = xmlrpc.client.ServerProxy(f"http://{host}:{port}", allow_none=True)

    def ping(self) -> bool:
        return self.server.ping()

    def create_document(self, name: str) -> dict[str, Any]:
        return self.server.create_document(name)

    def create_object(self, doc_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.create_object(doc_name, obj_data)

    def edit_object(self, doc_name: str, obj_name: str, obj_data: dict[str, Any]) -> dict[str, Any]:
        return self.server.edit_object(doc_name, obj_name, obj_data)

    def delete_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.delete_object(doc_name, obj_name)

    def insert_part_from_library(self, relative_path: str) -> dict[str, Any]:
        return self.server.insert_part_from_library(relative_path)

    def execute_code(self, code: str) -> dict[str, Any]:
        return self.server.execute_code(code)

    def get_active_screenshot(self, view_name: str = "Isometric") -> str | None:
        try:
            # Check if we're in a view that supports screenshots
            result = self.server.execute_code("""
import FreeCAD
import FreeCADGui

if FreeCAD.Gui.ActiveDocument and FreeCAD.Gui.ActiveDocument.ActiveView:
    view_type = type(FreeCAD.Gui.ActiveDocument.ActiveView).__name__
    
    # These view types don't support screenshots
    unsupported_views = ['SpreadsheetGui::SheetView', 'DrawingGui::DrawingView', 'TechDrawGui::MDIViewPage']
    
    if view_type in unsupported_views or not hasattr(FreeCAD.Gui.ActiveDocument.ActiveView, 'saveImage'):
        print("Current view does not support screenshots")
        False
    else:
        print(f"Current view supports screenshots: {view_type}")
        True
else:
    print("No active view")
    False
""")

            # If the view doesn't support screenshots, return None
            if not result.get("success", False) or "Current view does not support screenshots" in result.get("message", ""):
                logger.info("Screenshot unavailable in current view (likely Spreadsheet or TechDraw view)")
                return None

            # Otherwise, try to get the screenshot
            return self.server.get_active_screenshot(view_name)
        except Exception as e:
            # Log the error but return None instead of raising an exception
            logger.error(f"Error getting screenshot: {e}")
            return None

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return self.server.get_objects(doc_name)

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.get_object(doc_name, obj_name)

    def get_parts_list(self) -> list[str]:
        return self.server.get_parts_list()


@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    try:
        logger.info("FreeCADMCP server starting up")
        try:
            _ = get_freecad_connection()
            logger.info("Successfully connected to FreeCAD on startup")
        except Exception as e:
            logger.warning(f"Could not connect to FreeCAD on startup: {str(e)}")
            logger.warning(
                "Make sure the FreeCAD addon is running before using FreeCAD resources or tools"
            )
        yield {}
    finally:
        # Clean up the global connection on shutdown
        global _freecad_connection
        if _freecad_connection:
            logger.info("Disconnecting from FreeCAD on shutdown")
            _freecad_connection.disconnect()
            _freecad_connection = None
        logger.info("FreeCADMCP server shut down")


mcp = FastMCP(
    "FreeCADMCP",
    instructions="FreeCAD integration through the Model Context Protocol",
    lifespan=server_lifespan,
)


_freecad_connection: FreeCADConnection | None = None


def get_freecad_connection():
    """Get or create a persistent FreeCAD connection"""
    global _freecad_connection
    if _freecad_connection is None:
        # Always attempt to connect; skip ping to avoid disconnects
        _freecad_connection = FreeCADConnection(host="localhost", port=9875)
    return _freecad_connection


# Helper function to safely add screenshot to response
def add_screenshot_if_available(response, screenshot):
    """Safely add screenshot to response only if it's available"""
    if screenshot is not None and not _only_text_feedback:
        response.append(ImageContent(type="image", data=screenshot, mimeType="image/png"))
    elif not _only_text_feedback:
        # Add an informative message that will be seen by the AI model and user
        response.append(TextContent(
            type="text", 
            text="Note: Visual preview is unavailable in the current view type (such as TechDraw or Spreadsheet). "
                 "Switch to a 3D view to see visual feedback."
        ))
    return response


@mcp.tool()
def create_document(ctx: Context, name: str) -> list[TextContent]:
    """Create a new document in FreeCAD.

    Args:
        name: The name of the document to create.

    Returns:
        A message indicating the success or failure of the document creation.

    Examples:
        If you want to create a document named "MyDocument", you can use the following data.
        ```json
        {
            "name": "MyDocument"
        }
        ```
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.create_document(name)
        if res["success"]:
            return [
                TextContent(type="text", text=f"Document '{res['document_name']}' created successfully")
            ]
        else:
            return [
                TextContent(type="text", text=f"Failed to create document: {res['error']}")
            ]
    except Exception as e:
        logger.error(f"Failed to create document: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create document: {str(e)}")
        ]


@mcp.tool()
def create_object(
    ctx: Context,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] = None,
) -> list[TextContent | ImageContent]:
    """Create a new object in FreeCAD.
    Object type is starts with "Part::" or "Draft::" or "PartDesign::" or "Fem::".

    Args:
        doc_name: The name of the document to create the object in.
        obj_type: The type of the object to create (e.g. 'Part::Box', 'Part::Cylinder', 'Draft::Circle', 'PartDesign::Body', etc.).
        obj_name: The name of the object to create.
        obj_properties: The properties of the object to create.

    Returns:
        A message indicating the success or failure of the object creation and a screenshot of the object.

    Examples:
        If you want to create a cylinder with a height of 30 and a radius of 10, you can use the following data.
        ```json
        {
            "doc_name": "MyCylinder",
            "obj_name": "Cylinder",
            "obj_type": "Part::Cylinder",
            "obj_properties": {
                "Height": 30,
                "Radius": 10,
                "Placement": {
                    "Base": {
                        "x": 10,
                        "y": 10,
                        "z": 0
                    },
                    "Rotation": {
                        "Axis": {
                            "x": 0,
                            "y": 0,
                            "z": 1
                        },
                        "Angle": 45
                    }
                },
                "ViewObject": {
                    "ShapeColor": [0.5, 0.5, 0.5, 1.0]
                }
            }
        }
        ```

        If you want to create a circle with a radius of 10, you can use the following data.
        ```json
        {
            "doc_name": "MyCircle",
            "obj_name": "Circle",
            "obj_type": "Draft::Circle",
        }
        ```

        If you want to create a FEM analysis, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMAnalysis",
            "obj_name": "FemAnalysis",
            "obj_type": "Fem::AnalysisPython",
        }
        ```

        If you want to create a FEM constraint, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMConstraint",
            "obj_name": "FemConstraint",
            "obj_type": "Fem::ConstraintFixed",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "References": [
                    {
                        "object_name": "MyObject",
                        "face": "Face1"
                    }
                ]
            }
        }
        ```

        If you want to create a FEM mechanical material, you can use the following data.
        ```json
        {
            "doc_name": "MyFEMAnalysis",
            "obj_name": "FemMechanicalMaterial",
            "obj_type": "Fem::MaterialCommon",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Material": {
                    "Name": "MyMaterial",
                    "Density": "7900 kg/m^3",
                    "YoungModulus": "210 GPa",
                    "PoissonRatio": 0.3
                }
            }
        }
        ```

        If you want to create a FEM mesh, you can use the following data.
        The `Part` property is required.
        ```json
        {
            "doc_name": "MyFEMMesh",
            "obj_name": "FemMesh",
            "obj_type": "Fem::FemMeshGmsh",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Part": "MyObject",
                "ElementSizeMax": 10,
                "ElementSizeMin": 0.1,
                "MeshAlgorithm": 2
            }
        }
        ```
    """
    freecad = get_freecad_connection()
    try:
        obj_data = {"Name": obj_name, "Type": obj_type, "Properties": obj_properties or {}, "Analysis": analysis_name}
        res = freecad.create_object(doc_name, obj_data)
        screenshot = freecad.get_active_screenshot()
        
        if res["success"]:
            response = [
                TextContent(type="text", text=f"Object '{res['object_name']}' created successfully"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to create object: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to create object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to create object: {str(e)}")
        ]


@mcp.tool()
def edit_object(
    ctx: Context, doc_name: str, obj_name: str, obj_properties: dict[str, Any]
) -> list[TextContent | ImageContent]:
    """Edit an object in FreeCAD.
    This tool is used when the `create_object` tool cannot handle the object creation.

    Args:
        doc_name: The name of the document to edit the object in.
        obj_name: The name of the object to edit.
        obj_properties: The properties of the object to edit.

    Returns:
        A message indicating the success or failure of the object editing and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.edit_object(doc_name, obj_name, {"Properties": obj_properties})
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = [
                TextContent(type="text", text=f"Object '{res['object_name']}' edited successfully"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to edit object: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to edit object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to edit object: {str(e)}")
        ]


@mcp.tool()
def delete_object(ctx: Context, doc_name: str, obj_name: str) -> list[TextContent | ImageContent]:
    """Delete an object in FreeCAD.

    Args:
        doc_name: The name of the document to delete the object from.
        obj_name: The name of the object to delete.

    Returns:
        A message indicating the success or failure of the object deletion and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.delete_object(doc_name, obj_name)
        screenshot = freecad.get_active_screenshot()
        
        if res["success"]:
            response = [
                TextContent(type="text", text=f"Object '{res['object_name']}' deleted successfully"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to delete object: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to delete object: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to delete object: {str(e)}")
        ]


@mcp.tool()
def execute_code(ctx: Context, code: str) -> list[TextContent | ImageContent]:
    """Execute arbitrary Python code in FreeCAD.

    Args:
        code: The Python code to execute.

    Returns:
        A message indicating the success or failure of the code execution, the output of the code execution, and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.execute_code(code)
        screenshot = freecad.get_active_screenshot()
        
        if res["success"]:
            response = [
                TextContent(type="text", text=f"Code executed successfully: {res['message']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to execute code: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to execute code: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to execute code: {str(e)}")
        ]


@mcp.tool()
def get_view(ctx: Context, view_name: Literal["Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"]) -> list[ImageContent | TextContent]:
    """Get a screenshot of the active view.

    Args:
        view_name: The name of the view to get the screenshot of.
        The following views are available:
        - "Isometric"
        - "Front"
        - "Top"
        - "Right"
        - "Back"
        - "Left"
        - "Bottom"
        - "Dimetric"
        - "Trimetric"

    Returns:
        A screenshot of the active view.
    """
    freecad = get_freecad_connection()
    screenshot = freecad.get_active_screenshot(view_name)
    
    if screenshot is not None:
        return [ImageContent(type="image", data=screenshot, mimeType="image/png")]
    else:
        return [TextContent(type="text", text="Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)")]


@mcp.tool()
def insert_part_from_library(ctx: Context, relative_path: str) -> list[TextContent | ImageContent]:
    """Insert a part from the parts library addon.

    Args:
        relative_path: The relative path of the part to insert.

    Returns:
        A message indicating the success or failure of the part insertion and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        res = freecad.insert_part_from_library(relative_path)
        screenshot = freecad.get_active_screenshot()
        
        if res["success"]:
            response = [
                TextContent(type="text", text=f"Part inserted from library: {res['message']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
        else:
            response = [
                TextContent(type="text", text=f"Failed to insert part from library: {res['error']}"),
            ]
            return add_screenshot_if_available(response, screenshot)
    except Exception as e:
        logger.error(f"Failed to insert part from library: {str(e)}")
        return [
            TextContent(type="text", text=f"Failed to insert part from library: {str(e)}")
        ]


@mcp.tool()
def get_objects(ctx: Context, doc_name: str) -> list[dict[str, Any]]:
    """Get all objects in a document.
    You can use this tool to get the objects in a document to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the objects from.

    Returns:
        A list of objects in the document and a screenshot of the document.
    """
    freecad = get_freecad_connection()
    try:
        return freecad.get_objects(doc_name)
    except Exception as e:
        logger.error(f"Failed to get objects: {str(e)}")
        return []


@mcp.tool()
def get_object(ctx: Context, doc_name: str, obj_name: str) -> dict[str, Any]:
    """Get an object from a document.
    You can use this tool to get the properties of an object to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the object from.
        obj_name: The name of the object to get.

    Returns:
        The object and a screenshot of the object.
    """
    freecad = get_freecad_connection()
    try:
        return freecad.get_object(doc_name, obj_name)
    except Exception as e:
        logger.error(f"Failed to get object: {str(e)}")
        return {"error": str(e)}


@mcp.tool()
def get_parts_list(ctx: Context) -> list[str]:
    """Get the list of parts in the parts library addon.
    """
    freecad = get_freecad_connection()
    parts = freecad.get_parts_list()
    return parts or []


@mcp.tool()
def create_datum_plane_tool(
    ctx: Context,
    doc_name: str,
    plane_name: str,
    alignment: str = "xy",
    offset: float = 0.0,
) -> list[TextContent | ImageContent]:
    """Create a datum plane aligned with XY, XZ, or YZ coordinate system.
    
    This creates a reference plane (Body with Origin) that serves as the foundation for sketching.
    The plane name will be used as the base for related objects (sketch, solid).
    
    Args:
        doc_name: Document name
        plane_name: Name for the datum plane (e.g., 'base_plane', 'side_plane')
        alignment: Plane alignment - 'xy', 'xz', or 'yz' (default: 'xy')
        offset: Offset distance from origin (default: 0.0)
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "plane_name": "base_plane",
            "alignment": "xy",
            "offset": 0.0
        }
    """
    freecad = get_freecad_connection()
    return _create_datum_plane(ctx, freecad, add_screenshot_if_available, doc_name, plane_name, alignment, offset)


@mcp.tool()
def create_sketch_on_plane_tool(
    ctx: Context,
    doc_name: str,
    plane_name: str,
) -> list[TextContent | ImageContent]:
    """Create a sketch attached to a datum plane.
    
    The sketch is automatically named as '{plane_name}_sketch'.
    This sketch inherits the coordinate system from the datum plane.
    
    Args:
        doc_name: Document name
        plane_name: Name of the datum plane (Body) to attach the sketch to
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "plane_name": "base_plane"
        }
        
        This creates: "base_plane_sketch"
    """
    freecad = get_freecad_connection()
    return _create_sketch_on_plane(ctx, freecad, add_screenshot_if_available, doc_name, plane_name)


@mcp.tool()
def add_contour_to_sketch_tool(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geometry_elements: list[dict[str, Any]],
    constraints: list[dict[str, Any]] | None = None,
    fix_first_point_to_origin: bool = True,
) -> list[TextContent | ImageContent]:
    """Add geometric contour elements and constraints to a sketch.
    
    Supported geometry types:
    - point: {"type": "point", "x": float, "y": float}
    - line: {"type": "line", "start": {"x": float, "y": float}, "end": {"x": float, "y": float}}
    - arc: {"type": "arc", "center": {"x": float, "y": float}, "radius": float, "start_angle": float, "end_angle": float}
    - circle: {"type": "circle", "center": {"x": float, "y": float}, "radius": float}
    - bspline: {"type": "bspline", "points": [{"x": float, "y": float}, ...], "degree": int, "closed": bool}
    - ellipse: {"type": "ellipse", "center": {"x": float, "y": float}, "major_radius": float, "minor_radius": float, "angle": float}
    
    Supported constraints:
    - coincident: {"type": "coincident", "geo1": int, "point1": int, "geo2": int, "point2": int}
    - tangent: {"type": "tangent", "geo1": int, "geo2": int}
    - distance: {"type": "distance", "geo1": int, "point1": int, "geo2": int, "point2": int, "value": float}
    - horizontal: {"type": "horizontal", "geo": int}
    - vertical: {"type": "vertical", "geo": int}
    - angle: {"type": "angle", "geo1": int, "geo2": int, "value": float}
    - fix: {"type": "fix", "geo": int, "point": int}
    
    Args:
        doc_name: Document name
        sketch_name: Sketch name
        geometry_elements: List of geometry elements to add
        constraints: List of constraints to apply (optional)
        fix_first_point_to_origin: If True, fixes the first point to sketch origin (default: True)
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "sketch_name": "base_plane_sketch",
            "geometry_elements": [
                {"type": "line", "start": {"x": 0, "y": 0}, "end": {"x": 100, "y": 0}},
                {"type": "arc", "center": {"x": 100, "y": 50}, "radius": 50, "start_angle": 270, "end_angle": 0},
                {"type": "line", "start": {"x": 100, "y": 100}, "end": {"x": 0, "y": 100}}
            ],
            "constraints": [
                {"type": "coincident", "geo1": 0, "point1": 2, "geo2": 1, "point2": 1},
                {"type": "tangent", "geo1": 0, "geo2": 1}
            ],
            "fix_first_point_to_origin": true
        }
    """
    freecad = get_freecad_connection()
    return _add_contour_to_sketch(ctx, freecad, add_screenshot_if_available, doc_name, sketch_name, geometry_elements, constraints, fix_first_point_to_origin)


@mcp.tool()
def extrude_sketch_bidirectional_tool(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    length_forward: float,
    length_backward: float = 0.0,
    use_midplane: bool = False,
) -> list[TextContent | ImageContent]:
    """Extrude a sketch bidirectionally to create a 3D solid.
    
    The solid is automatically named by replacing '_sketch' with '_solid' in the sketch name.
    Can extrude in both directions (forward and backward) from the sketch plane.
    
    Args:
        doc_name: Document name
        sketch_name: Sketch name to extrude
        length_forward: Extrusion length in the forward direction (normal to sketch)
        length_backward: Extrusion length in the backward direction (default: 0.0)
        use_midplane: If True, extrude symmetrically (default: False)
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "sketch_name": "base_plane_sketch",
            "length_forward": 50.0,
            "length_backward": 25.0,
            "use_midplane": false
        }
        
        This creates: "base_plane_solid"
    """
    freecad = get_freecad_connection()
    return _extrude_sketch_bidirectional(ctx, freecad, add_screenshot_if_available, doc_name, sketch_name, length_forward, length_backward, use_midplane)


@mcp.tool()
def attach_solid_to_plane_tool(
    ctx: Context,
    doc_name: str,
    solid_body_name: str,
    target_plane_name: str,
    align_origin: bool = True,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    offset_z: float = 0.0,
    rotation_angle: float = 0.0,
    rotation_axis: str = "z",
) -> list[TextContent | ImageContent]:
    """Attach (position) a solid body to align with another datum plane.
    
    This positions a solid body so that its base plane aligns with a target plane.
    Useful for creating assemblies and positioning parts relative to each other.
    
    Args:
        doc_name: Document name
        solid_body_name: Name of the Body containing the solid to position
        target_plane_name: Name of the target datum plane (Body) to align with
        align_origin: If True, align the origins of the planes (default: True)
        offset_x: X offset from target plane origin (default: 0.0)
        offset_y: Y offset from target plane origin (default: 0.0)
        offset_z: Z offset from target plane origin (default: 0.0)
        rotation_angle: Rotation angle in degrees (default: 0.0)
        rotation_axis: Rotation axis - 'x', 'y', or 'z' (default: 'z')
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "solid_body_name": "base_plane",
            "target_plane_name": "mounting_plane",
            "align_origin": true,
            "offset_x": 0.0,
            "offset_y": 0.0,
            "offset_z": 10.0,
            "rotation_angle": 90.0,
            "rotation_axis": "z"
        }
    """
    freecad = get_freecad_connection()
    return _attach_solid_to_plane(ctx, freecad, add_screenshot_if_available, doc_name, solid_body_name, target_plane_name, align_origin, offset_x, offset_y, offset_z, rotation_angle, rotation_axis)


@mcp.tool()
def boolean_union_tool(
    ctx: Context,
    doc_name: str,
    base_object_name: str,
    tool_object_names: list[str],
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Fuse multiple solids into one using Boolean Union operation.
    
    This operation merges the base object with one or more tool objects,
    creating a single unified solid. The source objects are hidden by default.
    
    Args:
        doc_name: Document name
        base_object_name: Name of the base object
        tool_object_names: List of object names to fuse with the base
        result_name: Name for the result (default: base_object_name + "_union")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "base_object_name": "base_plane_solid",
            "tool_object_names": ["side_plane_solid", "top_plane_solid"],
            "result_name": "assembled_part"
        }
    """
    freecad = get_freecad_connection()
    return _boolean_union(ctx, freecad, add_screenshot_if_available, doc_name, base_object_name, tool_object_names, result_name)


@mcp.tool()
def boolean_cut_tool(
    ctx: Context,
    doc_name: str,
    base_object_name: str,
    tool_object_name: str,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Subtract one solid from another using Boolean Cut operation.
    
    This operation removes the volume of the tool object from the base object,
    useful for creating holes, pockets, and cutouts. The source objects are hidden by default.
    
    Args:
        doc_name: Document name
        base_object_name: Name of the base object (what remains)
        tool_object_name: Name of the tool object (what is subtracted)
        result_name: Name for the result (default: base_object_name + "_cut")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "base_object_name": "base_plane_solid",
            "tool_object_name": "hole_solid",
            "result_name": "part_with_hole"
        }
    """
    freecad = get_freecad_connection()
    return _boolean_cut(ctx, freecad, add_screenshot_if_available, doc_name, base_object_name, tool_object_name, result_name)


@mcp.tool()
def boolean_intersection_tool(
    ctx: Context,
    doc_name: str,
    object1_name: str,
    object2_name: str,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Keep only the common volume between two solids using Boolean Intersection.
    
    This operation creates a new solid containing only the volume that is common
    to both input objects. The source objects are hidden by default.
    
    Args:
        doc_name: Document name
        object1_name: Name of the first object
        object2_name: Name of the second object
        result_name: Name for the result (default: object1_name + "_intersection")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "object1_name": "sphere_solid",
            "object2_name": "cube_solid",
            "result_name": "sphere_cube_common"
        }
    """
    freecad = get_freecad_connection()
    return _boolean_intersection(ctx, freecad, add_screenshot_if_available, doc_name, object1_name, object2_name, result_name)


@mcp.tool()
def boolean_common_tool(
    ctx: Context,
    doc_name: str,
    object1_name: str,
    object2_name: str,
    result_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Alias of boolean_intersection_tool for FreeCAD terminology compatibility.
    
    Keep only the common volume between two solids.
    
    Args:
        doc_name: Document name
        object1_name: Name of the first object
        object2_name: Name of the second object
        result_name: Name for the result (default: object1_name + "_common")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDocument",
            "object1_name": "sphere_solid",
            "object2_name": "cube_solid",
            "result_name": "common_shape"
        }
    """
    freecad = get_freecad_connection()
    return _boolean_common(ctx, freecad, add_screenshot_if_available, doc_name, object1_name, object2_name, result_name)


@mcp.tool()
def transform_object_tool(
    ctx: Context,
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
        doc_name: Document name
        obj_name: Name of the object to transform
        position: Position dict {"x": float, "y": float, "z": float} (optional)
        rotation: Rotation dict {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        relative: If True, transformation is relative to current placement
        
    Returns:
        Confirmation message and screenshot
        
    Examples:
        # Absolute position
        {
            "doc_name": "MyDoc",
            "obj_name": "Cylinder",
            "position": {"x": 100, "y": 50, "z": 20}
        }
        
        # Rotation around Z axis
        {
            "doc_name": "MyDoc",
            "obj_name": "Cylinder",
            "rotation": {"axis": {"x": 0, "y": 0, "z": 1}, "angle": 45}
        }
        
        # Combined position and rotation
        {
            "doc_name": "MyDoc",
            "obj_name": "Cylinder",
            "position": {"x": 100, "y": 50, "z": 20},
            "rotation": {"axis": {"x": 0, "y": 0, "z": 1}, "angle": 90}
        }
        
        # Relative move (+10 in X direction)
        {
            "doc_name": "MyDoc",
            "obj_name": "Cylinder",
            "position": {"x": 10, "y": 0, "z": 0},
            "relative": true
        }
    """
    freecad = get_freecad_connection()
    return _transform_object(ctx, freecad, add_screenshot_if_available, doc_name, obj_name, position, rotation, relative)


@mcp.tool()
def align_object_tool(
    ctx: Context,
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
        doc_name: Document name
        source_obj_name: Name of the object to move
        target_obj_name: Name of the reference object
        align_type: Type of alignment - "position", "rotation", or "both"
        offset: Optional offset dict {"x": float, "y": float, "z": float}
        
    Returns:
        Confirmation message and screenshot
        
    Examples:
        # Copy position only
        {
            "doc_name": "MyDoc",
            "source_obj_name": "Part1",
            "target_obj_name": "Part2",
            "align_type": "position"
        }
        
        # Copy rotation only
        {
            "doc_name": "MyDoc",
            "source_obj_name": "Part1",
            "target_obj_name": "Part2",
            "align_type": "rotation"
        }
        
        # Copy both with offset
        {
            "doc_name": "MyDoc",
            "source_obj_name": "Part1",
            "target_obj_name": "Part2",
            "align_type": "both",
            "offset": {"x": 10, "y": 0, "z": 5}
        }
    """
    freecad = get_freecad_connection()
    return _align_object(ctx, freecad, add_screenshot_if_available, doc_name, source_obj_name, target_obj_name, align_type, offset)


@mcp.tool()
def attach_to_face_tool(
    ctx: Context,
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
        doc_name: Document name
        obj_name: Name of the object to attach
        target_obj_name: Name of the target face owner
        face_name: Face name (e.g., "Face1", "Face2", etc.)
        map_mode: Attachment mode - "FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"
        offset: Optional offset dict {"x": float, "y": float, "z": float}
        
    Returns:
        Confirmation message and screenshot
        
    Map Modes:
        - "FlatFace": Align to a flat face
        - "ObjectXY": Align to object's XY plane
        - "ObjectXZ": Align to object's XZ plane
        - "ObjectYZ": Align to object's YZ plane
        - "NormalToEdge": Perpendicular to an edge
        
    Examples:
        # Attach to top face
        {
            "doc_name": "MyDoc",
            "obj_name": "Sketch",
            "target_obj_name": "Box",
            "face_name": "Face6",
            "map_mode": "FlatFace"
        }
        
        # Attach with offset
        {
            "doc_name": "MyDoc",
            "obj_name": "Sketch",
            "target_obj_name": "Box",
            "face_name": "Face1",
            "map_mode": "FlatFace",
            "offset": {"x": 0, "y": 0, "z": 10}
        }
    """
    freecad = get_freecad_connection()
    return _attach_to_face(ctx, freecad, add_screenshot_if_available, doc_name, obj_name, target_obj_name, face_name, map_mode, offset)


@mcp.tool()
def create_assembly3_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str = "Assembly",
) -> list[TextContent | ImageContent]:
    """Create a new Assembly3 object for constraint-based assembly.
    
    Assembly3 uses automatic constraint solving for part positioning.
    
    Args:
        doc_name: Document name
        assembly_name: Name for the assembly (default: "Assembly")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _create_assembly3(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.tool()
def add_part_to_assembly3_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    part_file: str | None = None,
    part_object: str | None = None,
    part_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Add a part to Assembly3 from file or existing object.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        part_file: Path to external part file (optional)
        part_object: Existing object name in document (optional)
        part_name: Name for the imported part (optional)
        
    Returns:
        Confirmation message and screenshot
        
    Examples:
        # From external file
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "part_file": "C:/parts/base.FCStd",
            "part_name": "Base"
        }
        
        # From existing object
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "part_object": "Box001"
        }
    """
    freecad = get_freecad_connection()
    return _add_part_to_assembly3(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, part_file, part_object, part_name)


@mcp.tool()
def add_assembly3_constraint_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    constraint_type: str,
    references: list[dict[str, str]],
    constraint_name: str | None = None,
    properties: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Add a constraint to Assembly3.
    
    Constraint types: PlaneCoincident, Axial, PointsCoincident, PointOnLine,
    PointOnPlane, SameOrientation, MultiParallel, Angle, Distance, Lock, Perpendicular
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        constraint_type: Type of constraint
        references: List of [{"object": "PartName", "element": "Face1"}, ...]
        constraint_name: Optional constraint name
        properties: Optional properties like {"Angle": 90, "Distance": 10}
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "constraint_type": "PlaneCoincident",
            "references": [
                {"object": "Base", "element": "Face6"},
                {"object": "Cover", "element": "Face1"}
            ]
        }
    """
    freecad = get_freecad_connection()
    return _add_assembly3_constraint(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, constraint_type, references, constraint_name, properties)


@mcp.tool()
def solve_assembly3_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """Solve Assembly3 constraints to update part positions.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _solve_assembly3(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.tool()
def create_assembly4_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str = "Assembly",
) -> list[TextContent | ImageContent]:
    """Create a new Assembly4 container for LCS-based assembly.
    
    Assembly4 uses Local Coordinate Systems (LCS) for manual placement.
    
    Args:
        doc_name: Document name
        assembly_name: Name for the assembly (default: "Assembly")
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _create_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.tool()
def create_lcs_assembly4_tool(
    ctx: Context,
    doc_name: str,
    parent_name: str,
    lcs_name: str,
    position: dict[str, float],
    rotation: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Create a Local Coordinate System (LCS) in Assembly4.
    
    Args:
        doc_name: Document name
        parent_name: Parent object (Assembly or Part)
        lcs_name: Name for the LCS
        position: Position dict {"x": float, "y": float, "z": float}
        rotation: Rotation dict {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "parent_name": "MainAssembly",
            "lcs_name": "LCS_Base",
            "position": {"x": 0, "y": 0, "z": 0}
        }
    """
    freecad = get_freecad_connection()
    return _create_lcs_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, parent_name, lcs_name, position, rotation)


@mcp.tool()
def insert_part_assembly4_tool(
    ctx: Context,
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
        doc_name: Document name
        assembly_name: Assembly object name
        part_file: Path to external part file
        part_name: Name for the inserted part
        attach_lcs_part: LCS name in the part (optional)
        attach_lcs_target: LCS name in assembly (optional)
        offset: Optional offset {"x": float, "y": float, "z": float}
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "part_file": "C:/parts/base.FCStd",
            "part_name": "Base",
            "attach_lcs_part": "LCS_Origin",
            "attach_lcs_target": "LCS_Base"
        }
    """
    freecad = get_freecad_connection()
    return _insert_part_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, part_file, part_name, attach_lcs_part, attach_lcs_target, offset)


@mcp.tool()
def attach_lcs_to_geometry_tool(
    ctx: Context,
    doc_name: str,
    lcs_name: str,
    target_object: str,
    element: str,
    map_mode: str = "FlatFace",
) -> list[TextContent | ImageContent]:
    """Attach an LCS to a geometric element in Assembly4.
    
    Args:
        doc_name: Document name
        lcs_name: LCS object name
        target_object: Target object name
        element: Element name (e.g., "Face1", "Edge1")
        map_mode: Attachment mode - "FlatFace", "ObjectXY", "ObjectXZ", "ObjectYZ", "NormalToEdge"
        
    Returns:
        Confirmation message and screenshot
        
    Example:
        {
            "doc_name": "MyDoc",
            "lcs_name": "LCS_Mount",
            "target_object": "Box",
            "element": "Face6",
            "map_mode": "FlatFace"
        }
    """
    freecad = get_freecad_connection()
    return _attach_lcs_to_geometry(ctx, freecad, add_screenshot_if_available, doc_name, lcs_name, target_object, element, map_mode)


@mcp.tool()
def list_assembly_parts_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    assembly_type: str = "auto",
) -> list[TextContent | ImageContent]:
    """List all parts in an assembly (works with Assembly3 and Assembly4).
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        assembly_type: Type - "auto", "assembly3", or "assembly4"
        
    Returns:
        List of parts with details
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "assembly_type": "auto"
        }
    """
    freecad = get_freecad_connection()
    return _list_assembly_parts(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, assembly_type)


@mcp.tool()
def export_assembly_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    export_path: str,
    export_format: str = "step",
) -> list[TextContent | ImageContent]:
    """Export an assembly to a file.
    
    Formats: step, iges, stl, obj, brep
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        export_path: Path for exported file
        export_format: Format - "step", "iges", "stl", "obj", "brep"
        
    Returns:
        Confirmation message
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "export_path": "C:/exports/assembly.step",
            "export_format": "step"
        }
    """
    freecad = get_freecad_connection()
    return _export_assembly(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, export_path, export_format)


@mcp.tool()
def calculate_assembly_mass_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """Calculate total mass of assembly (requires material/density properties).
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        Mass calculation details
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _calculate_assembly_mass(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


# ==================== ASSEMBLY PHASE 2 - ADVANCED TOOLS (2025-10-08) ====================

@mcp.tool()
def list_assembly3_constraints_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """List all constraints in an Assembly3 with details.
    
    Returns constraint type, references, properties, and state.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        JSON list of all constraints with details
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _list_assembly3_constraints(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.tool()
def delete_assembly3_constraint_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    constraint_name: str,
) -> list[TextContent | ImageContent]:
    """Delete a constraint from Assembly3.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        constraint_name: Constraint name to delete
        
    Returns:
        Confirmation message
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "constraint_name": "PlaneCoincident001"
        }
    """
    freecad = get_freecad_connection()
    return _delete_assembly3_constraint(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, constraint_name)


@mcp.tool()
def modify_assembly3_constraint_tool(
    ctx: Context,
    doc_name: str,
    constraint_name: str,
    properties: dict[str, Any],
) -> list[TextContent | ImageContent]:
    """Modify properties of an Assembly3 constraint.
    
    Args:
        doc_name: Document name
        constraint_name: Constraint name
        properties: Properties to modify {"Distance": 10.0, "Enabled": False}
        
    Returns:
        Confirmation message
        
    Example:
        {
            "doc_name": "MyDoc",
            "constraint_name": "Distance001",
            "properties": {
                "Distance": 15.0,
                "Enabled": true
            }
        }
    """
    freecad = get_freecad_connection()
    return _modify_assembly3_constraint(ctx, freecad, add_screenshot_if_available, doc_name, constraint_name, properties)


@mcp.tool()
def list_assembly4_lcs_tool(
    ctx: Context,
    doc_name: str,
    parent_name: str,
) -> list[TextContent | ImageContent]:
    """List all LCS in an Assembly4 or Part with details.
    
    Returns position, rotation, and attachment information.
    
    Args:
        doc_name: Document name
        parent_name: Parent object (Assembly or Part) name
        
    Returns:
        JSON list of all LCS with details
        
    Example:
        {
            "doc_name": "MyDoc",
            "parent_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _list_assembly4_lcs(ctx, freecad, add_screenshot_if_available, doc_name, parent_name)


@mcp.tool()
def delete_lcs_assembly4_tool(
    ctx: Context,
    doc_name: str,
    parent_name: str,
    lcs_name: str,
) -> list[TextContent | ImageContent]:
    """Delete an LCS from Assembly4.
    
    Args:
        doc_name: Document name
        parent_name: Parent object name
        lcs_name: LCS name to delete
        
    Returns:
        Confirmation message
        
    Example:
        {
            "doc_name": "MyDoc",
            "parent_name": "MainAssembly",
            "lcs_name": "LCS_Mount1"
        }
    """
    freecad = get_freecad_connection()
    return _delete_lcs_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, parent_name, lcs_name)


@mcp.tool()
def modify_lcs_assembly4_tool(
    ctx: Context,
    doc_name: str,
    lcs_name: str,
    position: dict[str, float] | None = None,
    rotation: dict[str, Any] | None = None,
) -> list[TextContent | ImageContent]:
    """Modify position and/or rotation of an LCS in Assembly4.
    
    Args:
        doc_name: Document name
        lcs_name: LCS name
        position: New position {"x": float, "y": float, "z": float} (optional)
        rotation: New rotation {"axis": {"x": 0, "y": 0, "z": 1}, "angle": float} (optional)
        
    Returns:
        Confirmation message
        
    Examples:
        # Change position only
        {
            "doc_name": "MyDoc",
            "lcs_name": "LCS_Mount1",
            "position": {"x": 100, "y": 0, "z": 50}
        }
        
        # Change rotation only
        {
            "doc_name": "MyDoc",
            "lcs_name": "LCS_Mount1",
            "rotation": {"axis": {"x": 0, "y": 0, "z": 1}, "angle": 90}
        }
    """
    freecad = get_freecad_connection()
    return _modify_lcs_assembly4(ctx, freecad, add_screenshot_if_available, doc_name, lcs_name, position, rotation)


@mcp.tool()
def generate_bom_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
    format: str = "json",
) -> list[TextContent | ImageContent]:
    """Generate Bill of Materials (BOM) for an assembly.
    
    Counts parts, calculates masses, generates formatted BOM.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        format: Output format - "json", "csv", or "markdown"
        
    Returns:
        Formatted BOM
        
    Examples:
        # JSON format
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "format": "json"
        }
        
        # Markdown table
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly",
            "format": "markdown"
        }
    """
    freecad = get_freecad_connection()
    return _generate_bom(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name, format)


@mcp.tool()
def get_assembly_properties_tool(
    ctx: Context,
    doc_name: str,
    assembly_name: str,
) -> list[TextContent | ImageContent]:
    """Get detailed properties of an assembly.
    
    Returns mass, center of gravity, bounding box, part/constraint counts.
    
    Args:
        doc_name: Document name
        assembly_name: Assembly object name
        
    Returns:
        Detailed assembly properties
        
    Example:
        {
            "doc_name": "MyDoc",
            "assembly_name": "MainAssembly"
        }
    """
    freecad = get_freecad_connection()
    return _get_assembly_properties(ctx, freecad, add_screenshot_if_available, doc_name, assembly_name)


@mcp.prompt()
def asset_creation_strategy() -> str:
    return """
Asset Creation Strategy for FreeCAD MCP

When creating content in FreeCAD, always follow these steps:

0. Before starting any task, always use get_objects() to confirm the current state of the document.

1. Utilize the parts library:
   - Check available parts using get_parts_list().
   - If the required part exists in the library, use insert_part_from_library() to insert it into your document.

2. If the appropriate asset is not available in the parts library:
   - Create basic shapes (e.g., cubes, cylinders, spheres) using create_object().
   - Adjust and define detailed properties of the shapes as necessary using edit_object().

3. Always assign clear and descriptive names to objects when adding them to the document.

4. Explicitly set the position, scale, and rotation properties of created or inserted objects using edit_object() to ensure proper spatial relationships.

5. After editing an object, always verify that the set properties have been correctly applied by using get_object().

6. If detailed customization or specialized operations are necessary, use execute_code() to run custom Python scripts.

Only revert to basic creation methods in the following cases:
- When the required asset is not available in the parts library.
- When a basic shape is explicitly requested.
- When creating complex shapes requires custom scripting.
"""


@mcp.prompt()
def sketch_workflow() -> str:
    """Strategic guide for sketch-based workflow (2025-10-08)"""
    return sketch_workflow_strategy()


@mcp.prompt()
def boolean_operations_guide() -> str:
    """Strategic guide for Boolean operations (2025-10-08)"""
    return boolean_operations_strategy()


@mcp.prompt()
def assembly_guide() -> str:
    """Strategic guide for Assembly3 and Assembly4 (2025-10-08)"""
    return assembly_strategy()


# ==================== ADVANCED MODELING TOOLS ====================

@mcp.tool()
def create_loft_tool(ctx: Context, doc_name: str, sketch_names: list[str], result_name: str, solid: bool = True, ruled: bool = False) -> list[TextContent]:
    freecad = get_freecad_connection()
    return _create_loft(ctx, freecad, add_screenshot_if_available, doc_name, sketch_names, result_name, solid, ruled)

@mcp.tool()
def create_revolve_tool(ctx: Context, doc_name: str, sketch_name: str, axis: dict[str, dict[str, float]], angle: float = 360.0, result_name: str = None) -> list[TextContent]:
    freecad = get_freecad_connection()
    return _create_revolve(ctx, freecad, add_screenshot_if_available, doc_name, sketch_name, axis, angle, result_name or f"{sketch_name}_revolve")

@mcp.tool()
def create_sweep_tool(ctx: Context, doc_name: str, profile_sketch: str, path_sketch: str, result_name: str) -> list[TextContent]:
    freecad = get_freecad_connection()
    return _create_sweep(ctx, freecad, add_screenshot_if_available, doc_name, profile_sketch, path_sketch, result_name)

@mcp.tool()
def create_spline_3d_tool(ctx: Context, doc_name: str, points: list[dict[str, float]], spline_name: str, closed: bool = False) -> list[TextContent]:
    freecad = get_freecad_connection()
    return _create_spline_3d(ctx, freecad, add_screenshot_if_available, doc_name, points, spline_name, closed)

@mcp.tool()
def add_fillet_tool(ctx: Context, doc_name: str, object_name: str, edges: list[str], radius: float, result_name: str = None) -> list[TextContent | ImageContent]:
    """Add fillet (rounded edges) to an object
    
    Args:
        doc_name: Document name
        object_name: Object to modify
        edges: List of edge names ["Edge1", "Edge2", ...]
        radius: Fillet radius
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "Fuselage",
            "edges": ["Edge1", "Edge2", "Edge5"],
            "radius": 10.0,
            "result_name": "Fuselage_rounded"
        }
    """
    freecad = get_freecad_connection()
    return _add_fillet(ctx, freecad, add_screenshot_if_available, doc_name, object_name, edges, radius, result_name)

@mcp.tool()
def add_chamfer_tool(ctx: Context, doc_name: str, object_name: str, edges: list[str], distance: float, result_name: str = None) -> list[TextContent | ImageContent]:
    """Add chamfer (beveled edges) to an object
    
    Args:
        doc_name: Document name
        object_name: Object to modify
        edges: List of edge names ["Edge1", "Edge2", ...]
        distance: Chamfer distance
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "Panel",
            "edges": ["Edge1", "Edge3"],
            "distance": 2.0,
            "result_name": "Panel_chamfered"
        }
    """
    freecad = get_freecad_connection()
    return _add_chamfer(ctx, freecad, add_screenshot_if_available, doc_name, object_name, edges, distance, result_name)

@mcp.tool()
def shell_object_tool(ctx: Context, doc_name: str, object_name: str, thickness: float, faces_to_remove: list[str] | None = None, result_name: str = None) -> list[TextContent | ImageContent]:
    """Create hollow shell by removing faces and adding thickness
    
    Args:
        doc_name: Document name
        object_name: Object to shell
        thickness: Wall thickness
        faces_to_remove: List of face names to remove (opens the shell)
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "Fuselage_solid",
            "thickness": 2.0,
            "faces_to_remove": ["Face1", "Face6"],
            "result_name": "Fuselage_shell"
        }
    """
    freecad = get_freecad_connection()
    return _shell_object(ctx, freecad, add_screenshot_if_available, doc_name, object_name, thickness, faces_to_remove, result_name)

@mcp.tool()
def mirror_object_tool(ctx: Context, doc_name: str, source_obj: str, mirror_plane: dict[str, Any], result_name: str = None, merge: bool = True) -> list[TextContent | ImageContent]:
    """Mirror object across a plane
    
    Args:
        doc_name: Document name
        source_obj: Object to mirror
        mirror_plane: {"base": {"x": 0, "y": 0, "z": 0}, "normal": {"x": 1, "y": 0, "z": 0}}
        result_name: Result name (optional)
        merge: If True, fuse with original (creates symmetric object)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "source_obj": "RightWing",
            "mirror_plane": {
                "base": {"x": 0, "y": 0, "z": 0},
                "normal": {"x": 1, "y": 0, "z": 0}
            },
            "merge": true,
            "result_name": "BothWings"
        }
    """
    freecad = get_freecad_connection()
    return _mirror_object(ctx, freecad, add_screenshot_if_available, doc_name, source_obj, mirror_plane, result_name, merge)

@mcp.tool()
def circular_pattern_tool(ctx: Context, doc_name: str, object_name: str, axis: dict[str, dict[str, float]], count: int, angle: float = 360.0, result_name: str = None) -> list[TextContent | ImageContent]:
    """Create circular pattern (polar array) of an object
    
    Args:
        doc_name: Document name
        object_name: Object to pattern
        axis: {"point": {"x": 0, "y": 0, "z": 0}, "direction": {"x": 0, "y": 0, "z": 1}}
        count: Number of instances
        angle: Total angle in degrees (default 360)
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "EngineCylinder",
            "axis": {
                "point": {"x": 0, "y": 0, "z": 0},
                "direction": {"x": 1, "y": 0, "z": 0}
            },
            "count": 18,
            "angle": 360,
            "result_name": "RadialEngine"
        }
    """
    freecad = get_freecad_connection()
    return _circular_pattern(ctx, freecad, add_screenshot_if_available, doc_name, object_name, axis, count, angle, result_name)

@mcp.tool()
def linear_pattern_tool(ctx: Context, doc_name: str, object_name: str, direction: dict[str, float], spacing: float, count: int, result_name: str = None) -> list[TextContent | ImageContent]:
    """Create linear pattern (rectangular array) of an object
    
    Args:
        doc_name: Document name
        object_name: Object to pattern
        direction: {"x": 1, "y": 0, "z": 0} - normalized direction
        spacing: Distance between instances
        count: Number of instances
        result_name: Result name (optional)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "object_name": "MachineGun",
            "direction": {"x": 0, "y": 1, "z": 0},
            "spacing": 300,
            "count": 6,
            "result_name": "WingGuns"
        }
    """
    freecad = get_freecad_connection()
    return _linear_pattern(ctx, freecad, add_screenshot_if_available, doc_name, object_name, direction, spacing, count, result_name)

@mcp.tool()
def create_reference_plane_tool(ctx: Context, doc_name: str, plane_name: str, definition: dict[str, Any]) -> list[TextContent | ImageContent]:
    """Create reference plane with various definition modes
    
    Args:
        doc_name: Document name
        plane_name: Name for the plane
        definition: Plane definition (multiple modes supported)
            Mode 1 - Offset from existing plane:
                {"mode": "offset", "plane": "XY", "offset": 50.0}
            Mode 2 - Three points:
                {"mode": "3points", 
                 "p1": {"x": 0, "y": 0, "z": 0},
                 "p2": {"x": 100, "y": 0, "z": 0},
                 "p3": {"x": 0, "y": 100, "z": 0}}
            Mode 3 - Point and normal:
                {"mode": "point_normal",
                 "point": {"x": 0, "y": 0, "z": 0},
                 "normal": {"x": 0, "y": 0, "z": 1}}
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "plane_name": "WingPlane",
            "definition": {
                "mode": "point_normal",
                "point": {"x": 0, "y": 0, "z": 100},
                "normal": {"x": 0.2, "y": 0, "z": 1}
            }
        }
    """
    freecad = get_freecad_connection()
    return _create_reference_plane(ctx, freecad, add_screenshot_if_available, doc_name, plane_name, definition)

@mcp.tool()
def create_reference_axis_tool(ctx: Context, doc_name: str, axis_name: str, point: dict[str, float], direction: dict[str, float]) -> list[TextContent | ImageContent]:
    """Create reference axis from point and direction
    
    Args:
        doc_name: Document name
        axis_name: Name for the axis
        point: {"x": 0, "y": 0, "z": 0} - point on axis
        direction: {"x": 0, "y": 0, "z": 1} - axis direction
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "axis_name": "PropellerAxis",
            "point": {"x": 500, "y": 0, "z": 0},
            "direction": {"x": 1, "y": 0, "z": 0}
        }
    """
    freecad = get_freecad_connection()
    return _create_reference_axis(ctx, freecad, add_screenshot_if_available, doc_name, axis_name, point, direction)

@mcp.tool()
def import_airfoil_profile_tool(ctx: Context, doc_name: str, sketch_name: str, naca_code: str, chord_length: float, position: dict[str, float] | None = None) -> list[TextContent | ImageContent]:
    """Import standard NACA airfoil profile into sketch
    
    Args:
        doc_name: Document name
        sketch_name: Sketch name to create
        naca_code: NACA code (e.g., "2412", "0012", "23015")
        chord_length: Chord length in mm
        position: Optional position {"x": 0, "y": 0, "z": 0}
    
    Returns:
        Confirmation message and screenshot
    
    Note:
        Supports NACA 4-digit and 5-digit series
        Points are calculated using standard NACA equations
    
    Example:
        {
            "doc_name": "Corsair",
            "sketch_name": "WingProfile",
            "naca_code": "2412",
            "chord_length": 2000,
            "position": {"x": 0, "y": 0, "z": 0}
        }
    """
    freecad = get_freecad_connection()
    return _import_airfoil_profile(ctx, freecad, add_screenshot_if_available, doc_name, sketch_name, naca_code, chord_length, position)

@mcp.tool()
def import_dxf_tool(ctx: Context, doc_name: str, file_path: str, sketch_name: str, scale: float = 1.0) -> list[TextContent | ImageContent]:
    """Import DXF file into a sketch
    
    Args:
        doc_name: Document name
        file_path: Full path to DXF file
        sketch_name: Sketch name to create
        scale: Scale factor (default 1.0)
    
    Returns:
        Confirmation message and screenshot
    
    Example:
        {
            "doc_name": "Corsair",
            "file_path": "C:/models/fuselage_section.dxf",
            "sketch_name": "FuselageProfile",
            "scale": 1.0
        }
    """
    freecad = get_freecad_connection()
    return _import_dxf(ctx, freecad, add_screenshot_if_available, doc_name, file_path, sketch_name, scale)


def main():
    """Run the MCP server"""
    global _only_text_feedback
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-text-feedback", action="store_true", help="Only return text feedback")
    args = parser.parse_args()
    _only_text_feedback = args.only_text_feedback
    logger.info(f"Only text feedback: {_only_text_feedback}")
    mcp.run()