import importlib
import sys
import types
from collections.abc import Iterator

import pytest

from test_gui_dispatch import load_gui_dispatch


class FakeVertex:
    def __init__(self, point: tuple[float, float, float]):
        self.Point = point


class FakeEdge:
    def __init__(self, verts: list[tuple[float, float, float]]):
        self.Vertexes = [FakeVertex(v) for v in verts]


class FakeCommon:
    def __init__(self, edges: list[FakeEdge]):
        self.Edges = edges


class FakeLine:
    """A segment that reports the material it crosses, taken from the fixture."""

    def __init__(self, start, end, solid_spans: list[tuple[float, float]], axis: int):
        self.start, self.end = start, end
        self.solid_spans, self.axis = solid_spans, axis

    def common(self, shape) -> FakeCommon:
        lo = min(self.start[self.axis], self.end[self.axis])
        hi = max(self.start[self.axis], self.end[self.axis])
        edges = []
        for s0, s1 in self.solid_spans:
            a, b = max(s0, lo), min(s1, hi)
            if b > a:
                p0 = list(self.start)
                p1 = list(self.start)
                p0[self.axis], p1[self.axis] = a, b
                edges.append(FakeEdge([tuple(p0), tuple(p1)]))
        return FakeCommon(edges)


@pytest.fixture
def measure() -> Iterator[tuple[types.ModuleType, dict]]:
    with load_gui_dispatch() as dispatch:
        state = {"spans": [], "axis": 0}
        shape = types.SimpleNamespace(isNull=lambda: False)
        doc = types.SimpleNamespace(getObject=lambda name: types.SimpleNamespace(Shape=shape))
        dispatch.FreeCAD.getDocument = lambda name: doc
        dispatch.FreeCAD.Vector = lambda *a: tuple(a)
        part = types.ModuleType("Part")
        part.makeLine = lambda s, e: FakeLine(s, e, state["spans"], state["axis"])
        sys.modules["Part"] = part
        sys.modules.pop("rpc_server.measure", None)
        module = importlib.import_module("rpc_server.measure")
        try:
            yield module, state
        finally:
            sys.modules.pop("rpc_server.measure", None)
            sys.modules.pop("Part", None)


def test_probe_reports_ribs_as_spans_and_slots_as_gaps(measure) -> None:
    module, state = measure
    # A vented wall: ribs at 20.73..24.73 and 26.73..30.73, a 2 mm slot between.
    state["spans"] = [(20.73, 24.73), (26.73, 30.73)]
    result = module.probe("Doc", "Korpus", [15, 12.4, 12.4], [35, 12.4, 12.4])
    assert result["axis"] == "x"
    assert result["spans"] == [[20.73, 24.73], [26.73, 30.73]]
    assert result["gaps"] == [[24.73, 26.73, 2.0]]
    assert result["material"] == 8.0


def test_compare_flags_a_fill_that_added_material(measure) -> None:
    module, state = measure
    state["spans"] = [(11.15, 13.65)]
    rays = [{"start": [22.73, 5, 16.0], "end": [22.73, 20, 16.0]}]
    state["axis"] = 1
    baseline = module.compare("Doc", "Korpus", rays)["probes"]
    # The repair fill was 0.5 mm wider than the 2.5 mm wall on each side.
    state["spans"] = [(10.65, 14.15)]
    result = module.compare("Doc", "Korpus", rays, baseline)
    verdict = result["verdicts"][0]
    assert verdict["material_was"] == 2.5
    assert verdict["material_now"] == 3.5
    assert verdict["delta"] == 1.0
    assert verdict["grew"] is True


def test_compare_does_not_flag_a_cut(measure) -> None:
    module, state = measure
    state["spans"] = [(20.73, 24.73), (26.73, 30.73)]
    rays = [{"start": [15, 12.4, 12.4], "end": [35, 12.4, 12.4]}]
    baseline = module.compare("Doc", "Korpus", rays)["probes"]
    state["spans"] = [(20.73, 24.73)]
    verdict = module.compare("Doc", "Korpus", rays, baseline)["verdicts"][0]
    assert verdict["grew"] is False
    assert verdict["spans_changed"] is True


def test_compare_refuses_a_baseline_from_a_different_ray(measure) -> None:
    module, state = measure
    state["spans"] = [(20.73, 24.73)]
    baseline = module.compare(
        "Doc", "Korpus", [{"start": [15, 12.4, 12.4], "end": [35, 12.4, 12.4]}]
    )["probes"]
    # Same index, but this ray runs along Y: the pair says nothing about growth.
    state["axis"] = 1
    verdict = module.compare(
        "Doc", "Korpus", [{"start": [22.73, 5, 16.0], "end": [22.73, 20, 16.0]}], baseline
    )["verdicts"][0]
    assert verdict["note"] == "baseline is a different ray"
    assert "grew" not in verdict


def test_probe_rejects_a_missing_object(measure) -> None:
    module, _ = measure
    doc = types.SimpleNamespace(getObject=lambda name: None)
    sys.modules["FreeCAD"].getDocument = lambda name: doc
    with pytest.raises(ValueError, match="no object 'Nope'"):
        module.probe("Doc", "Nope", [0, 0, 0], [1, 0, 0])
