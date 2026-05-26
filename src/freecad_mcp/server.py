import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ImageContent, TextContent

from .freecad_client import FreeCADConnection
from .operations import (
    create_document_operation,
    create_object_operation,
    delete_object_operation,
    edit_object_operation,
    execute_code_async_operation,
    execute_code_operation,
    get_object_operation,
    get_objects_operation,
    get_parts_list_operation,
    get_view_operation,
    insert_part_from_library_operation,
    list_documents_operation,
    run_fem_analysis_operation,
)
from .prompt_text import ASSET_CREATION_STRATEGY
from .server_state import ServerState


logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FreeCADMCPserver")
logger.setLevel(logging.INFO)

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
    return create_document_operation(get_freecad_connection(), name)


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
    )


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
    return edit_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
        obj_properties,
    )


@mcp.tool()
def delete_object(ctx: Context, doc_name: str, obj_name: str) -> list[TextContent | ImageContent]:
    """Delete an object in FreeCAD.

    Args:
        doc_name: The name of the document to delete the object from.
        obj_name: The name of the object to delete.

    Returns:
        A message indicating the success or failure of the object deletion and a screenshot of the object.
    """
    return delete_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
    )


@mcp.tool()
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


@mcp.tool()
def execute_code(ctx: Context, code: str) -> list[TextContent | ImageContent]:
    """Execute arbitrary Python code in FreeCAD.

    Args:
        code: The Python code to execute.

    Returns:
        A message indicating the success or failure of the code execution, the output of the code execution, and a screenshot of the object.
    """
    return execute_code_operation(get_freecad_connection(), state.only_text_feedback, code)


@mcp.tool()
def get_view(
    ctx: Context,
    view_name: Literal["Isometric", "Front", "Top", "Right", "Back", "Left", "Bottom", "Dimetric", "Trimetric"],
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> list[ImageContent | TextContent]:
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
        width: The width of the screenshot in pixels. If not specified, uses the viewport width.
        height: The height of the screenshot in pixels. If not specified, uses the viewport height.
        focus_object: The name of the object to focus on. If not specified, fits all objects in the view.

    Returns:
        A screenshot of the active view.
    """
    return get_view_operation(get_freecad_connection(), view_name, width, height, focus_object)


@mcp.tool()
def insert_part_from_library(ctx: Context, relative_path: str) -> list[TextContent | ImageContent]:
    """Insert a part from the parts library addon.

    Args:
        relative_path: The relative path of the part to insert.

    Returns:
        A message indicating the success or failure of the part insertion and a screenshot of the object.
    """
    return insert_part_from_library_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        relative_path,
    )


@mcp.tool()
def get_objects(ctx: Context, doc_name: str) -> list[TextContent | ImageContent]:
    """Get all objects in a document.
    You can use this tool to get the objects in a document to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the objects from.

    Returns:
        A list of objects in the document and a screenshot of the document.
    """
    return get_objects_operation(get_freecad_connection(), state.only_text_feedback, doc_name)


@mcp.tool()
def get_object(ctx: Context, doc_name: str, obj_name: str) -> list[TextContent | ImageContent]:
    """Get an object from a document.
    You can use this tool to get the properties of an object to see what you can check or edit.

    Args:
        doc_name: The name of the document to get the object from.
        obj_name: The name of the object to get.

    Returns:
        The object and a screenshot of the object.
    """
    return get_object_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        obj_name,
    )


@mcp.tool()
def get_parts_list(ctx: Context) -> list[TextContent]:
    """Get the list of parts in the parts library addon.
    """
    return get_parts_list_operation(get_freecad_connection())


@mcp.tool()
def list_documents(ctx: Context) -> list[TextContent]:
    """Get the list of open documents in FreeCAD.

    Returns:
        A list of document names.
    """
    return list_documents_operation(get_freecad_connection())


@mcp.tool()
def run_fem_analysis(
    ctx: Context,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
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
    """
    return run_fem_analysis_operation(
        get_freecad_connection(),
        state.only_text_feedback,
        doc_name,
        analysis_name,
        timeout,
    )


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
