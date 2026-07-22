"""Shared test setup: stub the FreeCAD module and make the addon importable.

The addon modules under ``addon/FreeCADMCP/rpc_server`` import ``FreeCAD``
at module level. Outside a running FreeCAD there is no such module, so a
minimal stub is installed into ``sys.modules`` before any addon import.
Only the attributes the pure-Python modules actually touch are stubbed.
"""

import sys
import types
from pathlib import Path

ADDON_DIR = Path(__file__).resolve().parent.parent / "addon" / "FreeCADMCP"


def _install_freecad_stub() -> types.ModuleType:
    if "FreeCAD" in sys.modules:
        return sys.modules["FreeCAD"]

    fc = types.ModuleType("FreeCAD")

    class Console:
        messages: list = []

        @classmethod
        def PrintMessage(cls, msg):
            cls.messages.append(("message", msg))

        @classmethod
        def PrintWarning(cls, msg):
            cls.messages.append(("warning", msg))

        @classmethod
        def PrintError(cls, msg):
            cls.messages.append(("error", msg))

    class Vector:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x, self.y, self.z = x, y, z

    class Rotation:
        def __init__(self, axis=None, angle=0.0):
            self.Axis = axis if axis is not None else Vector(0, 0, 1)
            self.Angle = angle

    class Placement:
        def __init__(self, base=None, rotation=None):
            self.Base = base if base is not None else Vector()
            self.Rotation = rotation if rotation is not None else Rotation()

    class Document:
        pass

    class DocumentObject:
        pass

    fc.Console = Console
    fc.Vector = Vector
    fc.Rotation = Rotation
    fc.Placement = Placement
    fc.Document = Document
    fc.DocumentObject = DocumentObject
    fc.getUserAppDataDir = lambda: ""
    sys.modules["FreeCAD"] = fc
    return fc


_install_freecad_stub()

if str(ADDON_DIR) not in sys.path:
    sys.path.insert(0, str(ADDON_DIR))
