from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QPainter
from PySide6.QtWidgets import QTableWidgetItem, QWidget

from worker import CynoWorker
from paths import icon_path


CYNO_ICON_PATH = icon_path("cyno.png")
BEAR_ICON_PATH = icon_path("bear.png")
SKULL_ICON_PATH = icon_path("skull.png")

ICON_SIZE = 12


class CenteredPixmapWidget(QWidget):
    def __init__(self, icon_path, icon_size=ICON_SIZE, parent=None):
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
        y = (self.height() - scaled.height()) // 2 + 1

        y = max(0, y)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(x, y, scaled)



def safe_int(value):
    try:
        return int(str(value).replace(" ", "").strip())
    except Exception:
        return 0


def get_row_color(danger: int):
    return QColor(0, 0, 0, 0)


def get_danger_icon_path(danger: int):
    if 0 < danger <= 50:
        return BEAR_ICON_PATH

    if danger >= 80:
        return SKULL_ICON_PATH

    return None


def format_top_ships(top_ships):
    ship_names = []

    for ship in top_ships:
        name = ship.get("display_name") or ship.get("name", "?")
        ship_names.append(name)

    return " | ".join(ship_names) if ship_names else "-"


def prepare_cell_item(window, row, col):
    item = window.table.item(row, col)

    if item is None:
        item = QTableWidgetItem("")
        window.table.setItem(row, col, item)

    item.setText("")
    item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    item.setBackground(window.row_base_colors.get(row, get_row_color(0)))
    item.setForeground(QColor("#FFFFFF"))

    return item


def set_icon_cell(window, row, col, icon_path_value, icon_size=ICON_SIZE):
    window.table.setCellWidget(row, col, None)

    item = prepare_cell_item(window, row, col)

    if not icon_path_value:
        return

    if not Path(icon_path_value).exists():
        print("Icon not found:", icon_path_value)
        return

    icon_widget = CenteredPixmapWidget(
        icon_path_value,
        icon_size=icon_size,
    )

    window.table.setCellWidget(row, col, icon_widget)


def set_danger_cell(window, row, danger_value):
    icon_path_value = get_danger_icon_path(danger_value)

    set_icon_cell(
        window,
        row,
        0,
        icon_path_value,
        icon_size=ICON_SIZE,
    )


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

    bg_color = QColor(0, 0, 0, 0)

    for item in items:
        item.setBackground(bg_color)
        item.setForeground(QColor("#FFFFFF"))
        item.setFont(window.table.font())

    items[0].setTextAlignment(Qt.AlignCenter)
    items[1].setTextAlignment(Qt.AlignCenter)
    items[2].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    items[3].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    items[4].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    items[5].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    items[6].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

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
    items[2].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    items[3].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    items[4].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    items[5].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
    items[6].setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

    for col, item in enumerate(items):
        window.table.setItem(row, col, item)

    set_danger_cell(window, row, danger_value)

    clear_cyno_cell(window, row)

    if character_id:
        start_cyno_worker(window, row, character_id)

    window.pending_pilots -= 1

    if window.pending_pilots <= 0:
        window.start_relations_scan()


def clear_cyno_cell(window, row):
    window.table.setCellWidget(row, 1, None)
    prepare_cell_item(window, row, 1)


def start_cyno_worker(window, row, character_id):
    window.table.setCellWidget(row, 1, None)

    item = prepare_cell_item(window, row, 1)
    item.setText("◌")
    item.setForeground(QColor("#FF3366"))

    cyno_worker = CynoWorker(row, character_id)
    cyno_worker.signals.finished.connect(window.update_cyno_cell)
    window.cyno_pool.start(cyno_worker)


def render_cyno_cell(window, row, cyno):
    window.spinner.remove(row)
    window.table.setCellWidget(row, 1, None)

    item = prepare_cell_item(window, row, 1)
    item.setText("")

    if not cyno:
        return

    set_icon_cell(
        window,
        row,
        1,
        CYNO_ICON_PATH,
        icon_size=ICON_SIZE,
    )