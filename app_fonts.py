from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase

from paths import USER_DATA_DIR, ensure_user_data_dirs, resource_path


APP_FONT_FAMILY = "Anthropic Serif"
FALLBACK_FONT_FAMILY = "Georgia"

_DEFAULT_FONT_CANDIDATES = (
    "Anthropic Serif",
    "AnthropicSerif Text",
    "AnthropicSerif",
    "Bahnschrift",
    "Georgia",
)

_SELECTED_FONT_FAMILY: str | None = None
_FONT_LOADED_FAMILY: str | None = None
_LOADED_FONT_PATHS: set[str] = set()
_LOADED_FONT_FAMILIES: list[str] = []


def _clean_font_family(value: str | None) -> str:
    value = str(value or "").strip()
    value = value.replace('"', "").replace("'", "")
    return value[:120]


def _font_key(value: str | None) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _font_exists(family: str) -> bool:
    family_norm = _clean_font_family(family).lower()
    if not family_norm:
        return False

    try:
        return any(str(item).strip().lower() == family_norm for item in QFontDatabase.families())
    except Exception:
        return False


def ensure_user_fonts_dir() -> Path:
    ensure_user_data_dirs()
    path = USER_DATA_DIR / "fonts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _candidate_font_dirs() -> list[Path]:
    paths: list[Path] = []

    try:
        paths.append(Path(resource_path(str(Path("assets") / "fonts"))))
    except Exception:
        pass

    try:
        paths.append(ensure_user_fonts_dir())
    except Exception:
        pass

    # Preserve order while removing duplicates.
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve()).lower() if path.exists() else str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _candidate_font_files() -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()

    for font_dir in _candidate_font_dirs():
        if not font_dir.exists() or not font_dir.is_dir():
            continue

        for pattern in ("*.ttf", "*.otf", "*.ttc", "*.otc"):
            for path in sorted(font_dir.glob(pattern)):
                key = str(path.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                result.append(path)

    return result


def refresh_app_fonts() -> list[str]:
    """Scan assets/fonts and the user Local fonts folder for font files."""
    load_available_app_fonts(force=True)
    return available_font_families()


def load_available_app_fonts(force: bool = False) -> list[str]:
    """Load all app/user font files and return discovered font families."""
    global _LOADED_FONT_PATHS, _LOADED_FONT_FAMILIES, _FONT_LOADED_FAMILY

    if force:
        _FONT_LOADED_FAMILY = None

    for font_path in _candidate_font_files():
        path_key = str(font_path.resolve()).lower()
        if path_key in _LOADED_FONT_PATHS:
            continue

        font_id = QFontDatabase.addApplicationFont(str(font_path))
        _LOADED_FONT_PATHS.add(path_key)

        if font_id < 0:
            print(f"[FONT] failed to load: {font_path}")
            continue

        families = [str(f).strip() for f in QFontDatabase.applicationFontFamilies(font_id) if str(f).strip()]
        for family in families:
            if family not in _LOADED_FONT_FAMILIES:
                _LOADED_FONT_FAMILIES.append(family)
                print(f"[FONT] loaded app font: {family} from {font_path}")

    return list(_LOADED_FONT_FAMILIES)


def available_font_families(include_common_system: bool = True) -> list[str]:
    """Fonts shown in Options.

    This intentionally focuses on app/user fonts instead of dumping every
    installed Windows font into the combo box.
    """
    load_available_app_fonts()

    result: list[str] = []

    def add(name: str | None):
        name = _clean_font_family(name)
        if not name:
            return
        if name not in result:
            result.append(name)

    for family in _LOADED_FONT_FAMILIES:
        add(family)

    if include_common_system:
        for family in _DEFAULT_FONT_CANDIDATES:
            if _font_exists(family):
                add(family)

    add(FALLBACK_FONT_FAMILY)
    return result


def resolve_app_font_family(preferred: str | None = None) -> str:
    """Resolve the requested family to a real loaded/installed font family."""
    global _FONT_LOADED_FAMILY

    requested = _clean_font_family(preferred or _SELECTED_FONT_FAMILY or APP_FONT_FAMILY)
    cache_key = requested or APP_FONT_FAMILY

    if _FONT_LOADED_FAMILY and _font_key(_FONT_LOADED_FAMILY) == _font_key(cache_key):
        return _FONT_LOADED_FAMILY

    load_available_app_fonts()

    if requested and _font_exists(requested):
        _FONT_LOADED_FAMILY = requested
        return _FONT_LOADED_FAMILY

    requested_key = _font_key(requested)
    if requested_key:
        for family in available_font_families():
            family_key = _font_key(family)
            if family_key == requested_key or requested_key in family_key or family_key in requested_key:
                if _font_exists(family):
                    _FONT_LOADED_FAMILY = family
                    return _FONT_LOADED_FAMILY

    for family in _DEFAULT_FONT_CANDIDATES:
        if _font_exists(family):
            _FONT_LOADED_FAMILY = family
            return _FONT_LOADED_FAMILY

    _FONT_LOADED_FAMILY = FALLBACK_FONT_FAMILY
    print(f"[FONT] {requested or APP_FONT_FAMILY} not found, using fallback: {_FONT_LOADED_FAMILY}")
    return _FONT_LOADED_FAMILY


def set_app_font_family(preferred: str | None) -> str:
    """Set global UI font preference and return the resolved real family."""
    global _SELECTED_FONT_FAMILY, _FONT_LOADED_FAMILY

    cleaned = _clean_font_family(preferred) or APP_FONT_FAMILY
    if cleaned != _SELECTED_FONT_FAMILY:
        _SELECTED_FONT_FAMILY = cleaned
        _FONT_LOADED_FAMILY = None
    return resolve_app_font_family(cleaned)


def get_app_font_family() -> str:
    return resolve_app_font_family(_SELECTED_FONT_FAMILY or APP_FONT_FAMILY)


def make_app_font(point_size: int | None = None, family: str | None = None) -> QFont:
    font = QFont(resolve_app_font_family(family))
    if point_size is not None:
        font.setPointSize(int(point_size))
    return font
