# Demos and examples

[Back to README](../README.md) · [Installation](installation.md) · [Tools](tools.md)

## Design demos

### Design a flange

![Designing a flange in FreeCAD](../assets/freecad_mcp4.gif)

### Design a toy car

![Designing a toy car in FreeCAD](../assets/make_toycar4.gif)

### Design a part from a 2D drawing

Input drawing:

![Input 2D drawing](../assets/b9-1.png)

Demo:

![Modelling the part from the drawing](../assets/from_2ddrawing.gif)

[Conversation history](https://claude.ai/share/7b48fd60-68ba-46fb-bb21-2fbb17399b48)

## Example scripts

| Example | Description |
| --- | --- |
| [Cantilever FEM analysis](../examples/cantilever_fem.py) | Build a cantilever, run CalculiX, and compare the results with an analytical solution. |
| [Google ADK agent](../examples/adk/agent.py) | Connect an ADK agent to the MCP server using a local checkout. |
| [LangChain / LangGraph agent](../examples/langchain/react.py) | Run an interactive CAD agent using MCP tools and a Groq model. |

The agent examples use optional third-party dependencies and provider
configuration. Adjust the repository path and model settings in each example
before running it; the LangChain example also expects `GROQ_API_KEY` in the
environment.
