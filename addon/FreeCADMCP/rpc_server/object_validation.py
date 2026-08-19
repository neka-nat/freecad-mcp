"""Post-recompute validity checks for FreeCAD document objects."""

from typing import Any


_FAILED_STATES = {"invalid", "error", "touched"}


def _object_states(obj: Any) -> list[str]:
    """Return FreeCAD's state labels without assuming a concrete container."""
    try:
        raw_state = obj.State
    except Exception:
        return []

    if isinstance(raw_state, str):
        return [raw_state]

    try:
        return [str(item) for item in raw_state]
    except Exception:
        return []


def object_validity_error(obj: Any) -> str | None:
    """Return a diagnostic when ``obj`` is invalid, otherwise ``None``.

    Shape presence is deliberately not used as the discriminator. Containers,
    groups, spreadsheets, and empty sketches can all be valid without a shape.
    """
    name = str(getattr(obj, "Name", "<unknown>"))
    states = _object_states(obj)
    failed_states = [
        state for state in states if state.strip().casefold() in _FAILED_STATES
    ]
    is_valid = getattr(obj, "isValid", None)

    if callable(is_valid):
        try:
            is_valid_result = bool(is_valid())
        except Exception as exc:
            return (
                f"Object '{name}' exists, but its validity could not be checked after "
                f"recompute: {type(exc).__name__}: {exc}. Fix or remove the object "
                "before building on it."
            )
    else:
        is_valid_result = True

    # FreeCAD's isValid() only reflects the Error bit. A feature can still be
    # incomplete after recompute while its State reports Touched, so retain the
    # explicit state check requested by issue #110.
    if is_valid_result and not failed_states:
        return None

    get_status = getattr(obj, "getStatusString", None)
    try:
        reason = str(get_status()).strip() if callable(get_status) else ""
    except Exception:
        reason = ""

    state = ", ".join(states) if states else "unknown"

    detail = f": {reason}" if reason else ""
    return (
        f"Object '{name}' exists but failed to compute{detail} "
        f"(State: {state}). Fix the cause or remove the object before building "
        "on it."
    )
