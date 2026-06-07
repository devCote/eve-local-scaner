from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QTableWidgetItem

from worker import CynoWorker


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

    for item in items:
        item.setBackground(QColor(26, 29, 33, 220))
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

    window.table.setCellWidget(row, 1, None)

    if character_id:
        start_cyno_worker(window, row, character_id)

    window.pending_pilots -= 1

    if window.pending_pilots <= 0:
        window.start_relations_scan()


def start_cyno_worker(window, row, character_id):
    cyno_loading = QLabel(window.spinner.current_frame())
    cyno_loading.setAlignment(Qt.AlignCenter)
    cyno_loading.setStyleSheet("""
        QLabel {
            background-color: transparent;
            color: #FF9900;
            font-size: 11pt;
            font-weight: bold;
        }
    """)

    window.spinner.add(row, cyno_loading)
    window.table.setCellWidget(row, 1, cyno_loading)

    cyno_worker = CynoWorker(row, character_id)
    cyno_worker.signals.finished.connect(window.update_cyno_cell)
    window.cyno_pool.start(cyno_worker)


def render_cyno_cell(window, row, cyno):
    window.spinner.remove(row)
    window.table.setCellWidget(row, 1, None)

    if not cyno:
        empty = QLabel("")
        empty.setAlignment(Qt.AlignCenter)
        empty.setStyleSheet("background-color: transparent;")
        window.table.setCellWidget(row, 1, empty)
        return

    emoji = QLabel("📡")
    emoji.setAlignment(Qt.AlignCenter)
    emoji.setStyleSheet("""
        QLabel {
            background-color: transparent;
            color: #FFFFFF;
            font-family: "Segoe UI Emoji";
            font-size: 12pt;
            padding: 0px;
            margin: 0px;
        }
    """)

    window.table.setCellWidget(row, 1, emoji)
