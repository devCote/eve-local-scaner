import sys
import pyperclip

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
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

from row_renderer import (
    set_loading_row as render_loading_row,
    render_pilot_row,
    render_cyno_cell,
)

from window_resize import handle_resize_event
from windows_blur import enable_eve_blur


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Scanner")
        self.resize(760, 440)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(560, 240)

        self.resize_margin = 8

        self.ui_transparency = 20
        self.ui_blur = 35
        self.ui_font_size = 8
        self.ui_frame_color = "#444A52"
        self.ui_text_color = "#C7C9CC"
        self.ui_bg_color = "#07080A"
        self.ui_alpha = self.alpha_from_transparency(self.ui_transparency)

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

    def alpha_from_transparency(self, transparency_percent):
        transparency_percent = max(0, min(100, int(transparency_percent)))
        return max(0, min(255, int(round(255 * (100 - transparency_percent) / 100))))

    def bg_rgb(self):
        color = QColor(self.ui_bg_color)
        return color.red(), color.green(), color.blue()

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_window_blur()

    def apply_window_blur(self):
        blur_alpha = int(self.alpha_from_transparency(self.ui_transparency))
        enable_eve_blur(
            int(self.winId()),
            blur_alpha,
            self.ui_blur,
            self.bg_rgb(),
        )

    def build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.main_panel = QFrame()
        self.main_panel.setObjectName("MainPanel")
        outer_layout.addWidget(self.main_panel)

        layout = QVBoxLayout(self.main_panel)
        # This margin is the visual frame thickness. No extra bottom padding.
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)

        self.tabs = EveTabs(self)
        self.tabs.tabChanged.connect(self.switch_tab)
        layout.addWidget(self.tabs)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.general_page = QWidget()
        self.general_page.setAttribute(Qt.WA_TranslucentBackground)
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
        self.options_panel.settingsChanged.connect(self.apply_ui_settings)

        self.stack.addWidget(self.general_page)
        self.stack.addWidget(self.zkill_panel)
        self.stack.addWidget(self.options_panel)

        self.apply_ui_settings(
            self.ui_transparency,
            self.ui_blur,
            self.ui_font_size,
            self.ui_frame_color,
            self.ui_text_color,
            self.ui_bg_color,
        )

    def setup_table(self):
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", "", "Pilot", "Danger", "Gang", "Corp/Ally", "Top Ships"]
        )

        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setHighlightSections(False)

        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(True)

        self.table.rowHovered.connect(self.on_table_row_hovered)
        self.table.mouseLeft.connect(self.on_table_mouse_left)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 24)
        self.table.setColumnWidth(1, 24)

        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)

        self.table.verticalHeader().setDefaultSectionSize(22)

    def apply_ui_settings(self, transparency, blur, font_size, frame_color, text_color, bg_color):
        self.ui_transparency = max(0, min(100, int(transparency)))
        self.ui_blur = max(0, min(100, int(blur)))
        self.ui_font_size = int(font_size)
        self.ui_frame_color = frame_color
        self.ui_text_color = text_color
        self.ui_bg_color = bg_color
        self.ui_alpha = self.alpha_from_transparency(self.ui_transparency)

        bg = QColor(bg_color)
        alpha = self.ui_alpha
        table_alpha = max(0, min(255, alpha - 35))
        header_alpha = max(0, min(255, alpha + 30))
        tab_alpha = max(0, min(255, alpha - 15))
        title_alpha = max(0, min(255, alpha - 5))

        self.main_panel.setStyleSheet(f"""
            QFrame#MainPanel {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {alpha});
                border: 1px solid {frame_color};
            }}

            QStackedWidget {{
                background: transparent;
                border: none;
            }}
        """)

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {table_alpha});
                alternate-background-color: transparent;
                border: 1px solid rgba(37, 42, 49, {max(80, alpha)});
                gridline-color: rgba(70, 76, 86, 90);
                color: {text_color};
                font-size: {font_size}pt;
                selection-background-color: transparent;
                outline: none;
            }}

            QTableWidget::item {{
                color: {text_color};
                padding: 1px 5px;
                border: none;
                background: transparent;
                font-size: {font_size}pt;
            }}

            QTableWidget::item:selected {{
                background: transparent;
                color: {text_color};
            }}

            QHeaderView::section {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {header_alpha});
                color: {text_color};
                border: 1px solid {frame_color};
                padding: 2px 5px;
                font-size: {font_size}pt;
                font-weight: normal;
            }}
        """)

        self.tabs.apply_colors(frame_color, text_color, font_size, tab_alpha)
        self.title_bar.apply_style(frame_color, text_color, font_size, title_alpha)

        font = self.font()
        font.setPointSize(font_size)
        self.setFont(font)
        self.table.setFont(font)
        self.general_page.setFont(font)
        self.zkill_panel.setFont(font)
        self.options_panel.setFont(font)
        self.title_bar.setFont(font)
        self.tabs.setFont(font)

        if hasattr(self.zkill_panel, "apply_ui_settings"):
            self.zkill_panel.apply_ui_settings(
                alpha,
                font_size,
                frame_color,
                text_color,
                bg_color,
            )

        self.update_existing_table_text_color(text_color)
        self.apply_window_blur()

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
        self.apply_window_blur()
        self.raise_()
        self.activateWindow()
        self.force_windows_topmost(checked)

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

        highlight_rows = {row: active_color}
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

    def on_cell_double_clicked(self, row, col):
        item = self.table.item(row, col)
        if not item:
            return

        if col == 2:
            character_id = item.data(Qt.UserRole)
            if character_id:
                self.open_in_zkill_tab(f"https://zkillboard.com/character/{character_id}/")
            return

        if col == 6:
            top_ships = item.data(Qt.UserRole)
            if not top_ships:
                return

            first_ship = top_ships[0]
            ship_type_id = first_ship.get("ship_type_id")
            if ship_type_id:
                self.open_in_zkill_tab(f"https://zkillboard.com/ship/{ship_type_id}/")
            return

    def closeEvent(self, event):
        self.thread_pool.clear()
        self.cyno_pool.clear()
        self.relations_pool.clear()
        self.active_relation_workers.clear()
        event.accept()
