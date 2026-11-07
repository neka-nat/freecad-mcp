"""Snapshot FEM constraints in explicit units in the solver's GUI operation."""

import math
from typing import Any


def _value(quantity: Any, unit: str) -> float:
    converted = quantity.getValueAs(unit)
    value = float(getattr(converted, "Value", converted))
    if not math.isfinite(value):
        raise ValueError(f"Non-finite load in {unit}")
    return value


def _references(constraint: Any) -> list[str]:
    return [
        f"{obj.Name}:{sub}"
        for obj, subs in constraint.References
        for sub in (subs if isinstance(subs, (list, tuple)) else [subs])
    ]


def applied_loads(analysis: Any) -> list[dict[str, Any]]:
    """Read supported mechanical loads; a failed read must stop the solve."""
    loads = []
    for member in analysis.Group:
        tid = getattr(member, "TypeId", "")
        if tid == "Fem::ConstraintForce":
            vector = member.DirectionVector  # already accounts for Reversed
            direction = [float(vector.x), float(vector.y), float(vector.z)]
            if not all(math.isfinite(v) for v in direction):
                raise ValueError(f"Non-finite direction on {member.Name}")
            link = getattr(member, "Direction", None)
            source = "normal of the loaded face"
            if link and link[0] is not None:
                subs = link[1] if isinstance(link[1], (list, tuple)) else [link[1]]
                source = f"along {link[0].Name}:{','.join(subs)}"
            loads.append({
                "name": member.Name, "kind": "force",
                "newtons": _value(member.Force, "N"),
                "references": _references(member), "direction": direction,
                "direction_from": source, "reversed": bool(member.Reversed),
            })
        elif tid == "Fem::ConstraintPressure":
            loads.append({
                "name": member.Name, "kind": "pressure",
                "megapascals": _value(member.Pressure, "MPa"),
                "references": _references(member), "reversed": bool(member.Reversed),
            })
        elif tid == "Fem::ConstraintFixed":
            loads.append({"name": member.Name, "kind": "fixed", "references": _references(member)})
    return loads
