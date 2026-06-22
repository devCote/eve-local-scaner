"""Compatibility wrapper.

Old code imported `get_ship_name()` from this module. The app no longer uses
ships.json. All local names now come from types.json via type_names.py.
"""

from __future__ import annotations

from type_names import get_local_type_name, load_type_names, reload_type_names


def load_ship_names():
    """Return the full local type-name cache for backwards compatibility."""
    return load_type_names()


def reload_ship_names():
    return reload_type_names()


def get_ship_name(ship_type_id: int) -> str:
    try:
        type_id = int(ship_type_id)
    except Exception:
        return "Unknown"

    return get_local_type_name(type_id) or f"Type {type_id}"
