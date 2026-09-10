from dataclasses import dataclass

from .freecad_client import FreeCADConnection


@dataclass
class ServerState:
    only_text_feedback: bool = False
    rpc_host: str = "localhost"
    freecad_connection: FreeCADConnection | None = None
    freecadcmd: list[str] | None = None  # headless FreeCAD command; None = auto-detect
