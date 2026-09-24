import importlib
import sys
import types
from collections.abc import Iterator

import pytest

from test_gui_dispatch import load_gui_dispatch


class Face:
    def __init__(self, area, centre, normal=(0, 0, 1)):
        self.Area = area
        self.Edges = [object()] * 4
        self.CenterOfMass = types.SimpleNamespace(x=centre[0], y=centre[1], z=centre[2])
        self.BoundBox = types.SimpleNamespace(
            XMin=0.0, XMax=10.0, YMin=0.0, YMax=10.0, ZMin=0.0, ZMax=0.0
        )
        plane = type("Plane", (), {})()
        plane.Axis = types.SimpleNamespace(x=normal[0], y=normal[1], z=normal[2])
        self.Surface = plane


class View:
    """A view that draws one face over a known rectangle of pixels."""

    def __init__(self, size=(100, 80), drawn=None):
        self.size = size
        # {(x, y): info}; anything else is background.
        self.drawn = drawn or {}
        self.screen = {}

    def getSize(self):
        return self.size

    def getObjectInfo(self, xy):
        return self.drawn.get(tuple(xy))

    def getPointOnScreen(self, vec):
        return self.screen[(vec.x, vec.y, vec.z)]


def _info(x, y, z, obj="Body", comp="Face3"):
    return {"x": x, "y": y, "z": z, "Object": obj, "Component": comp,
            "Document": "Doc"}


@pytest.fixture
def picking() -> Iterator[tuple[types.ModuleType, View]]:
    with load_gui_dispatch() as dispatch:
        view = View()
        gui_doc = types.SimpleNamespace(ActiveView=view)
        gui = types.ModuleType("FreeCADGui")
        gui.ActiveDocument = gui_doc
        gui.setActiveDocument = lambda name: None
        sys.modules["FreeCADGui"] = gui

        body = types.SimpleNamespace(
            Shape=types.SimpleNamespace(Faces=[Face(1.0, (0, 0, 0)),
                                              Face(2.0, (1, 1, 1)),
                                              Face(42.5, (5.0, 5.0, 10.0))])
        )
        doc = types.SimpleNamespace(Name="Doc", getObject=lambda n: body if n == "Body" else None)
        dispatch.FreeCAD.ActiveDocument = doc
        dispatch.FreeCAD.getDocument = lambda n: doc if n == "Doc" else None
        dispatch.FreeCAD.Vector = lambda x, y, z: types.SimpleNamespace(x=x, y=y, z=z)

        sys.modules.pop("rpc_server.picking", None)
        module = importlib.import_module("rpc_server.picking")
        try:
            yield module, view
        finally:
            sys.modules.pop("rpc_server.picking", None)
            sys.modules.pop("FreeCADGui", None)


def test_a_pixel_resolves_to_a_face_with_its_geometry(picking) -> None:
    module, view = picking
    view.drawn[(50, 40)] = _info(12.5, 7.25, 3.0)
    hit = module.pick(50, 40)
    assert hit["hit"] is True
    assert hit["object"] == "Body"
    assert hit["component"] == "Face3"
    assert hit["at"] == [12.5, 7.25, 3.0]
    # The face itself, so the reply says what was hit and not just where.
    assert hit["face"]["area"] == 42.5
    assert hit["face"]["surface"] == "Plane"
    assert hit["face"]["centre"] == [5.0, 5.0, 10.0]


def test_a_pixel_from_a_scaled_screenshot_is_scaled_back(picking) -> None:
    module, view = picking
    # Screenshots come back smaller than the view, so a pixel read off one is
    # not the pixel the view would pick: without scaling it lands half a screen
    # away and reports a confident hit on the wrong face.
    view.drawn[(50, 40)] = _info(1.0, 2.0, 3.0)
    assert module.pick(25, 20, image_width=50, image_height=40)["hit"] is True
    # The same pixel taken at face value misses.
    assert module.pick(25, 20)["hit"] is False


def test_a_region_from_a_scaled_screenshot_is_scaled_back(picking) -> None:
    module, view = picking
    for x in range(40, 61, 2):
        for y in range(30, 51, 2):
            view.drawn[(x, y)] = _info(0.0, 0.0, 0.0, comp="Face1")
    out = module.pick_region(20, 15, 30, 25, step=1, image_width=50, image_height=40)
    assert out["rect"] == [40, 30, 60, 50]
    assert [f["component"] for f in out["faces"]] == ["Face1"]


def test_empty_space_is_reported_as_a_miss(picking) -> None:
    module, _ = picking
    assert module.pick(10, 10)["hit"] is False


def test_a_radius_finds_a_face_too_thin_to_hit_dead_on(picking) -> None:
    module, view = picking
    # A sliver one pixel wide, two pixels off where the caller aimed.
    view.drawn[(52, 40)] = _info(1.0, 2.0, 3.0)
    missed = module.pick(50, 40)
    assert missed["hit"] is False
    found = module.pick(50, 40, radius=2)
    assert found["hit"] is True
    assert found["pixel"] == [52, 40]


def test_a_pixel_outside_the_view_is_not_picked(picking) -> None:
    module, view = picking
    view.drawn[(500, 500)] = _info(1.0, 1.0, 1.0)
    assert module.pick(500, 500)["hit"] is False


def test_a_region_reports_faces_by_how_much_they_cover(picking) -> None:
    module, view = picking
    for x in range(0, 40, 4):
        for y in range(0, 40, 4):
            view.drawn[(x, y)] = _info(0.0, 0.0, 0.0, comp="Face1")
    view.drawn[(0, 0)] = _info(9.0, 9.0, 9.0, comp="Face2")
    out = module.pick_region(0, 0, 39, 39, step=4)
    assert [f["component"] for f in out["faces"]] == ["Face1", "Face2"]
    assert out["faces"][0]["pixels"] > out["faces"][1]["pixels"]


def test_a_point_inside_the_part_is_not_called_visible(picking) -> None:
    module, view = picking
    view.screen[(5.0, 5.0, 2.0)] = (25.0, 30.0)
    # A nearer wall is what that pixel actually draws.
    view.drawn[(25, 30)] = _info(5.0, 5.0, 8.0, comp="Face1")
    out = module.locate([5.0, 5.0, 2.0])
    assert out["pixel"] == [25, 30]
    assert out["on_screen"] is True
    assert out["drawn_there"]["at"] == [5.0, 5.0, 8.0]


def test_a_point_off_screen_says_so(picking) -> None:
    module, view = picking
    view.screen[(1.0, 1.0, 1.0)] = (-40.0, 900.0)
    out = module.locate([1.0, 1.0, 1.0])
    assert out["on_screen"] is False
    assert "drawn_there" not in out
