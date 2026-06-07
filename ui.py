import webbrowser
import pyperclip

from PySide6.QtCore import Qt, QThreadPool, QTimer, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QSizeGrip,
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
from relations import RelationWorker


class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        self.parent_window = parent

        self.setObjectName("TitleBar")
        self.setFixedHeight(32)

        layout = QHBoxLayout()
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self.title = QLabel("EVE LOCAL INTEL SCANNER")
        self.title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.title.setStyleSheet("""
            QLabel {
                color: #FF9900;
                font-weight: bold;
                letter-spacing: 2px;
                background-color: transparent;
            }
        """)

        self.minimize_button = QPushButton("—")
        self.maximize_button = QPushButton("□")
        self.close_button = QPushButton("×")

        for button in [
            self.minimize_button,
            self.maximize_button,
            self.close_button,
        ]:
            button.setFixedSize(28, 24)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(30, 34, 40, 180);
                    color: #D0D0D0;
                    border: 1px solid #3A4048;
                    font-weight: bold;
                }

                QPushButton:hover {
                    background-color: #FF9900;
                    color: #000000;
                }
            """)

        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 34, 40, 180);
                color: #D0D0D0;
                border: 1px solid #3A4048;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #AA2222;
                color: #FFFFFF;
            }
        """)

        self.minimize_button.clicked.connect(self.parent_window.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximize)
        self.close_button.clicked.connect(self.parent_window.close)

        layout.addWidget(self.title)
        layout.addStretch()
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        self.setLayout(layout)

        self.setStyleSheet("""
            QWidget#TitleBar {
                background-color: rgba(10, 12, 14, 245);
                border-bottom: 1px solid #FF9900;
            }
        """)

    def toggle_maximize(self):
        if self.parent_window.isMaximized():
            self.parent_window.showNormal()
        else:
            self.parent_window.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.parent_window.windowHandle()

            if window:
                window.startSystemMove()

            event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggle_maximize()
            event.accept()


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Scanner")
        self.resize(900, 650)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(650, 400)

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

        self.build_ui()

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        self.start_clipboard_timer()

    def build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.main_panel = QWidget()
        self.main_panel.setObjectName("MainPanel")
        self.main_panel.setStyleSheet("""
            QWidget#MainPanel {
                background-color: rgba(16, 18, 20, 240);
                border: 1px solid #3A4048;
            }
        """)

        outer_layout.addWidget(self.main_panel)

        layout = QVBoxLayout(self.main_panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)

        self.status_label = QLabel("Status: ready")
        self.status_label.hide()

        controls = QHBoxLayout()

        self.always_on_top = QCheckBox("Always on top")
        self.always_on_top.stateChanged.connect(self.toggle_always_on_top)
        controls.addWidget(self.always_on_top)

        controls.addStretch()

        self.scan_button = QPushButton("Scan Clipboard")
        self.scan_button.clicked.connect(self.scan_clipboard)
        controls.addWidget(self.scan_button)

        layout.addLayout(controls)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["D", "C", "Pilot", "Danger", "Gang", "Corp/Ally", "Top Ships"]
        )

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

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)

        self.table.setMouseTracking(True)
        self.table.viewport().setMouseTracking(True)
        self.table.viewport().setAttribute(Qt.WA_Hover, True)
        self.table.viewport().installEventFilter(self)

        layout.addWidget(self.table)

        self.footer_label = QLabel(
            "Copy local from EVE: Ctrl+A → Ctrl+C | Cyno loads separately"
        )
        self.footer_label.setAlignment(Qt.AlignCenter)
        self.footer_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #B0B0B0;
            }
        """)
        layout.addWidget(self.footer_label)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)
        bottom_bar.addStretch()

        self.size_grip = QSizeGrip(self.main_panel)
        self.size_grip.setFixedSize(18, 18)
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

    def toggle_always_on_top(self):
        checked = self.always_on_top.isChecked()

        flags = Qt.Window | Qt.FramelessWindowHint

        if checked:
            flags |= Qt.WindowStaysOnTopHint
            flags |= Qt.Tool

        self.setWindowFlags(flags)
        self.show()
        self.raise_()
        self.activateWindow()

        if checked:
            self.status_label.setText("Status: always on top enabled")
        else:
            self.status_label.setText("Status: always on top disabled")

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
        return QColor(26, 29, 33, 220)

    def get_danger_emoji(self, danger: int):
        if danger < 40:
            return "🐻"
        if danger >= 80:
            return "☠️"
        if danger > 60:
            return "💪🏼"
        return ""

    def set_emoji_cell(self, row, col, emoji):
        self.table.setCellWidget(row, col, None)

        if not emoji:
            return

        label = QLabel(emoji)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #FFFFFF;
                font-family: "Segoe UI Emoji";
                font-size: 12pt;
                padding: 0px;
                margin: 0px;
            }
        """)

        self.table.setCellWidget(row, col, label)

    def set_loading_row(self, row, pilot):
        items = [
            QTableWidgetItem(""),
            QTableWidgetItem(""),
            QTableWidgetItem(pilot),
            QTableWidgetItem("..."),
            QTableWidgetItem("..."),
            QTableWidgetItem("loading"),
            QTableWidgetItem("loading..."),
        ]

        for item in items:
            item.setBackground(QColor(26, 29, 33, 220))
            item.setForeground(QColor("#FFFFFF"))
            item.setFont(self.table.font())

        items[0].setTextAlignment(Qt.AlignCenter)
        items[1].setTextAlignment(Qt.AlignCenter)
        items[3].setTextAlignment(Qt.AlignCenter)
        items[4].setTextAlignment(Qt.AlignCenter)
        items[5].setTextAlignment(Qt.AlignCenter)

        for col, item in enumerate(items):
            self.table.setItem(row, col, item)

        self.table.setCellWidget(row, 0, None)
        self.table.setCellWidget(row, 1, None)

    def update_table(self, pilots):
        self.table.setRowCount(len(pilots))
        self.status_label.setText(f"Status: loading pilots fast: {len(pilots)}")

        self.relations = {}
        self.row_character_ids = {}
        self.row_base_colors = {}
        self.pending_pilots = len(pilots)

        self.relations_running = False
        self.active_relation_workers.clear()

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
            QTableWidgetItem(""),
            QTableWidgetItem(pilot),
            QTableWidgetItem(str(danger_value)),
            QTableWidgetItem(str(gang_value)),
            QTableWidgetItem(ally),
            QTableWidgetItem(top_ships_text),
        ]

        character_id = result.get("character_id")

        items[2].setData(Qt.UserRole, character_id)
        items[6].setData(Qt.UserRole, top_ships)

        bg_color = self.get_row_color(danger_value)

        self.row_base_colors[row] = bg_color

        if character_id:
            self.row_character_ids[row] = character_id

        for item in items:
            item.setBackground(bg_color)
            item.setForeground(QColor("#FFFFFF"))
            item.setFont(self.table.font())

        items[0].setTextAlignment(Qt.AlignCenter)
        items[1].setTextAlignment(Qt.AlignCenter)
        items[3].setTextAlignment(Qt.AlignCenter)
        items[4].setTextAlignment(Qt.AlignCenter)
        items[5].setTextAlignment(Qt.AlignCenter)

        for col, item in enumerate(items):
            self.table.setItem(row, col, item)

        danger_emoji = self.get_danger_emoji(danger_value)
        self.set_emoji_cell(row, 0, danger_emoji)

        self.table.setCellWidget(row, 1, None)

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
            self.table.setCellWidget(row, 1, cyno_loading)

            cyno_worker = CynoWorker(row, character_id)
            cyno_worker.signals.finished.connect(self.update_cyno_cell)
            self.cyno_pool.start(cyno_worker)

        self.pending_pilots -= 1

        if self.pending_pilots <= 0:
            self.start_relations_scan()

        self.status_label.setText("Status: fast data updated, cyno loading...")

    def update_cyno_cell(self, row, cyno):
        self.spinner.remove(row)
        self.table.setCellWidget(row, 1, None)

        if not cyno:
            empty = QLabel("")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("background-color: transparent;")
            self.table.setCellWidget(row, 1, empty)
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

        self.table.setCellWidget(row, 1, emoji)

    def start_relations_scan(self):
        if self.relations_running:
            return

        if len(self.row_character_ids) < 2:
            self.status_label.setText("Status: not enough pilots for relations")
            return

        ids = sorted(self.row_character_ids.values())
        relations_key = ",".join(str(x) for x in ids)

        if relations_key == self.last_relations_key and self.relations:
            self.status_label.setText("Status: relations already loaded")
            return

        self.last_relations_key = relations_key
        self.relations_running = True

        self.status_label.setText("Status: scanning pilot relations...")

        worker = RelationWorker(dict(self.row_character_ids))
        worker.signals.finished.connect(self.update_relations)

        self.active_relation_workers.append(worker)
        self.relations_pool.start(worker)

    def update_relations(self, relations):
        self.relations_running = False
        self.active_relation_workers.clear()

        self.relations = relations or {}

        links = sum(len(v) for v in self.relations.values())

        self.status_label.setText(f"Status: relations updated ({links} links)")

    def clear_relation_highlight(self):
        for row, bg_color in self.row_base_colors.items():
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)

                if item:
                    item.setBackground(bg_color)

    def highlight_relation_rows(self, row):
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

    def get_resize_edges(self, pos):
        edges = Qt.Edges()

        x = pos.x()
        y = pos.y()
        w = self.width()
        h = self.height()
        m = self.resize_margin

        if x <= m:
            edges |= Qt.LeftEdge

        if x >= w - m:
            edges |= Qt.RightEdge

        if y <= m:
            edges |= Qt.TopEdge

        if y >= h - m:
            edges |= Qt.BottomEdge

        return edges

    def update_resize_cursor(self, edges):
        if not edges:
            self.unsetCursor()
            return

        left = bool(edges & Qt.LeftEdge)
        right = bool(edges & Qt.RightEdge)
        top = bool(edges & Qt.TopEdge)
        bottom = bool(edges & Qt.BottomEdge)

        if (left and top) or (right and bottom):
            self.setCursor(Qt.SizeFDiagCursor)
        elif (right and top) or (left and bottom):
            self.setCursor(Qt.SizeBDiagCursor)
        elif left or right:
            self.setCursor(Qt.SizeHorCursor)
        elif top or bottom:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.unsetCursor()

    def eventFilter(self, obj, event):
        # Hover relations over table
        if obj == self.table.viewport():
            if event.type() == QEvent.MouseMove:
                index = self.table.indexAt(event.pos())

                if index.isValid():
                    self.highlight_relation_rows(index.row())

            elif event.type() == QEvent.Leave:
                self.clear_relation_highlight()

        # Resize frameless window from edges
        if isinstance(obj, QWidget) and obj.window() == self:
            if event.type() == QEvent.MouseMove:
                if not self.isMaximized():
                    local_pos = event.position().toPoint()
                    window_pos = obj.mapTo(self, local_pos)

                    edges = self.get_resize_edges(window_pos)
                    self.update_resize_cursor(edges)

            elif event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton and not self.isMaximized():
                    local_pos = event.position().toPoint()
                    window_pos = obj.mapTo(self, local_pos)

                    edges = self.get_resize_edges(window_pos)

                    if edges:
                        window = self.windowHandle()

                        if window:
                            window.startSystemResize(edges)
                            return True

            elif event.type() == QEvent.Leave:
                self.unsetCursor()

        return super().eventFilter(obj, event)

    def on_cell_double_clicked(self, row, col):
        item = self.table.item(row, col)

        if not item:
            return

        if col == 2:
            character_id = item.data(Qt.UserRole)

            if character_id:
                webbrowser.open(f"https://zkillboard.com/character/{character_id}/")
                self.status_label.setText("Status: opened pilot zKill")
            else:
                self.status_label.setText("Status: no character id")

            return

        if col == 6:
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

    def closeEvent(self, event):
        self.thread_pool.clear()
        self.cyno_pool.clear()
        self.relations_pool.clear()
        self.active_relation_workers.clear()

        event.accept()
