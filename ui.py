import sys
import pyperclip

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QCursor, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QSizeGrip,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QHeaderView,
    QAbstractItemView,
    QFrame,
    QStackedWidget,
)

from parser import parse_pilots
from worker import PilotWorker
from spinner import SpinnerManager
from relations import RelationWorker
from title_bar import TitleBar
from intel_table import IntelTable
from eve_tabs import EveTabs
from zkill_panel import ZkillPanel
from options_panel import OptionsPanel
from user_settings import load_ui_settings, save_ui_settings
from windows_blur import enable_eve_blur

from row_renderer import (
    set_loading_row as render_loading_row,
    render_pilot_row,
    render_cyno_cell,
)

from window_resize import handle_resize_event


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Scanner")
        self.setObjectName("RootWindow")
        self.resize(760, 440)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(560, 280)

        self.resize_margin = 8

        self.user_settings = load_ui_settings()
        self.ui_transparency = int(self.user_settings["transparency"])
        self.ui_alpha = self.transparency_to_alpha(self.ui_transparency)
        self.ui_blur = int(self.user_settings["blur"])
        self.ui_font_size = int(self.user_settings["font_size"])
        self.ui_frame_color = self.user_settings["frame_color"]
        self.ui_text_color = self.user_settings["text_color"]
        self.ui_bg_color = self.user_settings["bg_color"]


        self.last_clipboard_text = ""
        self.last_pilots = []

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(12)

        self.cyno_pool = QThreadPool()
        self.cyno_pool.setMaxThreadCount(3)

        self.relations_pool = QThreadPool()
        self.relations_pool.setMaxThreadCount(1)

        self.spinner = SpinnerManager(self)

        self.relations = {}
        self.row_character_ids = {}
        self.row_base_colors = {}
        self.pending_pilots = 0

        self.relations_running = False
        self.last_relations_key = None
        self.active_relation_workers = []

        self.last_hover_row = None

        self.build_ui()

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        self.start_clipboard_timer()

    def transparency_to_alpha(self, transparency):
        transparency = max(0, min(100, int(transparency)))
        return int(round(255 * (100 - transparency) / 100))

    def build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.main_panel = QFrame()
        self.main_panel.setObjectName("MainPanel")
        self.main_panel.setAttribute(Qt.WA_StyledBackground, True)

        outer_layout.addWidget(self.main_panel)

        layout = QVBoxLayout(self.main_panel)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)

        self.tabs = EveTabs(self)
        self.tabs.tabChanged.connect(self.switch_tab)
        layout.addWidget(self.tabs)

        self.stack = QStackedWidget()
        self.stack.setObjectName("MainStack")
        self.stack.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(self.stack, 1)

        self.general_page = QWidget()
        self.general_page.setObjectName("GeneralPage")
        self.general_page.setAttribute(Qt.WA_StyledBackground, True)
        general_layout = QVBoxLayout(self.general_page)
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(0)

        self.status_label = QLabel("Status: ready")
        self.status_label.hide()

        self.table = IntelTable()
        self.setup_table()

        general_layout.addWidget(self.table, 1)

        self.zkill_panel = ZkillPanel(self)
        self.options_panel = OptionsPanel(self)
        self.options_panel.setObjectName("OptionsPage")
        self.options_panel.setAttribute(Qt.WA_StyledBackground, True)
        self.options_panel.settingsChanged.connect(self.apply_ui_settings)
        self.options_panel.set_values(
            self.ui_transparency,
            self.ui_blur,
            self.ui_font_size,
            self.ui_frame_color,
            self.ui_text_color,
            self.ui_bg_color,
            emit=False,
        )

        self.stack.addWidget(self.general_page)
        self.stack.addWidget(self.zkill_panel)
        self.stack.addWidget(self.options_panel)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(0)
        bottom_bar.addStretch()

        self.size_grip = QSizeGrip(self.main_panel)
        self.size_grip.setFixedSize(10, 10)
        bottom_bar.addWidget(self.size_grip)

        layout.addLayout(bottom_bar)

        self.apply_ui_settings(
            self.ui_transparency,
            self.ui_blur,
            self.ui_font_size,
            self.ui_frame_color,
            self.ui_text_color,
            self.ui_bg_color,
            persist=False,
        )

    def setup_table(self):
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", "", "Name", "Danger", "Gang", "Corp/Ally", "Last Ships"]
        )

        for col in (2, 3, 4, 5, 6):
            header_item = self.table.horizontalHeaderItem(col)
            if header_item:
                header_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setMinimumSectionSize(6)
        self.table.horizontalHeader().setDefaultSectionSize(24)

        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)

        self.table.rowHovered.connect(self.on_table_row_hovered)
        self.table.mouseLeft.connect(self.on_table_mouse_left)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)

        self.table.setColumnWidth(0, 18)
        self.table.setColumnWidth(1, 14)

        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)

        self.table.verticalHeader().setDefaultSectionSize(20)

    def apply_ui_settings(
        self,
        transparency,
        blur=0,
        font_size=10,
        frame_color="#161616",
        text_color="#d6d6d6",
        bg_color="#0b0b0b",
        persist=True,
    ):
        self.ui_transparency = max(0, min(100, int(transparency)))
        self.ui_alpha = self.transparency_to_alpha(self.ui_transparency)
        self.ui_blur = 1 if int(blur) else 0
        self.ui_font_size = int(font_size)
        self.ui_frame_color = str(frame_color).lower()
        self.ui_text_color = str(text_color).lower()
        self.ui_bg_color = str(bg_color).lower()

        if persist:
            save_ui_settings(
                {
                    "transparency": self.ui_transparency,
                    "blur": self.ui_blur,
                    "font_size": self.ui_font_size,
                    "frame_color": self.ui_frame_color,
                    "text_color": self.ui_text_color,
                    "bg_color": self.ui_bg_color,
                }
            )

        bg = QColor(self.ui_bg_color)

        self.setStyleSheet("""
            QWidget#RootWindow {
                background: transparent;
            }
        """)

        self.main_panel.setStyleSheet(f"""
            QFrame#MainPanel {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {self.ui_alpha});
                border: 1px solid {self.ui_frame_color};
            }}

            QStackedWidget#MainStack,
            QWidget#GeneralPage,
            QWidget#OptionsPage {{
                background-color: transparent;
            }}
        """)

        table_alpha = max(40, min(255, self.ui_alpha - 20))
        header_alpha = max(80, min(255, self.ui_alpha + 25))

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {table_alpha});
                border: none;
                gridline-color: transparent;
                color: {self.ui_text_color};
                font-size: {self.ui_font_size}pt;
                outline: none;
            }}

            QTableWidget::item {{
                color: {self.ui_text_color};
                padding: 1px 2px;
                border: none;
                font-size: {self.ui_font_size}pt;
            }}

            QHeaderView {{
                background: transparent;
                border: none;
            }}

            QHeaderView::section {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {header_alpha});
                color: {self.ui_text_color};
                border: none;
                padding: 2px 2px;
                font-size: {self.ui_font_size}pt;
                font-weight: normal;
            }}
        """)

        self.tabs.apply_colors(
            self.ui_frame_color,
            self.ui_text_color,
            self.ui_font_size,
            self.ui_bg_color,
        )

        self.title_bar.title.setStyleSheet(f"""
            QLabel {{
                color: {self.ui_text_color};
                font-size: {self.ui_font_size}pt;
                font-weight: normal;
                background-color: transparent;
            }}
        """)

        self.apply_font_size(self.ui_font_size)
        self.update_existing_table_text_color(self.ui_text_color)
        self.apply_window_blur()

    def apply_font_size(self, font_size):
        font = self.font()
        font.setPointSize(int(font_size))
        self.setFont(font)

        app = QApplication.instance()
        if app:
            app_font = app.font()
            app_font.setPointSize(int(font_size))
            app.setFont(app_font)

        for widget in self.findChildren(QWidget):
            widget_font = widget.font()
            widget_font.setPointSize(int(font_size))
            widget.setFont(widget_font)

    def bg_rgb(self):
        color = QColor(self.ui_bg_color)
        return (color.red(), color.green(), color.blue())

    def apply_window_blur(self):
        try:
            enable_eve_blur(
                int(self.winId()),
                panel_alpha=self.ui_alpha,
                blur_percent=self.ui_blur,
                rgb=self.bg_rgb(),
            )
        except Exception as e:
            print("Blur apply error:", e)

    def reapply_current_ui_settings(self):
        try:
            self.apply_ui_settings(
                self.ui_transparency,
                self.ui_blur,
                self.ui_font_size,
                self.ui_frame_color,
                self.ui_text_color,
                self.ui_bg_color,
                persist=False,
            )

            if hasattr(self, "options_panel"):
                self.options_panel.apply_local_style()
                self.options_panel.update()

            self.update()
            self.main_panel.update()

        except Exception as e:
            print("Startup UI reapply error:", e)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.reapply_current_ui_settings)
        QTimer.singleShot(80, self.reapply_current_ui_settings)
        QTimer.singleShot(250, self.reapply_current_ui_settings)

    def update_existing_table_text_color(self, text_color):
        color = QColor(text_color)

        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)

                if item:
                    item.setForeground(color)

        self.table.viewport().update()

    def switch_tab(self, name):
        if name == "General":
            self.stack.setCurrentWidget(self.general_page)
            return

        if name == "Zkill":
            self.stack.setCurrentWidget(self.zkill_panel)
            return

        if name == "Options":
            self.stack.setCurrentWidget(self.options_panel)
            return

    def start_clipboard_timer(self):
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.timeout.connect(self.check_clipboard_background)
        self.clipboard_timer.start(700)

    def read_clipboard_text(self):
        try:
            text = pyperclip.paste()

            if text is None:
                return ""

            return str(text).strip()

        except Exception as e:
            print("Clipboard error:", e)
            return ""

    def check_clipboard_background(self):
        text = self.read_clipboard_text()

        if not text:
            return

        if text == self.last_clipboard_text:
            return

        pilots = parse_pilots(text)

        if not pilots:
            self.last_clipboard_text = text
            return

        if pilots == self.last_pilots:
            self.last_clipboard_text = text
            return

        self.last_clipboard_text = text
        self.last_pilots = pilots
        self.update_table(pilots)

    def force_windows_topmost(self, enabled: bool):
        if sys.platform != "win32":
            return

        try:
            import ctypes

            hwnd = int(self.winId())

            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2

            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_SHOWWINDOW = 0x0040

            ctypes.windll.user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST if enabled else HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW,
            )

        except Exception as e:
            print("Topmost error:", e)

    def toggle_always_on_top(self, checked):
        flags = Qt.Window | Qt.FramelessWindowHint

        if checked:
            flags |= Qt.WindowStaysOnTopHint

        self.setWindowFlags(flags)
        self.show()
        self.raise_()
        self.activateWindow()
        self.force_windows_topmost(checked)
        QTimer.singleShot(0, self.apply_window_blur)

    def set_loading_row(self, row, pilot):
        render_loading_row(self, row, pilot)

    def update_table(self, pilots):
        self.table.setRowCount(len(pilots))

        self.relations = {}
        self.row_character_ids = {}
        self.row_base_colors = {}
        self.pending_pilots = len(pilots)

        self.relations_running = False
        self.active_relation_workers.clear()

        self.last_hover_row = None
        self.tabs.set_linked_count(0)
        self.title_bar.title.setText("Overview (Local Intel)")

        for row, pilot in enumerate(pilots):
            self.set_loading_row(row, pilot)

            worker = PilotWorker(row, pilot)
            worker.signals.finished.connect(self.update_pilot_row)
            self.thread_pool.start(worker)

    def update_pilot_row(self, row, result):
        render_pilot_row(self, row, result)
        self.update_existing_table_text_color(self.ui_text_color)

    def update_cyno_cell(self, row, cyno):
        render_cyno_cell(self, row, cyno)

    def start_relations_scan(self):
        if self.relations_running:
            return

        if len(self.row_character_ids) < 2:
            return

        ids = sorted(self.row_character_ids.values())
        relations_key = ",".join(str(x) for x in ids)

        if relations_key == self.last_relations_key and self.relations:
            return

        self.last_relations_key = relations_key
        self.relations_running = True

        worker = RelationWorker(dict(self.row_character_ids))
        worker.signals.finished.connect(self.update_relations)

        self.active_relation_workers.append(worker)
        self.relations_pool.start(worker)

    def update_relations(self, relations):
        self.relations_running = False
        self.active_relation_workers.clear()
        self.relations = relations or {}

        if self.last_hover_row is not None:
            self.highlight_relation_rows(self.last_hover_row)

    def clear_relation_highlight(self):
        if hasattr(self.table, "clear_highlight_rows"):
            self.table.clear_highlight_rows()

    def highlight_relation_rows(self, row):
        if row < 0 or row >= self.table.rowCount():
            return

        self.last_hover_row = row

        active_color = QColor("#2F5F8F")
        related_color = QColor("#1F5A32")

        related_rows = self.relations.get(row, [])

        highlight_rows = {
            row: active_color,
        }

        for related_row in related_rows:
            highlight_rows[related_row] = related_color

        if hasattr(self.table, "set_highlight_rows"):
            self.table.set_highlight_rows(highlight_rows)

        self.tabs.set_linked_count(len(related_rows))

    def on_table_row_hovered(self, row):
        self.highlight_relation_rows(row)

    def on_table_mouse_left(self):
        self.last_hover_row = None
        self.clear_relation_highlight()
        self.title_bar.title.setText("Overview (Local Intel)")
        self.tabs.set_linked_count(0)

    def eventFilter(self, obj, event):
        if handle_resize_event(self, obj, event):
            return True

        return super().eventFilter(obj, event)

    def open_in_zkill_tab(self, url):
        self.tabs.set_active("Zkill")
        self.zkill_panel.load_url(url)

    def get_clicked_last_ship_index(self, row, col, ships):
        if not ships:
            return 0

        index = self.table.model().index(row, col)
        rect = self.table.visualRect(index)

        pos = self.table.viewport().mapFromGlobal(QCursor.pos())
        x = pos.x() - rect.x() - 3

        if x <= 0:
            return 0

        metrics = QFontMetrics(self.table.font())
        cursor_x = 0

        for i, ship in enumerate(ships):
            name = str(ship.get("display_name") or ship.get("name", "?"))
            name_width = metrics.horizontalAdvance(name)

            if cursor_x <= x <= cursor_x + name_width:
                return i

            cursor_x += name_width

            if i < len(ships) - 1:
                sep = " | "
                sep_width = metrics.horizontalAdvance(sep)

                if cursor_x <= x <= cursor_x + sep_width:
                    # Click on separator: choose the nearest ship.
                    left_distance = x - cursor_x
                    right_distance = (cursor_x + sep_width) - x
                    return i if left_distance <= right_distance else i + 1

                cursor_x += sep_width

        return max(0, len(ships) - 1)

    def open_last_ship_loss(self, ship):
        if not ship:
            return

        loss_url = ship.get("last_loss_url")

        if loss_url:
            self.open_in_zkill_tab(loss_url)
            return

        killmail_id = ship.get("killmail_id")
        if killmail_id:
            self.open_in_zkill_tab(f"https://zkillboard.com/kill/{killmail_id}/")
            return

        ship_type_id = ship.get("ship_type_id")
        if ship_type_id:
            self.open_in_zkill_tab(f"https://zkillboard.com/ship/{ship_type_id}/")

    def on_cell_double_clicked(self, row, col):
        item = self.table.item(row, col)

        if not item:
            return

        if col == 2:
            character_id = item.data(Qt.UserRole)

            if character_id:
                self.open_in_zkill_tab(
                    f"https://zkillboard.com/character/{character_id}/"
                )

            return

        if col == 6:
            last_ships = item.data(Qt.UserRole)

            if not last_ships:
                return

            ship_index = self.get_clicked_last_ship_index(row, col, last_ships)
            ship = last_ships[ship_index]
            self.open_last_ship_loss(ship)
            return

    def closeEvent(self, event):
        self.thread_pool.clear()
        self.cyno_pool.clear()
        self.relations_pool.clear()
        self.active_relation_workers.clear()

        event.accept()
