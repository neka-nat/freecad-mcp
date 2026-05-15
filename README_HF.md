# Deployment Guide for Stlux on Hugging Face

To deploy this integrated FreeCAD AI Operator (Stlux) to your Hugging Face Space:

## 1. Create a New Space
- Go to [Hugging Face Spaces](https://huggingface.co/spaces).
- Click **"Create new Space"**.
- Name it `Stlux`.
- Select **"Docker"** as the Space SDK.
- Choose a template (Blank is fine).

## 2. Push the Code
You can push the code using Git:

```bash
git remote add hf https://huggingface.co/spaces/acecalisto3/Stlux
git push hf main
```

## 3. AI Assistant Features
This Space includes an **AI Operator** interface that translates natural language into FreeCAD commands.

### How it works:
- **Direct Code**: Enter Python code directly (e.g. `doc.addObject('Part::Box', 'MyBox')`).
- **AI Agent**: Use natural language (e.g. "Create a 20mm cube").

### Future Expansion (LLM Integration):
To enable advanced AI reasoning, you can modify `app.py` to use an LLM API (like OpenAI or Anthropic).
1. Add your API Key to the Hugging Face Space **Settings > Variables and secrets**.
2. Reference the secret in `app.py` using `os.getenv("YOUR_API_KEY")`.

## 4. Troubleshooting
- **FreeCAD Status**: The web UI shows a green status indicator when the backend has successfully connected to the FreeCAD RPC server.
- **Logs**: If the status stays red, check the "Logs" tab for errors in `Xvfb` or `FreeCAD` startup.

## Included Files
- `Dockerfile`: Headless environment setup.
- `app.py`: FastAPI server with AI command processing.
- `entrypoint.sh`: Process orchestration.
- `static/`: Modern AI-chat frontend.
- `addon/FreeCADMCP`: The core FreeCAD-to-MCP bridge.
