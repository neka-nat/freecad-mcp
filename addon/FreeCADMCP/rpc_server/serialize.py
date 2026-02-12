import FreeCAD as App


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
    elif isinstance(value, (App.Color)):
        return tuple(value)
    else:
        return str(value)


def serialize_shape(shape):
    if shape is None:
        return None
    return {
        "Volume": shape.Volume,
        "Area": shape.Area,
        "VertexCount": len(shape.Vertexes),
        "EdgeCount": len(shape.Edges),
        "FaceCount": len(shape.Faces),
    }


def serialize_view_object(view):
    if view is None:
        return None
    return {
        "ShapeColor": serialize_value(view.ShapeColor),
        "Transparency": view.Transparency,
        "Visibility": view.Visibility,
    }


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
            "Placement": serialize_value(getattr(obj, "Placement", None)),
            "Shape": serialize_shape(getattr(obj, "Shape", None)),
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
