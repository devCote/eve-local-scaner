"""Local EVE inventory type-name resolver.

`types.json` is now the single source for local type names.

Supported format:
  {"33475": "Mobile Depot"}
  {"33475": {"name": "Mobile Depot"}}

Lookup order:
  1. %LOCALAPPDATA%/EVE Local Intel Scanner/types.json
  2. bundled/project types.json

This lets an installed app use a bundled types.json, while still allowing a
user to drop a newer file into the writable app-data folder later.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paths import app_path, user_data_path


_CACHE: dict[int, str] | None = None


def _normalize_name(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str):
            return name.strip()

        # Be tolerant of SDE translation-like shapes if someone stores them
        # directly in types.json.
        for key in ("en", "en-us", "en_US"):
            translated = value.get(key)
            if isinstance(translated, str) and translated.strip():
                return translated.strip()

    if value is None:
        return ""

    return str(value).strip()


def _load_one(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[TYPE NAMES] failed to load {path}: {exc}")
        return {}

    if not isinstance(data, dict):
        print(f"[TYPE NAMES] invalid types.json format: {path}")
        return {}

    result: dict[int, str] = {}
    for key, value in data.items():
        try:
            type_id = int(key)
        except Exception:
            continue

        name = _normalize_name(value)
        if name and not name.lower().startswith("type "):
            result[type_id] = name

    return result


def load_type_names(force_reload: bool = False) -> dict[int, str]:
    global _CACHE

    if _CACHE is not None and not force_reload:
        return _CACHE

    # User-data copy overrides bundled/project copy. This is useful after
    # installation because Program Files may be read-only.
    user_types = user_data_path("types.json")
    bundled_types = Path(app_path("types.json"))

    merged: dict[int, str] = {}
    merged.update(_load_one(bundled_types))
    merged.update(_load_one(user_types))

    if not merged:
        print(
            "[TYPE NAMES] types.json not found or empty. "
            "Type names will fall back to ESI/cache."
        )

    _CACHE = merged
    return _CACHE


def reload_type_names() -> dict[int, str]:
    return load_type_names(force_reload=True)


def get_local_type_name(type_id: int) -> str:
    try:
        type_id = int(type_id)
    except Exception:
        return ""

    return load_type_names().get(type_id, "")
