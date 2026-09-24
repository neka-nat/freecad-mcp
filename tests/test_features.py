"""The point of these features is the geometry, so they are checked on real solids."""

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from rpc_server import dfm, features  # noqa: E402


def stock():
    return Part.makeBox(40, 30, 10)


def radii(shape):
    return sorted({round(f.Surface.Radius, 3) for f in shape.Faces
                   if f.Surface.__class__.__name__ == "Cylinder"})


def test_a_pocket_has_no_corner_the_cutter_could_not_reach() -> None:
    tool = features.cutter_volume([(8, 8), (32, 8), (32, 22), (8, 22)],
                                  3.0, 4.0, 6.0, closed=True)
    pocket = stock().cut(tool).removeSplitter()
    assert pocket.isValid()
    assert len(pocket.Solids) == 1
    # Every inside corner is an arc of the cutter, so none of them is vertical
    # and sharp -- which is exactly what a box-built pocket leaves four of.
    sharp = dfm.sharp_concave_edges(pocket)
    assert [e for e in sharp if e["direction"] == "vertical"] == []
    assert radii(pocket) == [3.0]


def test_a_box_built_pocket_is_what_this_avoids() -> None:
    # The comparison the feature exists for: same opening, cut as a box.
    hand = stock().cut(Part.makeBox(24, 14, 6, FreeCAD.Vector(8, 8, 4)))
    sharp = dfm.sharp_concave_edges(hand)
    assert len([e for e in sharp if e["direction"] == "vertical"]) == 4


def test_a_bent_slot_has_no_notch_at_the_bend() -> None:
    tool = features.cutter_volume([(6, 15), (20, 15), (20, 25)], 2.5, 4.0, 6.0)
    slot = stock().cut(tool).removeSplitter()
    assert slot.isValid()
    assert len(slot.Solids) == 1
    assert [e for e in dfm.sharp_concave_edges(slot)
            if e["direction"] == "vertical"] == []


def test_a_slot_ends_in_an_arc_of_the_cutter() -> None:
    tool = features.cutter_volume([(10, 15), (30, 15)], 2.5, 4.0, 6.0)
    slot = stock().cut(tool).removeSplitter()
    assert radii(slot) == [2.5]


def test_a_single_point_path_is_a_plunge() -> None:
    tool = features.cutter_volume([(20, 15)], 2.5, 4.0, 6.0)
    hole = stock().cut(tool).removeSplitter()
    assert radii(hole) == [2.5]
    assert len(hole.Solids) == 1


def test_a_cutter_too_big_for_the_pocket_is_refused(tmp_path) -> None:
    doc = FreeCAD.newDocument("FeatureTest")
    try:
        obj = doc.addObject("Part::Feature", "Stock")
        obj.Shape = stock()
        doc.recompute()
        # A Ø10 cutter cannot produce a 6 mm wide pocket; saying so beats
        # quietly cutting something else.
        with pytest.raises(ValueError, match="does not fit"):
            features.pocket("FeatureTest", "Stock", [[10, 10], [16, 25]],
                            4.0, 5.0, 10.0)
    finally:
        FreeCAD.closeDocument("FeatureTest")


def test_a_pocket_removes_the_volume_it_reports() -> None:
    doc = FreeCAD.newDocument("FeatureTest")
    try:
        obj = doc.addObject("Part::Feature", "Stock")
        obj.Shape = stock()
        doc.recompute()
        before = obj.Shape.Volume
        out = features.pocket("FeatureTest", "Stock", [[8, 8], [32, 22]],
                              4.0, 3.0, 10.0)
        assert out["corner_radius"] == 3.0
        assert out["z"] == [6.0, 10.0]
        assert abs((before - out["shape"].Volume) - out["volume_removed"]) < 1e-6
        # Short of the full rectangle by the four corner arcs it cannot reach.
        assert out["volume_removed"] < 24 * 14 * 4
    finally:
        FreeCAD.closeDocument("FeatureTest")


class TestCheckCutter:
    """A cutting block is placed from remembered numbers, so it is checked."""

    def test_a_block_inside_the_region_is_clean(self) -> None:
        target = Part.makeBox(10, 10, 10)
        tool = Part.makeBox(2, 2, 2, FreeCAD.Vector(8, 0, 8))
        within = Part.makeBox(3, 3, 3, FreeCAD.Vector(7, 0, 7))
        out = features.check_cutter(target, tool, within)
        assert out["clean"] is True
        assert out["strays"] == []
        assert out["removes"] == 8.0

    def test_a_block_reaching_past_the_region_reports_where(self) -> None:
        # The fault this exists for: a cutter 0.2 taller than the feature, which
        # shaves the face above it. Valid, one solid, and a sliver somewhere the
        # next audit cannot trace back to this edit.
        target = Part.makeBox(10, 10, 10)
        tool = Part.makeBox(2, 2, 3, FreeCAD.Vector(8, 0, 7))
        within = Part.makeBox(2, 2, 2, FreeCAD.Vector(8, 0, 8))
        out = features.check_cutter(target, tool, within)
        assert out["clean"] is False
        assert len(out["strays"]) == 1
        assert out["strays"][0]["volume"] == 4.0
        assert out["strays"][0]["bbox"][5] == 8.0

    def test_a_block_that_misses_is_not_silently_accepted(self) -> None:
        target = Part.makeBox(10, 10, 10)
        tool = Part.makeBox(2, 2, 2, FreeCAD.Vector(50, 50, 50))
        out = features.check_cutter(target, tool)
        assert out["touches_target"] is False
        assert "warning" in out

    def test_anything_in_avoid_is_named(self) -> None:
        target = Part.makeBox(10, 10, 10)
        neighbour = Part.makeBox(4, 10, 10, FreeCAD.Vector(9, 0, 0))
        tool = Part.makeBox(3, 2, 2, FreeCAD.Vector(8, 0, 4))
        out = features.check_cutter(target, tool, avoid={"housing": neighbour})
        assert out["clean"] is False
        assert out["hits"][0]["name"] == "housing"

    def test_a_tool_without_a_solid_is_refused(self) -> None:
        target = Part.makeBox(10, 10, 10)
        with pytest.raises(ValueError, match="no solid"):
            features.check_cutter(target, Part.makeVertex(FreeCAD.Vector(0, 0, 0)))
