# Installation

[Back to README](../README.md) · [Configuration](configuration.md)

Install FreeCAD and [uv / uvx](https://docs.astral.sh/uv/guides/tools/) before
setting up the addon and MCP client. The MCP server requires Python 3.12 or later.

The two components use separate Python environments. The addon runs inside
FreeCAD with its bundled Python (which can be Python 3.11); the external MCP
server runs with Python 3.12 or later, supplied by `uv` or a separate installation.
Do not install the `freecad-mcp` package into FreeCAD's bundled Python.

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
| Windows, FreeCAD 1.1 | `%APPDATA%\FreeCAD\v1-1\Mod\` |
| Windows, older unversioned installations | `%APPDATA%\FreeCAD\Mod\` |
| macOS, FreeCAD 1.1 | `~/Library/Application Support/FreeCAD/v1-1/Mod/` |
| macOS, FreeCAD 1.0 | `~/Library/Application Support/FreeCAD/v1-0/Mod/` |
| Linux, Ubuntu | `~/.FreeCAD/Mod/` |
| Linux, Snap | `~/snap/freecad/common/Mod/` |
| Linux, Debian | `~/.local/share/FreeCAD/Mod/` |
| Linux, Arch / CachyOS (FreeCAD 1.1 from `extra/freecad`) | `~/.local/share/FreeCAD/v1-1/Mod/` |
| Linux, Flatpak | `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/` |

Paths depend on the FreeCAD version and packaging. To find the user addon
directory for the running installation, open **View → Panels → Python console**
in FreeCAD and run:

```python
import os
print(os.path.join(FreeCAD.getUserAppDataDir(), "Mod"))
```

On Windows, the directory must contain `FreeCADMCP\InitGui.py` directly, for
example `%APPDATA%\FreeCAD\v1-1\Mod\FreeCADMCP\InitGui.py`. Do not copy the
whole repository into `Mod` or add a second `FreeCADMCP` directory level. If the
workbench is missing after restarting FreeCAD, open **View → Panels → Report view**
and inspect addon import errors.

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

The command displays its result in the status bar and Report View. A successful
start includes the listening address, port, and FreeCAD process ID; by default
the address is `127.0.0.1:9875`. Startup errors include the exception, such as an
address already in use. A failed start releases its listener so you can retry
after correcting the cause.

Examples from a Linux smoke test: [successful startup](../assets/rpc-startup-success.png)
and [reported startup failure](../assets/rpc-startup-error.png).

The server starts manually by default. See [auto-start configuration](configuration.md#auto-start-rpc-server)
to enable it on subsequent launches.

### Verify the connection on Windows

Check the listening port in PowerShell:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 9875
```

A successful TCP check only shows that something is listening. To verify that
it is the FreeCAD XML-RPC server, run this from an external Python 3.12
installation in PowerShell or Command Prompt:

```powershell
py -3.12 -c "import socket, xmlrpc.client; socket.setdefaulttimeout(5); s = xmlrpc.client.ServerProxy('http://127.0.0.1:9875'); print(s.ping()); print(s.get_rpc_status())"
```

`ping()` should print `True`; the status result includes GUI-dispatch health.
If the port is closed, start the addon server and check Report View. If the
port is open but the RPC check fails, check for another process using port 9875.
For remote installations, also check the [allowed IP configuration](configuration.md#remote-connections).

To inspect the listener directly from FreeCAD's Python console:

```python
from rpc_server import rpc_server as bridge
print(bridge.rpc_server_instance.server_address if bridge.rpc_server_instance else "RPC server stopped")
```

## Connect an MCP client

Use the [Claude Desktop configuration in the quick start](../README.md#2-connect-claude-desktop)
to run the published package with `uvx`. For remote FreeCAD installations, see
[remote connections](configuration.md#remote-connections).

### Windows client launch troubleshooting

First confirm that the external server can start with `uvx freecad-mcp --help`.
The MCP server communicates with its client over standard input/output. Port
9875 is the addon's XML-RPC endpoint, so do not configure an HTTP/SSE MCP client
to connect directly to that port.

Some Windows clients report `EFTYPE` / `uv_spawn` when launching the Python
entrypoint executable. A [reported workaround](https://github.com/neka-nat/freecad-mcp/issues/140)
is to launch it through `cmd`:

```json
["cmd", "/c", "freecad-mcp"]
```

Use the absolute path to `freecad-mcp.exe` if it is not on the client's `PATH`,
and adapt this command array to your client's configuration format. This is a
client-specific workaround, not a requirement for all Windows clients.

After connecting, ask the client to create a new document with a small
`Part::Box`. Confirm that the box appears in FreeCAD and that `list_documents`
and `get_objects` return it. The addon provides CAD tools; an external MCP client
is still responsible for the conversation and model's tool-calling loop.

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
