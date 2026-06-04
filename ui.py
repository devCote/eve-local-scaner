from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QPushButton,
)

from parser import parse_pilots
from worker import PilotWorker
import pyperclip


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Intel Scanner")
        self.resize(700, 650)

        self.last_clipboard_text = ""
        self.last_pilots = []

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(8)

        self.build_ui()
        self.start_clipboard_timer()

    def build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top_bar = QLabel()
        top_bar.setFixedHeight(3)
        top_bar.setStyleSheet("background-color: #FF9900;")
        layout.addWidget(top_bar)

        title = QLabel("EVE LOCAL INTEL")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                color: #FF9900;
                font-size: 16pt;
                font-weight: bold;
                letter-spacing: 2px;
            }
        """)
        layout.addWidget(title)

        self.status_label = QLabel("Status: watching clipboard in background")
        layout.addWidget(self.status_label)

        controls = QHBoxLayout()

        self.always_on_top = QCheckBox("Always on top")
        self.always_on_top.stateChanged.connect(self.toggle_always_on_top)
        controls.addWidget(self.always_on_top)

        self.scan_button = QPushButton("Scan Clipboard")
        self.scan_button.clicked.connect(self.scan_clipboard)
        controls.addWidget(self.scan_button)

        layout.addLayout(controls)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["C", "Pilot", "Danger", "Gang", "Ally/Corp", "Notes"]
        )

        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.table)

        self.footer_label = QLabel("Copy local from EVE: Ctrl+A → Ctrl+C")
        self.footer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.footer_label)

        self.setLayout(layout)


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Intel Scanner")
        self.resize(700, 650)

        self.last_clipboard_text = ""
        self.last_pilots = []

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(8)

        self.build_ui()
        self.start_clipboard_timer()

    def build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        top_bar = QLabel()
        top_bar.setFixedHeight(3)
        top_bar.setStyleSheet("background-color: #FF9900;")
        layout.addWidget(top_bar)

        title = QLabel("EVE LOCAL INTEL")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                color: #FF9900;
                font-size: 16pt;
                font-weight: bold;
                letter-spacing: 2px;
            }
        """)
        layout.addWidget(title)

        self.status_label = QLabel("Status: watching clipboard in background")
        layout.addWidget(self.status_label)

        controls = QHBoxLayout()

        self.always_on_top = QCheckBox("Always on top")
        self.always_on_top.stateChanged.connect(self.toggle_always_on_top)
        controls.addWidget(self.always_on_top)

        self.scan_button = QPushButton("Scan Clipboard")
        self.scan_button.clicked.connect(self.scan_clipboard)
        controls.addWidget(self.scan_button)

        layout.addLayout(controls)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["C", "Pilot", "Danger", "Gang", "Ally/Corp", "Notes"]
        )

        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.table)

        self.footer_label = QLabel("Copy local from EVE: Ctrl+A → Ctrl+C")
        self.footer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.footer_label)

        self.setLayout(layout)

    def start_clipboard_timer(self):
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.timeout.connect(self.check_clipboard_background)
        self.clipboard_timer.start(700)

    def read_clipboard_text(self):
        try:
            return pyperclip.paste().strip()
        except Exception as e:
            self.status_label.setText(f"Status: clipboard error: {e}")
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

    def toggle_always_on_top(self):
        checked = self.always_on_top.isChecked()

        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.status_label.setText("Status: always on top enabled")
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.status_label.setText("Status: always on top disabled")

        self.show()
        self.raise_()

    def scan_clipboard(self):
        text = self.read_clipboard_text()

        if not text:
            self.status_label.setText("Status: clipboard is empty")
            return

        pilots = parse_pilots(text)

        if not pilots:
            self.status_label.setText("Status: no pilots found in clipboard")
            return

        self.last_clipboard_text = text
        self.last_pilots = pilots
        self.update_table(pilots)

    def get_row_color(self, danger: int):
        if danger >= 60:
            return "#552222"
        if danger >= 40:
            return "#555022"
        return "#225533"

    def set_loading_row(self, row, pilot):
        items = [
            QTableWidgetItem(""),
            QTableWidgetItem(pilot),
            QTableWidgetItem("..."),
            QTableWidgetItem("..."),
            QTableWidgetItem("loading"),
            QTableWidgetItem("loading..."),
        ]

        for item in items:
            item.setBackground(QColor("#1A1D21"))

        items[0].setTextAlignment(Qt.AlignCenter)
        items[2].setTextAlignment(Qt.AlignCenter)
        items[3].setTextAlignment(Qt.AlignCenter)
        items[4].setTextAlignment(Qt.AlignCenter)

        for col, item in enumerate(items):
            self.table.setItem(row, col, item)

    def update_table(self, pilots):
        self.table.setRowCount(len(pilots))
        self.status_label.setText(f"Status: loading pilots: {len(pilots)}")

        for row, pilot in enumerate(pilots):
            self.set_loading_row(row, pilot)

            worker = PilotWorker(row, pilot)
            worker.signals.finished.connect(self.update_pilot_row)
            self.thread_pool.start(worker)

    def update_pilot_row(self, row, result):
        danger = result.get("danger", 0)
        gang = result.get("gang", 0)
        ally = result.get("ally", "?")
        cyno_icon = "✴︎" if result.get("cyno") else ""
        notes = result.get("url", "pilot not found")
        pilot = result.get("pilot", "")

        items = [
            QTableWidgetItem(cyno_icon),
            QTableWidgetItem(pilot),
            QTableWidgetItem(str(danger)),
            QTableWidgetItem(str(gang)),
            QTableWidgetItem(ally),
            QTableWidgetItem(notes),
        ]

        bg_color = QColor(self.get_row_color(danger))

        for item in items:
            item.setBackground(bg_color)

        items[0].setTextAlignment(Qt.AlignCenter)
        items[2].setTextAlignment(Qt.AlignCenter)
        items[3].setTextAlignment(Qt.AlignCenter)
        items[4].setTextAlignment(Qt.AlignCenter)

        for col, item in enumerate(items):
            self.table.setItem(row, col, item)

        self.status_label.setText("Status: updated")
