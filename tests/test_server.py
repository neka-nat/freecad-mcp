"""Tests for the FreeCAD MCP server."""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestFreeCADConnection:
    """Test cases for FreeCADConnection class."""

    def test_connection_init(self):
        """Test that connection initializes with correct defaults."""
        with patch("freecad_mcp.server.xmlrpc.client.ServerProxy"):
            from freecad_mcp.server import FreeCADConnection

            conn = FreeCADConnection()
            assert conn.host == "localhost"
            assert conn.port == 9875
            assert conn._connected is False

    def test_connection_custom_host_port(self):
        """Test connection with custom host and port."""
        with patch("freecad_mcp.server.xmlrpc.client.ServerProxy"):
            from freecad_mcp.server import FreeCADConnection

            conn = FreeCADConnection(host="127.0.0.1", port=8080)
            assert conn.host == "127.0.0.1"
            assert conn.port == 8080

    def test_ping_success(self):
        """Test successful ping."""
        with patch("freecad_mcp.server.xmlrpc.client.ServerProxy") as mock_proxy:
            from freecad_mcp.server import FreeCADConnection

            mock_server = Mock()
            mock_server.ping.return_value = True
            mock_proxy.return_value = mock_server

            conn = FreeCADConnection()
            result = conn.ping()

            assert result is True
            assert conn._connected is True

    def test_disconnect(self):
        """Test disconnect method."""
        with patch("freecad_mcp.server.xmlrpc.client.ServerProxy"):
            from freecad_mcp.server import FreeCADConnection

            conn = FreeCADConnection()
            conn._connected = True
            conn.disconnect()

            assert conn._connected is False


class TestHelperFunctions:
    """Test helper functions."""

    def test_add_screenshot_if_available_with_screenshot(self):
        """Test adding screenshot when available."""
        from freecad_mcp.server import add_screenshot_if_available
        from mcp.types import TextContent, ImageContent
        import freecad_mcp.server as server_module

        # Set to allow images
        original_value = server_module._only_text_feedback
        server_module._only_text_feedback = False

        response = [TextContent(type="text", text="Test")]
        screenshot = "base64encodeddata"

        result = add_screenshot_if_available(response, screenshot)

        assert len(result) == 2
        assert isinstance(result[1], ImageContent)
        assert result[1].data == "base64encodeddata"

        # Restore
        server_module._only_text_feedback = original_value

    def test_add_screenshot_if_available_without_screenshot(self):
        """Test adding note when screenshot unavailable."""
        from freecad_mcp.server import add_screenshot_if_available
        from mcp.types import TextContent
        import freecad_mcp.server as server_module

        # Set to allow images
        original_value = server_module._only_text_feedback
        server_module._only_text_feedback = False

        response = [TextContent(type="text", text="Test")]
        screenshot = None

        result = add_screenshot_if_available(response, screenshot)

        assert len(result) == 2
        assert isinstance(result[1], TextContent)
        assert "unavailable" in result[1].text.lower()

        # Restore
        server_module._only_text_feedback = original_value

    def test_add_screenshot_only_text_mode(self):
        """Test that screenshot is not added in text-only mode."""
        from freecad_mcp.server import add_screenshot_if_available
        from mcp.types import TextContent
        import freecad_mcp.server as server_module

        # Set to text-only mode
        original_value = server_module._only_text_feedback
        server_module._only_text_feedback = True

        response = [TextContent(type="text", text="Test")]
        screenshot = "base64encodeddata"

        result = add_screenshot_if_available(response, screenshot)

        assert len(result) == 1  # No screenshot added

        # Restore
        server_module._only_text_feedback = original_value


class TestGetFreeCADConnection:
    """Test get_freecad_connection function."""

    def test_creates_new_connection(self):
        """Test that a new connection is created when none exists."""
        import freecad_mcp.server as server_module

        with patch("freecad_mcp.server.xmlrpc.client.ServerProxy") as mock_proxy:
            mock_server = Mock()
            mock_server.ping.return_value = True
            mock_proxy.return_value = mock_server

            # Reset global connection
            original_conn = server_module._freecad_connection
            server_module._freecad_connection = None

            conn = server_module.get_freecad_connection()

            assert conn is not None
            assert server_module._freecad_connection is conn

            # Restore
            server_module._freecad_connection = original_conn

    def test_reuses_existing_connection(self):
        """Test that existing connection is reused."""
        import freecad_mcp.server as server_module

        with patch("freecad_mcp.server.xmlrpc.client.ServerProxy"):
            from freecad_mcp.server import FreeCADConnection

            # Set up existing connection
            original_conn = server_module._freecad_connection
            mock_conn = Mock(spec=FreeCADConnection)
            server_module._freecad_connection = mock_conn

            result = server_module.get_freecad_connection()

            assert result is mock_conn

            # Restore
            server_module._freecad_connection = original_conn

    def test_raises_on_ping_failure(self):
        """Test that exception is raised when ping fails."""
        import freecad_mcp.server as server_module

        with patch("freecad_mcp.server.xmlrpc.client.ServerProxy") as mock_proxy:
            mock_server = Mock()
            mock_server.ping.return_value = False
            mock_proxy.return_value = mock_server

            # Reset global connection
            original_conn = server_module._freecad_connection
            server_module._freecad_connection = None

            with pytest.raises(Exception, match="Failed to connect"):
                server_module.get_freecad_connection()

            # Restore
            server_module._freecad_connection = original_conn
