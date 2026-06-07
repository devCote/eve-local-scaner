import sys
import pyperclip

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor
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
)

from parser import parse_pilots
from worker import PilotWorker
from spinner import SpinnerManager
from relations import RelationWorker
from title_bar import TitleBar
from intel_table import IntelTable
from browser_utils import open_url

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
        self.resize(760, 440)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(560, 280)

        self.resize_margin = 8

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

    def build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.main_panel = QFrame()
        self.main_panel.setObjectName("MainPanel")
        self.main_panel.setStyleSheet("""
            QFrame#MainPanel {
                background-color: rgba(14, 16, 20, 245);
                border-top: 1px solid #6A7078;
                border-left: 1px solid #6A7078;
                border-right: 1px solid #25282E;
                border-bottom: 1px solid #25282E;
            }
        """)

        outer_layout.addWidget(self.main_panel)

        layout = QVBoxLayout(self.main_panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)

        # тонкая инфо-панель как в EVE
        self.info_bar = QFrame()
        self.info_bar.setFixedHeight(20)
        self.info_bar.setStyleSheet("""
            QFrame {
                background-color: rgba(22, 24, 29, 240);
                border-top: 1px solid #555B63;
                border-left: 1px solid #555B63;
                border-right: 1px solid #2A2D33;
                border-bottom: 1px solid #1A1C21;
            }
        """)

        info_layout = QHBoxLayout(self.info_bar)
        info_layout.setContentsMargins(6, 0, 6, 0)
        info_layout.setSpacing(4)

        self.info_label = QLabel("Overview")
        self.info_label.setStyleSheet("""
            QLabel {
                color: #E2E5E8;
                font-size: 8pt;
                background: transparent;
            }
        """)

        self.linked_label = QLabel("")
        self.linked_label.setStyleSheet("""
            QLabel {
                color: #AEB6C0;
                font-size: 8pt;
                background: transparent;
            }
        """)

        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        info_layout.addWidget(self.linked_label)

        layout.addWidget(self.info_bar)

        self.table = IntelTable()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["D", "C", "Pilot", "Danger", "Gang", "Corp/Ally", "Top Ships"]
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

        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
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

        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: rgba(16, 18, 22, 250);
            }
        """)

        layout.addWidget(self.table, 1)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.setSpacing(0)
        bottom_bar.addStretch()

        self.size_grip = QSizeGrip(self.main_panel)
        self.size_grip.setFixedSize(12, 12)
        bottom_bar.addWidget(self.size_grip)

        layout.addLayout(bottom_bar)

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
        self.linked_label.setText("")
        self.title_bar.title.setText("Local Intel")
        self.info_label.setText("Overview")

        for row, pilot in enumerate(pilots):
            self.set_loading_row(row, pilot)

            worker = PilotWorker(row, pilot)
            worker.signals.finished.connect(self.update_pilot_row)
            self.thread_pool.start(worker)

    def update_pilot_row(self, row, result):
        render_pilot_row(self, row, result)

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
        for row, bg_color in self.row_base_colors.items():
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)

                if item:
                    item.setBackground(bg_color)

    def highlight_relation_rows(self, row):
        if row < 0 or row >= self.table.rowCount():
            return

        self.last_hover_row = row
        self.clear_relation_highlight()

        active_color = QColor("#334466")
        related_color = QColor("#1F4D2E")

        related_rows = self.relations.get(row, [])
        rows_to_highlight = [row] + related_rows

        for highlight_row in rows_to_highlight:
            color = active_color if highlight_row == row else related_color

            for col in range(self.table.columnCount()):
                item = self.table.item(highlight_row, col)

                if item:
                    item.setBackground(color)

        self.title_bar.title.setText("Local Intel")
        self.info_label.setText(f"Pilot row {row + 1}")
        self.linked_label.setText(f"linked pilots: {len(related_rows)}")

    def on_table_row_hovered(self, row):
        self.highlight_relation_rows(row)

    def on_table_mouse_left(self):
        self.last_hover_row = None
        self.clear_relation_highlight()
        self.title_bar.title.setText("Local Intel")
        self.info_label.setText("Overview")
        self.linked_label.setText("")

    def eventFilter(self, obj, event):
        if handle_resize_event(self, obj, event):
            return True

        return super().eventFilter(obj, event)

    def on_cell_double_clicked(self, row, col):
        item = self.table.item(row, col)

        if not item:
            return

        if col == 2:
            character_id = item.data(Qt.UserRole)

            if character_id:
                open_url(f"https://zkillboard.com/character/{character_id}/")

            return

        if col == 6:
            top_ships = item.data(Qt.UserRole)

            if not top_ships:
                return

            first_ship = top_ships[0]
            ship_type_id = first_ship.get("ship_type_id")

            if ship_type_id:
                open_url(f"https://zkillboard.com/ship/{ship_type_id}/")

            return

    def closeEvent(self, event):
        self.thread_pool.clear()
        self.cyno_pool.clear()
        self.relations_pool.clear()
        self.active_relation_workers.clear()
        event.accept()
