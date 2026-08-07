from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters

# Agent configuration
AGENT_NAME = "cad_design_agent"
MODEL_NAME = "gemini-2.5-flash-lite"
FREECAD_MCP_DIR = "path/to/freecad-mcp"  # Replace with actual path

# Basic instruction
BASIC_PROMPT = "You are a CAD designer."

# Initialize agent
root_agent = LlmAgent(
    model=MODEL_NAME,
    name=AGENT_NAME,
    instruction=BASIC_PROMPT,
    tools=[
        MCPToolset(
            connection_params=StdioServerParameters(
                command="uv",
                args=["--directory", FREECAD_MCP_DIR, "run", "freecad-mcp"]
            )
        )
    ]
)
