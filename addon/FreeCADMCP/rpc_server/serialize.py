import FreeCAD as App
import json


def _get_optional_app_type(name: str) -> type | tuple[type, ...] | None:
    value = getattr(App, name, None)
    if isinstance(value, type):
        return value
    if isinstance(value, tuple) and all(isinstance(item, type) for item in value):
        return value
    return None


_COLOR_TYPE = _get_optional_app_type("Color")


def serialize_value(value):
    if isinstance(value, (int, float, str, bool)):
        return value
    elif isinstance(value, App.Vector):
        return {"x": value.x, "y": value.y, "z": value.z}
    elif isinstance(value, App.Rotation):
        return {
            "Axis": {"x": value.Axis.x, "y": value.Axis.y, "z": value.Axis.z},
            "Angle": value.Angle,
        }
    elif isinstance(value, App.Placement):
        return {
            "Base": serialize_value(value.Base),
            "Rotation": serialize_value(value.Rotation),
        }
    elif isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    elif _COLOR_TYPE is not None and isinstance(value, _COLOR_TYPE):
        return tuple(value)
    else:
        return str(value)


def safe_attr(obj, name):
    """``getattr`` that also tolerates FreeCAD properties which raise on read.

    ``getattr(obj, name, None)`` only swallows AttributeError. Reading ``Shape``
    on an object whose recompute failed raises RuntimeError instead, which the
    three-argument form does not catch.
    """
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def serialize_shape(shape):
    """Summarise a shape, tolerating shapes that failed to compute.

    A feature whose recompute failed still exposes a ``Shape``, but reading its
    geometry raises ``RuntimeError: shape is invalid``. Letting that escape turns
    a single broken object into an XML-RPC Fault that fails the whole
    ``get_objects`` call for the document -- and ``get_objects`` is what the
    asset-creation prompt tells the model to run before every task. Report the
    breakage on that one object instead of blinding the caller to all of them.
    """
    if shape is None:
        return None
    try:
        if shape.isNull():
            return {"Valid": False, "Error": "shape is null (feature failed to compute)"}
        return {
            "Volume": shape.Volume,
            "Area": shape.Area,
            "VertexCount": len(shape.Vertexes),
            "EdgeCount": len(shape.Edges),
            "FaceCount": len(shape.Faces),
        }
    except Exception as e:
        return {"Valid": False, "Error": f"{type(e).__name__}: {e}"}


def serialize_view_object(view):
    if view is None:
        return None
    result = {}
    try:
        result["ShapeColor"] = serialize_value(view.ShapeColor)
    except AttributeError:
        pass
    try:
        result["Transparency"] = view.Transparency
    except AttributeError:
        pass
    try:
        result["Visibility"] = view.Visibility
    except AttributeError:
        pass
    return result


def serialize_object(obj):
    if isinstance(obj, list):
        return [serialize_object(item) for item in obj]
    elif isinstance(obj, App.Document):
        return {
            "Name": obj.Name,
            "Label": obj.Label,
            "FileName": obj.FileName,
            "Objects": [serialize_object(child) for child in obj.Objects],
        }
    else:
        result = {
            "Name": obj.Name,
            "Label": obj.Label,
            "TypeId": obj.TypeId,
            "Properties": {},
            "Placement": serialize_value(safe_attr(obj, "Placement")),
            "Shape": serialize_shape(safe_attr(obj, "Shape")),
            "ViewObject": {},
        }

        for prop in obj.PropertiesList:
            try:
                result["Properties"][prop] = serialize_value(getattr(obj, prop))
            except Exception as e:
                result["Properties"][prop] = f"<error: {str(e)}>"

        if hasattr(obj, "ViewObject") and obj.ViewObject is not None:
            view = obj.ViewObject
            result["ViewObject"] = serialize_view_object(view)

        return result
