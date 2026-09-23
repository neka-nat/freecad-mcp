import json
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
    create_document_operation,
    create_object_operation,
    delete_object_operation,
    edit_object_operation,
    execute_code_async_operation,
    execute_code_headless_operation,
    execute_code_operation,
    get_object_operation,
    get_objects_operation,
    get_parts_list_operation,
    get_async_status_operation,
    get_rpc_status_operation,
    get_view_operation,
    insert_part_from_library_operation,
    list_documents_operation,
    reload_document_operation,
    run_fem_analysis_operation,
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
) -> list[TextContent | ImageContent]:
    """Create a new object in FreeCAD.
    Object type is starts with "Part::" or "Draft::" or "PartDesign::" or "Fem::".

    Args:
        doc_name: The name of the document to create the object in.
        obj_type: The type of the object to create (e.g. 'Part::Box', 'Part::Cylinder', 'Draft::Circle', 'PartDesign::Body', etc.).
        obj_name: The name of the object to create.
        obj_properties: The properties of the object to create.
        include_screenshot: Whether to return a screenshot of the model (default True).
            Set to False to save tokens when visual feedback is not needed,
            e.g. for intermediate steps in a longer sequence of changes.
        view_name: The view orientation of the returned screenshot (default "Isometric").
            Pick the view that best shows the change being made.

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
        include_screenshot,
        view_name,
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
    must NOT directly call FreeCADGui APIs, manipulate the active view or
    selection, create or edit document objects, change object properties, call
    doc.recompute(), or save documents. FreeCAD documents and the Coin3D
    scenegraph are not thread-safe: writing to them from this thread races the
    GUI thread and can wedge FreeCAD's event loop, after which the RPC server
    stops responding entirely and FreeCAD must be restarted.

    Every document or view write must instead be handed to the GUI thread through
    the injected commit() helper:

        commit(fn, timeout=120) -> fn's return value

    Scripts share a live namespace. Saved functions can use commit() in later
    async calls; calling it from execute_code or a GUI callback raises immediately.
    Coordinate concurrent scripts that intentionally modify the same variables.

    commit() queues fn on the GUI thread, waits for it, and raises RuntimeError if
    dispatch fails or times out. Example:

        fused = base.fuse(addition).removeSplitter()   # slow, safe in background

        def apply():                                   # runs on the GUI thread
            obj.Shape = fused
            doc.recompute()

        commit(apply)

    For code that is not dominated by heavy geometry computation, use execute_code
    instead. execute_code runs entirely on the FreeCAD GUI thread and is the safe
    default for normal FreeCAD automation.

    Use execute_code_async only when the heavy part is long-running OCCT geometry
    (e.g. fuse/cut/loft on already-fetched shapes) or other CPU-bound computation
    that would exceed execute_code's 90 s GUI-thread budget.

    Typical usage pattern:
    1. Fetch shapes into module-level variables first (via execute_code).
    2. Run the heavy computation via execute_code_async.
    3. Apply the result inside commit(), or store it in a module-level Python
       variable (not in the FreeCAD document) for a later execute_code call.

    Performance note: boolean operations against shapes with many faces (e.g. a
    ribbed lid) are expensive. Fuse the additions together first, then apply a
    single boolean against the heavy shape, and avoid doc.recompute() unless the
    dependency graph really needs it.

    Args:
        code: Background-safe Python code to execute. Use commit(fn) for all
            document and view writes.

    Returns:
        A message with the job_id of the started background execution.
    """
    return execute_code_async_operation(get_freecad_connection(), code)


@mcp.tool(structured_output=False)
def execute_code_headless(ctx: Context, code: str, timeout: float = 600) -> list[TextContent]:
    """Run a FreeCAD Python script in a separate headless `freecadcmd` process.

    Use this for OCCT work that can crash or block FreeCAD: helical threads
    (makeHelix + makePipeShell), lofts and sweeps, booleans with many or
    B-spline tools, long parametric rebuilds. A native OpenCascade crash
    here only kills the helper process; the GUI and its open documents
    survive, and the tool reports the crash signal and the script's output.

    The script runs on the MCP server machine, independently of --host, in a
    fresh process without GUI: import FreeCAD/Part
    yourself, open documents from disk (FreeCAD.openDocument(path)), save
    results with doc.save()/saveAs() or Shape.exportBrep(). Nothing from the
    execute_code namespace is available. Print progress to stdout; it is
    returned when the process ends. After the script saved a .FCStd that is
    open in the GUI, call reload_document(doc_name) to show the result.

    Args:
        code: Complete Python script for freecadcmd.
        timeout: Positive finite seconds to wait before killing the process
            (default 600). Partial output is preserved on timeout.

    Returns:
        Exit status, crash/timeout diagnosis and the script's printed output.
    """
    return execute_code_headless_operation(state.freecadcmd, code, timeout)


@mcp.tool(structured_output=False)
def get_async_status(ctx: Context, job_id: str = "") -> list[TextContent]:
    """Report the state of background jobs started by execute_code_async.

    Does not use the FreeCAD GUI thread, so it answers even while a job runs.

    Args:
        job_id: The id returned by execute_code_async. Empty lists all running
            jobs and up to 20 recently completed jobs.

    Returns:
        For one job: its state (running/done/failed), the error and traceback
        when it failed. History is held in memory until FreeCAD exits.
    """
    return get_async_status_operation(get_freecad_connection(), job_id)


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


@mcp.tool()
def undo_last_edit(ctx: Context, doc_name: str | None = None) -> list[TextContent]:
    """Revert the last execute_code call.

    Every execute_code runs inside one undo transaction, so this restores the
    state from just before it. Use it as soon as a check shows an edit went
    wrong: FreeCAD overwrites the .FCBak file on the next save, so saving over a
    bad edit destroys the only copy on disk.

    Args:
        doc_name: Document to undo. If omitted, undoes one step in the active document.
    """
    res = get_freecad_connection().undo_last_edit(doc_name)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def measure_probe(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    start: list[float],
    end: list[float],
) -> list[TextContent]:
    """Report where a ray passes through material, and where the gaps are.

    Use this to verify a feature's real dimensions instead of inferring them.
    `spans` are the solid intervals along the ray, `gaps` the open ones: probing
    across a vented wall returns the ribs as spans and the slots as gaps, which
    tells you which of the two a planned cut would actually remove. Probe across
    a wall's thickness to confirm it before and after an edit.

    Args:
        doc_name: Document name.
        obj_name: Object to measure.
        start: Ray start as [x, y, z].
        end: Ray end as [x, y, z].
    """
    res = get_freecad_connection().measure_probe(doc_name, obj_name, start, end)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def execute_guarded(
    ctx: Context,
    doc_name: str,
    code: str,
    label: str = "",
    policy: dict[str, Any] | None = None,
    objects: list[str] | None = None,
) -> list[TextContent]:
    """Run an edit and keep it only if it leaves the part sound.

    Prefer this over `execute_code` for anything that changes geometry. A
    checkpoint is written first, the code runs, and the result is audited: if
    the edit split the solid, invalidated it, grew its bounding box or added
    slivers, the document is restored from that checkpoint and the damage never
    reaches the model. `execute_code` reports the same defects but keeps them.

    A rejected reply names the defect and where it is, which is the input for
    the next attempt rather than a reason to guess.

    Args:
        doc_name: Document the edit targets.
        code: Python to execute, same environment as execute_code.
        label: What the edit is for; shown when listing checkpoints.
        policy: Overrides for the accept/reject thresholds, e.g.
            {"forbid_bbox_growth": false} for an edit that is meant to add
            material, or {"max_new_thin_faces": 2} to tolerate known slivers.
        objects: Names of the objects the edit may change. Narrows what is
            copied and judged; leave unset to cover the whole document.
    """
    res = get_freecad_connection().execute_guarded(
        doc_name, code, label, policy, objects
    )
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def cut_pocket(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    corners: list[list[float]],
    depth: float,
    tool_radius: float,
    z_top: float,
    through: bool = False,
    policy: dict[str, Any] | None = None,
) -> list[TextContent]:
    """Cut a pocket the way a mill does, and keep it only if the part stays sound.

    Prefer this over assembling a pocket from boxes and cylinders in
    execute_code. A round cutter cannot leave a square inside corner, so a
    hand-built pocket is both unmachinable and a source of notches and slivers
    where the primitives cross. Here the corners come out as arcs of
    `tool_radius` because the cut is what the cutter sweeps.

    Refused outright if the cutter does not fit the opening, rather than
    approximating a pocket no tool can produce.

    Args:
        doc_name: Document to edit.
        obj_name: Object to cut.
        corners: Finished opening as [[x0, y0], [x1, y1]].
        depth: How far down from z_top to cut.
        tool_radius: Cutter radius; also the radius of every inside corner.
        z_top: Surface the pocket starts from.
        through: Cut clear through instead of leaving a floor.
        policy: Overrides for the accept/reject thresholds.
    """
    res = get_freecad_connection().cut_pocket(
        doc_name, obj_name, corners, depth, tool_radius, z_top, through, policy
    )
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def cut_slot(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    path: list[list[float]],
    width: float,
    depth: float,
    z_top: float,
    policy: dict[str, Any] | None = None,
) -> list[TextContent]:
    """Cut a slot along a path, with the rounded ends a cutter leaves.

    `path` is the centreline in XY; the slot reaches half its width either side.
    A bent path is cut as one swept volume, so the bend has no notch in it --
    which is what fusing a box per segment produces.

    Args:
        doc_name: Document to edit.
        obj_name: Object to cut.
        path: Centreline as [[x, y], ...]; two points for a straight slot.
        width: Slot width, equal to the cutter diameter.
        depth: How far down from z_top to cut.
        z_top: Surface the slot starts from.
        policy: Overrides for the accept/reject thresholds.
    """
    res = get_freecad_connection().cut_slot(
        doc_name, obj_name, path, width, depth, z_top, policy
    )
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def pick_pixel(ctx: Context, x: int, y: int, radius: int = 0) -> list[TextContent]:
    """Name the face drawn at a pixel of the last screenshot.

    Use this whenever a defect is visible in a render: it turns the thing on
    screen into a face name, a surface type and a coordinate, instead of
    scanning the part hoping the numbers match what is in the picture.

    Coordinates match the screenshot: x from the left, y from the top. The
    screenshot may be scaled down from the view, in which case `view_size` in
    the reply gives the real size to scale the pixel by.

    Args:
        x: Pixel column.
        y: Pixel row.
        radius: Also try a ring this many pixels around the point, for a target
            too thin to hit dead-on.
    """
    res = get_freecad_connection().pick_pixel(x, y, radius)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def pick_region(
    ctx: Context, x0: int, y0: int, x1: int, y1: int, step: int = 8
) -> list[TextContent]:
    """List every face drawn inside a rectangle of the last screenshot.

    For "what is all this over here": a single pixel lands on one face, while a
    suspicious area is usually several. Faces come back most-visible first, with
    the pixel count each covers.

    Args:
        x0: Left edge of the rectangle.
        y0: Top edge.
        x1: Right edge.
        y1: Bottom edge.
        step: Pixels between samples; smaller finds thinner faces and costs more.
    """
    res = get_freecad_connection().pick_region(x0, y0, x1, y1, step)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def locate_point(ctx: Context, point: list[float]) -> list[TextContent]:
    """Say where a 3D point appears in the current view.

    The reverse of pick_pixel, for pointing at a defect an audit reported by
    coordinate. `drawn_there` names what is actually visible at that pixel,
    which is not the point itself when it sits inside the part or behind a wall.

    Args:
        point: [x, y, z] in model coordinates.
    """
    res = get_freecad_connection().locate_point(point)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def create_checkpoint(
    ctx: Context, doc_name: str, label: str = "", objects: list[str] | None = None
) -> list[TextContent]:
    """Copy the shapes so a later edit can be rolled back to this exact state.

    Undo is a stack the user also drives, and it stops working once its depth
    runs out; a checkpoint holds its own copies and restores the same way every
    time.

    Args:
        doc_name: Document to snapshot.
        label: What this state represents.
        objects: Names to copy; leave unset for every shape in the document.
    """
    res = get_freecad_connection().create_checkpoint(doc_name, label, objects)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def list_checkpoints(ctx: Context) -> list[TextContent]:
    """List the checkpoints available to restore."""
    res = get_freecad_connection().list_checkpoints()
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def restore_checkpoint(ctx: Context, checkpoint_id: str) -> list[TextContent]:
    """Put every shape back the way a checkpoint recorded it.

    Args:
        checkpoint_id: Id returned by create_checkpoint.
    """
    res = get_freecad_connection().restore_checkpoint(checkpoint_id)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def audit_shapes(
    ctx: Context,
    doc_name: str,
    checkpoint_id: str = "",
    policy: dict[str, Any] | None = None,
) -> list[TextContent]:
    """Report the defects in a document, and which ones an edit introduced.

    Without a checkpoint this is the current state of every shape. With one, the
    verdict covers only what changed since, so a part's pre-existing slivers are
    not charged to the edit being judged.

    Args:
        doc_name: Document to audit.
        checkpoint_id: Compare against this checkpoint instead of judging in
            isolation.
        policy: Overrides for the accept/reject thresholds.
    """
    res = get_freecad_connection().audit_shapes(doc_name, checkpoint_id, policy)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def measure_sweep(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    ray_axis: str,
    step_axis: str,
    step_from: float,
    step_to: float,
    step: float,
    at: float,
) -> list[TextContent]:
    """Scan a wall with parallel rays to find where a feature starts and stops.

    Reach for this instead of guessing a feature's extent from two `measure_probe`
    calls: a pocket that ends just above the sampled height reads as absent, and
    the conclusion "there is no cutout here" is then wrong by a millimetre. Sweep
    the range and the answer is in the data.

    `slices` holds the spans at every stop; `transitions` flags the stops where
    the span count changed, i.e. the Z where a hole opens or a wall closes.

    Args:
        doc_name: Document name.
        obj_name: Object to measure.
        ray_axis: Axis each ray travels along ("x", "y" or "z"); the ray spans the
            object's full extent on it.
        step_axis: Axis to walk between rays; must differ from ray_axis.
        step_from: First stop on step_axis.
        step_to: Last stop on step_axis.
        step: Distance between stops.
        at: Fixed coordinate on the remaining third axis.
    """
    res = get_freecad_connection().measure_sweep(
        doc_name, obj_name, ray_axis, step_axis, step_from, step_to, step, at
    )
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def measure_compare(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    rays: list[dict[str, list[float]]],
    before: list[dict[str, Any]] | None = None,
) -> list[TextContent]:
    """Probe several rays at once, and compare them against an earlier baseline.

    Call it before an edit to capture a baseline, then pass that call's `probes`
    list back as `before` afterwards. Any ray whose `grew` flag is true gained
    material, which after a repair edit means a fill reached past the region it
    was meant to restore. shape_check cannot see that: the solid stays valid and
    single, and the bounding box does not move.

    Args:
        doc_name: Document name.
        obj_name: Object to measure.
        rays: Rays as [{"start": [x, y, z], "end": [x, y, z]}, ...].
        before: `probes` from an earlier call, to diff against.
    """
    res = get_freecad_connection().measure_compare(doc_name, obj_name, rays, before)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def check_manufacturability(
    ctx: Context,
    doc_name: str = "",
    obj_name: str = "",
    file_path: str = "",
    r_min: float = 2.0,
    max_width: float = 0.3,
    min_edge: float = 0.1,
    vertical_only: bool = True,
) -> list[TextContent]:
    """Audit one solid for what a 3-axis mill cannot make and what a boolean left behind.

    Reports concave cylindrical faces below `r_min` (inside corners smaller than
    the cutter), sharp concave edges between non-tangent faces of any surface
    type (with `vertical_only` true, only vertical ones, which is what matters
    for pockets and walls milled from above), faces narrower than `max_width`
    and edges shorter than `min_edge`. The last two catch slivers: a fill that
    overhangs an arc by 0.04 mm, a tab bottom 0.14 mm wide. Those stay valid,
    single and invisible in a render, and a shop finds them by measuring.

    Pass `file_path` (STEP or BREP) to audit the exact file being sent out
    instead of a document object.

    Args:
        doc_name: Document name (ignored when file_path is given).
        obj_name: Object to audit (ignored when file_path is given).
        file_path: STEP/BREP file to audit instead of a document object.
        r_min: Smallest acceptable internal radius, mm.
        max_width: Faces narrower than this are reported, mm.
        min_edge: Edges shorter than this are reported, mm.
        vertical_only: Report only vertical sharp concave edges.
    """
    res = get_freecad_connection().check_manufacturability(
        doc_name, obj_name, file_path, r_min, max_width, min_edge, vertical_only
    )
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def section_profile(
    ctx: Context,
    doc_name: str,
    obj_name: str,
    axis: Literal["x", "y", "z"],
    value: float,
    min_segment: float = 0.1,
    max_jog_deg: float = 2.0,
    file_path: str = "",
) -> list[TextContent]:
    """Cut the shape with a plane and read its outline segment by segment.

    Every wire of the section comes back as ordered segments with curve type,
    length and end points, so a wall profile can be read as numbers rather than
    guessed from a screenshot. `short` lists segments under `min_segment`;
    `steps` lists the short ones whose neighbours are nearly parallel, the
    signature of a ledge left where two features were meant to meet flush.

    Args:
        doc_name: Document name.
        obj_name: Object to section.
        axis: Plane normal: "x", "y" or "z".
        value: Position of the plane along that axis.
        min_segment: Segments shorter than this are flagged, mm.
        max_jog_deg: Neighbours within this angle count as parallel, degrees.
        file_path: STEP/BREP file to section instead of a document object.
    """
    res = get_freecad_connection().section_profile(
        doc_name, obj_name, axis, value, min_segment, max_jog_deg, file_path
    )
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool()
def shape_diff(
    ctx: Context,
    doc_a: str,
    obj_a: str,
    doc_b: str,
    obj_b: str,
    file_a: str = "",
    file_b: str = "",
) -> list[TextContent]:
    """List the material one shape has and the other does not.

    Returns the solids of A−B and B−A with volume and bounding box, largest
    first, plus the shared volume. Use it to see exactly what a rebuild changed
    against the previous version, or what a hand edit added that the build
    script does not know about.

    Args:
        doc_a: Document of the first shape.
        obj_a: First object.
        doc_b: Document of the second shape (may equal doc_a).
        obj_b: Second object.
        file_a: STEP/BREP file for the first shape instead of a document object.
        file_b: STEP/BREP file for the second shape instead of a document object.
    """
    res = get_freecad_connection().shape_diff(doc_a, obj_a, doc_b, obj_b, file_a, file_b)
    return [TextContent(type="text", text=json.dumps(res, indent=2))]


@mcp.tool(structured_output=False)
def get_view(
    ctx: Context,
    view_name: ViewName,
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
def get_rpc_status(ctx: Context) -> list[TextContent]:
    """Get RPC and FreeCAD GUI-dispatch health.

    This tool does not use FreeCAD's GUI thread, so it remains available after
    a GUI operation times out. A ``stuck`` state identifies the operation that
    is still running and indicates that FreeCAD may need to be restarted.
    """
    return get_rpc_status_operation(get_freecad_connection())


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
    parser.add_argument("--freecadcmd", default=None, help="Command that starts headless FreeCAD for execute_code_headless, e.g. 'flatpak run --command=freecadcmd org.freecad.FreeCAD' (default: auto-detect PATH, then Flatpak)")
    args = parser.parse_args()
    state.only_text_feedback = args.only_text_feedback
    state.rpc_host = args.host
    from .headless import parse_command
    state.freecadcmd = parse_command(args.freecadcmd)
    logger.info(f"Only text feedback: {state.only_text_feedback}")
    logger.info(f"Connecting to FreeCAD RPC server at: {state.rpc_host}")
    mcp.run()
