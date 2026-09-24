"""These answer geometric questions, so they are checked on real solids."""

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from rpc_server import connectivity  # noqa: E402


def V(x, y, z):
    return FreeCAD.Vector(x, y, z)


def test_a_part_in_one_piece_reports_one_island() -> None:
    box = Part.makeBox(10, 10, 10)
    assert connectivity.islands(box)["islands"] == 1


def test_two_boxes_sharing_a_face_are_one_island() -> None:
    a = Part.makeBox(10, 10, 10)
    b = Part.makeBox(10, 10, 10, V(10, 0, 0))
    assert connectivity.islands(a.fuse(b))["islands"] == 1


def test_boxes_touching_only_at_an_edge_are_two_pieces() -> None:
    a = Part.makeBox(10, 10, 10)
    b = Part.makeBox(10, 10, 10, V(10, 10, 0))
    out = connectivity.islands(a.fuse(b))
    assert out["islands"] == 2
    assert out["groups"][0]["faces"] == 6


def test_a_gap_left_by_a_fuse_that_fell_short_is_found() -> None:
    # The fault this exists for: a block added half a millimetre short of what
    # it was meant to meet. One valid solid, and in the render the block hangs
    # in mid-air with nothing in the audit to say so.
    a = Part.makeBox(10, 10, 2)
    b = Part.makeBox(10, 10, 2, V(10.5, 0, 0))
    out = connectivity.gaps(a.fuse(b), "x", "y", 1.0, 9.0, 2.0, 1.0)
    assert len(out["gaps"]) == 5
    assert all(abs(g["gap"] - 0.5) < 1e-9 for g in out["gaps"])
    assert out["gaps"][0]["between"] == [10.0, 10.5]


def test_a_part_that_really_is_joined_has_no_gaps() -> None:
    a = Part.makeBox(10, 10, 2)
    b = Part.makeBox(10, 10, 2, V(10, 0, 0))
    assert connectivity.gaps(a.fuse(b), "x", "y", 1.0, 9.0, 2.0, 1.0)["gaps"] == []


def test_a_cavity_wider_than_the_limit_is_not_a_fault() -> None:
    # A part is allowed to have a hole in it; only the hairline ones are faults.
    a = Part.makeBox(10, 10, 2)
    b = Part.makeBox(10, 10, 2, V(14.0, 0, 0))
    out = connectivity.gaps(a.fuse(b), "x", "y", 1.0, 9.0, 2.0, 1.0, max_gap=1.0)
    assert out["gaps"] == []


def test_two_parts_facing_each_other_report_their_clearance() -> None:
    lid = Part.makeBox(2, 10, 2)
    housing = Part.makeBox(2, 10, 2, V(2.5, 0, 0))
    out = connectivity.compare_section(lid, housing, "z", 1.0, "x", 1.0, 9.0, 4.0)
    assert out["clearance_min"] == 0.5
    assert out["clearance_max"] == 0.5
    assert out["rows"][0]["a"] == [[0.0, 2.0]]
    assert out["rows"][0]["b"] == [[2.5, 4.5]]


def test_parts_that_touch_report_no_clearance() -> None:
    lid = Part.makeBox(2, 10, 2)
    housing = Part.makeBox(2, 10, 2, V(2.0, 0, 0))
    out = connectivity.compare_section(lid, housing, "z", 1.0, "x", 1.0, 9.0, 4.0)
    assert out["clearance_min"] == 0.0


def test_a_uniform_clearance_holds_all_the_way_along() -> None:
    a = Part.makeBox(2, 20, 2)
    b = Part.makeBox(2, 20, 2, V(2.5, 0, 0))
    out = connectivity.clearance(a, b, "y", 4.0, expect=0.5)
    assert out["holds"] is True
    assert out["gap_min"] == out["gap_max"] == 0.5


def test_a_clearance_that_only_holds_at_one_end_is_caught() -> None:
    # The reason this measures every stop: a tapered pair reads as a perfect
    # 0.5 mm at the station someone happens to section, and as contact at the
    # other end.
    a = Part.makeBox(2, 20, 2)
    wedge = Part.makeWedge(2.0, 0, 0, 0, 0, 3.0, 20, 2, 20, 2)
    wedge.Placement = FreeCAD.Placement(V(2.0, 0, 0), FreeCAD.Rotation(V(1, 0, 0), 0))
    out = connectivity.clearance(a, wedge, "y", 4.0, expect=0.5)
    assert out["holds"] is False
    assert out["off_spec_count"] > 0
    assert out["gap_min"] < 0.5 < out["gap_max"]


def test_a_run_too_long_to_sit_through_is_refused() -> None:
    # Each stop is a boolean against both shapes; a fine step over a long part
    # wedges the GUI thread for minutes, which is worse than saying no.
    a = Part.makeBox(2, 200, 2)
    b = Part.makeBox(2, 200, 2, V(2.5, 0, 0))
    with pytest.raises(ValueError, match="would take minutes"):
        connectivity.clearance(a, b, "y", 0.5)


def test_shapes_that_do_not_overlap_are_not_measured() -> None:
    a = Part.makeBox(2, 20, 2)
    far = Part.makeBox(2, 5, 2, V(0, 100, 0))
    assert connectivity.clearance(a, far, "y", 4.0)["overlap"] is None


def test_compare_section_refuses_a_ray_along_its_own_plane() -> None:
    box = Part.makeBox(10, 10, 10)
    with pytest.raises(ValueError, match="must differ"):
        connectivity.compare_section(box, box, "z", 1.0, "z", 0.0, 5.0, 1.0)
