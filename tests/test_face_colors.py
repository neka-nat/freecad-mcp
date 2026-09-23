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


def _obj(name, faces, colors, shape_color=GREY):
    view = types.SimpleNamespace(DiffuseColor=list(colors), ShapeColor=shape_color)
    return types.SimpleNamespace(
        Name=name,
        Shape=types.SimpleNamespace(Faces=faces, isNull=lambda: False),
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
        obj.Shape = types.SimpleNamespace(
            Faces=[half_a, half_b, side], isNull=lambda: False
        )
        obj.ViewObject.DiffuseColor = [RED, BLUE]

        repaired = module.restore(before)
        assert repaired == ["Doc.Board: 3/3 faces"]
        # Both halves inherit the original top color; the side keeps its own.
        assert obj.ViewObject.DiffuseColor == [RED, RED, BLUE]
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
        obj.Shape = types.SimpleNamespace(Faces=[top, pocket], isNull=lambda: False)
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
