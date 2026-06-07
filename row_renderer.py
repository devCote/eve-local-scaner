from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QPainter
from PySide6.QtWidgets import QLabel, QTableWidgetItem, QWidget

from worker import CynoWorker
from paths import icon_path


CYNO_ICON_PATH = icon_path("cyno.png")


class CenteredPixmapWidget(QWidget):
    def __init__(self, icon_path, icon_size=15, parent=None):
        super().__init__(parent)

        self.icon_path = icon_path
        self.icon_size = icon_size
        self.pixmap = QPixmap(icon_path)

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background-color: transparent;")

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.pixmap.isNull():
            return

        scaled = self.pixmap.scaled(
            self.icon_size,
            self.icon_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(x, y, scaled)


def safe_int(value):
    try:
        return int(str(value).replace(" ", "").strip())
    except Exception:
        return 0


def get_row_color(danger: int):
    return QColor(26, 29, 33, 220)


def get_danger_emoji(danger: int):
    if danger < 40:
        return "🐻"

    if danger >= 80:
        return "☠️"

    if danger > 60:
        return "💪🏼"

    return ""


def format_top_ships(top_ships):
    ship_names = []

    for ship in top_ships:
        name = ship.get("name", "?")
        ship_names.append(name)

    return " | ".join(ship_names) if ship_names else "-"


def set_emoji_cell(window, row, col, emoji):
    window.table.setCellWidget(row, col, None)

    item = window.table.item(row, col)

    if item is None:
        item = QTableWidgetItem("")
        window.table.setItem(row, col, item)

    item.setText("")
    item.setTextAlignment(Qt.AlignCenter)
    item.setBackground(window.row_base_colors.get(row, get_row_color(0)))
    item.setForeground(QColor("#FFFFFF"))

    if not emoji:
        return

    label = QLabel(emoji)
    label.setAlignment(Qt.AlignCenter)
    label.setStyleSheet("""
        QLabel {
            background-color: transparent;
            color: #FFFFFF;
            font-family: "Segoe UI Emoji";
            font-size: 11pt;
            padding: 0px;
            margin: 0px;
        }
    """)

    window.table.setCellWidget(row, col, label)


def set_loading_row(window, row, pilot):
    items = [
        QTableWidgetItem(""),
        QTableWidgetItem(""),
        QTableWidgetItem(pilot),
        QTableWidgetItem("..."),
        QTableWidgetItem("..."),
        QTableWidgetItem("loading"),
        QTableWidgetItem("loading..."),
    ]

    bg_color = QColor(26, 29, 33, 220)

    for item in items:
        item.setBackground(bg_color)
        item.setForeground(QColor("#FFFFFF"))
        item.setFont(window.table.font())

    items[0].setTextAlignment(Qt.AlignCenter)
    items[1].setTextAlignment(Qt.AlignCenter)
    items[3].setTextAlignment(Qt.AlignCenter)
    items[4].setTextAlignment(Qt.AlignCenter)
    items[5].setTextAlignment(Qt.AlignCenter)

    for col, item in enumerate(items):
        window.table.setItem(row, col, item)

    window.table.setCellWidget(row, 0, None)
    window.table.setCellWidget(row, 1, None)


def render_pilot_row(window, row, result):
    danger_value = safe_int(result.get("danger", 0))
    gang_value = safe_int(result.get("gang", 0))

    ally = result.get("ally", "?")
    pilot = result.get("pilot", "")
    top_ships = result.get("top_ships", [])
    top_ships_text = format_top_ships(top_ships)

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

    bg_color = get_row_color(danger_value)
    window.row_base_colors[row] = bg_color

    if character_id:
        window.row_character_ids[row] = character_id

    for item in items:
        item.setBackground(bg_color)
        item.setForeground(QColor("#FFFFFF"))
        item.setFont(window.table.font())

    items[0].setTextAlignment(Qt.AlignCenter)
    items[1].setTextAlignment(Qt.AlignCenter)
    items[3].setTextAlignment(Qt.AlignCenter)
    items[4].setTextAlignment(Qt.AlignCenter)
    items[5].setTextAlignment(Qt.AlignCenter)

    for col, item in enumerate(items):
        window.table.setItem(row, col, item)

    set_emoji_cell(
        window,
        row,
        0,
        get_danger_emoji(danger_value),
    )

    clear_cyno_cell(window, row)

    if character_id:
        start_cyno_worker(window, row, character_id)

    window.pending_pilots -= 1

    if window.pending_pilots <= 0:
        window.start_relations_scan()


def clear_cyno_cell(window, row):
    window.table.setCellWidget(row, 1, None)

    item = window.table.item(row, 1)

    if item is None:
        item = QTableWidgetItem("")
        window.table.setItem(row, 1, item)

    item.setText("")
    item.setTextAlignment(Qt.AlignCenter)
    item.setBackground(window.row_base_colors.get(row, get_row_color(0)))
    item.setForeground(QColor("#FFFFFF"))


def start_cyno_worker(window, row, character_id):
    window.table.setCellWidget(row, 1, None)

    item = window.table.item(row, 1)

    if item is None:
        item = QTableWidgetItem("")
        window.table.setItem(row, 1, item)

    item.setText("◌")
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QColor("#FF3366"))
    item.setBackground(window.row_base_colors.get(row, get_row_color(0)))

    cyno_worker = CynoWorker(row, character_id)
    cyno_worker.signals.finished.connect(window.update_cyno_cell)
    window.cyno_pool.start(cyno_worker)


def render_cyno_cell(window, row, cyno):
    window.spinner.remove(row)
    window.table.setCellWidget(row, 1, None)

    item = window.table.item(row, 1)

    if item is None:
        item = QTableWidgetItem("")
        window.table.setItem(row, 1, item)

    item.setText("")
    item.setTextAlignment(Qt.AlignCenter)
    item.setForeground(QColor("#FFFFFF"))
    item.setBackground(window.row_base_colors.get(row, get_row_color(0)))

    if not cyno:
        return

    if not Path(CYNO_ICON_PATH).exists():
        item.setText("*")
        item.setForeground(QColor("#FF3366"))
        print("Cyno icon not found:", CYNO_ICON_PATH)
        return

    icon_widget = CenteredPixmapWidget(
        CYNO_ICON_PATH,
        icon_size=15,
    )

    window.table.setCellWidget(row, 1, icon_widget)
