"""Embedded zKill API viewer. No QtWebEngine/Chromium imports."""

from __future__ import annotations

import traceback

from cache import cache

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QLabel, QFrame, QGridLayout, QHBoxLayout, QTabWidget, QVBoxLayout, QWidget, QSizePolicy

from zkill_client import (
    get_danger_percent,
    get_gangRatio,
    get_recent_kills,
    get_recent_losses,
    get_soloRatio,
    get_zkill_stats,
)
from zkill_compact_table import KillsLossesTable
from zkill_fit_popup import FittingPanelPopup
from esi_client import TTL_CHARACTER_INFO, TTL_CORP_ALLIANCE_INFO

from zkill_table_model import (
    format_kills_losses_data,
    format_kills_losses_data_fast_local,
    get_character_avatar_bytes,
    get_character_name,
    get_character_profile,
)


class ZKillLoadThread(QThread):
    # Progressive signals: show something fast, then fill tables later.
    header_loaded = Signal(int, dict)
    overview_loaded = Signal(int, dict)
    details_loaded = Signal(int, dict)
    avatar_loaded = Signal(int, bytes)
    failed = Signal(int, str)

    def __init__(self, request_id: int, character_id: int, character_name: str, parent=None):
        super().__init__(parent)
        self.request_id = int(request_id)
        self.character_id = int(character_id)
        self.character_name = character_name or "Unknown"

    def _interrupted(self) -> bool:
        return bool(self.isInterruptionRequested())

    def run(self):
        try:
            character_name = self.character_name

            # Phase 1: DB-first. This must not wait for ESI/zKill profile, stats,
            # avatar, or name resolving. It gives the user visible rows almost
            # immediately when local_intel.sqlite has data.
            overview_kills = get_recent_kills(self.character_id, limit=10) or []
            overview_losses = get_recent_losses(self.character_id, limit=10) or []
            overview = format_kills_losses_data_fast_local(self.character_id, overview_kills, overview_losses)
            overview["character_id"] = self.character_id
            self.overview_loaded.emit(self.request_id, overview)

            if self._interrupted():
                return

            # Phase 2: header can use cache/network, but it no longer blocks the DB table.
            if character_name in ("", "Unknown", f"#{self.character_id}"):
                character_name = get_character_name(self.character_id)

            if self._interrupted():
                return

            profile = get_character_profile(self.character_id) or {}
            stats = get_zkill_stats(self.character_id) or {}
            header = {
                "character_id": self.character_id,
                "character_name": profile.get("name") or character_name,
                "profile": profile,
                "stats": stats,
                "danger": int(stats.get("dangerRatio", 0) or 0),
                "gang": int(stats.get("gangRatio", 0) or 0),
                "solo": int(stats.get("soloRatio", 0) or 0),
            }
            self.header_loaded.emit(self.request_id, header)

            if self._interrupted():
                return

            # Phase 3: avatar is nice, but it must not block first rows.
            avatar_bytes = get_character_avatar_bytes(self.character_id, 128)
            if avatar_bytes and not self._interrupted():
                self.avatar_loaded.emit(self.request_id, avatar_bytes)

            if self._interrupted():
                return

            # Phase 4: prettier/full data with name resolving. This can replace the
            # instant DB-first rows after cache/API work finishes.
            kills_list = get_recent_kills(self.character_id, limit=20) or []
            losses_list = get_recent_losses(self.character_id, limit=50) or []
            details = format_kills_losses_data(self.character_id, kills_list, losses_list)
            details["character_id"] = self.character_id
            details["recent_kills_raw_count"] = len(kills_list)
            details["recent_losses_raw_count"] = len(losses_list)
            self.details_loaded.emit(self.request_id, details)
        except Exception:
            if not self._interrupted():
                self.failed.emit(self.request_id, traceback.format_exc())


class ZKillViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.character_id: int | None = None
        self.character_name = "Unknown"
        self._avatar_source_pixmap = QPixmap()
        self._request_id = 0
        self._loader: ZKillLoadThread | None = None
        self._font_size = max(7, self.font().pointSize() or 10)
        self._text_color = "#D6D8DC"
        self._frame_color = "#3D424A"
        self._fit_popup = FittingPanelPopup(self)
        self._fit_hover_timer = QTimer(self)
        self._fit_hover_timer.setSingleShot(True)
        self._fit_hover_timer.timeout.connect(self._show_pending_fit_popup)
        self._pending_fit_row = None

        root = QVBoxLayout(self)
        # Bottom padding should visually match the left/right breathing room of the app.
        root.setContentsMargins(4, 3, 4, 4)
        root.setSpacing(1)

        header_frame = QFrame()
        header_frame.setObjectName("ZkillHeader")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.avatar_label = QLabel("👤")
        self.avatar_label.setFixedSize(64, 64)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.avatar_label.setStyleSheet("""
            QLabel {
                color: #9FB7D7;
                background-color: transparent;
                border: 0px;
            }
        """)

        info_layout = QGridLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setHorizontalSpacing(5)
        info_layout.setVerticalSpacing(0)

        self.info_key_labels = []
        self.info_value_labels = []

        self.name_value = QLabel("No character loaded")
        name_font = QFont(self.font())
        name_font.setBold(True)
        self.name_value.setFont(name_font)

        self.corp_value = QLabel("-")
        self.alliance_value = QLabel("-")
        self.sec_birthday_value = QLabel("-")

        def add_row(row: int, label: str, widget: QLabel, muted: bool = False):
            key = QLabel(label)
            key.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            key.setMinimumWidth(64)
            key.setContentsMargins(0, 0, 0, 0)
            widget.setContentsMargins(0, 0, 0, 0)
            widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            key.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            widget.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            key.setProperty("zkill_label_role", "key")
            widget.setProperty("zkill_label_role", "muted" if muted else "value")
            self.info_key_labels.append(key)
            self.info_value_labels.append(widget)
            info_layout.addWidget(key, row, 0)
            info_layout.addWidget(widget, row, 1)

        add_row(0, "Character:", self.name_value)
        add_row(1, "Corporation:", self.corp_value)
        add_row(2, "Alliance:", self.alliance_value)
        add_row(3, "Sec / Birthday:", self.sec_birthday_value, muted=True)

        header_layout.addWidget(self.avatar_label, 0, Qt.AlignLeft | Qt.AlignTop)
        header_layout.addLayout(info_layout, 0)
        header_layout.addStretch(1)
        root.addWidget(header_frame, 0, Qt.AlignLeft)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setDocumentMode(True)
        self._apply_tabs_style()

        self.overview_table = KillsLossesTable(show_kind=False)
        self.kills_table = KillsLossesTable(show_kind=False, default_kind="kill")
        self.losses_table = KillsLossesTable(show_kind=False, default_kind="loss")

        for table in (self.overview_table, self.kills_table, self.losses_table):
            table.killmailActivated.connect(self.show_killmail_id)
            table.columnWidthsChanged.connect(self._sync_zkill_column_widths)
            # Popup opens only by click, not hover.
            table.shipClicked.connect(self._on_ship_clicked)

        self.tabs.addTab(self.overview_table, "All")
        self.tabs.addTab(self.kills_table, "Kill")
        self.tabs.addTab(self.losses_table, "Loss")
        self.tabs.tabBar().hide()
        root.addWidget(self.tabs, 1)

        self.setStyleSheet("""
            QFrame#ZkillHeader {
                background-color: transparent;
                border: 0px;
            }
        """)
        self.apply_ui_settings(self._font_size, self._text_color)

    def set_mode(self, mode: str):
        """Switch the external zKill mode buttons: All / Kill / Loss."""
        mode = str(mode or "All").strip().lower()
        index = {"all": 0, "kill": 1, "kills": 1, "loss": 2, "losses": 2}.get(mode, 0)
        self.tabs.setCurrentIndex(index)


    def close_fit_popup(self):
        if hasattr(self, "_fit_hover_timer"):
            self._fit_hover_timer.stop()
        self._pending_fit_row = None
        if hasattr(self, "_fit_popup"):
            self._fit_popup.hide_panel(force=True)


    def _on_ship_hovered(self, row_data: dict):
        """Deprecated: popup no longer opens on hover."""
        return

    def _on_ship_clicked(self, row_data: dict):
        """Open and pin fitting popup by clicking a ship cell."""
        row_data = dict(row_data or {})
        if not row_data.get("killmail_id"):
            return
        self._fit_hover_timer.stop()
        self._pending_fit_row = row_data
        self._fit_popup.show_for_row(row_data, self, pinned=True)

    def _on_ship_hover_left(self):
        """Deprecated: leaving the table should not close the popup."""
        self._fit_hover_timer.stop()
        self._pending_fit_row = None

    def _show_pending_fit_popup(self):
        """Deprecated: hover timer no longer opens the popup."""
        return

    def _sync_zkill_column_widths(self, widths: dict):
        sender = self.sender()
        for table in (self.overview_table, self.kills_table, self.losses_table):
            if table is not sender:
                table.apply_external_column_widths(widths)

    def _apply_header_label_styles(self):
        size = int(self._font_size)
        key_style = (
            f"color: #BEC5CE; font-weight: bold; background: transparent; "
            f"font-size: {size}pt;"
        )
        value_style = (
            f"color: #A9F5E0; background: transparent; "
            f"font-size: {size}pt;"
        )
        muted_style = (
            f"color: #BFC5CC; background: transparent; "
            f"font-size: {size}pt;"
        )

        for label in getattr(self, "info_key_labels", []):
            label.setStyleSheet(key_style)

        for label in getattr(self, "info_value_labels", []):
            role = label.property("zkill_label_role")
            label.setStyleSheet(muted_style if role == "muted" else value_style)


    def _update_header_metrics(self):
        """Keep zKill header compact and scale avatar with the global font size."""
        fm = self.fontMetrics()
        line_h = max(12, fm.height())
        row_h = line_h + 1

        for label in getattr(self, "info_key_labels", []) + getattr(self, "info_value_labels", []):
            label.setFixedHeight(row_h)
            label.setMinimumHeight(row_h)
            label.setMaximumHeight(row_h)

        # Avatar follows the 4-line header block instead of staying hard-coded.
        avatar_size = max(48, min(92, row_h * 4))
        if self.avatar_label.width() != avatar_size or self.avatar_label.height() != avatar_size:
            self.avatar_label.setFixedSize(avatar_size, avatar_size)
        self._refresh_avatar_pixmap()

    def _refresh_avatar_pixmap(self):
        """Re-scale cached avatar whenever Options font size changes."""
        if getattr(self, "_avatar_source_pixmap", QPixmap()).isNull():
            return
        size = max(24, min(self.avatar_label.width(), self.avatar_label.height()))
        pixmap = self._avatar_source_pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.avatar_label.setText("")
        self.avatar_label.setPixmap(pixmap)

    def _apply_tabs_style(self):
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 0px;
                background-color: transparent;
            }}
            QTabBar::tab {{
                background-color: rgba(14, 16, 20, 120);
                color: #AEB4BC;
                padding: 3px 9px;
                margin: 0px;
                border: 1px solid transparent;
                border-bottom: 1px solid rgba(55, 67, 80, 120);
                font-size: {self._font_size}pt;
            }}
            QTabBar::tab:selected {{
                background-color: rgba(18, 24, 26, 210);
                color: #A9F5E0;
                border-bottom: 1px solid #39C7B5;
            }}
            QTabBar::tab:hover {{
                background-color: rgba(40, 45, 52, 180);
                color: #FFFFFF;
            }}
        """)

    def apply_ui_settings(self, font_size: int | None = None, text_color: str | None = None, frame_color: str | None = None):
        """Apply global Options font size/color/frame color to the zKill tab."""
        if font_size is not None:
            try:
                self._font_size = max(7, min(18, int(font_size)))
            except Exception:
                self._font_size = max(7, self._font_size)
        if text_color:
            self._text_color = str(text_color)
        if frame_color:
            self._frame_color = str(frame_color)

        font = self.font()
        font.setPointSize(int(self._font_size))
        self.setFont(font)

        for label in self.findChildren(QLabel):
            label_font = label.font()
            label_font.setPointSize(int(self._font_size))
            label.setFont(label_font)

        name_font = self.name_value.font()
        name_font.setPointSize(int(self._font_size))
        name_font.setBold(True)
        self.name_value.setFont(name_font)

        self._apply_header_label_styles()
        self._update_header_metrics()

        tab_font = self.tabs.font()
        tab_font.setPointSize(int(self._font_size))
        self.tabs.setFont(tab_font)
        self.tabs.tabBar().setFont(tab_font)
        self._apply_tabs_style()

        for table in (self.overview_table, self.kills_table, self.losses_table):
            table.apply_ui_settings(font_size=self._font_size, text_color=self._text_color, frame_color=self._frame_color)

    def _profile_from_general_or_cache(self, character_id: int, character_name: str = "Unknown", profile_hint: dict | None = None) -> dict:
        """Build instant header data from already-loaded General/cache data.

        This avoids the visual reload where zKill shows Loading... even though
        General already resolved the pilot/profile moments earlier.
        """
        hint = profile_hint if isinstance(profile_hint, dict) else {}
        character_id = int(character_id or 0)

        name = str(hint.get("character_name") or character_name or "Unknown").strip() or "Unknown"
        corp = str(hint.get("corporation") or "").strip()
        alliance = str(hint.get("alliance") or "").strip()
        corp_ally = str(hint.get("corp_ally") or "").strip()
        security_status = str(hint.get("security_status") or "").strip()
        birthday = str(hint.get("birthday") or "").strip()

        # General worker uses esi_client cache keys. Reading cache directly keeps
        # this method non-blocking: no network request is made here.
        character = cache.get(f"esi:character_info:{character_id}", ttl_seconds=TTL_CHARACTER_INFO)
        if isinstance(character, dict):
            if not security_status:
                try:
                    security_status = f"{float(character.get('security_status')):.2f}"
                except Exception:
                    security_status = "?"
            if not birthday:
                birthday = self._short_date(str(character.get("birthday") or "?"))

            corp_id = int(character.get("corporation_id") or 0)
            alliance_id = int(character.get("alliance_id") or 0)

            if corp_id and not corp:
                corp_info = cache.get(f"esi:corp_info:{corp_id}", ttl_seconds=TTL_CORP_ALLIANCE_INFO)
                if isinstance(corp_info, dict):
                    corp = str(corp_info.get("name") or "").strip()

            if alliance_id and not alliance:
                alliance_info = cache.get(f"esi:alliance_info:{alliance_id}", ttl_seconds=TTL_CORP_ALLIANCE_INFO)
                if isinstance(alliance_info, dict):
                    alliance = str(alliance_info.get("name") or "").strip()

        # zKill viewer may have its own profile cache from previous opens.
        profile_cache = cache.get(f"esi:character-profile:{character_id}", ttl_seconds=TTL_CHARACTER_INFO)
        if isinstance(profile_cache, dict):
            if not security_status:
                try:
                    security_status = f"{float(profile_cache.get('security_status')):.2f}"
                except Exception:
                    security_status = "?"
            if not birthday:
                birthday = self._short_date(str(profile_cache.get("birthday") or "?"))

        # If General only had Corp/Ally text, use it as a non-loading fallback.
        if corp_ally and not alliance and not corp:
            alliance = corp_ally

        return {
            "character_name": name if name != "Unknown" else f"Character #{character_id}",
            "corporation": corp or "-",
            "alliance": alliance or "- none -",
            "security_status": security_status or "-",
            "birthday": birthday or "-",
        }

    def open_character(self, character_id: int, character_name: str = "Unknown", profile_hint: dict | None = None):
        character_id = int(character_id or 0)
        if not character_id:
            self.show_message("Invalid character id.")
            return

        self.character_id = character_id
        self.character_name = character_name or "Unknown"
        self._request_id += 1
        request_id = self._request_id

        self._set_avatar_placeholder()

        instant_profile = self._profile_from_general_or_cache(character_id, self.character_name, profile_hint)
        self.name_value.setText(instant_profile.get("character_name") or f"Character #{character_id}")
        self.corp_value.setText(instant_profile.get("corporation") or "-")
        self.alliance_value.setText(instant_profile.get("alliance") or "- none -")
        sec = instant_profile.get("security_status") or "-"
        birthday = instant_profile.get("birthday") or "-"
        self.sec_birthday_value.setText(f"{sec}  ·  {birthday}")

        self.overview_table.clear_data()
        self.kills_table.clear_data()
        self.losses_table.clear_data()

        if self._loader and self._loader.isRunning():
            self._loader.requestInterruption()

        self._loader = ZKillLoadThread(request_id, character_id, self.character_name, self)
        self._loader.header_loaded.connect(self._on_header_loaded)
        self._loader.overview_loaded.connect(self._on_overview_loaded)
        self._loader.details_loaded.connect(self._on_details_loaded)
        self._loader.avatar_loaded.connect(self._on_avatar_loaded)
        self._loader.failed.connect(self._on_failed)
        self._loader.finished.connect(self._cleanup_loader)
        self._loader.start()

    def reload_current(self):
        if self.character_id:
            self.open_character(self.character_id, self.character_name)

    def show_message(self, text: str):
        self._set_avatar_placeholder()
        self.name_value.setText("zKill API Viewer")
        self.corp_value.setText(text)
        self.alliance_value.setText("")
        self.sec_birthday_value.setText("")
        self.overview_table.clear_data()
        self.kills_table.clear_data()
        self.losses_table.clear_data()

    def show_killmail_id(self, killmail_id: int):
        # Double click browser opening disabled by user request.
        return

    def _cleanup_loader(self):
        loader = self.sender()
        if loader:
            loader.deleteLater()
        if loader is self._loader:
            self._loader = None

    def _on_failed(self, request_id: int, error: str):
        if request_id != self._request_id:
            return
        self.corp_value.setText("Load failed")
        self.alliance_value.setText("")
        self.sec_birthday_value.setText("")
        self.overview_table.clear_data()
        self.kills_table.clear_data()
        self.losses_table.clear_data()
        print("[ZKILL VIEWER] failed:\n" + str(error))

    def _on_header_loaded(self, request_id: int, data: dict):
        if request_id != self._request_id:
            return

        character_id = int(data.get("character_id") or self.character_id or 0)
        character_name = data.get("character_name") or self.character_name or f"#{character_id}"
        profile = data.get("profile") or {}
        self.character_id = character_id
        self.character_name = character_name

        self.name_value.setText(character_name)
        self.corp_value.setText(profile.get("corporation") or "Unknown")
        self.alliance_value.setText(profile.get("alliance") or "- none -")
        sec_status = str(profile.get("security_status") or "?")
        birthday = self._short_date(profile.get("birthday") or "?")
        self.sec_birthday_value.setText(f"{sec_status}  ·  {birthday}")

    def _on_overview_loaded(self, request_id: int, data: dict):
        if request_id != self._request_id:
            return

        kills = data.get("kills") or []
        losses = data.get("losses") or []
        combined = data.get("combined") or (list(kills) + list(losses))
        combined.sort(key=lambda r: r.get("raw_time") or r.get("date") or "", reverse=True)

        self.overview_table.load_data(combined)
        # Give Kills/Losses tabs quick preview too; full data arrives after this.
        self.kills_table.load_data(kills)
        self.losses_table.load_data(losses)

    def _on_details_loaded(self, request_id: int, data: dict):
        if request_id != self._request_id:
            return

        kills = data.get("kills") or []
        losses = data.get("losses") or []
        combined = data.get("combined") or (list(kills) + list(losses))
        combined.sort(key=lambda r: r.get("raw_time") or r.get("date") or "", reverse=True)

        self.overview_table.load_data(combined)
        self.kills_table.load_data(kills)
        self.losses_table.load_data(losses)

    def _on_avatar_loaded(self, request_id: int, avatar_bytes: bytes):
        if request_id != self._request_id:
            return
        self._set_avatar_from_bytes(avatar_bytes or b"")

    def _short_date(self, value: str) -> str:
        value = str(value or "").strip()
        if not value or value == "?":
            return "?"
        # ESI birthday is usually YYYY-MM-DD. UI wants compact YY-MM-DD.
        if len(value) >= 10 and value[4] == "-" and value[7] == "-":
            return value[2:10]
        return value

    def _set_avatar_placeholder(self):
        self._avatar_source_pixmap = QPixmap()
        self.avatar_label.setPixmap(QPixmap())
        self.avatar_label.setText("👤")
        self._update_header_metrics()

    def _set_avatar_from_bytes(self, avatar_bytes: bytes):
        if not avatar_bytes:
            self._set_avatar_placeholder()
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(avatar_bytes):
            self._set_avatar_placeholder()
            return

        self._avatar_source_pixmap = pixmap
        self._update_header_metrics()
