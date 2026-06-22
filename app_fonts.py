from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

from paths import resource_path


APP_FONT_FAMILY = "Anthropic Serif"
FALLBACK_FONT_FAMILY = "Georgia"

_FONT_LOADED_FAMILY: str | None = None


def _font_exists(family: str) -> bool:
    family_norm = str(family or "").strip().lower()
    if not family_norm:
        return False

    try:
        return any(str(item).strip().lower() == family_norm for item in QFontDatabase.families())
    except Exception:
        return False


def _candidate_font_files() -> list[Path]:
    """Font files are not bundled here.

    To use Anthropic Serif in the app, either install it in Windows or place
    your own font file into assets/fonts before building/running.

    Supported example names:
      assets/fonts/AnthropicSerif.ttf
      assets/fonts/AnthropicSerif.otf
      assets/fonts/AnthropicSerif-Regular.ttf
      assets/fonts/AnthropicSerif-Regular.otf
      assets/fonts/Anthropic Serif.ttf
      assets/fonts/Anthropic Serif.otf
    """
    names = (
        "AnthropicSerif.ttf",
        "AnthropicSerif.otf",
        "AnthropicSerif-Regular.ttf",
        "AnthropicSerif-Regular.otf",
        "Anthropic Serif.ttf",
        "Anthropic Serif.otf",
        "anthropic-serif.ttf",
        "anthropic-serif.otf",
        "anthropic_serif.ttf",
        "anthropic_serif.otf",
    )

    paths: list[Path] = []
    for name in names:
        try:
            paths.append(Path(resource_path(str(Path("assets") / "fonts" / name))))
        except Exception:
            pass
    return paths


def resolve_app_font_family() -> str:
    """Use Anthropic Serif if available, otherwise try assets/fonts, otherwise fallback."""
    global _FONT_LOADED_FAMILY

    if _FONT_LOADED_FAMILY:
        return _FONT_LOADED_FAMILY

    if _font_exists(APP_FONT_FAMILY):
        _FONT_LOADED_FAMILY = APP_FONT_FAMILY
        return _FONT_LOADED_FAMILY

    for font_path in _candidate_font_files():
        if not font_path.exists() or not font_path.is_file():
            continue

        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            print(f"[FONT] failed to load: {font_path}")
            continue

        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            _FONT_LOADED_FAMILY = str(families[0])
            print(f"[FONT] loaded app font: {_FONT_LOADED_FAMILY} from {font_path}")
            return _FONT_LOADED_FAMILY

    _FONT_LOADED_FAMILY = FALLBACK_FONT_FAMILY
    print(f"[FONT] {APP_FONT_FAMILY} not found, using fallback: {_FONT_LOADED_FAMILY}")
    return _FONT_LOADED_FAMILY


def make_app_font(point_size: int | None = None) -> QFont:
    font = QFont(resolve_app_font_family())
    if point_size is not None:
        font.setPointSize(int(point_size))
    return font
