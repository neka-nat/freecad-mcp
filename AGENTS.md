# Repository Guidelines

## Project Structure & Module Organization
`src/freecad_mcp/` contains the packaged MCP server and CLI entrypoint exposed as `freecad-mcp`. `addon/FreeCADMCP/` is the FreeCAD addon loaded inside FreeCAD, with XML-RPC and toolbar logic under `rpc_server/`. `examples/` holds integration samples for ADK and LangChain. `assets/` stores README media, while `results/` and `dist/` contain sample outputs and built distributions rather than core source.

## Build, Test, and Development Commands
`uv sync` installs the pinned Python environment from `uv.lock`. `uv run freecad-mcp --help` verifies the CLI entrypoint; use `uv run freecad-mcp --host localhost --only-text-feedback` for a local MCP run against an existing FreeCAD RPC server. `uv run python -m compileall src addon` is the current fast validation pass for syntax issues. `uv build` creates the wheel and source distribution in `dist/`.

For addon testing, copy `addon/FreeCADMCP` into your FreeCAD `Mod/` directory, restart FreeCAD, switch to the `MCP Addon` workbench, and start the RPC server from the `FreeCAD MCP` toolbar.

## Coding Style & Naming Conventions
Target Python 3.12, use 4-space indentation, and add type hints to new or modified code. Follow the existing split: MCP transport and CLI code in `src/`, FreeCAD GUI and RPC behavior in `addon/`. Use `snake_case` for modules, functions, and variables, `PascalCase` for classes, and keep command IDs consistent with existing strings such as `"Start_RPC_Server"`. Keep docstrings brief and move FreeCAD-specific side effects into small helper functions where practical.

## Testing Guidelines
There is no committed automated test suite yet. For every change, run `uv run python -m compileall src addon` and perform a manual smoke test in FreeCAD for the affected workflow, such as local RPC, remote connections, auto-start, or headless mode. When adding pure-Python logic that can be tested outside FreeCAD, add `pytest` tests in a new `tests/` package and name files `test_*.py`.

## Commit & Pull Request Guidelines
Recent history follows short, imperative Conventional Commit-style subjects such as `feat: ...`, `fix(addon): ...`, and `docs: ...`; continue that pattern. Keep each commit focused on one logical change. Pull requests should describe user-visible behavior, list validation steps, link the relevant issue, and include screenshots or GIFs for toolbar or UI changes.

## Security & Configuration Tips
Remote connections default to `localhost`; keep that default unless the feature explicitly requires broader access. Do not commit real tokens, local machine paths, or generated FreeCAD user settings from example `.env` files or desktop configuration snippets.
