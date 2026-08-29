from dataclasses import dataclass

from .freecad_client import FreeCADConnection


@dataclass
class ServerState:
    only_text_feedback: bool = False
    rpc_host: str = "localhost"
    auth_token: str | None = None
    freecad_connection: FreeCADConnection | None = None
