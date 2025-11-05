# modeling_tools.py: advanced modeling operations for FreeCAD MCP
from mcp.types import TextContent, ImageContent
from mcp.server.fastmcp import Context

def create_loft(ctx: Context, freecad_connection, add_screenshot_helper, doc_name: str, sketch_names: list[str], result_name: str, solid: bool = True, ruled: bool = False) -> list[TextContent | ImageContent]:
    """Create a loft between multiple sketches"""
    sketches_list = ", ".join([f"'{name}'" for name in sketch_names])
    solid_flag = 'True' if solid else 'False'
    ruled_flag = 'True' if ruled else 'False'
    code = f"""
import FreeCAD as App
import Part
from FreeCAD import Base
doc = App.getDocument('{doc_name}')
if not doc:
    print('ERROR: Document {doc_name} not found')
else:
    sketches = [{sketches_list}]
    loft = doc.addObject('Part::Loft', '{result_name}')
    loft.Sections = sketches
    loft.Solid = {solid_flag}
    loft.Ruled = {ruled_flag}
    doc.recompute()
    print('SUCCESS: Loft {result_name} created')
"""
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    if res.get('success') and 'SUCCESS' in res.get('message',''):
        return add_screenshot_helper([TextContent(type='text', text=res['message'])], screenshot)
    else:
        err = res.get('error') or res.get('message','Unknown error')
        return add_screenshot_helper([TextContent(type='text', text=f'Failed to create loft: {err}')], screenshot)

def create_revolve(ctx: Context, freecad_connection, add_screenshot_helper, doc_name: str, sketch_name: str, axis: dict[str, dict[str, float]], angle: float, result_name: str) -> list[TextContent | ImageContent]:
    """Create a revolve of a sketch around a given axis"""
    px,py,pz = axis['point']['x'], axis['point']['y'], axis['point']['z']
    dx,dy,dz = axis['direction']['x'], axis['direction']['y'], axis['direction']['z']
    code = f"""
import FreeCAD as App
import Part
from FreeCAD import Base
doc = App.getDocument('{doc_name}')
if not doc:
    print('ERROR: Document {doc_name} not found')
else:
    rev = doc.addObject('Part::Revolution', '{result_name}')
    rev.Profile = '{sketch_name}'
    rev.Axis = (Base.Vector({px},{py},{pz}), Base.Vector({dx},{dy},{dz}))
    rev.Angle = {angle}
    doc.recompute()
    print('SUCCESS: Revolve {result_name} created')
"""
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    if res.get('success') and 'SUCCESS' in res.get('message',''):
        return add_screenshot_helper([TextContent(type='text', text=res['message'])], screenshot)
    else:
        err = res.get('error') or res.get('message','Unknown error')
        return add_screenshot_helper([TextContent(type='text', text=f'Failed to create revolve: {err}')], screenshot)

def create_sweep(ctx: Context, freecad_connection, add_screenshot_helper, doc_name: str, profile_sketch: str, path_sketch: str, result_name: str) -> list[TextContent | ImageContent]:
    """Sweep a profile along a path"""
    code = f"""
import FreeCAD as App
import Part
from FreeCAD import Base
doc = App.getDocument('{doc_name}')
if not doc:
    print('ERROR: Document {doc_name} not found')
else:
    sweep = doc.addObject('Part::Sweep', '{result_name}')
    sweep.Spin = False
    sweep.Solid = True
    sweep.Sections = ['{profile_sketch}']
    sweep.Spine = ['{path_sketch}']
    doc.recompute()
    print('SUCCESS: Sweep {result_name} created')
"""
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    if res.get('success') and 'SUCCESS' in res.get('message',''):
        return add_screenshot_helper([TextContent(type='text', text=res['message'])], screenshot)
    else:
        err = res.get('error') or res.get('message','Unknown error')
        return add_screenshot_helper([TextContent(type='text', text=f'Failed to create sweep: {err}')], screenshot)

def create_spline_3d(ctx: Context, freecad_connection, add_screenshot_helper, doc_name: str, points: list[dict[str, float]], spline_name: str, closed: bool = False) -> list[TextContent | ImageContent]:
    """Create a 3D spline through control points"""
    vecs = ', '.join([f'App.Vector({pt["x"]},{pt["y"]},{pt["z"]})' for pt in points])
    close_flag = 'True' if closed else 'False'
    code = f"""
import FreeCAD as App
import Part
from FreeCAD import Base
doc = App.getDocument('{doc_name}')
if not doc:
    print('ERROR: Document {doc_name} not found')
else:
    spline = doc.addObject('Part::Spline', '{spline_name}')
    spline.Placement = App.Placement()
    spline.Shape = Part.BSplineCurve([{vecs}], None, None, {close_flag}).toShape()
    doc.recompute()
    print('SUCCESS: Spline {spline_name} created')
"""
    res = freecad_connection.execute_code(code)
    screenshot = freecad_connection.get_active_screenshot()
    if res.get('success') and 'SUCCESS' in res.get('message',''):
        return add_screenshot_helper([TextContent(type='text', text=res['message'])], screenshot)
    else:
        err = res.get('error') or res.get('message','Unknown error')
        return add_screenshot_helper([TextContent(type='text', text=f'Failed to create spline: {err}')], screenshot)








