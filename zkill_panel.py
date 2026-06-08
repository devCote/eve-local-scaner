import re
from datetime import datetime

import requests
from PySide6.QtCore import QUrl, Qt, QObject, Signal, QRunnable, QThreadPool
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
    QStackedWidget,
    QFrame,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from esi_client import get_character_info, get_corporation_info, get_alliance_info
from zkill_client import get_recent_kills, get_full_killmail
from ship_names import get_ship_name

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import (
        QWebEngineUrlRequestInterceptor,
        QWebEngineProfile,
        QWebEnginePage,
    )

    WEBENGINE_AVAILABLE = True

except Exception:
    QWebEngineView = None
    QWebEngineUrlRequestInterceptor = None
    QWebEngineProfile = None
    QWebEnginePage = None
    WEBENGINE_AVAILABLE = False


ZKILL_CHARACTER_RE = re.compile(r"zkillboard\.com/character/(\d+)")
ESI_URL = "https://esi.evetech.net/latest"
USER_AGENT = "EVE-Local-Scanner"


class AdBlocker(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.blocked_hosts = [
            "googlesyndication.com",
            "googleadservices.com",
            "doubleclick.net",
            "adservice.google.com",
            "pagead2.googlesyndication.com",
            "securepubads.g.doubleclick.net",
            "googletagservices.com",
            "googletagmanager.com",
            "google-analytics.com",
            "analytics.google.com",
            "facebook.net",
            "ads-twitter.com",
            "amazon-adsystem.com",
            "static.cloudflareinsights.com",
        ]

        self.blocked_url_parts = [
            "/ads?",
            "/ads/",
            "googleads",
            "googletag",
            "doubleclick",
            "pubads",
            "pagead",
            "adservice",
            "analytics",
            "beacon.min.js",
            "cloudflareinsights",
            "markeedragon",
            "patreon",
        ]

    def interceptRequest(self, info):
        url = info.requestUrl().toString().lower()
        host = info.requestUrl().host().lower()

        for blocked_host in self.blocked_hosts:
            if blocked_host in host:
                info.block(True)
                return

        for blocked_part in self.blocked_url_parts:
            if blocked_part in url:
                info.block(True)
                return


class QuietWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        return


class ZkillNativeSignals(QObject):
    finished = Signal(dict)


class ZkillNativeWorker(QRunnable):
    def __init__(self, character_id: int):
        super().__init__()
        self.character_id = character_id
        self.signals = ZkillNativeSignals()

    def run(self):
        result = {
            "character_id": self.character_id,
            "character_name": f"Character {self.character_id}",
            "corporation": "?",
            "alliance": "",
            "sec_status": "?",
            "birthday": "?",
            "portrait_bytes": None,
            "kills": [],
            "error": None,
        }

        try:
            char = get_character_info(self.character_id) or {}

            result["character_name"] = char.get("name", result["character_name"])
            result["sec_status"] = self.format_sec_status(char.get("security_status"))
            result["birthday"] = self.format_birthday(char.get("birthday"))

            corp_id = char.get("corporation_id")
            alliance_id = char.get("alliance_id")

            if corp_id:
                corp = get_corporation_info(corp_id) or {}
                corp_name = corp.get("name", "?")
                corp_ticker = corp.get("ticker")
                result["corporation"] = (
                    f"{corp_name} [{corp_ticker}]" if corp_ticker else corp_name
                )

            if alliance_id:
                alliance = get_alliance_info(alliance_id) or {}
                alliance_name = alliance.get("name", "")
                alliance_ticker = alliance.get("ticker")
                result["alliance"] = (
                    f"{alliance_name} <{alliance_ticker}>" if alliance_ticker else alliance_name
                )

            result["portrait_bytes"] = self.fetch_portrait(self.character_id)
            result["kills"] = self.fetch_kills(self.character_id)

        except Exception as e:
            result["error"] = str(e)

        self.signals.finished.emit(result)

    def fetch_portrait(self, character_id: int):
        try:
            url = f"https://images.evetech.net/characters/{character_id}/portrait?size=128"
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
            if response.status_code == 200:
                return response.content
        except Exception:
            pass
        return None

    def fetch_kills(self, character_id: int, limit: int = 25):
        zkill_rows = get_recent_kills(character_id, limit=limit)
        killmails = []
        ids_to_resolve = set()

        for zrow in zkill_rows:
            killmail_id = zrow.get("killmail_id")
            killmail_hash = zrow.get("zkb", {}).get("hash")

            if not killmail_id or not killmail_hash:
                continue

            km = get_full_killmail(killmail_id, killmail_hash)
            if not km:
                continue

            killmails.append((zrow, km))

            victim = km.get("victim", {})
            for key in ["character_id", "corporation_id", "alliance_id", "ship_type_id"]:
                value = victim.get(key)
                if value:
                    ids_to_resolve.add(int(value))

            system_id = km.get("solar_system_id")
            if system_id:
                ids_to_resolve.add(int(system_id))

            for attacker in km.get("attackers", []):
                for key in ["character_id", "corporation_id", "alliance_id", "ship_type_id"]:
                    value = attacker.get(key)
                    if value:
                        ids_to_resolve.add(int(value))

        names = self.resolve_names(list(ids_to_resolve))
        rows = []

        for zrow, km in killmails:
            victim = km.get("victim", {})
            attackers = km.get("attackers", [])
            final_blow = next((a for a in attackers if a.get("final_blow")), None)

            if not final_blow and attackers:
                final_blow = attackers[0]

            victim_character_id = victim.get("character_id")
            victim_corp_id = victim.get("corporation_id")
            victim_ship_id = victim.get("ship_type_id")
            system_id = km.get("solar_system_id")

            victim_name = names.get(victim_character_id) or names.get(victim_corp_id) or "Unknown"
            victim_ship = get_ship_name(victim_ship_id) if victim_ship_id else "?"
            system_name = names.get(system_id, "?")

            final_text = "?"
            if final_blow:
                fb_char_id = final_blow.get("character_id")
                fb_corp_id = final_blow.get("corporation_id")
                fb_ship_id = final_blow.get("ship_type_id")

                fb_name = names.get(fb_char_id) or names.get(fb_corp_id) or "Unknown"
                fb_ship = get_ship_name(fb_ship_id) if fb_ship_id else "?"
                final_text = f"{fb_name}\n{fb_ship}"

            rows.append(
                {
                    "time": self.format_time(km.get("killmail_time")),
                    "ship": victim_ship,
                    "location": system_name,
                    "victim": f"{victim_name}\n{victim_ship}",
                    "final_blow": final_text,
                }
            )

        return rows

    def resolve_names(self, ids):
        ids = [int(x) for x in ids if x]
        if not ids:
            return {}

        result = {}

        for start in range(0, len(ids), 1000):
            chunk = ids[start : start + 1000]
            try:
                response = requests.post(
                    f"{ESI_URL}/universe/names/",
                    json=chunk,
                    headers={"User-Agent": USER_AGENT},
                    timeout=10,
                )
                if response.status_code != 200:
                    continue

                for item in response.json():
                    result[int(item.get("id"))] = item.get("name", str(item.get("id")))

            except Exception:
                continue

        return result

    def format_time(self, value):
        if not value:
            return ""

        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%m-%d %H:%M")
        except Exception:
            return str(value)[:16]

    def format_birthday(self, value):
        if not value:
            return "?"
        return str(value)[:10]

    def format_sec_status(self, value):
        try:
            return f"{float(value):.1f}"
        except Exception:
            return "?"


class ZkillPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.home_url = "https://zkillboard.com/"
        self.browser = None
        self.profile = None
        self.page = None
        self.adblocker = None
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(2)
        self.active_worker = None
        self.current_character_id = None

        self.ui_alpha = 204
        self.ui_font_size = 8
        self.ui_frame_color = "#444A52"
        self.ui_text_color = "#C7C9CC"
        self.ui_bg_color = "#07080A"

        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(2)

        self.back_button = QPushButton("<")
        self.forward_button = QPushButton(">")
        self.reload_button = QPushButton("R")
        self.home_button = QPushButton("Home")

        for button in [
            self.back_button,
            self.forward_button,
            self.reload_button,
            self.home_button,
        ]:
            button.setFixedHeight(20)

        self.url_input = QLineEdit()
        self.url_input.setFixedHeight(20)
        self.url_input.returnPressed.connect(self.load_from_input)

        top_bar.addWidget(self.back_button)
        top_bar.addWidget(self.forward_button)
        top_bar.addWidget(self.reload_button)
        top_bar.addWidget(self.home_button)
        top_bar.addWidget(self.url_input, 1)

        layout.addLayout(top_bar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.stack, 1)

        self.native_page = self.build_native_page()
        self.stack.addWidget(self.native_page)

        if WEBENGINE_AVAILABLE:
            self.browser = QWebEngineView()
            self.browser.setAttribute(Qt.WA_TranslucentBackground, True)
            self.browser.setStyleSheet("background: transparent; border: none;")

            self.profile = QWebEngineProfile.defaultProfile()
            self.adblocker = AdBlocker(self)
            self.profile.setUrlRequestInterceptor(self.adblocker)

            self.page = QuietWebPage(self.profile, self.browser)
            self.browser.setPage(self.page)
            self.page.setBackgroundColor(QColor(0, 0, 0, 0))

            self.browser.urlChanged.connect(self.on_url_changed)

            self.stack.addWidget(self.browser)
        else:
            self.browser_warning = QLabel(
                "QtWebEngine не найден.\n\nДля обычных страниц поставь:\npip install PySide6 PySide6-Addons"
            )
            self.browser_warning.setAlignment(Qt.AlignCenter)
            self.browser_warning.setStyleSheet(
                "color: #C7C9CC; background-color: rgba(8,9,11,90); padding: 12px;"
            )
            self.stack.addWidget(self.browser_warning)

        self.back_button.clicked.connect(self.go_back)
        self.forward_button.clicked.connect(self.go_forward)
        self.reload_button.clicked.connect(self.reload_current)
        self.home_button.clicked.connect(lambda: self.load_url(self.home_url))

        self.apply_style()
        self.load_url(self.home_url)

    def build_native_page(self):
        page = QWidget()
        page.setObjectName("NativeZkillPage")
        page.setAttribute(Qt.WA_TranslucentBackground, True)

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.profile_frame = QFrame()
        self.profile_frame.setObjectName("ZkillProfileFrame")
        profile_layout = QHBoxLayout(self.profile_frame)
        profile_layout.setContentsMargins(5, 5, 5, 5)
        profile_layout.setSpacing(10)

        portrait_box = QVBoxLayout()
        portrait_box.setContentsMargins(0, 0, 0, 0)
        portrait_box.setSpacing(2)

        self.portrait_label = QLabel()
        self.portrait_label.setFixedSize(128, 128)
        self.portrait_label.setAlignment(Qt.AlignCenter)
        self.portrait_label.setStyleSheet("background: rgba(0,0,0,80); border: none;")

        self.enlarge_label = QLabel("Enlarge")
        self.enlarge_label.setAlignment(Qt.AlignCenter)
        self.enlarge_label.setStyleSheet("color: #42bfff; font-size: 10px; font-style: italic;")

        portrait_box.addWidget(self.portrait_label)
        portrait_box.addWidget(self.enlarge_label)
        profile_layout.addLayout(portrait_box)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(3)

        self.character_label = self.make_info_label("Character:", "loading...")
        self.corp_label = self.make_info_label("Corporation:", "")
        self.alliance_label = self.make_info_label("Alliance:", "")
        self.sec_label = self.make_info_label("Sec. Status:", "")
        self.birthday_label = self.make_info_label("Birthday:", "")

        info_layout.addWidget(self.character_label)
        info_layout.addWidget(self.corp_label)
        info_layout.addWidget(self.alliance_label)
        info_layout.addWidget(self.sec_label)
        info_layout.addWidget(self.birthday_label)
        info_layout.addStretch()

        profile_layout.addLayout(info_layout, 1)
        layout.addWidget(self.profile_frame)

        self.kills_title = QLabel("Kills")
        self.kills_title.setStyleSheet("color: #d7dbe0; font-weight: bold; font-size: 14px;")
        layout.addWidget(self.kills_title)

        self.kills_table = QTableWidget()
        self.kills_table.setColumnCount(5)
        self.kills_table.setHorizontalHeaderLabels(
            ["Time", "Ship", "Location", "Victim", "Final Blow"]
        )
        self.kills_table.verticalHeader().setVisible(False)
        self.kills_table.horizontalHeader().setHighlightSections(False)
        self.kills_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.kills_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.kills_table.setFocusPolicy(Qt.NoFocus)
        self.kills_table.setShowGrid(True)
        self.kills_table.verticalHeader().setDefaultSectionSize(38)

        self.kills_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.kills_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.kills_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.kills_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.kills_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

        self.kills_table.setColumnWidth(0, 75)
        self.kills_table.setColumnWidth(1, 110)
        self.kills_table.setColumnWidth(2, 120)

        layout.addWidget(self.kills_table, 1)

        return page

    def make_info_label(self, title, value):
        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setStyleSheet("background: transparent;")
        self.set_info_label(label, title, value)
        return label

    def set_info_label(self, label, title, value, blue=True):
        label_color = self.ui_text_color
        value_color = "#28a8ff" if blue else self.ui_text_color
        font_size = self.ui_font_size
        label.setText(
            f"<span style='color:{label_color};font-weight:700;font-size:{font_size}pt'>{title}</span> "
            f"<span style='color:{value_color};font-size:{font_size}pt'>{self.escape_html(str(value))}</span>"
        )

    def apply_ui_settings(self, alpha, font_size, frame_color, text_color, bg_color):
        self.ui_alpha = int(alpha)
        self.ui_font_size = int(font_size)
        self.ui_frame_color = frame_color
        self.ui_text_color = text_color
        self.ui_bg_color = bg_color
        self.apply_style()

    def apply_style(self):
        bg = QColor(self.ui_bg_color)
        alpha = max(0, min(255, int(self.ui_alpha)))
        font_size = int(self.ui_font_size)
        frame_color = self.ui_frame_color
        text_color = self.ui_text_color

        panel_alpha = max(0, min(255, alpha - 65))
        item_alpha = max(0, min(255, alpha - 80))
        header_alpha = max(0, min(255, alpha - 35))
        button_alpha = max(0, min(255, alpha - 55))

        self.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                color: {text_color};
                font-size: {font_size}pt;
            }}

            QLineEdit {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {button_alpha});
                color: {text_color};
                border: 1px solid {frame_color};
                padding-left: 6px;
                font-size: {font_size}pt;
            }}

            QPushButton {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {button_alpha});
                color: {text_color};
                border: 1px solid {frame_color};
                padding: 0px 6px;
                font-size: {font_size}pt;
            }}

            QPushButton:hover {{
                background-color: rgba(42, 46, 54, {min(255, button_alpha + 45)});
                color: #FFFFFF;
                border: 1px solid #69707A;
            }}

            QFrame#ZkillProfileFrame {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {panel_alpha});
                border: 1px solid {frame_color};
            }}

            QLabel {{
                background: transparent;
                color: {text_color};
                font-size: {font_size}pt;
            }}

            QTableWidget {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {panel_alpha});
                color: {text_color};
                border: 1px solid {frame_color};
                gridline-color: rgba(70, 76, 86, 90);
                font-size: {font_size}pt;
                selection-background-color: transparent;
                outline: none;
            }}

            QTableWidget::item {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {item_alpha});
                color: {text_color};
                padding: 2px 5px;
                font-size: {font_size}pt;
            }}

            QTableWidget::item:hover {{
                background-color: rgba(35, 70, 95, 150);
            }}

            QHeaderView::section {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {header_alpha});
                color: {text_color};
                border: 1px solid {frame_color};
                padding: 3px 5px;
                font-weight: normal;
                font-size: {font_size}pt;
            }}
        """)

        self.kills_title.setStyleSheet(
            f"color: {text_color}; font-weight: bold; font-size: {font_size + 2}pt; background: transparent;"
        )
        self.enlarge_label.setStyleSheet(
            f"color: #42bfff; font-size: {max(7, font_size - 1)}pt; font-style: italic; background: transparent;"
        )
        self.portrait_label.setStyleSheet(
            f"background: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {max(0, alpha - 120)}); border: none;"
        )

    def load_from_input(self):
        self.load_url(self.url_input.text().strip())

    def load_url(self, url):
        if not url:
            return

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        self.url_input.setText(url)

        character_id = self.extract_character_id(url)

        if character_id:
            self.load_character_native(character_id)
            return

        if self.browser:
            self.stack.setCurrentWidget(self.browser)
            self.browser.setUrl(QUrl(url))
        else:
            self.stack.setCurrentWidget(self.browser_warning)

    def extract_character_id(self, url):
        match = ZKILL_CHARACTER_RE.search(url)
        if not match:
            return None

        try:
            return int(match.group(1))
        except Exception:
            return None

    def load_character_native(self, character_id):
        self.current_character_id = character_id
        self.stack.setCurrentWidget(self.native_page)
        self.url_input.setText(f"https://zkillboard.com/character/{character_id}/")

        self.portrait_label.clear()
        self.portrait_label.setText("loading")
        self.set_info_label(self.character_label, "Character:", "loading...")
        self.set_info_label(self.corp_label, "Corporation:", "")
        self.set_info_label(self.alliance_label, "Alliance:", "")
        self.set_info_label(self.sec_label, "Sec. Status:", "")
        self.set_info_label(self.birthday_label, "Birthday:", "", blue=False)

        self.kills_table.setRowCount(1)
        self.kills_table.setItem(0, 0, QTableWidgetItem("loading..."))
        self.kills_table.setSpan(0, 0, 1, 5)

        worker = ZkillNativeWorker(character_id)
        worker.signals.finished.connect(self.on_native_loaded)
        self.active_worker = worker
        self.pool.start(worker)

    def on_native_loaded(self, data):
        if data.get("character_id") != self.current_character_id:
            return

        self.set_info_label(self.character_label, "Character:", f"{data.get('character_name', '?')} +")
        self.set_info_label(self.corp_label, "Corporation:", data.get("corporation", ""))
        self.set_info_label(self.alliance_label, "Alliance:", data.get("alliance", ""))
        self.set_info_label(self.sec_label, "Sec. Status:", data.get("sec_status", ""))
        self.set_info_label(self.birthday_label, "Birthday:", data.get("birthday", ""), blue=False)

        portrait_bytes = data.get("portrait_bytes")
        if portrait_bytes:
            pixmap = QPixmap()
            pixmap.loadFromData(portrait_bytes)
            if not pixmap.isNull():
                self.portrait_label.setPixmap(
                    pixmap.scaled(128, 128, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                )
            else:
                self.portrait_label.setText("no image")
        else:
            self.portrait_label.setText("no image")

        self.fill_kills_table(data.get("kills", []))

    def fill_kills_table(self, kills):
        self.kills_table.clearSpans()

        if not kills:
            self.kills_table.setRowCount(1)
            self.kills_table.setItem(0, 0, QTableWidgetItem("No kills loaded"))
            self.kills_table.setSpan(0, 0, 1, 5)
            return

        self.kills_table.setRowCount(len(kills))

        for row, kill in enumerate(kills):
            values = [
                kill.get("time", ""),
                kill.get("ship", ""),
                kill.get("location", ""),
                kill.get("victim", ""),
                kill.get("final_blow", ""),
            ]

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setForeground(QColor("#cfd5dc"))

                if col in (0, 1, 2):
                    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

                self.kills_table.setItem(row, col, item)

    def go_back(self):
        if self.stack.currentWidget() == self.browser and self.browser:
            self.browser.back()

    def go_forward(self):
        if self.stack.currentWidget() == self.browser and self.browser:
            self.browser.forward()

    def reload_current(self):
        if self.stack.currentWidget() == self.native_page and self.current_character_id:
            self.load_character_native(self.current_character_id)
            return

        if self.browser:
            self.browser.reload()

    def on_url_changed(self, url):
        self.url_input.setText(url.toString())

    def escape_html(self, text):
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#039;")
        )
