"""Check the defect scanners against solids whose answer is known by hand.

The stubbed tests in test_dfm.py fix the logic in isolation; these fix the
answer. A scanner can satisfy every stub and still miscount a real pocket,
which is how a concavity check shipped that found one inside corner on a solid
that has one -- and would have found one on a solid that has eight.

Skipped where FreeCAD is not importable, so the suite still runs on a plain
Python: these need the real kernel by definition.
"""

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from rpc_server import dfm  # noqa: E402


def V(x, y, z):
    return FreeCAD.Vector(x, y, z)


def box():
    return Part.makeBox(10, 10, 10)


def concave_at(shape):
    return sorted(tuple(e["at"]) for e in dfm.sharp_concave_edges(shape))


def test_a_plain_box_has_no_inside_corners() -> None:
    assert dfm.sharp_concave_edges(box()) == []


def test_an_l_shape_has_exactly_one_inside_corner() -> None:
    # Cutting a corner out from top to bottom leaves one vertical inside edge.
    # The four edges where that cut meets the top and bottom faces are convex:
    # a count of three here means convex edges are being counted as concave.
    L = box().cut(Part.makeBox(5, 5, 12, V(5, 5, -1)))
    found = dfm.sharp_concave_edges(L)
    assert len(found) == 1
    assert found[0]["at"] == [5.0, 5.0, 5.0]
    assert found[0]["direction"] == "vertical"


def test_a_pocket_has_four_wall_corners_and_four_floor_edges() -> None:
    pocket = box().cut(Part.makeBox(4, 4, 4, V(3, 3, 6)))
    found = dfm.sharp_concave_edges(pocket)
    assert len(found) == 8
    directions = sorted(e["direction"] for e in found)
    assert directions == ["horizontal"] * 4 + ["vertical"] * 4
    assert all(abs(e["dihedral_deg"] - 90.0) < 1e-6 for e in found)


def test_a_through_slot_has_only_its_two_floor_edges() -> None:
    # Open at both ends, so there are no end walls and no vertical corners.
    slot = box().cut(Part.makeBox(12, 3, 3, V(-1, 3, 7)))
    assert concave_at(slot) == [(2.5, 3.0, 7.0), (2.5, 6.0, 7.0)]


def test_a_round_bore_has_no_sharp_corner() -> None:
    # The bore wall meets the top face tangentially to nothing: its floor is
    # open, so a cylinder through a box adds no inside corner at all.
    bore = box().cut(Part.makeCylinder(2, 12, V(5, 5, -1)))
    assert dfm.sharp_concave_edges(bore) == []


def test_a_filleted_pocket_corner_is_not_reported_as_sharp() -> None:
    pocket = box().cut(Part.makeBox(4, 4, 4, V(3, 3, 6)))
    vertical = [e for e in pocket.Edges
                if e.Length > 3.9 and abs(e.tangentAt(e.FirstParameter).z) > 0.99
                and 3 <= e.Vertexes[0].Point.x <= 7
                and 3 <= e.Vertexes[0].Point.y <= 7]
    rounded = pocket.makeFillet(1.0, vertical)
    found = dfm.sharp_concave_edges(rounded)
    # The corners became fillets; their edges are now tangent joins, so only the
    # floor ring is left as a genuine corner.
    assert all(e["direction"] != "vertical" for e in found)


def test_the_scan_is_fast_enough_to_gate_an_edit() -> None:
    import time

    pocket = box().cut(Part.makeBox(4, 4, 4, V(3, 3, 6)))
    start = time.time()
    dfm.sharp_concave_edges(pocket)
    # Classifying points against the solid put this at tens of milliseconds for
    # a 12-face box, and 31 seconds for a 444-face lid.
    assert time.time() - start < 0.1
