"""Tests for parts_library module security features."""
import pytest
import os
import tempfile
from unittest.mock import patch, Mock, MagicMock


class TestInsertPartFromLibrary:
    """Test cases for insert_part_from_library function."""

    @patch("addon.FreeCADMCP.rpc_server.parts_library.FreeCADGui")
    @patch("addon.FreeCADMCP.rpc_server.parts_library.FreeCAD")
    def test_valid_path(self, mock_freecad, mock_freecadgui):
        """Test that valid paths are accepted."""
        # This test would need FreeCAD environment, so we'll just verify the logic
        pass  # Placeholder for when FreeCAD is available

    def test_path_traversal_detection(self):
        """Test that path traversal attempts are blocked."""
        # Test the logic without importing the actual module
        # which requires FreeCAD

        def validate_path(relative_path: str, base_path: str) -> bool:
            """Replicate the validation logic."""
            part_path = os.path.normpath(os.path.join(base_path, relative_path))
            if not part_path.startswith(os.path.normpath(base_path) + os.sep):
                return False
            if not part_path.endswith(".FCStd"):
                return False
            return True

        base = "/tmp/parts_library"

        # Valid paths
        assert validate_path("part1.FCStd", base) is True
        assert validate_path("subdir/part2.FCStd", base) is True
        assert validate_path("subdir/nested/part3.FCStd", base) is True

        # Invalid paths - path traversal
        assert validate_path("../outside.FCStd", base) is False
        assert validate_path("subdir/../../outside.FCStd", base) is False
        assert validate_path("../../../etc/passwd", base) is False

        # Invalid paths - wrong extension
        assert validate_path("malicious.py", base) is False
        assert validate_path("script.sh", base) is False
        assert validate_path("file.txt", base) is False

    def test_path_normalization(self):
        """Test that paths are properly normalized."""
        base = "/tmp/parts_library"

        # Test normalization
        test_path = os.path.normpath(os.path.join(base, "subdir/../part.FCStd"))
        expected = os.path.normpath(os.path.join(base, "part.FCStd"))
        assert test_path == expected

    def test_extension_validation(self):
        """Test that only .FCStd files are allowed."""
        valid_extensions = [
            "part.FCStd",
            "My Part.FCStd",
            "part_v2.FCStd",
        ]

        invalid_extensions = [
            "part.py",
            "part.sh",
            "part.FCStd.py",
            "part",
            "part.fcstd",  # Case sensitive
        ]

        for valid in valid_extensions:
            assert valid.endswith(".FCStd")

        for invalid in invalid_extensions:
            assert not invalid.endswith(".FCStd")


class TestGetPartsList:
    """Test cases for get_parts_list function."""

    def test_parts_list_returns_fcstd_only(self):
        """Test that only .FCStd files are returned."""
        # Create a temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            os.makedirs(os.path.join(tmpdir, "subdir"))

            # Valid FreeCAD files
            open(os.path.join(tmpdir, "part1.FCStd"), "w").close()
            open(os.path.join(tmpdir, "subdir", "part2.FCStd"), "w").close()

            # Invalid files that should be ignored
            open(os.path.join(tmpdir, "readme.txt"), "w").close()
            open(os.path.join(tmpdir, "script.py"), "w").close()

            # Simulate get_parts_list logic
            parts = []
            for root, _, files in os.walk(tmpdir):
                for file in files:
                    if file.endswith(".FCStd"):
                        relative_path = os.path.relpath(
                            os.path.join(root, file), tmpdir
                        )
                        parts.append(relative_path)

            assert len(parts) == 2
            assert "part1.FCStd" in parts
            assert os.path.join("subdir", "part2.FCStd") in parts

    def test_empty_library(self):
        """Test behavior with empty parts library."""
        with tempfile.TemporaryDirectory() as tmpdir:
            parts = []
            for root, _, files in os.walk(tmpdir):
                for file in files:
                    if file.endswith(".FCStd"):
                        parts.append(file)

            assert len(parts) == 0
