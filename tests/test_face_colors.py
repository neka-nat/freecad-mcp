import types

from test_gui_dispatch import load_gui_dispatch

RED = (1.0, 0.0, 0.0, 1.0)
BLUE = (0.0, 0.0, 1.0, 1.0)
GREY = (0.5, 0.5, 0.5, 1.0)


class Plane:
    def __init__(self, nx, ny, nz, px, py, pz):
        self.Axis = types.SimpleNamespace(x=nx, y=ny, z=nz)
        self.Position = types.SimpleNamespace(x=px, y=py, z=pz)


class Face:
    """A face that reports where it sits, which is what the keys are built from."""

    def __init__(self, center, area, normal, offset):
        self.CenterOfMass = types.SimpleNamespace(x=center[0], y=center[1], z=center[2])
        self.Area = area
        self._normal, self._offset = normal, offset

    @property
    def Surface(self):
        n = self._normal
        p = [c * self._offset for c in n]
        return Plane(n[0], n[1], n[2], p[0], p[1], p[2])


def _shape(faces):
    """A shape whose identity follows its faces, as the real one's does."""
    area = sum(f.Area for f in faces)
    return types.SimpleNamespace(
        Faces=faces, Area=area, Volume=area * 10, isNull=lambda: False
    )


def _obj(name, faces, colors, shape_color=GREY):
    view = types.SimpleNamespace(DiffuseColor=list(colors), ShapeColor=shape_color)
    return types.SimpleNamespace(
        Name=name,
        Shape=_shape(faces),
        ViewObject=view,
    )


def _doc(name, objs):
    return types.SimpleNamespace(Name=name, Objects=objs)


def _load(docs):
    ctx = load_gui_dispatch()
    dispatch = ctx.__enter__()
    dispatch.FreeCAD.listDocuments = lambda: {d.Name: d for d in docs}
    import importlib
    import sys

    sys.modules.pop("rpc_server.face_colors", None)
    module = importlib.import_module("rpc_server.face_colors")
    return ctx, module


def test_split_face_hands_its_color_to_both_halves() -> None:
    top = Face((50.0, 50.0, 10.0), 100.0, (0, 0, 1), 10.0)
    side = Face((0.0, 50.0, 5.0), 40.0, (1, 0, 0), 0.0)
    obj = _obj("Board", [top, side], [RED, BLUE])
    docs = [_doc("Doc", [obj])]
    ctx, module = _load(docs)
    try:
        before = module.snapshot()
        # The edit splits the top face in two and renumbers everything.
        half_a = Face((25.0, 50.0, 10.0), 50.0, (0, 0, 1), 10.0)
        half_b = Face((75.0, 50.0, 10.0), 50.0, (0, 0, 1), 10.0)
        obj.Shape = _shape([half_a, half_b, side])
        obj.ViewObject.DiffuseColor = [RED, BLUE]

        repaired = module.restore(before)
        assert repaired == ["Doc.Board: 3/3 faces"]
        # Both halves inherit the original top color; the side keeps its own.
        assert obj.ViewObject.DiffuseColor == [RED, RED, BLUE]
    finally:
        ctx.__exit__(None, None, None)


def test_a_plane_two_parts_share_does_not_lend_its_color() -> None:
    # A mounting pad's side and a connector's side sit flush, so they share a
    # plane while being different colors. Taking whichever was recorded first
    # paints a new face on that plane as its neighbour.
    pad_side = Face((0.0, 20.0, 10.0), 40.0, (0, 1, 0), 20.0)
    plug_side = Face((0.0, 20.0, 30.0), 25.0, (0, 1, 0), 20.0)
    obj = _obj("Board", [pad_side, plug_side], [RED, BLUE])
    ctx, module = _load([_doc("Doc", [obj])])
    try:
        before = module.snapshot()
        # Far from both, so proximity cannot speak for it either.
        stranger = Face((0.0, 20.0, 400.0), 48.0, (0, 1, 0), 20.0)
        obj.Shape = _shape([stranger, plug_side])
        obj.ViewObject.DiffuseColor = [RED, BLUE]

        module.restore(before)
        assert obj.ViewObject.DiffuseColor == [GREY, BLUE]
    finally:
        ctx.__exit__(None, None, None)


def test_a_face_that_moved_keeps_its_colour() -> None:
    # Growing a pad thicker replaces its end cap with one a fraction further
    # out, facing the same way. Neither key survives that -- the plane itself
    # changed -- and without the fallback a yellow pad comes out part grey.
    cap = Face((20.0, 0.0, 10.0), 40.0, (1, 0, 0), 20.0)
    other = Face((0.0, 50.0, 10.0), 90.0, (0, 0, 1), 10.0)
    obj = _obj("Board", [cap, other], [RED, BLUE])
    ctx, module = _load([_doc("Doc", [obj])])
    try:
        before = module.snapshot()
        moved = Face((20.35, 0.0, 10.0), 40.0, (1, 0, 0), 20.35)
        obj.Shape = _shape([moved, other])
        obj.ViewObject.DiffuseColor = [GREY, BLUE]

        module.restore(before)
        assert obj.ViewObject.DiffuseColor == [RED, BLUE]
    finally:
        ctx.__exit__(None, None, None)


def test_neighbours_that_disagree_do_not_decide() -> None:
    # A new face between two differently coloured parts has no single
    # neighbourhood colour, so it takes the object's rather than a coin toss.
    left = Face((0.0, 0.0, 0.0), 4.0, (1, 0, 0), 0.0)
    right = Face((1.0, 0.0, 0.0), 4.0, (0, 1, 0), 1.0)
    obj = _obj("Board", [left, right], [RED, BLUE])
    ctx, module = _load([_doc("Doc", [obj])])
    try:
        before = module.snapshot()
        between = Face((0.5, 0.0, 0.0), 4.0, (0, 0, 1), 0.5)
        obj.Shape = _shape([left, right, between])
        obj.ViewObject.DiffuseColor = [RED, BLUE, GREY]

        module.restore(before)
        assert obj.ViewObject.DiffuseColor == [RED, BLUE, GREY]
    finally:
        ctx.__exit__(None, None, None)


def test_a_face_that_moved_too_far_is_not_claimed() -> None:
    # Far enough away it is a different face, and inheriting from across the
    # part would be a guess rather than a restore.
    cap = Face((20.0, 0.0, 10.0), 40.0, (1, 0, 0), 20.0)
    other = Face((0.0, 50.0, 10.0), 90.0, (0, 0, 1), 10.0)
    obj = _obj("Board", [cap, other], [RED, BLUE])
    ctx, module = _load([_doc("Doc", [obj])])
    try:
        before = module.snapshot()
        elsewhere = Face((95.0, 0.0, 10.0), 40.0, (1, 0, 0), 95.0)
        obj.Shape = _shape([elsewhere, other])
        obj.ViewObject.DiffuseColor = [GREY, BLUE]

        module.restore(before)
        assert obj.ViewObject.DiffuseColor == [GREY, BLUE]
    finally:
        ctx.__exit__(None, None, None)


def test_a_brand_new_face_falls_back_to_shape_color() -> None:
    top = Face((50.0, 50.0, 10.0), 100.0, (0, 0, 1), 10.0)
    obj = _obj("Board", [top, Face((0.0, 50.0, 5.0), 40.0, (1, 0, 0), 0.0)], [RED, BLUE])
    docs = [_doc("Doc", [obj])]
    ctx, module = _load(docs)
    try:
        before = module.snapshot()
        pocket = Face((50.0, 50.0, 4.0), 12.0, (0, 0, 1), 4.0)
        obj.Shape = _shape([top, pocket])
        obj.ViewObject.DiffuseColor = [RED, BLUE]

        module.restore(before)
        assert obj.ViewObject.DiffuseColor == [RED, GREY]
    finally:
        ctx.__exit__(None, None, None)


def test_a_uniform_object_is_left_alone() -> None:
    # One color for the whole object: there is no per-face mapping to protect,
    # and re-applying a stale color would be a change the caller never asked for.
    faces = [Face((50.0, 50.0, 10.0), 100.0, (0, 0, 1), 10.0)]
    obj = _obj("Plain", faces, [GREY])
    ctx, module = _load([_doc("Doc", [obj])])
    try:
        assert module.snapshot() == {}
    finally:
        ctx.__exit__(None, None, None)


def test_a_deliberate_recolour_is_left_alone() -> None:
    # A script asked to recolour a face changes no geometry. Treating that as
    # damage and putting the old colours back undoes the edit, which is what
    # made four recolour attempts in a row appear to do nothing.
    top = Face((50.0, 50.0, 10.0), 100.0, (0, 0, 1), 10.0)
    side = Face((0.0, 50.0, 5.0), 40.0, (1, 0, 0), 0.0)
    obj = _obj("Board", [top, side], [RED, BLUE])
    ctx, module = _load([_doc("Doc", [obj])])
    try:
        before = module.snapshot()
        obj.ViewObject.DiffuseColor = [GREY, BLUE]   # same shape, new colour
        assert module.restore(before) == []
        assert obj.ViewObject.DiffuseColor == [GREY, BLUE]
    finally:
        ctx.__exit__(None, None, None)


def test_an_untouched_object_is_not_repainted() -> None:
    top = Face((50.0, 50.0, 10.0), 100.0, (0, 0, 1), 10.0)
    side = Face((0.0, 50.0, 5.0), 40.0, (1, 0, 0), 0.0)
    obj = _obj("Board", [top, side], [RED, BLUE])
    ctx, module = _load([_doc("Doc", [obj])])
    try:
        before = module.snapshot()
        obj.ViewObject.DiffuseColor = [RED, BLUE]
        assert module.restore(before) == []
    finally:
        ctx.__exit__(None, None, None)
