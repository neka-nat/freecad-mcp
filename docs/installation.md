# Installation

[Back to README](../README.md) · [Configuration](configuration.md)

Install FreeCAD and [uv / uvx](https://docs.astral.sh/uv/guides/tools/) before
setting up the addon and MCP client. The MCP server requires Python 3.12 or later.

## Install the addon

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
cd freecad-mcp
```

Copy the `addon/FreeCADMCP` directory into the addon directory for your FreeCAD
installation. The resulting directory should be `Mod/FreeCADMCP`.

### Addon directory

| Platform / installation | Directory |
| --- | --- |
| Windows | `%APPDATA%\FreeCAD\Mod\` |
| macOS, FreeCAD 1.1 | `~/Library/Application Support/FreeCAD/v1-1/Mod/` |
| macOS, FreeCAD 1.0 | `~/Library/Application Support/FreeCAD/v1-0/Mod/` |
| Linux, Ubuntu | `~/.FreeCAD/Mod/` |
| Linux, Snap | `~/snap/freecad/common/Mod/` |
| Linux, Debian | `~/.local/share/FreeCAD/Mod/` |
| Linux, Arch / CachyOS (FreeCAD 1.1 from `extra/freecad`) | `~/.local/share/FreeCAD/v1-1/Mod/` |
| Linux, Flatpak | `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/` |

### Copy commands

Run the commands for your installation from the cloned repository.

Ubuntu:

```bash
mkdir -p ~/.FreeCAD/Mod/
cp -r addon/FreeCADMCP ~/.FreeCAD/Mod/
```

Debian:

```bash
mkdir -p ~/.local/share/FreeCAD/Mod/
cp -r addon/FreeCADMCP ~/.local/share/FreeCAD/Mod/
```

Arch / CachyOS, FreeCAD 1.1 from `extra/freecad`:

```bash
mkdir -p ~/.local/share/FreeCAD/v1-1/Mod/
cp -r addon/FreeCADMCP ~/.local/share/FreeCAD/v1-1/Mod/
```

Flatpak:

```bash
mkdir -p ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/
cp -r addon/FreeCADMCP ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/
```

macOS, FreeCAD 1.1:

```bash
mkdir -p ~/Library/Application\ Support/FreeCAD/v1-1/Mod/
cp -r addon/FreeCADMCP ~/Library/Application\ Support/FreeCAD/v1-1/Mod/
```

## Start the RPC server

Restart FreeCAD after installing the addon, then select **MCP Addon** from the
workbench list.

![MCP Addon in the workbench list](../assets/workbench_list.png)

Click **Start RPC Server** in the **FreeCAD MCP** toolbar.

![Start RPC Server toolbar button](../assets/start_rpc_server.png)

The server starts manually by default. See [auto-start configuration](configuration.md#auto-start-rpc-server)
to enable it on subsequent launches.

## Connect an MCP client

Use the [Claude Desktop configuration in the quick start](../README.md#2-connect-claude-desktop)
to run the published package with `uvx`. For remote FreeCAD installations, see
[remote connections](configuration.md#remote-connections).

### Run from source

For development, install the pinned environment and check the CLI from the cloned
repository:

```bash
uv sync
uv run freecad-mcp --help
```

Configure Claude Desktop to use your checkout. Replace `/path/to/freecad-mcp/`
with its absolute path:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/freecad-mcp/",
        "run",
        "freecad-mcp"
      ]
    }
  }
}
```

Restart Claude Desktop after changing its configuration. When changing addon
code, copy the updated `addon/FreeCADMCP` directory into FreeCAD's addon directory
and restart FreeCAD as well.
