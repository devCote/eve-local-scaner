from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QPushButton
)

from parser import parse_pilots
from clipboard import ClipboardWatcher
from esi_client import get_character_id
from zkill_client import get_danger_percent, get_gangRatio


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Intel Scanner")
        self.resize(650, 650)

        self.build_ui()
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
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Pilot", "Danger", "Gang", "Cyno", "Notes"]
        )

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

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
            return "#552222"  # red background
        if danger >= 40:
            return "#555022"  # yellow background
        return "#225533"      # green background

    def get_cyno_status(self, danger: int, gang: int):
        if danger >= 60 and gang >= 70:
            return "HIGH"
        if danger >= 40 and gang >= 50:
            return "MED"
        return "-"

    def update_table(self, pilots):
        self.table.setRowCount(len(pilots))

        for row, pilot in enumerate(pilots):
            character_id = get_character_id(pilot)

            if character_id:
                danger = get_danger_percent(character_id)
                gang = get_gangRatio(character_id)
                cyno = self.get_cyno_status(danger, gang)
                notes = f"https://zkillboard.com/character/{character_id}/"
            else:
                danger = 0
                gang = 0
                cyno = "-"
                notes = "pilot not found"

            pilot_item = QTableWidgetItem(pilot)
            danger_item = QTableWidgetItem(str(danger))
            gang_item = QTableWidgetItem(str(gang))
            cyno_item = QTableWidgetItem(cyno)
            notes_item = QTableWidgetItem(notes)

            danger_item.setTextAlignment(Qt.AlignCenter)
            gang_item.setTextAlignment(Qt.AlignCenter)
            cyno_item.setTextAlignment(Qt.AlignCenter)

            bg_color = self.get_row_color(danger)

            for item in [pilot_item, danger_item, gang_item, cyno_item, notes_item]:
                item.setBackground(QColor(bg_color))

            self.table.setItem(row, 0, pilot_item)
            self.table.setItem(row, 1, danger_item)
            self.table.setItem(row, 2, gang_item)
            self.table.setItem(row, 3, cyno_item)
            self.table.setItem(row, 4, notes_item)

        self.status_label.setText(f"Status: pilots found: {len(pilots)}")
