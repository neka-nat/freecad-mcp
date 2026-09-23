import importlib
import math
import sys
import types
from collections.abc import Iterator

import pytest

from test_gui_dispatch import load_gui_dispatch


class Vec:
    """Just enough of FreeCAD.Vector for the checks."""

    def __init__(self, x: float, y: float, z: float):
        self.x, self.y, self.z = x, y, z

    def __add__(self, o: "Vec") -> "Vec":
        return Vec(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o: "Vec") -> "Vec":
        return Vec(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, k: float) -> "Vec":
        return Vec(self.x * k, self.y * k, self.z * k)

    def dot(self, o: "Vec") -> float:
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cross(self, o: "Vec") -> "Vec":
        return Vec(self.y * o.z - self.z * o.y, self.z * o.x - self.x * o.z, self.x * o.y - self.y * o.x)

    @property
    def Length(self) -> float:
        return math.sqrt(self.dot(self))

    def normalize(self) -> "Vec":
        n = self.Length
        self.x, self.y, self.z = self.x / n, self.y / n, self.z / n
        return self


class BBox:
    def __init__(self, x0, x1, y0, y1, z0, z1):
        self.XMin, self.XMax, self.YMin, self.YMax, self.ZMin, self.ZMax = x0, x1, y0, y1, z0, z1


class Plane:
    def __init__(self, normal: Vec):
        self.normal = normal

    def parameter(self, point: Vec) -> tuple[float, float]:
        return 0.0, 0.0


class Face:
    def __init__(self, area: float, perimeter: float, normal: Vec = Vec(0, 0, 1), bbox=BBox(0, 1, 0, 1, 0, 1), contains=lambda p: False):
        self.Area, self.Length, self.BoundBox = area, perimeter, bbox
        self.Surface = Plane(normal)
        self.Edges: list = []
        self.contains = contains

    def normalAt(self, u: float, v: float) -> Vec:
        return self.Surface.normal

    def isInside(self, p: Vec, tol: float, on_face: bool) -> bool:
        return self.contains(p)


class Edge:
    def __init__(self, length: float, start: Vec, direction: Vec, faces: list[Face] | None = None, curve: str = "Line", orientation: str = "Forward"):
        self.Length, self.start, self.direction, self.faces = length, start, direction, faces or []
        self.FirstParameter, self.LastParameter = 0.0, length
        self.Curve = type(curve, (), {})()
        # Which way the first face walks this edge: the sign of the dihedral
        # angle comes from that direction, not from the curve's own.
        self.Orientation = orientation
        e = start + direction * length
        self.BoundBox = BBox(min(start.x, e.x), max(start.x, e.x), min(start.y, e.y), max(start.y, e.y), min(start.z, e.z), max(start.z, e.z))

        for face in self.faces:
            face.Edges.append(self)

    def hashCode(self) -> int:
        return id(self)

    def valueAt(self, t: float) -> Vec:
        return self.start + self.direction * t

    def tangentAt(self, t: float) -> Vec:
        return self.direction


class Shape:
    def __init__(self, faces: list[Face], edges: list[Edge], inside=lambda p: False):
        # faces adjacent to edges are discovered through the edges, as the real check does
        seen = {id(f): f for f in faces}
        for e in edges:
            for f in e.faces:
                seen.setdefault(id(f), f)
        self.Faces, self.Edges, self._inside = list(seen.values()), edges, inside

    def isInside(self, p: Vec, tol: float, on_face: bool) -> bool:
        return self._inside(p)


@pytest.fixture
def dfm() -> Iterator[types.ModuleType]:
    with load_gui_dispatch() as dispatch:
        dispatch.FreeCAD.Vector = Vec
        part = types.ModuleType("Part")
        part.Face = Face
        sys.modules["Part"] = part
        sys.modules.pop("rpc_server.dfm", None)
        module = importlib.import_module("rpc_server.dfm")
        try:
            yield module
        finally:
            sys.modules.pop("rpc_server.dfm", None)
            sys.modules.pop("Part", None)


def test_thin_faces_flags_a_ledge_but_not_a_wall(dfm) -> None:
    ledge = Face(area=0.14 * 2.05, perimeter=2 * (0.14 + 2.05))   # tab bottom strip
    wall = Face(area=20 * 110, perimeter=2 * (20 + 110))
    groove_flank = Face(area=0.5 * 100, perimeter=2 * (0.5 + 100))  # 0.5 mm V-groove side
    found = dfm.thin_faces(Shape([ledge, wall, groove_flank], []), max_width=0.3)
    assert [round(f["width"], 2) for f in found] == [0.13]


def test_short_edges_catch_a_fill_that_overhangs_an_arc(dfm) -> None:
    # A concave fill that overhangs the outer arc by 0.042 mm leaves 0.042 mm edges
    # on a face that is 0.5 mm wide, so the width test alone would miss it.
    edges = [Edge(0.042, Vec(15.758, 84.15, 20), Vec(1, 0, 0)), Edge(20, Vec(15.8, 84, 0), Vec(0, 0, 1))]
    found = dfm.short_edges(Shape([], edges), min_length=0.1)
    assert len(found) == 1
    assert found[0]["length"] == 0.042
    assert found[0]["at"][2] == 20


def test_sharp_concave_edge_is_told_apart_from_a_convex_one(dfm) -> None:
    up = Vec(0, 0, 1)
    # L profile: floor z=0 for x<5, wall at x=5 rising above it (outward normal
    # -x). The floor walks this edge in +y, which is what makes the corner read
    # as inside.
    floor = Face(1, 4, up, contains=lambda p: p.x < 5 and abs(p.z) < 1e-9)
    wall_up = Face(1, 4, Vec(-1, 0, 0), contains=lambda p: abs(p.x - 5) < 1e-9 and p.z > 0)
    inside_corner = Edge(10, Vec(5, 0, 0), Vec(0, 1, 0), [floor, wall_up])
    # Box top edge: same two normals, but the top face walks it the other way,
    # and that alone is the difference between an inside and an outside corner.
    top = Face(1, 4, up, contains=lambda p: p.x > 0 and abs(p.z) < 1e-9)
    wall_down = Face(1, 4, Vec(-1, 0, 0), contains=lambda p: abs(p.x) < 1e-9 and p.z < 0)
    outside_corner = Edge(10, Vec(0, 0, 0), Vec(0, 1, 0), [top, wall_down],
                          orientation="Reversed")
    shape = Shape([], [inside_corner, outside_corner], inside=lambda p: pytest.fail("solid classifier must not be needed"))
    found = dfm.sharp_concave_edges(shape)
    assert len(found) == 1
    # A straight edge between two planes cannot change along its length, so it
    # is settled from its midpoint alone.
    assert found[0]["at"] == [5.0, 5.0, 0.0]
    assert found[0]["dihedral_deg"] == 90.0
    assert found[0]["direction"] == "horizontal"


def test_concavity_falls_back_to_the_solid_when_faces_cannot_place_the_point(dfm) -> None:
    up, side = Vec(0, 0, 1), Vec(-1, 0, 0)
    edge = Edge(10, Vec(5, 0, 0), Vec(0, 1, 0), [Face(1, 4, up), Face(1, 4, side)])
    shape = Shape([], [edge], inside=lambda p: True)
    assert len(dfm.sharp_concave_edges(shape)) == 1


def test_tangent_faces_are_not_sharp(dfm) -> None:
    n1, n2 = Vec(0, 0, 1), Vec(math.sin(math.radians(2)), 0, math.cos(math.radians(2)))
    edge = Edge(5, Vec(0, 0, 0), Vec(0, 1, 0), [Face(1, 4, n1), Face(1, 4, n2)])
    assert dfm.sharp_concave_edges(Shape([], [edge], inside=lambda p: True)) == []


def test_vertical_only_skips_floor_edges(dfm) -> None:
    up, side = Vec(0, 0, 1), Vec(-1, 0, 0)
    floor_edge = Edge(10, Vec(5, 0, 0), Vec(0, 1, 0), [Face(1, 4, up), Face(1, 4, side)])
    wall_edge = Edge(10, Vec(5, 5, 0), Vec(0, 0, 1),
                     [Face(1, 4, side), Face(1, 4, Vec(0, -1, 0))], orientation="Reversed")
    shape = Shape([], [floor_edge, wall_edge], inside=lambda p: True)
    found = dfm.sharp_concave_edges(shape, vertical_only=True)
    assert [f["direction"] for f in found] == ["vertical"]


class Wire:
    def __init__(self, edges: list[Edge]):
        self.OrderedEdges = edges
        self.Length = sum(e.Length for e in edges)

    def isClosed(self) -> bool:
        return True


class Arc(Edge):
    """Quarter arc whose chord is 45 degrees off its end tangents."""

    def __init__(self, start: Vec, t_in: Vec, t_out: Vec, length: float):
        super().__init__(length, start, t_in, curve="Circle")
        self.t_in, self.t_out = t_in, t_out

    def tangentAt(self, t: float) -> Vec:
        return self.t_in if t == self.FirstParameter else self.t_out


def test_section_profile_flags_a_leftover_that_blends_into_neither_neighbour(dfm) -> None:
    # Real numbers from a cavity corner built by filling R2 and cutting R3 with
    # slightly different centres: the 0.042 segment runs along +Y, the wall along
    # X, and the arc leaves at 9.6 degrees off X, so nothing there is tangent.
    wall = Edge(8.7, Vec(13.8, 13.65, 10), Vec(1, 0, 0))
    leftover = Edge(0.042, Vec(13.8, 13.692, 10), Vec(0, -1, 0))
    arc = Arc(Vec(10.342, 17.15, 10), Vec(-0.167, -0.986, 0), Vec(0.986, 0.167, 0), 5.7171)
    back = Edge(7.96, Vec(10.3, 25.11, 10), Vec(0, -1, 0))
    shape = types.SimpleNamespace(slice=lambda normal, value: [Wire([wall, leftover, arc, back])])
    result = dfm.section_profile(shape, "z", 10.0)
    assert [x["index"] for x in result["short"]] == [1]
    assert [x["index"] for x in result["steps"]] == [1]
    # 90 degrees against the wall, 170 against the arc that should have blended
    assert result["steps"][0]["tangent_break_deg"] == 170.39
    assert [x["curve"] for x in result["wires"][0]["segments"]] == ["Line", "Line", "Circle", "Line"]


def test_section_profile_leaves_a_fillet_alone(dfm) -> None:
    # Same corner done right: the arc leaves the wall tangentially, so the short
    # blend segment breaks the tangent at neither joint.
    wall = Edge(8.7, Vec(13.8, 13.65, 10), Vec(1, 0, 0))
    blend = Edge(0.05, Vec(13.75, 13.65, 10), Vec(-1, 0, 0))
    arc = Arc(Vec(10.3, 17.1, 10), Vec(0, -1, 0), Vec(-1, 0, 0), 5.42)
    back = Edge(7.96, Vec(10.3, 25.11, 10), Vec(0, -1, 0))
    shape = types.SimpleNamespace(slice=lambda normal, value: [Wire([wall, blend, arc, back])])
    result = dfm.section_profile(shape, "z", 10.0)
    assert [x["index"] for x in result["short"]] == [1]
    assert result["steps"] == []


def test_section_profile_flags_a_jog_between_parallel_walls(dfm) -> None:
    # A fill box 0.04 mm too wide: the outline steps sideways between two runs
    # that are parallel, so the short segment is square to both of them.
    a = Edge(10, Vec(15.8, 0, 10), Vec(0, 1, 0))
    jog = Edge(0.04, Vec(15.8, 10, 10), Vec(1, 0, 0))
    b = Edge(10, Vec(15.84, 10, 10), Vec(0, 1, 0))
    back = Edge(20, Vec(15.84, 20, 10), Vec(0, -1, 0))
    shape = types.SimpleNamespace(slice=lambda normal, value: [Wire([a, jog, b, back])])
    result = dfm.section_profile(shape, "z", 10.0)
    assert [x["index"] for x in result["steps"]] == [1]
    assert result["steps"][0]["tangent_break_deg"] == 90.0


def test_section_profile_does_not_flag_a_corner_chamfer(dfm) -> None:
    # A 45 degree chamfer across a square corner: it breaks the tangent at both
    # joints by 45 degrees, which a wider tolerance is meant to accept.
    a = Edge(10, Vec(0, 0, 0), Vec(1, 0, 0))
    chamfer = Edge(0.0707, Vec(9.95, 0, 0), Vec(0.7071, 0.7071, 0))
    b = Edge(10, Vec(10, 0.05, 0), Vec(0, 1, 0))
    back = Edge(14, Vec(10, 10.05, 0), Vec(-1, -1, 0))
    shape = types.SimpleNamespace(slice=lambda normal, value: [Wire([a, chamfer, b, back])])
    result = dfm.section_profile(shape, "z", 0.0, max_jog_deg=60.0)
    assert len(result["short"]) == 1
    assert result["steps"] == []


def test_shape_diff_lists_material_each_side_has_alone(dfm) -> None:
    class Solid:
        def __init__(self, volume: float, bbox: BBox):
            self.Volume, self.BoundBox = volume, bbox

    class Body:
        def __init__(self, own: list[Solid], shared: float):
            self.own, self.shared = own, shared

        def cut(self, other: "Body") -> "Body":
            return types.SimpleNamespace(Solids=self.own, Volume=sum(s.Volume for s in self.own))

        def common(self, other: "Body") -> object:
            return types.SimpleNamespace(Volume=self.shared)

    a = Body([Solid(73.1, BBox(57.8, 60.8, 81.4, 86.6, 0, 20)), Solid(0.0004, BBox(0, 0, 0, 0, 0, 0))], 54000.0)
    b = Body([Solid(21.5, BBox(-2.5, 0.5, 5.6, 8.6, 0, 20))], 54000.0)
    result = dfm.shape_diff(a, b)
    assert result["only_in_a"] == [{"volume": 73.1, "bbox": [57.8, 60.8, 81.4, 86.6, 0, 20]}]
    assert result["only_in_b"][0]["volume"] == 21.5
    assert result["common_volume"] == 54000.0


def test_load_shape_rejects_missing_object(dfm) -> None:
    doc = types.SimpleNamespace(getObject=lambda name: None)
    sys.modules["FreeCAD"].getDocument = lambda name: doc
    with pytest.raises(ValueError, match="no object 'Nope'"):
        dfm.load_shape("Doc", "Nope")


def test_section_profile_survives_reversed_edge_order(dfm) -> None:
    # same jog as above but the arc is stored end-to-start, as OrderedEdges may do
    wall = Edge(10, Vec(15.8, 0, 10), Vec(0, 1, 0))
    jog = Edge(0.04, Vec(15.8, 10, 10), Vec(1, 0, 0))
    arc = Arc(Vec(12.84, 13, 10), Vec(1, 0, 0), Vec(0, -1, 0), 4.71)   # runs from far end back to the jog
    back = Edge(20, Vec(12.84, 13, 10), Vec(0, -1, 0))
    shape = types.SimpleNamespace(slice=lambda normal, value: [Wire([wall, jog, arc, back])])
    assert [s["index"] for s in dfm.section_profile(shape, "z", 10.0)["steps"]] == [1]
