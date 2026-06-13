"""zKill tab panel: API-only, no browser toolbar, no QtWebEngine."""

from __future__ import annotations

import re

from PySide6.QtWidgets import QVBoxLayout, QWidget

from zkill_viewer import ZKillViewer


CHARACTER_RE = re.compile(r"(?:zkillboard\.com/)?character/(\d+)", re.IGNORECASE)
KILL_RE = re.compile(r"(?:zkillboard\.com/)?kill/(\d+)", re.IGNORECASE)
SHIP_RE = re.compile(r"(?:zkillboard\.com/)?ship/(\d+)", re.IGNORECASE)
CORP_RE = re.compile(r"(?:zkillboard\.com/)?corporation/(\d+)", re.IGNORECASE)
ALLIANCE_RE = re.compile(r"(?:zkillboard\.com/)?alliance/(\d+)", re.IGNORECASE)


class ZkillPanel(QWidget):
    def __init__(self, parent=None, test_mode: bool = False):
        super().__init__(parent)
        self.test_mode = test_mode
        self.current_url = ""
        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # No old browser buttons, no address bar, no WebEngine widget.
        self.viewer = ZKillViewer(self)
        layout.addWidget(self.viewer, 1)

    def apply_ui_settings(self, font_size: int | None = None, text_color: str | None = None, frame_color: str | None = None):
        if hasattr(self, "viewer"):
            self.viewer.apply_ui_settings(font_size=font_size, text_color=text_color, frame_color=frame_color)

    def set_mode(self, mode: str):
        if hasattr(self, "viewer"):
            self.viewer.set_mode(mode)

    def close_fit_popup(self):
        if hasattr(self, "viewer"):
            self.viewer.close_fit_popup()

    def load_url(self, url: str, profile_hint: dict | None = None):
        """Compatibility method used by ui.py.

        ui.py can still send old zKill URLs here. We parse character URLs and
        load them via API. Chromium/QtWebEngine is never created.
        """
        text = str(url or "").strip()
        if not text:
            return

        self.current_url = text
        normalized = text
        if normalized.isdigit():
            self.open_character_in_compact(int(normalized), f"#{normalized}", profile_hint=profile_hint)
            return

        if not normalized.startswith(("http://", "https://")) and "zkillboard.com" in normalized:
            normalized = "https://" + normalized

        match = CHARACTER_RE.search(normalized)
        if match:
            self.open_character_in_compact(int(match.group(1)), profile_hint=profile_hint)
            return

        match = KILL_RE.search(normalized)
        if match:
            self.viewer.show_message(
                f"Killmail selected: {int(match.group(1))}\n\n"
                "Browser was removed. Full killmail API detail view can be added later.\n"
                "Use pilot double-click to load character Overview/Kills/Losses."
            )
            return

        match = SHIP_RE.search(normalized)
        if match:
            self.viewer.show_message(
                f"Ship selected: {int(match.group(1))}\n\n"
                "Browser was removed. Ship API page is not implemented yet."
            )
            return

        if CORP_RE.search(normalized) or ALLIANCE_RE.search(normalized):
            self.viewer.show_message(
                "Corporation/alliance selected.\n\n"
                "Browser was removed. Corp/alliance API pages are not implemented yet."
            )
            return

        self.viewer.show_message(
            "Unsupported zKill input.\n\n"
            "Double-click a pilot name in General, or pass a character URL like:\n"
            "https://zkillboard.com/character/123456789/"
        )

    def open_character_in_compact(self, character_id: int, character_name: str = "Unknown", profile_hint: dict | None = None):
        character_id = int(character_id or 0)
        if not character_id:
            self.viewer.show_message("Invalid character id.")
            return

        self.current_url = f"https://zkillboard.com/character/{character_id}/"
        self.viewer.open_character(character_id, character_name, profile_hint=profile_hint)

    def open_character(self, character_id: int, character_name: str = "Unknown", profile_hint: dict | None = None):
        self.open_character_in_compact(character_id, character_name, profile_hint=profile_hint)

    def reload_current(self):
        self.viewer.reload_current()

    def clear_view(self):
        self.current_url = ""
        self.viewer.show_message("zKill API viewer cleared.")

    def unload_browser(self):
        # Browser no longer exists. Keep this method so old calls do not crash.
        return
