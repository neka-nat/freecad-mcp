# Configuration

[Back to README](../README.md) · [Installation](installation.md) · [Tools](tools.md)

## Auto-start RPC server

By default, the RPC server must be started manually each time FreeCAD opens. To
start it automatically:

1. Switch to the **MCP Addon** workbench and open the **FreeCAD MCP** menu.
2. Check **Auto-Start Server**.

The setting is saved to `freecad_mcp_settings.json` and persists across sessions.
On the next FreeCAD launch, the RPC server starts automatically once the
application finishes loading. Uncheck **Auto-Start Server** in the same menu to
disable it.

For a container or a provisioning script there is no one to click the toolbar, so
the addon also reads the `FREECAD_MCP_AUTO_START` environment variable and lets it
override the saved setting. Set it to `1`, `true`, `yes` or `on` to start the
server on launch, or to `0`, `false`, `no` or `off` to leave it stopped. Values
are matched case-insensitively; an unset or blank variable leaves the saved
setting in charge, and an unrecognised value is reported in the Report View and
ignored. FreeCAD must inherit the variable, so set it in the environment that
launches FreeCAD itself:

```bash
FREECAD_MCP_AUTO_START=1 freecad
```

```dockerfile
ENV FREECAD_MCP_AUTO_START=1
```

## Text feedback and screenshots

Pass `--only-text-feedback` to omit optional screenshots from tool feedback and
reduce token use:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": ["freecad-mcp", "--only-text-feedback"]
    }
  }
}
```

You can also control optional screenshots per call with `include_screenshot`
and `view_name`. The global flag takes precedence over `include_screenshot`.
See [screenshot options](tools.md#screenshot-options) for the applicable tools
and the explicit `get_view` tool.

## Remote connections

By default, the RPC server listens on `localhost` and does not accept remote
connections. To control FreeCAD from another machine on your network, configure
both the addon and the MCP client.

Unless you [set an auth token](#3-require-an-auth-token), the RPC server has no
authentication, and it never encrypts traffic. Any program that can reach the
port from an allowed address can call every tool, including `execute_code`,
which runs arbitrary Python inside FreeCAD with your user's permissions. Set a
token whenever remote connections are on, allow only machines you trust, keep
the list as narrow as possible, and prefer an [SSH tunnel](#alternative-ssh-tunnel)
on networks you do not control. Whatever the settings, the server refuses
requests sent by web browsers, so a web page cannot call it.

### 1. Enable remote connections in FreeCAD

In the **FreeCAD MCP** toolbar:

1. Check **Remote Connections**. On the next server restart, the RPC server binds
   to `0.0.0.0` (all interfaces). It only accepts connections from the IP addresses
   or CIDR subnets configured in **Allowed IPs**, which defaults to `127.0.0.1`.
2. Click **Configure Allowed IPs** and enter a comma-separated list of allowed
   client IP addresses or CIDR subnets, for example:

   ```text
   192.168.1.100, 10.0.0.0/24
   ```

   Invalid entries are rejected with an error dialog.
3. Restart the RPC server after changing these settings.

### 2. Point the MCP server at the remote host

Pass `--host` with the IP address or hostname of the machine running FreeCAD:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": ["freecad-mcp", "--host", "192.168.1.100"]
    }
  }
}
```

The `--host` value is validated on startup and must be a valid IPv4/IPv6 address
or hostname. Restart your MCP client after updating its configuration.

`--host` selects the GUI RPC host. [Headless execution](execution.md#headless-execution)
runs on the machine hosting the MCP server, so its file paths must be accessible
there.

### 3. Require an auth token

In the **FreeCAD MCP** toolbar, click **Set Auth Token** and enter a long random
value, such as the output of
`python -c "import secrets; print(secrets.token_urlsafe(32))"`. Restart the RPC
server. From then on, it answers only requests that carry the token. Clear the
field to turn authentication off again.

Give the MCP server the same token in the `FREECAD_MCP_TOKEN` environment
variable:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uvx",
      "args": ["freecad-mcp", "--host", "192.168.1.100"],
      "env": { "FREECAD_MCP_TOKEN": "<the token set in FreeCAD>" }
    }
  }
}
```

`--auth-token <token>` works too, but other users of the machine can read
command-line arguments in the process list. The token travels unencrypted, so
on a network you do not control, use the SSH tunnel below instead.

### Alternative: SSH tunnel

To reach FreeCAD on another machine without opening the port to the network,
leave **Remote Connections** off and forward the port over SSH from the machine
that runs the MCP server:

```bash
ssh -N -L 9875:localhost:9875 user@freecad-host
```

Keep the MCP server on its default `--host localhost`. With remote connections
off, the RPC server only answers requests addressed to `localhost` or a
loopback address such as `127.0.0.1`.
