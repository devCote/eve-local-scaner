from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paths import user_data_path


DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "transparency": 10,
    "blur": 0,
    "font_size": 10,
    "frame_color": "#161616",
    "text_color": "#d6d6d6",
    "bg_color": "#0b0b0b",
}

DEFAULT_WINDOW_SETTINGS: dict[str, Any] = {
    "x": None,
    "y": None,
    "width": 760,
    "height": 440,
}

DEFAULT_GENERAL_TABLE_SETTINGS: dict[str, Any] = {
    "column_widths": {
        "2": 120,
        "3": 64,
        "4": 54,
        "5": 86,
        "6": 190,
    },
    "visible_columns": {
        "3": True,   # Danger
        "4": True,   # Gang
        "5": True,   # Corp/Ally
        "6": True,   # Last Ships
    },
}

DEFAULT_ZKILL_TABLE_SETTINGS: dict[str, Any] = {
    "column_widths": {
        "0": 88,
        "1": 92,
        "2": 70,
        "3": 160,
    }
}


def get_user_settings_path() -> Path:
    return user_data_path("user.json")


def load_user_json() -> dict[str, Any]:
    path = get_user_settings_path()

    if not path.exists():
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception as e:
        print(f"[USER SETTINGS] failed to load {path}: {e}")
        return {}


def save_user_json(data: dict[str, Any]) -> None:
    path = get_user_settings_path()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")

        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        tmp.replace(path)

    except Exception as e:
        print(f"[USER SETTINGS] failed to save {path}: {e}")


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(value)
    except Exception:
        value = default

    return max(minimum, min(maximum, value))


def normalize_color(value: Any, default: str) -> str:
    value = str(value or "").strip().lower()

    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return value
        except Exception:
            pass

    return default


def normalize_ui_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    defaults = DEFAULT_UI_SETTINGS

    return {
        "transparency": clamp_int(
            raw.get("transparency", defaults["transparency"]),
            defaults["transparency"],
            0,
            100,
        ),
        "blur": 1 if bool(raw.get("blur", defaults["blur"])) else 0,
        "font_size": clamp_int(
            raw.get("font_size", defaults["font_size"]),
            defaults["font_size"],
            8,
            14,
        ),
        "frame_color": normalize_color(
            raw.get("frame_color", defaults["frame_color"]),
            defaults["frame_color"],
        ),
        "text_color": normalize_color(
            raw.get("text_color", defaults["text_color"]),
            defaults["text_color"],
        ),
        "bg_color": normalize_color(
            raw.get("bg_color", defaults["bg_color"]),
            defaults["bg_color"],
        ),
    }



def normalize_window_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    defaults = DEFAULT_WINDOW_SETTINGS

    x = raw.get("x", defaults["x"])
    y = raw.get("y", defaults["y"])

    try:
        x = int(x) if x is not None else None
    except Exception:
        x = None

    try:
        y = int(y) if y is not None else None
    except Exception:
        y = None

    return {
        "x": x,
        "y": y,
        "width": clamp_int(raw.get("width", defaults["width"]), defaults["width"], 250, 4000),
        "height": clamp_int(raw.get("height", defaults["height"]), defaults["height"], 200, 3000),
    }




def normalize_general_table_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    default_widths = DEFAULT_GENERAL_TABLE_SETTINGS["column_widths"]
    default_visible = DEFAULT_GENERAL_TABLE_SETTINGS["visible_columns"]
    raw_widths = raw.get("column_widths") if isinstance(raw.get("column_widths"), dict) else {}
    raw_visible = raw.get("visible_columns") if isinstance(raw.get("visible_columns"), dict) else {}

    widths: dict[str, int] = {}

    for col, default in default_widths.items():
        # Small columns are allowed, but not zero. Qt will also respect the
        # header minimum section size from the table setup.
        widths[col] = clamp_int(raw_widths.get(col, default), default, 6, 1200)

    visible_columns: dict[str, bool] = {}
    for col, default in default_visible.items():
        visible_columns[col] = bool(raw_visible.get(col, default))

    return {
        "column_widths": widths,
        "visible_columns": visible_columns,
    }


def load_general_table_settings() -> dict[str, Any]:
    data = load_user_json()
    raw = data.get("general_table") if isinstance(data, dict) else None
    settings = normalize_general_table_settings(raw if isinstance(raw, dict) else None)
    print(f"[USER SETTINGS] loaded general table: {get_user_settings_path()} {settings}")
    return settings


def save_general_table_settings(settings: dict[str, Any]) -> None:
    data = load_user_json()
    data["general_table"] = normalize_general_table_settings(settings)
    save_user_json(data)


def normalize_zkill_table_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    default_widths = DEFAULT_ZKILL_TABLE_SETTINGS["column_widths"]
    raw_widths = raw.get("column_widths") if isinstance(raw.get("column_widths"), dict) else {}

    widths: dict[str, int] = {}

    for col, default in default_widths.items():
        widths[col] = clamp_int(raw_widths.get(col, default), default, 26, 1400)

    return {"column_widths": widths}


def load_zkill_table_settings() -> dict[str, Any]:
    data = load_user_json()
    raw = data.get("zkill_table") if isinstance(data, dict) else None
    settings = normalize_zkill_table_settings(raw if isinstance(raw, dict) else None)
    print(f"[USER SETTINGS] loaded zkill table: {get_user_settings_path()} {settings}")
    return settings


def save_zkill_table_settings(settings: dict[str, Any]) -> None:
    data = load_user_json()
    data["zkill_table"] = normalize_zkill_table_settings(settings)
    save_user_json(data)

def load_ui_settings() -> dict[str, Any]:
    data = load_user_json()

    if isinstance(data, dict) and isinstance(data.get("ui"), dict):
        raw = data["ui"]
    else:
        raw = data if isinstance(data, dict) else {}

    settings = normalize_ui_settings(raw)
    print(f"[USER SETTINGS] loaded UI: {get_user_settings_path()} {settings}")
    return settings


def save_ui_settings(settings: dict[str, Any]) -> None:
    data = load_user_json()
    data["ui"] = normalize_ui_settings(settings)
    save_user_json(data)


def load_window_settings() -> dict[str, Any]:
    data = load_user_json()
    raw = data.get("window") if isinstance(data, dict) else None
    settings = normalize_window_settings(raw if isinstance(raw, dict) else None)
    print(f"[USER SETTINGS] loaded window: {get_user_settings_path()} {settings}")
    return settings


def save_window_settings(settings: dict[str, Any]) -> None:
    data = load_user_json()
    data["window"] = normalize_window_settings(settings)
    save_user_json(data)
