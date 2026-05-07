import os
import logging
import asyncio
from langchain_groq import ChatGroq
from mcp import ClientSession, StdioServerParameters
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
from mcp.client.stdio import stdio_client

# Setup logging and environment
logging.basicConfig(level=logging.INFO)


# Initialize LLM
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.7,
    name="cad_design_agent"
)

# MCP server parameters
server_params = StdioServerParameters(
    command="uv",
    args=["--directory", "path/to/freecad-mcp", "run", "freecad-mcp"]
)

# Basic CAD assistant prompt
INSTRUCTION = "You are a CAD designer."

async def main():
    if "GROQ_API_KEY" not in os.environ:
        logging.error("GROQ_API_KEY is missing.")
        return

    logging.info("Starting MCP client...")
    async with stdio_client(server_params) as (read, write):
        logging.info("Connected to MCP server.")
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)

            agent = create_react_agent(llm, tools)

            print("\n Ready! Type 'exit' to quit.\n")
            while True:
                user_input = input("You: ").strip()
                if user_input.lower() in ("exit", "quit"):
                    print("Goodbye!")
                    break

                messages = [
                    SystemMessage(content=INSTRUCTION),
                    HumanMessage(content=user_input)
                ]
                try:
                    response = await agent.ainvoke({"messages": messages})
                    ai_msgs = response.get("messages", [])
                    if ai_msgs:
                        print(f"\n{ai_msgs[-1].content}\n")
                    else:
                        print("No response from agent.")
                except Exception:
                    logging.exception("Agent error")
                    print("Something went wrong.")

if __name__ == "__main__":
    asyncio.run(main())
