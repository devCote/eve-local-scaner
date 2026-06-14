"""Shared helpers for the native zKill fitting popup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from paths import user_data_path

FITTING_TTL_SECONDS = 24 * 3600
IMAGE_CACHE_DIR = user_data_path(Path("cache") / "eve_images")

LOW_FLAGS = set(range(11, 19))
MID_FLAGS = set(range(19, 27))
HIGH_FLAGS = set(range(27, 35))
RIG_FLAGS = set(range(92, 100))
SUBSYSTEM_FLAGS = set(range(125, 133))


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def transparency_to_alpha(transparency: int) -> int:
    transparency = max(0, min(100, int(transparency)))
    if transparency >= 99:
        transparency = 99
    return int(round(255 * (100 - transparency) / 100))


def format_isk_short(value: Any) -> str:
    try:
        num = float(value or 0)
    except Exception:
        return "-"
    abs_num = abs(num)
    if abs_num >= 1_000_000_000:
        out = f"{num / 1_000_000_000:.2f}".replace('.', ',')
        return f"{out}b ISK"
    if abs_num >= 1_000_000:
        out = f"{num / 1_000_000:.2f}".replace('.', ',')
        return f"{out}m ISK"
    if abs_num >= 1_000:
        out = f"{num / 1_000:.2f}".replace('.', ',')
        return f"{out}k ISK"
    out = f"{num:.0f}".replace('.', ',')
    return f"{out} ISK"
