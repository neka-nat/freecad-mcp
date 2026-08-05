import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Literal

try:
    # mcp 1.x
    from mcp.server.fastmcp import Context, FastMCP
except ImportError:
    # mcp 2.x moved mcp.server.fastmcp to mcp.server.mcpserver and renamed
    # FastMCP to MCPServer; the API surface used here is unchanged.
    from mcp.server.mcpserver import Context
    from mcp.server.mcpserver import MCPServer as FastMCP
from mcp.types import ImageContent, TextContent

from .freecad_client import FreeCADConnection
from .operations import (
    close_document_operation,
    create_document_operation,
    create_object_operation,
    create_sketch_operation,
    delete_object_operation,
    edit_object_operation,
    execute_code_async_operation,
    execute_code_operation,
    export_objects_operation,
    get_object_operation,
    get_objects_operation,
    get_parts_list_operation,
    get_view_operation,
    import_file_operation,
    insert_part_from_library_operation,
    list_documents_operation,
    open_document_operation,
    reload_document_operation,
    run_fem_analysis_operation,
    save_document_as_operation,
    save_document_operation,
)
from .prompt_text import ASSET_CREATION_STRATEGY
from .server_state import ServerState


logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FreeCADMCPserver")
logger.setLevel(logging.INFO)

ViewName = Literal[
    "Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"
]

state = ServerState()


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
        if state.freecad_connection:
            logger.info("Disconnecting from FreeCAD on shutdown")
            state.freecad_connection.disconnect()
            state.freecad_connection = None
        logger.info("FreeCADMCP server shut down")


mcp = FastMCP(
    "FreeCADMCP",
    instructions="FreeCAD integration through the Model Context Protocol",
    lifespan=server_lifespan,
)


def get_freecad_connection() -> FreeCADConnection:
    """Get or create a persistent FreeCAD connection"""
    if state.freecad_connection is None:
        state.freecad_connection = FreeCADConnection(host=state.rpc_host, port=9875)
        if not state.freecad_connection.ping():
            logger.error("Failed to ping FreeCAD")
            state.freecad_connection = None
            raise Exception(
                "Failed to connect to FreeCAD. Make sure the FreeCAD addon is running."
            )
    return state.freecad_connection


@mcp.tool(structured_output=False)
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
    return create_document_operation(get_freecad_connection(), name)


@mcp.tool(structured_output=False)
def create_object(
    ctx: Context,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] = None,
    include_screenshot: bool = True,
    view_name: ViewName = "Isometric",
    body_name: str | None = None,
) -> list[TextContent | ImageContent]:
    """Create a new object in FreeCAD.
    Object type is starts with "Part::" or "Draft::" or "PartDesign::" or "Fem::".

    Args:
        doc_name: The name of the document to create the object in.
        obj_type: The type of the object to create (e.g. 'Part::Box', 'Part::Cylinder', 'Draft::Circle', 'PartDesign::Body', etc.).
        obj_name: The name of the object to create.
        obj_properties: The properties of the object to create.
        body_name: The name of an existing PartDesign::Body to create this feature
            inside. REQUIRED for every PartDesign feature except the Body itself.
            A PartDesign feature created without it lands outside any Body, computes
            to nothing, and the call fails. Body membership cannot be set afterwards
            through obj_properties -- it is not a property.
        include_screenshot: Whether to return a screenshot of the model (default True).
            Set to False to save tokens when visual feedback is not needed,
            e.g. for intermediate steps in a longer sequence of changes.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Pick the view that best shows the change being made.
            Applies to the 3D view only -- when the active window is a TechDraw page or
            a spreadsheet it is ignored, since there is no 3D orientation to apply.

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

        PartDesign: create the Body first, then every feature WITH body_name.
        Sketch-free primitives (Additive/Subtractive Box, Cylinder, Sphere, Cone,
        Torus, Prism, Wedge) need no sketch and are the simplest way to build a
        solid. Each feature is applied to the running result and advances the
        Body's Tip, so order matters.
        ```json
        {"doc_name": "Doc", "obj_name": "Body", "obj_type": "PartDesign::Body"}
        ```
        ```json
        {
            "doc_name": "Doc",
            "obj_name": "Base",
            "obj_type": "PartDesign::AdditiveBox",
            "body_name": "Body",
            "obj_properties": {"Length": 20, "Width": 10, "Height": 5}
        }
        ```
        ```json
        {
            "doc_name": "Doc",
            "obj_name": "Hole",
            "obj_type": "PartDesign::SubtractiveCylinder",
            "body_name": "Body",
            "obj_properties": {"Radius": 3, "Height": 20}
        }
        ```

        For a sketch-based feature (Pad, Pocket, Revolution, ...) the sketch must
        also live in the same Body, and its profile must be a CLOSED wire. Sketch
        geometry cannot be sent through this tool -- use execute_code to add the
        geometry and constraints, then create the Pad here with body_name set.

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
        The `Shape` property is required (legacy `Part` is also accepted).
        On FreeCAD 1.x the size limits are `CharacteristicLengthMax/Min`;
        the legacy `ElementSizeMax/Min` keys are also accepted.
        ```json
        {
            "doc_name": "MyFEMMesh",
            "obj_name": "FemMesh",
            "obj_type": "Fem::FemMeshGmsh",
            "analysis_name": "MyFEMAnalysis",
            "obj_properties": {
                "Shape": "MyObject",
                "CharacteristicLengthMax": 10,
                "CharacteristicLengthMin": 0.1
            }
        }
        ```
    """
    return create_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_type,
        obj_name,
        analysis_name,
        obj_properties,
        include_screenshot,
        view_name,
        body_name,
    )


@mcp.tool(structured_output=False)
def edit_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    obj_properties: dict[str, Any],
    include_screenshot: bool = True,
    view_name: ViewName = "Isometric",
) -> list[TextContent | ImageContent]:
    """Edit an object in FreeCAD.
    This tool is used when the `create_object` tool cannot handle the object creation.

    Args:
        doc_name: The name of the document to edit the object in.
        obj_name: The name of the object to edit.
        obj_properties: The properties of the object to edit.
        include_screenshot: Whether to return a screenshot of the model (default True).
            Set to False to save tokens when visual feedback is not needed,
            e.g. for intermediate steps in a longer sequence of changes.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Pick the view that best shows the change being made.
            Applies to the 3D view only -- when the active window is a TechDraw page or
            a spreadsheet it is ignored, since there is no 3D orientation to apply.

    Returns:
        A message indicating the success or failure of the object editing and a screenshot of the object.
    """
    return edit_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
        obj_properties,
        include_screenshot,
        view_name,
    )


@mcp.tool(structured_output=False)
def delete_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    include_screenshot: bool = True,
    view_name: ViewName = "Isometric",
) -> list[TextContent | ImageContent]:
    """Delete an object in FreeCAD.

    Args:
        doc_name: The name of the document to delete the object from.
        obj_name: The name of the object to delete.
        include_screenshot: Whether to return a screenshot of the model (default True).
            Set to False to save tokens when visual feedback is not needed,
            e.g. for intermediate steps in a longer sequence of changes.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Pick the view that best shows the change being made.
            Applies to the 3D view only -- when the active window is a TechDraw page or
            a spreadsheet it is ignored, since there is no 3D orientation to apply.

    Returns:
        A message indicating the success or failure of the object deletion and a screenshot of the object.
    """
    return delete_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
        include_screenshot,
        view_name,
    )


@mcp.tool(structured_output=False)
def execute_code_async(ctx: Context, code: str) -> list[TextContent]:
    """Execute Python code in FreeCAD without waiting for completion.

    Use this ONLY for long-running background computations that do NOT touch the
    FreeCAD GUI or mutate the FreeCAD document tree directly.

    This tool runs the submitted code in a background thread and returns
    immediately. Because it does not run on FreeCAD's main GUI thread, the code
    must NOT call FreeCADGui APIs, manipulate the active view or selection, create
    or edit document objects, change object properties, call doc.recompute(), or
    save documents.

    For code that touches FreeCAD documents, document objects, FreeCADGui, the
    active view, selection, recompute, or save operations, use execute_code instead.
    execute_code runs on the FreeCAD GUI thread and is the safe default for normal
    FreeCAD automation.

    Use execute_code_async only for background-safe work such as long-running
    pure OCCT geometry calculations (e.g. fuse/cut/loft on already-fetched shapes)
    or other CPU-bound computations that do not interact with the document or GUI.

    Typical usage pattern:
    1. Fetch shapes into local variables first (via execute_code on the GUI thread).
    2. Store intermediate results in a module-level Python variable (not in the
       FreeCAD document) so execute_code can read them later.
    3. Run the heavy computation via execute_code_async.
    4. After the expected computation time has elapsed, apply results to the
       document via execute_code (which runs on the GUI thread).

    Args:
        code: Background-safe Python code to execute.

    Returns:
        A message confirming that background execution has started.
    """
    return execute_code_async_operation(get_freecad_connection(), code)


@mcp.tool(structured_output=False)
def execute_code(
    ctx: Context,
    code: str,
    include_screenshot: bool = True,
    view_name: ViewName = "Isometric",
) -> list[TextContent | ImageContent]:
    """Execute arbitrary Python code in FreeCAD.

    Args:
        code: The Python code to execute.
        include_screenshot: Whether to return a screenshot of the model (default True).
            Set to False to save tokens when the code does not change the model's
            appearance, e.g. analytical or computational scripts whose result is
            printed output, or intermediate steps in a longer sequence of changes.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Pick the view that best shows the change being made.
            Applies to the 3D view only -- when the active window is a TechDraw page or
            a spreadsheet it is ignored, since there is no 3D orientation to apply.

    Returns:
        A message indicating the success or failure of the code execution, the output of the code execution, and a screenshot of the object.
    """
    return execute_code_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        code,
        include_screenshot,
        view_name,
    )


@mcp.tool(structured_output=False)
def get_view(
    ctx: Context,
    view_name: ViewName,
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> list[ImageContent | TextContent]:
    """Get a screenshot of whatever window is currently active in FreeCAD.

    Captures the 3D view, a TechDraw drawing page, or a spreadsheet -- whichever
    the user last opened. To see a drawing, open its page in FreeCAD first (the
    page must be the active window), then call this.

    Args:
        view_name: The 3D view orientation to apply before capturing.
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
        Ignored when the active window is a TechDraw page or a spreadsheet, since
        there is no 3D orientation to apply -- those are captured as they are.
        width: The width of the screenshot in pixels. If not specified, uses the viewport width.
        height: The height of the screenshot in pixels. If not specified, uses the viewport height.
        focus_object: The name of the object to focus on. If not specified, fits all objects in the view.
            3D view only; ignored for drawings and spreadsheets.

    Returns:
        A screenshot of the active window.

    Notes:
        A TechDraw page is captured by rendering its contents, so the image does
        not depend on how the page is zoomed or scrolled on screen, and calling
        this never changes what the user is looking at. A spreadsheet is captured
        as displayed, so it does reflect the current scroll position.
    """
    return get_view_operation(get_freecad_connection(), view_name, width, height, focus_object)


@mcp.tool(structured_output=False)
def insert_part_from_library(
    ctx: Context,
    relative_path: str,
    include_screenshot: bool = True,
    view_name: ViewName = "Isometric",
) -> list[TextContent | ImageContent]:
    """Insert a part from the parts library addon.

    Args:
        relative_path: The relative path of the part to insert.
        include_screenshot: Whether to return a screenshot of the model (default True).
            Set to False to save tokens when visual feedback is not needed,
            e.g. for intermediate steps in a longer sequence of changes.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Pick the view that best shows the change being made.
            Applies to the 3D view only -- when the active window is a TechDraw page or
            a spreadsheet it is ignored, since there is no 3D orientation to apply.

    Returns:
        A message indicating the success or failure of the part insertion and a screenshot of the object.
    """
    return insert_part_from_library_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        relative_path,
        include_screenshot,
        view_name,
    )


@mcp.tool(structured_output=False)
def get_objects(
    ctx: Context,
    doc_name: str,
    include_screenshot: bool = True,
    view_name: ViewName = "Isometric",
) -> list[TextContent | ImageContent]:
    """Get all objects in a document.
    You can use this tool to get the objects in a document to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the objects from.
        include_screenshot: Whether to return a screenshot of the document (default True).
            Set to False to save tokens when only the object data is needed.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Applies to the 3D view only -- when the active window is a TechDraw page or
            a spreadsheet it is ignored, since there is no 3D orientation to apply.

    Returns:
        A list of objects in the document and a screenshot of the document.
    """
    return get_objects_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        include_screenshot,
        view_name,
    )


@mcp.tool(structured_output=False)
def get_object(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    include_screenshot: bool = True,
    view_name: ViewName = "Isometric",
) -> list[TextContent | ImageContent]:
    """Get an object from a document.
    You can use this tool to get the properties of an object to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the object from.
        obj_name: The name of the object to get.
        include_screenshot: Whether to return a screenshot of the document (default True).
            Set to False to save tokens when only the object data is needed.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Applies to the 3D view only -- when the active window is a TechDraw page or
            a spreadsheet it is ignored, since there is no 3D orientation to apply.

    Returns:
        The object and a screenshot of the object.
    """
    return get_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
        include_screenshot,
        view_name,
    )


@mcp.tool(structured_output=False)
def get_parts_list(ctx: Context) -> list[TextContent]:
    """Get the list of parts in the parts library addon.
    """
    return get_parts_list_operation(get_freecad_connection())


@mcp.tool(structured_output=False)
def reload_document(ctx: Context, doc_name: str) -> list[TextContent]:
    """Close and re-open a document to pick up external file changes.

    Use this AFTER the document's .FCStd file has been modified by
    something outside of FreeCAD's GUI process — for example, a
    headless `freecadcmd` script that edited and saved the file. The
    open GUI document is otherwise unaware of on-disk changes; this
    tool closes the stale in-memory copy and reopens the file from
    disk so the GUI shows current geometry.

    Args:
        doc_name: The name of the open document to reload. Must match
            the name shown by ``list_documents``.

    Returns:
        A message confirming the document was reloaded, or describing
        the failure (document not loaded, no associated file, etc).

    Examples:
        ```json
        {
            "doc_name": "chassis"
        }
        ```
    """
    return reload_document_operation(get_freecad_connection(), doc_name)


@mcp.tool(structured_output=False)
def list_documents(ctx: Context) -> list[TextContent]:
    """Get the list of open documents in FreeCAD.

    Returns:
        A list of document names.
    """
    return list_documents_operation(get_freecad_connection())


@mcp.tool(structured_output=False)
def run_fem_analysis(
    ctx: Context,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
    include_screenshot: bool = True,
    view_name: ViewName = "Isometric",
) -> list[TextContent | ImageContent]:
    """Run the CalculiX solver on an existing Fem::FemAnalysis container and return summary results.

    Prerequisites in the document:
    - A Part-derived solid (e.g. Part::Box, PartDesign::Body) acting as the geometry.
    - A Fem::AnalysisPython container created via `create_object`.
    - A Fem::MaterialCommon assigned to the geometry, added to the analysis.
    - A Fem::FemMeshGmsh referencing the geometry, added to the analysis (the
      mesh is generated automatically when created via `create_object`).
    - At least one Fem::ConstraintFixed and one Fem::ConstraintForce (or
      ConstraintPressure) bound to faces of the geometry, added to the analysis.

    A SolverCcxTools is auto-created if the analysis has none.

    The solver runs synchronously on the FreeCAD GUI thread and blocks all
    other RPC calls for its duration; do not fan out parallel requests.

    Returns max von Mises stress (MPa), max/min displacement (mm), node count,
    and the working directory CalculiX wrote to. On failure, returns the
    prerequisite-check or solver error along with the working directory for
    triage.

    Args:
        doc_name: Name of the FreeCAD document.
        analysis_name: Name of the Fem::AnalysisPython object.
        timeout: Seconds to wait for the solver (default 600).
        include_screenshot: Whether to return a screenshot of the model (default True).
            Set to False to save tokens when only the numeric results are needed.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Applies to the 3D view only -- when the active window is a TechDraw page or
            a spreadsheet it is ignored, since there is no 3D orientation to apply.
    """
    return run_fem_analysis_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        analysis_name,
        timeout,
        include_screenshot,
        view_name,
    )


@mcp.tool(structured_output=False)
def create_sketch(
    ctx: Context,
    doc_name: str,
    sketch_name: str,
    geometry: list[dict[str, Any]],
    constraints: list[dict[str, Any]] | None = None,
    body_name: str | None = None,
    plane: str = "XY",
) -> list[TextContent]:
    """Create a Sketcher sketch from geometry described as JSON.

    Use this instead of execute_code for sketches. A sketch made here can then be
    the Profile of a PartDesign Pad, Pocket, Revolution and so on.

    Coordinates are 2D [x, y] -- the sketch has its own plane.

    GEOMETRY (each entry may also set "construction": true)
        {"type": "polyline", "points": [[0,0],[60,0],[60,20]], "closed": true}
        {"type": "rectangle", "corner": [0,0], "width": 60, "height": 40}
        {"type": "line", "start": [0,0], "end": [60,0]}
        {"type": "circle", "center": [12,10], "radius": 4}
        {"type": "arc", "center": [30,10], "radius": 6, "start_angle": 0, "end_angle": 180}
        {"type": "ellipse", "center": [0,0], "major_radius": 8, "minor_radius": 4, "angle": 0}
        {"type": "point", "at": [5,5]}

    PREFER polyline and rectangle for profiles: they add the coincident
    constraints between consecutive segments for you. An unclosed wire is the
    usual reason a Pad computes to nothing, and stitching one by hand is where
    that goes wrong.

    CONSTRAINTS reference geometry by index in creation order. A polyline of N
    points creates N segments (N-1 if open), each taking its own index -- the
    reply's geometry_index maps every spec to the indices it produced. Use -1 to
    mean the sketch origin. Point names are "start", "end" and "center".

        {"type": "Horizontal", "first": 0}
        {"type": "Coincident", "first": 0, "first_pos": "start",
                               "second": -1, "second_pos": "start"}
        {"type": "DistanceX", "first": 0, "first_pos": "start",
                              "second": 0, "second_pos": "end", "value": 60}
        {"type": "Radius", "first": 0, "value": 4}
        {"type": "Parallel", "first": 0, "second": 2}

    Available: Horizontal, Vertical, Block, Coincident, PointOnObject, Parallel,
    Perpendicular, Equal, Tangent, Symmetric, Distance, DistanceX, DistanceY,
    Angle (radians), Radius, Diameter, Weight. Names are case-sensitive.

    Args:
        doc_name: Document to create the sketch in.
        sketch_name: Name for the new sketch.
        geometry: The geometry specs, as above.
        constraints: Optional constraint specs.
        body_name: PartDesign::Body to create the sketch inside. Required if the
            sketch will feed a PartDesign feature -- the feature and its profile
            must live in the same Body.
        plane: "XY" (default), "XZ" or "YZ".

    Returns:
        The created name, the geometry index map, the constraint and edge counts,
        the remaining degrees of freedom, whether it is fully constrained, and how
        many wires came out closed. Check closed_wires before padding: 0 means no
        usable profile.
    """
    return create_sketch_operation(
        get_freecad_connection(), doc_name, sketch_name, geometry,
        constraints, body_name, plane,
    )


@mcp.tool(structured_output=False)
def export_objects(
    ctx: Context,
    doc_name: str,
    path: str,
    obj_names: list[str] | None = None,
    overwrite: bool = False,
) -> list[TextContent]:
    """Export objects to a file. The file extension selects the format.

    Dispatches through FreeCAD's own handler registry, so every format FreeCAD
    can write is available: STEP, IGES, BREP (CAD interchange); STL, OBJ, PLY,
    3MF, AMF, OFF (mesh and 3D printing); DXF, SVG (2D); and others.

    Args:
        doc_name: Document holding the objects.
        path: Destination file. Use an absolute path, or ~ for your home
            directory; a bare filename is resolved against FreeCAD's working
            directory, which is rarely what you want. The extension decides the
            format -- '.step' writes STEP, '.stl' writes a mesh.
        obj_names: Objects to export. Omit or pass null to export everything in
            the document that has geometry.
        overwrite: False (default) refuses to replace an existing file. Pass
            True only when the user has asked to overwrite.

    Returns:
        The path written, the handler FreeCAD used, the objects exported and the
        file size, or the reason it failed.

    Examples:
        ```json
        {"doc_name": "Doc", "path": "~/parts/bracket.step"}
        ```
        ```json
        {"doc_name": "Doc", "path": "~/print/bracket.stl", "obj_names": ["Body"]}
        ```
    """
    return export_objects_operation(
        get_freecad_connection(), doc_name, obj_names, path, overwrite
    )


@mcp.tool(structured_output=False)
def save_document(ctx: Context, doc_name: str) -> list[TextContent]:
    """Save a document to the file it was opened from or last saved to.

    Fails if the document has never been saved and so has no path -- use
    save_document_as for that.

    Args:
        doc_name: The document to save.
    """
    return save_document_operation(get_freecad_connection(), doc_name)


@mcp.tool(structured_output=False)
def save_document_as(
    ctx: Context, doc_name: str, path: str, overwrite: bool = False
) -> list[TextContent]:
    """Save a document to a specific .FCStd path, which becomes its new path.

    This writes FreeCAD's own format. To write STEP, STL or any other format,
    use export_objects instead.

    Args:
        doc_name: The document to save.
        path: Destination .FCStd file, absolute or starting with ~.
        overwrite: False (default) refuses to replace an existing file.
    """
    return save_document_as_operation(get_freecad_connection(), doc_name, path, overwrite)


@mcp.tool(structured_output=False)
def open_document(ctx: Context, path: str) -> list[TextContent]:
    """Open a file as a new document.

    A .FCStd file is loaded natively. Any other format FreeCAD can read (STEP,
    IGES, STL, OBJ, DXF, ...) is imported into a new document.

    Args:
        path: File to open, absolute or starting with ~.

    Returns:
        The name of the document created -- use that name in later calls, as it
        may differ from the filename.
    """
    return open_document_operation(get_freecad_connection(), path)


@mcp.tool(structured_output=False)
def import_file(ctx: Context, path: str, doc_name: str) -> list[TextContent]:
    """Import a file's contents into an existing document.

    Use this to add geometry to a document you are already working in;
    open_document creates a new one instead.

    Args:
        path: File to import, absolute or starting with ~.
        doc_name: Existing document to import into.

    Returns:
        The names of the objects that were added, so they can be referenced
        immediately.
    """
    return import_file_operation(get_freecad_connection(), path, doc_name)


@mcp.tool(structured_output=False)
def close_document(ctx: Context, doc_name: str, force: bool = False) -> list[TextContent]:
    """Close a document, refusing to discard unsaved work.

    Refuses when the document has unsaved changes, or has never been saved at
    all. Call save_document (or save_document_as for a document with no path)
    first, then close.

    Args:
        doc_name: The document to close.
        force: True closes anyway and loses the unsaved work. Only use this when
            the user has explicitly said the changes can be discarded.
    """
    return close_document_operation(get_freecad_connection(), doc_name, force)


@mcp.prompt()
def asset_creation_strategy() -> str:
    return ASSET_CREATION_STRATEGY


def _validate_host(value: str) -> str:
    """Validate that *value* is a valid IP address or hostname.

    Used as the ``type`` callback for the ``--host`` argparse argument.
    Raises ``argparse.ArgumentTypeError`` on invalid input.
    """
    import argparse

    import validators

    if validators.ipv4(value) or validators.ipv6(value) or validators.hostname(value):
        return value
    raise argparse.ArgumentTypeError(
        f"Invalid host: '{value}'. Must be a valid IP address or hostname."
    )


def main():
    """Run the MCP server"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--only-text-feedback", action="store_true", help="Only return text feedback")
    parser.add_argument("--host", type=_validate_host, default="localhost", help="Host address of the FreeCAD RPC server to connect to (default: localhost)")
    args = parser.parse_args()
    state.only_text_feedback = args.only_text_feedback
    state.rpc_host = args.host
    logger.info(f"Only text feedback: {state.only_text_feedback}")
    logger.info(f"Connecting to FreeCAD RPC server at: {state.rpc_host}")
    mcp.run()
