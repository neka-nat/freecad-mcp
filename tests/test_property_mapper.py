import pytest

from rpc_server.property_mapper import _to_shape_color, parse_reference_entry


class TestParseReferenceEntry:
    def test_documented_dict_form(self):
        assert parse_reference_entry({"object_name": "Box", "face": "Face1"}) == ("Box", "Face1")

    def test_legacy_dict_keys(self):
        assert parse_reference_entry({"Object": "Box", "Face": "Face1"}) == ("Box", "Face1")

    def test_dict_without_face(self):
        assert parse_reference_entry({"object_name": "Box"}) == ("Box", None)

    def test_dict_missing_object_name_raises(self):
        with pytest.raises(ValueError, match="object_name"):
            parse_reference_entry({"face": "Face1"})

    def test_legacy_pair_list(self):
        assert parse_reference_entry(["Box", "Face1"]) == ("Box", "Face1")

    def test_legacy_pair_tuple(self):
        assert parse_reference_entry(("Box", "Face1")) == ("Box", "Face1")

    def test_wrong_length_list_raises(self):
        with pytest.raises(ValueError, match="Invalid reference entry"):
            parse_reference_entry(["Box", "Face1", "extra"])

    def test_scalar_raises(self):
        with pytest.raises(ValueError, match="Invalid reference entry"):
            parse_reference_entry("Box")


class TestToShapeColor:
    def test_rgb_gets_default_alpha(self):
        assert _to_shape_color([0.5, 0.5, 0.5]) == (0.5, 0.5, 0.5, 1.0)

    def test_rgba_passthrough(self):
        assert _to_shape_color([0.1, 0.2, 0.3, 0.4]) == (0.1, 0.2, 0.3, 0.4)

    def test_tuple_input(self):
        assert _to_shape_color((1, 0, 0)) == (1.0, 0.0, 0.0, 1.0)

    def test_ints_coerced_to_float(self):
        result = _to_shape_color([1, 1, 1, 1])
        assert result == (1.0, 1.0, 1.0, 1.0)
        assert all(isinstance(c, float) for c in result)

    def test_wrong_length_raises(self):
        with pytest.raises(ValueError, match="ShapeColor"):
            _to_shape_color([0.5, 0.5])

    def test_non_sequence_raises(self):
        with pytest.raises(ValueError, match="ShapeColor"):
            _to_shape_color("red")
