import FreeCAD as App

from rpc_server.serialize import serialize_value


class TestSerializeValue:
    def test_int_passthrough(self):
        assert serialize_value(42) == 42

    def test_float_passthrough(self):
        assert serialize_value(3.14) == 3.14

    def test_str_passthrough(self):
        assert serialize_value("hello") == "hello"

    def test_bool_passthrough(self):
        assert serialize_value(True) is True

    def test_vector(self):
        vec = App.Vector(1.0, 2.0, 3.0)
        assert serialize_value(vec) == {"x": 1.0, "y": 2.0, "z": 3.0}

    def test_rotation(self):
        rot = App.Rotation(App.Vector(0, 0, 1), 45.0)
        assert serialize_value(rot) == {
            "Axis": {"x": 0, "y": 0, "z": 1},
            "Angle": 45.0,
        }

    def test_placement_nested(self):
        placement = App.Placement(
            App.Vector(10.0, 20.0, 0.0),
            App.Rotation(App.Vector(0, 0, 1), 90.0),
        )
        assert serialize_value(placement) == {
            "Base": {"x": 10.0, "y": 20.0, "z": 0.0},
            "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 90.0},
        }

    def test_list_of_scalars(self):
        assert serialize_value([1, "two", 3.0]) == [1, "two", 3.0]

    def test_tuple_becomes_list(self):
        assert serialize_value((1, 2)) == [1, 2]

    def test_list_of_vectors(self):
        vecs = [App.Vector(1, 0, 0), App.Vector(0, 1, 0)]
        assert serialize_value(vecs) == [
            {"x": 1, "y": 0, "z": 0},
            {"x": 0, "y": 1, "z": 0},
        ]

    def test_unknown_object_falls_back_to_str(self):
        class Custom:
            def __str__(self):
                return "custom-repr"

        assert serialize_value(Custom()) == "custom-repr"

    def test_none_falls_back_to_str(self):
        assert serialize_value(None) == "None"
