#!/usr/bin/env python3
"""
Test script for the You.com web search integration in FreeCAD MCP.

This script validates that the web search functionality works correctly
without requiring FreeCAD to be running.
"""

import os
import sys
from unittest.mock import patch

# Add the src directory to the path to import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from freecad_mcp.operations.web_search import web_search_operation


def test_web_search_keyless():
    """Test the web search operation without API key (keyless mode)."""
    print("🔍 Testing keyless web search...")
    
    # Ensure no API key is set for keyless test
    original_key = os.environ.get("YDC_API_KEY")
    if "YDC_API_KEY" in os.environ:
        del os.environ["YDC_API_KEY"]
    
    try:
        # Test a simple technical search
        result = web_search_operation(
            query="steel properties yield strength",
            count=3
        )
        
        # Check that we got a response
        assert len(result) > 0, "Expected at least one result"
        assert result[0].type == "text", "Expected text content type"
        
        content = result[0].text
        assert "Web Search Results" in content, "Expected search results header"
        assert "steel properties yield strength" in content, "Expected query in results"
        
        print("✅ Keyless web search test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Keyless web search test failed: {e}")
        return False
        
    finally:
        # Restore original API key if it existed
        if original_key:
            os.environ["YDC_API_KEY"] = original_key


def test_web_search_with_filters():
    """Test the web search operation with domain and freshness filters."""
    print("🔍 Testing web search with filters...")
    
    try:
        # Test search with domain and freshness filters
        result = web_search_operation(
            query="aluminum properties",
            count=2,
            domains=["matweb.com"],
            freshness="year"
        )
        
        # Check that we got a response
        assert len(result) > 0, "Expected at least one result"
        assert result[0].type == "text", "Expected text content type"
        
        content = result[0].text
        assert "aluminum properties" in content, "Expected query in results"
        
        print("✅ Filtered web search test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Filtered web search test failed: {e}")
        return False


def test_error_handling():
    """Test error handling for various failure scenarios.""" 
    print("🔍 Testing error handling...")
    
    try:
        # Test with invalid count (should be clamped)
        result = web_search_operation(
            query="test query",
            count=999  # Should be clamped to 20
        )
        
        assert len(result) > 0, "Expected result even with invalid count"
        
        # Test with empty query
        result = web_search_operation(query="")
        assert len(result) > 0, "Expected result even with empty query"
        
        print("✅ Error handling test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Starting FreeCAD MCP You.com integration tests...\n")
    
    tests = [
        test_web_search_keyless,
        test_web_search_with_filters, 
        test_error_handling
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()  # Empty line between tests
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! You.com integration is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the integration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())