from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paths import EXE_DIR


DEFAULT_UI_SETTINGS: dict[str, Any] = {
    "transparency": 10,
    "blur": 0,
    "font_size": 10,
    "frame_color": "#161616",
    "text_color": "#d6d6d6",
    "bg_color": "#0b0b0b",
}


def get_user_settings_path() -> Path:
    return EXE_DIR / "user.json"


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
            7,
            16,
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


def load_ui_settings() -> dict[str, Any]:
    path = get_user_settings_path()

    if not path.exists():
        return dict(DEFAULT_UI_SETTINGS)

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict) and isinstance(data.get("ui"), dict):
            data = data["ui"]

        if not isinstance(data, dict):
            return dict(DEFAULT_UI_SETTINGS)

        settings = normalize_ui_settings(data)
        print(f"[USER SETTINGS] loaded: {path} {settings}")
        return settings

    except Exception as e:
        print(f"[USER SETTINGS] failed to load {path}: {e}")
        return dict(DEFAULT_UI_SETTINGS)


def save_ui_settings(settings: dict[str, Any]) -> None:
    path = get_user_settings_path()
    settings = normalize_ui_settings(settings)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")

        with tmp.open("w", encoding="utf-8") as f:
            json.dump({"ui": settings}, f, indent=2, ensure_ascii=False)

        tmp.replace(path)

    except Exception as e:
        print(f"[USER SETTINGS] failed to save {path}: {e}")
