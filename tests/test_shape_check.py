import importlib
import sys
import types
from collections.abc import Iterator

import pytest

from test_gui_dispatch import load_gui_dispatch


class FakeBoundBox:
    def __init__(self, bounds: tuple[float, float, float, float, float, float]):
        (self.XMin, self.XMax, self.YMin, self.YMax, self.ZMin, self.ZMax) = bounds


class FakeShape:
    def __init__(
        self,
        volume: float = 1.0,
        solids: int = 1,
        valid: bool = True,
        null: bool = False,
        area: float = 6.0,
        bounds: tuple[float, float, float, float, float, float] = (0, 1, 0, 1, 0, 1),
    ):
        self.volume, self.solids, self.valid, self.null = volume, solids, valid, null
        self.area, self.bounds = area, bounds
        self.validity_checks = 0

    def isNull(self) -> bool:
        return self.null

    def hashCode(self) -> int:
        return hash((self.volume, self.solids))

    @property
    def Area(self) -> float:
        return self.area

    @property
    def BoundBox(self) -> FakeBoundBox:
        return FakeBoundBox(self.bounds)

    @property
    def Solids(self) -> list:
        return [object()] * self.solids

    @property
    def Faces(self) -> list:
        return [object()] * (6 * self.solids)

    @property
    def Volume(self) -> float:
        return self.volume

    def isValid(self) -> bool:
        self.validity_checks += 1
        return self.valid


@pytest.fixture
def shape_check() -> Iterator[tuple[types.ModuleType, types.SimpleNamespace]]:
    with load_gui_dispatch() as dispatch:
        doc = types.SimpleNamespace(Objects=[])
        dispatch.FreeCAD.listDocuments = lambda: {"Doc": doc}
        sys.modules.pop("rpc_server.shape_check", None)
        module = importlib.import_module("rpc_server.shape_check")
        try:
            yield module, doc
        finally:
            sys.modules.pop("rpc_server.shape_check", None)


def obj(name: str, shape: FakeShape) -> types.SimpleNamespace:
    return types.SimpleNamespace(Name=name, Shape=shape)


def test_unchanged_shapes_are_not_validated(shape_check) -> None:
    module, doc = shape_check
    box = FakeShape()
    doc.Objects = [obj("Box", box), types.SimpleNamespace(Name="Text")]
    before = module.snapshot()
    assert set(before) == {"Doc.Box"}
    result = module.check(before)
    assert result == {"changed": [], "warnings": []}
    assert box.validity_checks == 0


def test_changed_valid_single_solid_is_reported_without_warning(shape_check) -> None:
    module, doc = shape_check
    box = FakeShape(volume=1.0)
    doc.Objects = [obj("Box", box)]
    before = module.snapshot()
    box.volume = 2.0
    result = module.check(before)
    assert result["warnings"] == []
    assert [c["object"] for c in result["changed"]] == ["Doc.Box"]
    assert result["changed"][0]["valid"] is True
    assert result["changed"][0]["was"]["volume"] == 1.0
    assert box.validity_checks == 1


def test_invalid_split_null_and_removed_shapes_warn(shape_check) -> None:
    module, doc = shape_check
    lid, body, gone = FakeShape(), FakeShape(volume=5.0), FakeShape()
    doc.Objects = [obj("Lid", lid), obj("Body", body), obj("Gone", gone)]
    before = module.snapshot()
    lid.valid = False
    lid.volume = 0.9
    body.solids = 2
    doc.Objects = [obj("Lid", lid), obj("Body", body), obj("New", FakeShape(null=True))]
    result = module.check(before)
    assert result["warnings"] == [
        "Doc.Gone: object removed",
        "Doc.Body: 2 solids (was 1)",
        "Doc.Lid: shape is INVALID",
        "Doc.New: null shape",
    ]
    assert [c["object"] for c in result["changed"]] == ["Doc.Body", "Doc.Lid", "Doc.New"]


def test_new_compound_reports_its_solid_count(shape_check) -> None:
    module, doc = shape_check
    before = module.snapshot()
    doc.Objects = [obj("Bolts", FakeShape(solids=8))]
    result = module.check(before)
    assert result["warnings"] == ["Doc.Bolts: 8 solids"]


def test_broken_shape_property_does_not_abort_the_check(shape_check) -> None:
    module, doc = shape_check

    class ExplodingShape(FakeShape):
        @property
        def Volume(self) -> float:
            raise RuntimeError("no mass properties")

    doc.Objects = [obj("Bad", ExplodingShape())]
    before = module.snapshot()
    assert before["Doc.Bad"] == {"error": "RuntimeError: no mass properties"}
    doc.Objects = [obj("Bad", ExplodingShape(volume=2.0))]
    assert module.check(before) == {"changed": [], "warnings": []}


def test_a_fuse_reaching_outside_the_old_bounds_warns(shape_check) -> None:
    module, doc = shape_check
    wall = FakeShape(volume=100.0, bounds=(0, 50, 11.15, 13.65, 0, 20))
    doc.Objects = [obj("Korpus", wall)]
    before = module.snapshot()
    # A fill box wider than the wall it repairs: the solid stays valid and single,
    # and the volume rises only slightly, but material now sits outside the part.
    wall.volume = 104.0
    wall.bounds = (0, 50, 10.65, 14.15, 0, 20)
    result = module.check(before)
    assert result["warnings"] == [
        "Doc.Korpus: bounding box grew (YMin 11.15->10.65, YMax 13.65->14.15)"
    ]


def test_a_cut_inside_the_old_bounds_does_not_warn(shape_check) -> None:
    module, doc = shape_check
    wall = FakeShape(volume=100.0, bounds=(0, 50, 11.15, 13.65, 0, 20))
    doc.Objects = [obj("Korpus", wall)]
    before = module.snapshot()
    wall.volume = 91.0
    wall.area = 7.5
    result = module.check(before)
    assert result["warnings"] == []


def test_wires_without_faces_do_not_warn_about_solids(shape_check) -> None:
    module, doc = shape_check
    before = module.snapshot()

    class WireShape(FakeShape):
        @property
        def Faces(self) -> list:
            return []

    doc.Objects = [obj("Polyline", WireShape(solids=0))]
    result = module.check(before)
    assert result["warnings"] == []
    assert result["changed"][0]["object"] == "Doc.Polyline"


def test_a_failing_document_listing_degrades_to_no_findings(shape_check) -> None:
    module, _ = shape_check

    def broken():
        raise RuntimeError("document list unavailable")

    module.FreeCAD.listDocuments = broken
    # The check is a diagnostic; it must not become the reason a script fails.
    assert module.snapshot() == {}
    assert module.check({"Doc.Korpus": {"null": False}})["warnings"] == []
