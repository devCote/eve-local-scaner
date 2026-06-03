from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QPushButton
)

from parser import parse_pilots
from clipboard import ClipboardWatcher
from esi_client import get_character_id, get_ally_or_corp
from zkill_client import get_danger_percent, get_gangRatio, has_cyno_history
from worker import PilotWorker


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Intel Scanner")
        self.resize(700, 650)

        self.build_ui()
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(8)
        self.clipboard_watcher = ClipboardWatcher(self.on_clipboard_text)


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

        self.status_label = QLabel("Status: watching clipboard")
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

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(self.table)

        self.footer_label = QLabel("Copy local from EVE: Ctrl+A → Ctrl+C")
        self.footer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.footer_label)

        self.setLayout(layout)

    def toggle_always_on_top(self):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.always_on_top.isChecked())
        self.show()

    def scan_clipboard(self):
        text = self.clipboard_watcher.clipboard.text().strip()
        self.on_clipboard_text(text)

    def on_clipboard_text(self, text):
        pilots = parse_pilots(text)
        self.update_table(pilots)

    def get_row_color(self, danger: int):
        if danger >= 60:
            return "#552222"
        if danger >= 40:
            return "#555022"
        return "#225533"

    def set_loading_row(self, row, pilot):
        cyno_item = QTableWidgetItem("")
        pilot_item = QTableWidgetItem(pilot)
        danger_item = QTableWidgetItem("...")
        gang_item = QTableWidgetItem("...")
        ally_item = QTableWidgetItem("loading")
        notes_item = QTableWidgetItem("loading...")

        cyno_item.setTextAlignment(Qt.AlignCenter)
        danger_item.setTextAlignment(Qt.AlignCenter)
        gang_item.setTextAlignment(Qt.AlignCenter)
        ally_item.setTextAlignment(Qt.AlignCenter)

        bg_color = QColor("#1A1D21")

        for item in [
            cyno_item,
            pilot_item,
            danger_item,
            gang_item,
            ally_item,
            notes_item,
        ]:
            item.setBackground(bg_color)

        self.table.setItem(row, 0, cyno_item)
        self.table.setItem(row, 1, pilot_item)
        self.table.setItem(row, 2, danger_item)
        self.table.setItem(row, 3, gang_item)
        self.table.setItem(row, 4, ally_item)
        self.table.setItem(row, 5, notes_item)

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

        cyno_item = QTableWidgetItem(cyno_icon)
        pilot_item = QTableWidgetItem(pilot)
        danger_item = QTableWidgetItem(str(danger))
        gang_item = QTableWidgetItem(str(gang))
        ally_item = QTableWidgetItem(ally)
        notes_item = QTableWidgetItem(notes)

        cyno_item.setTextAlignment(Qt.AlignCenter)
        danger_item.setTextAlignment(Qt.AlignCenter)
        gang_item.setTextAlignment(Qt.AlignCenter)
        ally_item.setTextAlignment(Qt.AlignCenter)

        bg_color = QColor(self.get_row_color(danger))

        for item in [
            cyno_item,
            pilot_item,
            danger_item,
            gang_item,
            ally_item,
            notes_item,
        ]:
            item.setBackground(bg_color)

        self.table.setItem(row, 0, cyno_item)
        self.table.setItem(row, 1, pilot_item)
        self.table.setItem(row, 2, danger_item)
        self.table.setItem(row, 3, gang_item)
        self.table.setItem(row, 4, ally_item)
        self.table.setItem(row, 5, notes_item)

        self.status_label.setText("Status: updated")
