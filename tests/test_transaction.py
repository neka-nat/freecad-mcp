import importlib
import sys
import types
from collections.abc import Iterator

import pytest

from test_gui_dispatch import load_gui_dispatch


class Shape:
    """A shape whose measurements the test dictates."""

    def __init__(self, volume=100.0, solids=1, valid=True, bbox=None,
                 thin=0, short=0, sharp=0):
        self.Volume, self.Area = volume, 200.0
        self.Solids = [object()] * solids
        self.Faces = [object()] * 6
        self._valid = valid
        b = bbox or (0.0, 10.0, 0.0, 10.0, 0.0, 10.0)
        self.BoundBox = types.SimpleNamespace(
            XMin=b[0], XMax=b[1], YMin=b[2], YMax=b[3], ZMin=b[4], ZMax=b[5]
        )
        self.thin, self.short, self.sharp = thin, short, sharp

    def isNull(self):
        return False

    def isValid(self):
        return self._valid

    def copy(self):
        return self


def _obj(name, shape):
    return types.SimpleNamespace(Name=name, Shape=shape)


@pytest.fixture
def tx() -> Iterator[tuple[types.ModuleType, types.SimpleNamespace]]:
    with load_gui_dispatch() as dispatch:
        doc = types.SimpleNamespace(
            Name="Doc",
            Objects=[_obj("Body", Shape())],
            FileName="/tmp/doc.FCStd",
            saveCopy=lambda path: None,
            recompute=lambda: None,
            getObject=lambda n: next((o for o in doc.Objects if o.Name == n), None),
        )
        dispatch.FreeCAD.getDocument = lambda name: doc
        dispatch.FreeCAD.openDocument = lambda path, hidden=False: doc
        dispatch.FreeCAD.closeDocument = lambda name: None

        sys.modules.pop("rpc_server.transaction", None)
        module = importlib.import_module("rpc_server.transaction")
        # Patch the reference the module already bound: replacing the entry in
        # sys.modules leaves `from rpc_server import dfm` pointing at whichever
        # dfm an earlier test imported.
        module.connectivity = types.SimpleNamespace(
            count_islands=lambda s: getattr(s, "pieces", 1),
        )
        module.dfm = types.SimpleNamespace(
            thin_faces=lambda s, w: [{"width": 0.1, "at": [1, 2, 3]}] * s.thin,
            short_edges=lambda s, l: [{"length": 0.01, "at": [1, 2, 3]}] * s.short,
            sharp_concave_edges=lambda s: [{"at": [1, 2, 3]}] * s.sharp,
        )
        try:
            yield module, doc
        finally:
            sys.modules.pop("rpc_server.transaction", None)


def test_a_split_solid_is_rejected_and_rolled_back(tx) -> None:
    module, doc = tx
    cp = module.checkpoint("Doc", "before")

    # The edit leaves the body in two pieces: valid, but no longer one part.
    doc.Objects[0].Shape = Shape(volume=95.0, solids=2)
    report = module.audit("Doc", cp["checkpoint_id"])

    assert report["verdict"] == "reject"
    codes = [e["code"] for e in report["errors"]]
    assert "SOLID_COUNT_CHANGED" in codes


def test_a_clean_cut_passes(tx) -> None:
    module, doc = tx
    cp = module.checkpoint("Doc", "before")
    doc.Objects[0].Shape = Shape(volume=80.0)
    report = module.audit("Doc", cp["checkpoint_id"])
    assert report["verdict"] == "pass"
    assert report["changed"][0]["volume"] == 80.0
    assert report["changed"][0]["volume_before"] == 100.0


def test_new_slivers_are_rejected_but_old_ones_are_not(tx) -> None:
    module, doc = tx
    doc.Objects[0].Shape = Shape(thin=4)
    cp = module.checkpoint("Doc", "already has slivers")

    # Same four slivers, less material: the edit added none of them.
    doc.Objects[0].Shape = Shape(volume=90.0, thin=4)
    assert module.audit("Doc", cp["checkpoint_id"])["verdict"] == "pass"

    doc.Objects[0].Shape = Shape(volume=90.0, thin=5)
    report = module.audit("Doc", cp["checkpoint_id"])
    assert report["verdict"] == "reject"
    assert [e["code"] for e in report["errors"]] == ["NEW_THIN_FACES"]


def test_an_edit_that_grows_the_part_is_rejected(tx) -> None:
    module, doc = tx
    cp = module.checkpoint("Doc", "before")
    # A fill 0.5 mm wider than the wall it repairs: still one valid solid.
    doc.Objects[0].Shape = Shape(volume=110.0, bbox=(0, 10.5, 0, 10, 0, 10))
    report = module.audit("Doc", cp["checkpoint_id"])
    assert report["verdict"] == "reject"
    assert [e["code"] for e in report["errors"]] == ["BBOX_GREW"]


def test_guarded_restores_the_shape_a_failing_script_left(tx) -> None:
    module, doc = tx
    ns = {"doc": doc, "Shape": Shape}
    report = module.guarded(
        "Doc",
        "doc.Objects[0].Shape = Shape(volume=1.0, solids=7)\nraise ValueError('boom')",
        ns,
    )
    assert report["verdict"] == "reject"
    assert report["errors"][0]["code"] == "SCRIPT_FAILED"
    assert report["restored"] is True


def test_guarded_keeps_a_good_edit(tx) -> None:
    module, doc = tx
    ns = {"doc": doc, "Shape": Shape}
    report = module.guarded("Doc", "doc.Objects[0].Shape = Shape(volume=70.0)", ns)
    assert report["verdict"] == "pass"
    assert report["restored"] is False
    assert doc.Objects[0].Shape.Volume == 70.0


def test_an_untouched_shape_is_not_reported_as_changed(tx) -> None:
    module, doc = tx
    doc.Objects[0].Shape = Shape(thin=3)
    cp = module.checkpoint("Doc", "before")

    # Same shape, but the scan hands back different examples each call.
    seq = [0]
    def varying(shape, *args):
        seq[0] += 1
        return [{"width": 0.1, "at": [seq[0], 0, 0]}] * shape.thin
    module.dfm.thin_faces = varying

    report = module.audit("Doc", cp["checkpoint_id"])
    assert report["verdict"] == "pass"
    assert report["changed"] == []


def test_an_edit_that_leaves_material_unattached_is_rejected(tx) -> None:
    module, doc = tx
    cp = module.checkpoint("Doc", "before")

    # Same solid count, still valid: a block fused a fraction short of the wall
    # it was meant to meet, which every other check passes.
    after = Shape(volume=110.0)
    after.pieces = 2
    doc.Objects[0].Shape = after

    report = module.audit("Doc", cp["checkpoint_id"], {"forbid_bbox_growth": False})
    assert report["verdict"] == "reject"
    assert [e["code"] for e in report["errors"]] == ["PART_IN_PIECES"]


def test_a_narrowed_checkpoint_ignores_objects_it_never_saw(tx) -> None:
    module, doc = tx
    doc.Objects.append(_obj("Fixture", Shape()))
    cp = module.checkpoint("Doc", "body only", ["Body"])
    assert cp["objects"] == ["Body"]

    # Another object changing is not this edit's business.
    doc.getObject("Fixture").Shape = Shape(volume=5.0, solids=3)
    assert module.audit("Doc", cp["checkpoint_id"])["verdict"] == "pass"


def test_restore_puts_the_face_colours_back_with_the_shape(tx) -> None:
    module, doc = tx
    red, blue, grey = (1, 0, 0, 1), (0, 0, 1, 1), (0.5, 0.5, 0.5, 1)
    original = [red, blue, red, blue, red, blue]     # one per face
    view = types.SimpleNamespace(DiffuseColor=list(original), ShapeColor=grey)
    doc.Objects[0].ViewObject = view
    cp = module.checkpoint("Doc", "before")

    # An edit renumbers the faces and repaints them; undoing only the geometry
    # would leave that colour list over the old face order.
    doc.Objects[0].Shape = Shape(volume=90.0)
    view.DiffuseColor = [grey] * 6

    module.restore(cp["checkpoint_id"])
    assert view.DiffuseColor == original


def test_restore_reports_an_object_it_could_not_put_back(tx) -> None:
    module, doc = tx
    cp = module.checkpoint("Doc", "before")
    doc.Objects = []
    out = module.restore(cp["checkpoint_id"])
    assert out["restored"] == []
    assert out["failed"] == ["Body"]


def test_a_scan_that_cannot_run_is_not_reported_as_clean(tx) -> None:
    module, doc = tx
    cp = module.checkpoint("Doc", "before")

    def explode(shape, *args):
        raise RuntimeError("OCCT gave up")

    module.dfm.thin_faces = explode
    doc.Objects[0].Shape = Shape(volume=90.0)
    report = module.audit("Doc", cp["checkpoint_id"])
    assert report["verdict"] == "reject"
    assert [e["code"] for e in report["errors"]] == ["DEFECT_SCAN_FAILED"]


def test_policy_can_allow_an_edit_that_adds_material(tx) -> None:
    module, doc = tx
    cp = module.checkpoint("Doc", "before")
    doc.Objects[0].Shape = Shape(volume=130.0, bbox=(0, 12, 0, 10, 0, 10))
    assert module.audit("Doc", cp["checkpoint_id"])["verdict"] == "reject"
    ok = module.audit("Doc", cp["checkpoint_id"], {"forbid_bbox_growth": False})
    assert ok["verdict"] == "pass"
