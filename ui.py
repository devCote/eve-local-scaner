import webbrowser
import pyperclip

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
from worker import PilotWorker, CynoWorker
from spinner import SpinnerManager


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Intel Scanner")
        self.resize(900, 650)

        self.last_clipboard_text = ""
        self.last_pilots = []

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(12)

        self.cyno_pool = QThreadPool()
        self.cyno_pool.setMaxThreadCount(3)

        self.build_ui()
        self.start_clipboard_timer()
        self.spinner = SpinnerManager(self)

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
            ["C", "Pilot", "Danger", "Gang", "Corp/Ally", "Top Ships"]
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
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)

        layout.addWidget(self.table)

        self.footer_label = QLabel(
            "Copy local from EVE: Ctrl+A → Ctrl+C | Cyno loads separately"
        )
        self.footer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.footer_label)

        self.setLayout(layout)

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
            item.setForeground(QColor("#FFFFFF"))
            item.setFont(self.table.font())

        items[0].setTextAlignment(Qt.AlignCenter)
        items[2].setTextAlignment(Qt.AlignCenter)
        items[3].setTextAlignment(Qt.AlignCenter)
        items[4].setTextAlignment(Qt.AlignCenter)

        for col, item in enumerate(items):
            self.table.setItem(row, col, item)

        self.table.setCellWidget(row, 0, None)

    def update_table(self, pilots):
        self.table.setRowCount(len(pilots))
        self.status_label.setText(f"Status: loading pilots fast: {len(pilots)}")

        for row, pilot in enumerate(pilots):
            self.set_loading_row(row, pilot)

            worker = PilotWorker(row, pilot)
            worker.signals.finished.connect(self.update_pilot_row)
            self.thread_pool.start(worker)

    def update_pilot_row(self, row, result):
        danger_raw = result.get("danger", 0)
        gang_raw = result.get("gang", 0)

        try:
            danger_value = int(str(danger_raw).replace(" ", "").strip())
        except Exception:
            danger_value = 0

        try:
            gang_value = int(str(gang_raw).replace(" ", "").strip())
        except Exception:
            gang_value = 0

        ally = result.get("ally", "?")
        pilot = result.get("pilot", "")
        top_ships = result.get("top_ships", [])

        ship_names = []

        for ship in top_ships:
            name = ship.get("name", "?")
            ship_names.append(name)

        top_ships_text = " | ".join(ship_names) if ship_names else "-"

        items = [
            QTableWidgetItem(""),
            QTableWidgetItem(pilot),
            QTableWidgetItem(str(danger_value)),
            QTableWidgetItem(str(gang_value)),
            QTableWidgetItem(ally),
            QTableWidgetItem(top_ships_text),
        ]

        items[5].setData(Qt.UserRole, top_ships)

        character_id = result.get("character_id")
        items[1].setData(Qt.UserRole, character_id)

        bg_color = QColor(self.get_row_color(danger_value))

        for item in items:
            item.setBackground(bg_color)
            item.setForeground(QColor("#FFFFFF"))
            item.setFont(self.table.font())

        items[0].setTextAlignment(Qt.AlignCenter)
        items[2].setTextAlignment(Qt.AlignCenter)
        items[3].setTextAlignment(Qt.AlignCenter)
        items[4].setTextAlignment(Qt.AlignCenter)

        for col, item in enumerate(items):
            self.table.setItem(row, col, item)

        self.table.setCellWidget(row, 0, None)

        if character_id:
            cyno_loading = QLabel(self.spinner.current_frame())
            cyno_loading.setAlignment(Qt.AlignCenter)
            cyno_loading.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    color: #FF9900;
                    font-size: 12pt;
                    font-weight: bold;
                }
            """)

            self.spinner.add(row, cyno_loading)
            self.table.setCellWidget(row, 0, cyno_loading)

            cyno_worker = CynoWorker(row, character_id)
            cyno_worker.signals.finished.connect(self.update_cyno_cell)
            self.cyno_pool.start(cyno_worker)

        self.status_label.setText("Status: fast data updated, cyno loading...")

    def update_cyno_cell(self, row, cyno):
        self.spinner.remove(row)

        self.table.setCellWidget(row, 0, None)

        if not cyno:
            empty = QLabel("")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("""
                    QLabel {
                        background-color: transparent;
                        color: #FFFFFF;
                    }
                """)
            self.table.setCellWidget(row, 0, empty)
            return

        emoji = QLabel("💥")
        emoji.setAlignment(Qt.AlignCenter)
        emoji.setStyleSheet("""
                QLabel {
                    background-color: transparent;
                    color: #FFFFFF;
                    font-family: "Segoe UI Emoji";
                    font-size: 14pt;
                    padding: 0px;
                    margin: 0px;
                }
            """)

        self.table.setCellWidget(row, 0, emoji)

    def on_cell_double_clicked(self, row, col):
        item = self.table.item(row, col)

        if not item:
            return

        # Double click on Pilot column -> open pilot zKill
        if col == 1:
            character_id = item.data(Qt.UserRole)

            if character_id:
                webbrowser.open(f"https://zkillboard.com/character/{character_id}/")
                self.status_label.setText("Status: opened pilot zKill")
            else:
                self.status_label.setText("Status: no character id")

            return

        # Double click on Top Ships column -> open first ship zKill page
        if col == 5:
            top_ships = item.data(Qt.UserRole)

            if not top_ships:
                self.status_label.setText("Status: no top ships data")
                return

            first_ship = top_ships[0]
            ship_type_id = first_ship.get("ship_type_id")
            ship_name = first_ship.get("name", "ship")

            if ship_type_id:
                webbrowser.open(f"https://zkillboard.com/ship/{ship_type_id}/")
                self.status_label.setText(
                    f"Status: opened zKill ship page: {ship_name}"
                )
            else:
                self.status_label.setText("Status: no ship id")

            return
