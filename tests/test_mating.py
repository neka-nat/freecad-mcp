"""Clearance is a geometric claim, so these run against real solids."""

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from rpc_server import mating  # noqa: E402


def V(x, y, z):
    return FreeCAD.Vector(x, y, z)


def gap_between(a, b, y, z=0.5):
    """Distance from a's far edge to b's near edge on one thin slice."""
    knife = Part.makeBox(40, 0.02, 0.2, V(-10, y - 0.01, z))
    sa, sb = a.common(knife), b.common(knife)
    if not sa.Faces or not sb.Faces:
        return None
    return round(sb.BoundBox.XMin - sa.BoundBox.XMax, 3)


def test_the_addition_stands_off_the_neighbour() -> None:
    target = Part.makeBox(2, 20, 1)
    neighbour = Part.makeBox(2, 20, 1, V(5, 0, 0))
    blank = Part.makeBox(4, 20, 1, V(1, 0, 0))
    out = mating.mating_addition(target, blank, neighbour, 0.5, "-x")
    assert out["result_valid"]
    assert out["clash_with_neighbour"] == 0.0
    assert gap_between(out["shape"], neighbour, 10.0) == 0.5


def test_a_neighbour_that_steps_keeps_its_clearance_at_the_step() -> None:
    # The fault this exists for: cutting against the neighbour itself stops at
    # its surface, so the two touch wherever that surface moves -- here, where
    # the wall steps 1 mm closer over part of its length.
    target = Part.makeBox(2, 20, 1)
    near = Part.makeBox(2, 8, 1, V(4, 0, 0))
    far = Part.makeBox(2, 12, 1, V(5, 8, 0))
    neighbour = near.fuse(far)
    blank = Part.makeBox(4, 20, 1, V(1, 0, 0))

    naive = target.fuse(blank.cut(neighbour))
    assert gap_between(naive, neighbour, 4.0) == 0.0     # touching

    out = mating.mating_addition(target, blank, neighbour, 0.5, "-x")
    assert gap_between(out["shape"], neighbour, 4.0) == 0.5
    assert gap_between(out["shape"], neighbour, 14.0) == 0.5


def test_the_addition_reports_how_much_it_overlaps_what_it_joins() -> None:
    # An addition overlapping nothing is one that will hang in mid-air, so the
    # figure is reported rather than left to be discovered on screen.
    target = Part.makeBox(2, 20, 1)
    neighbour = Part.makeBox(2, 20, 1, V(8, 0, 0))
    touching = mating.mating_addition(
        target, Part.makeBox(4, 20, 1, V(1, 0, 0)), neighbour, 0.5, "-x")
    assert touching["overlap_with_target"] > 0

    adrift = mating.mating_addition(
        target, Part.makeBox(2, 20, 1, V(4, 0, 0)), neighbour, 0.5, "-x")
    assert adrift["overlap_with_target"] == 0
    assert adrift["result_solids"] == 2


def test_anything_in_avoid_is_cut_out_too() -> None:
    target = Part.makeBox(2, 20, 1)
    neighbour = Part.makeBox(2, 20, 1, V(8, 0, 0))
    board = Part.makeBox(6, 4, 1, V(3, 8, 0))
    out = mating.mating_addition(
        target, Part.makeBox(5, 20, 1, V(1, 0, 0)), neighbour, 0.5, "-x",
        avoid=[board])
    # The addition specifically: what the target already overlapped is not this
    # call's to remove.
    assert out["addition"].common(board).Volume == 0.0


def test_zero_clearance_is_the_neighbour_itself() -> None:
    neighbour = Part.makeBox(2, 20, 1, V(5, 0, 0))
    zone = mating.keep_out(neighbour, 0.0, "-x")
    assert abs(zone.Volume - neighbour.Volume) < 1e-9


def test_a_direction_that_is_not_an_axis_is_refused() -> None:
    neighbour = Part.makeBox(2, 20, 1)
    with pytest.raises(ValueError, match="towards must be"):
        mating.keep_out(neighbour, 0.5, "sideways")


def test_a_neighbour_nowhere_near_keeps_nothing_out() -> None:
    # "The neighbour is not in the way" is an answer, not an error: cutting
    # against the empty result leaves the blank as it was.
    neighbour = Part.makeBox(2, 2, 2, V(100, 100, 100))
    zone = mating.keep_out(neighbour, 0.5, "-x", region=Part.makeBox(5, 5, 5))
    assert zone.Faces == []
