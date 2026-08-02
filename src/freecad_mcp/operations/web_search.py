import logging
import os
from typing import Any, List, Optional
from urllib.parse import urlencode, urljoin

import httpx
from mcp.types import ImageContent, TextContent

from ..responses import ToolResponse, text_response

logger = logging.getLogger("FreeCADMCPserver")


def web_search_operation(
    query: str,
    count: int = 5,
    domains: Optional[List[str]] = None,
    freshness: Optional[str] = None,
) -> ToolResponse:
    """Execute a web search using You.com's Search API.
    
    This is particularly useful for finding technical documentation, CAD part specifications,
    material properties, engineering standards, and design references when working with FreeCAD.
    
    Args:
        query: The search query string
        count: Number of results to return (1-20, default 5)
        domains: Optional list of domains to search within
        freshness: Optional freshness filter ("hour", "day", "week", "month", "year")
        
    Returns:
        ToolResponse containing formatted search results
    """
    try:
        # Get API key from environment, fallback to keyless operation
        api_key = os.environ.get("YDC_API_KEY")
        
        # Prepare request parameters
        params = {
            "query": query,
            "count": min(max(count, 1), 20),  # Clamp to valid range
        }
        
        if domains:
            params["domains"] = ",".join(domains)
        
        if freshness:
            params["freshness"] = freshness
            
        # Prepare headers
        headers = {
            "Accept": "application/json",
            "User-Agent": "FreeCAD-MCP/1.0",
        }
        
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        # Make the request
        url = "https://api.you.com/v1/agents/search"
        
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
        data = response.json()
        
        # Process results
        if "web" not in data or not data["web"]:
            return text_response("No web search results found for the query.")
            
        results = []
        results.append(f"**Web Search Results for: {query}**\n")
        
        for idx, result in enumerate(data["web"][:count], 1):
            title = result.get("title", "No title")
            url = result.get("url", "No URL")
            snippet = result.get("snippet", "No description available")
            
            results.append(f"{idx}. **{title}**")
            results.append(f"   URL: {url}")
            results.append(f"   Description: {snippet}")
            results.append("")  # Empty line for readability
            
        # Add helpful context about usage with FreeCAD
        results.append("💡 **Tip**: Use these search results to:")
        results.append("   • Find technical specifications and material properties")
        results.append("   • Locate CAD part libraries and component databases")
        results.append("   • Research engineering standards and design guidelines")
        results.append("   • Discover FreeCAD tutorials and documentation")
        results.append("   • Access manufacturing and fabrication resources")
        
        return text_response("\n".join(results))
        
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            error_msg = (
                "Authentication failed. Please check your YDC_API_KEY environment variable. "
                "Without an API key, the service may have limited functionality. "
                "Get an API key at: https://you.com/platform/api-keys"
            )
        elif e.response.status_code == 429:
            error_msg = (
                "Rate limit exceeded. If you're using the keyless API (100 free searches/day), "
                "consider getting an API key for higher quotas at: https://you.com/platform/api-keys"
            )
        elif 500 <= e.response.status_code < 600:
            error_msg = (
                "You.com search service is temporarily unavailable. Please try again later."
            )
        else:
            error_msg = f"Search request failed with status {e.response.status_code}: {e.response.text}"
            
        logger.error(f"You.com API error: {error_msg}")
        return text_response(f"Web search failed: {error_msg}")
        
    except httpx.RequestError as e:
        error_msg = f"Network error occurred while searching: {str(e)}"
        logger.error(f"Network error: {error_msg}")
        return text_response(f"Web search failed: {error_msg}")
        
    except Exception as e:
        error_msg = f"Unexpected error during web search: {str(e)}"
        logger.error(f"Unexpected error: {error_msg}")
        return text_response(f"Web search failed: {error_msg}")