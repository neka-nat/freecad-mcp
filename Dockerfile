# MCP server only. FreeCAD and its addon run on the host (or elsewhere) and are
# reached over XML-RPC. Keeps the server's Python dependencies off the host.
FROM python:3.12-slim

COPY pyproject.toml README.md LICENSE /src/
COPY addon/FreeCADMCP/package.xml /src/addon/FreeCADMCP/package.xml
COPY src /src/src
RUN pip install --no-cache-dir /src && rm -rf /src

RUN useradd --create-home --uid 1000 mcp
USER mcp

EXPOSE 8000
ENTRYPOINT ["freecad-mcp"]
# Default: HTTP on 127.0.0.1:8000, reaching FreeCAD at localhost:9875. That is
# only reachable from the host with `docker run --network host`. For bridge
# networking see docs/docker.md (it needs --listen-host 0.0.0.0 and a token).
CMD ["--transport", "streamable-http"]
