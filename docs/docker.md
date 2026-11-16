# Running the MCP server in Docker

[Back to README](../README.md) · [Configuration](configuration.md)

If you would rather not install Python or uv on your host, you can run the MCP
server in Docker. FreeCAD and the addon still run on the host; the container only
holds the MCP server and its Python dependencies.

## Linux: host networking (recommended)

```bash
docker build -t freecad-mcp .
docker run --rm --init --network host freecad-mcp
```

With `--network host` the container shares your machine's loopback, so it reaches
the addon at `localhost:9875` and serves MCP at `http://localhost:8000/mcp`. Nothing
else needs configuring: the addon keeps its default loopback-only setting, and the
server listens on `127.0.0.1` only, so no token is required. This works on Linux
only; on Docker Desktop (Mac, Windows) use the bridge setup below.

Options go after the image name, for example `--listen-port 9000` or
`--listen-token <token>` (or `-e FREECAD_MCP_LISTEN_TOKEN`) to also require a token.

## Connect your MCP client

**Clients that support HTTP servers** (Claude Code, Cursor, VS Code and others).
For Claude Code:

```bash
claude mcp add --transport http freecad http://localhost:8000/mcp
```

Or in a project `.mcp.json`; most clients accept the same shape, though the
field names (`type`, `url`, `headers`) vary slightly, so check your client's docs:

```json
{
  "mcpServers": {
    "freecad": { "type": "http", "url": "http://localhost:8000/mcp" }
  }
}
```

Keep the container running while you work. If you set a listen token, add the
header `Authorization: Bearer <token>` (`--header` for `claude mcp add`, or
`"headers": { "Authorization": "Bearer ..." }` in the JSON).

**Claude Desktop** takes local servers from `claude_desktop_config.json` as
commands, not URLs, and its remote-server support is not meant for `localhost`.
Let it start the container itself over stdio instead. This needs no port, no token
and no running container, because Claude Desktop launches it on demand:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--init", "--network", "host",
               "freecad-mcp", "--transport", "stdio"]
    }
  }
}
```

Use `-i`, never `-t`: a terminal corrupts the protocol stream. This form works with
any client that launches commands, including Claude Code
(`claude mcp add freecad -- docker run ...`). With stdio there is no network
listener at all, so it is the lowest-risk way to run the container.

FreeCAD does not have to be running when the server starts. Each tool call
connects to the addon when it is made, so start FreeCAD and its RPC server whenever
you like.

## Bridge networking (Docker Desktop, or if you avoid host networking)

Without host networking the container reaches FreeCAD through
`host.docker.internal`, which requires opening up the addon:

```bash
export FREECAD_MCP_LISTEN_TOKEN="$(openssl rand -hex 32)"
docker run --rm --init \
  --add-host=host.docker.internal:host-gateway \
  -e FREECAD_MCP_LISTEN_TOKEN \
  -p 127.0.0.1:8000:8000 \
  freecad-mcp --transport streamable-http --listen-host 0.0.0.0 \
  --host host.docker.internal
```

- In FreeCAD, enable **Remote Connections** in the addon, restart the RPC server,
  and add the Docker bridge subnet (see `docker network inspect bridge`, often
  `172.17.0.0/16`) to **Allowed IPs**. If the addon has a token set, also pass
  `-e FREECAD_MCP_TOKEN`.
- Your host firewall may block traffic from the Docker bridge to port 9875. If the
  container times out connecting to FreeCAD, allow it, or use host networking.
- The container refuses to start without a token because it listens on all of its
  interfaces. Always publish the port as `127.0.0.1:8000:8000`, never `8000:8000`.
- Clients send `Authorization: Bearer <token>`, as described above.

### Running without a token

If your client cannot send an Authorization header, you can opt out by adding
`--allow-insecure-remote` and dropping `-e FREECAD_MCP_LISTEN_TOKEN`:

```bash
docker run --rm --init \
  --add-host=host.docker.internal:host-gateway \
  -p 127.0.0.1:8000:8000 \
  freecad-mcp --transport streamable-http --listen-host 0.0.0.0 \
  --host host.docker.internal --allow-insecure-remote
```

> [!WARNING]
> Without a token, anything that can reach the port can run arbitrary Python in
> your FreeCAD session through `execute_code`. Do this only when the port is
> published on `127.0.0.1`. Publishing it as `-p 8000:8000` or `-p 0.0.0.0:8000:8000`
> exposes your machine to your whole network.

See [Configuration](configuration.md#http-and-sse-transports) for all HTTP options.
