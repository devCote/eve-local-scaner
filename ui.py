import sys
import shutil
import pyperclip

from PySide6.QtCore import QEvent, Qt, QThreadPool, QTimer, QPoint
from PySide6.QtGui import QColor, QCursor, QFontMetrics
from PySide6.QtWidgets import (
    QApplication,
    QSizeGrip,
    QWidget,
    QVBoxLayout,
    QLabel,
    QTableWidget,
    QHeaderView,
    QAbstractItemView,
    QFrame,
    QStackedWidget,
    QMessageBox,
)

from parser import parse_pilots
from worker import PilotWorker
from spinner import SpinnerManager
from relations import RelationWorker
from title_bar import TitleBar
from intel_table import IntelTable, GeneralHeaderView
from eve_tabs import EveTabs
from zkill_panel import ZkillPanel
from options_panel import OptionsPanel
from user_settings import (
    load_ui_settings,
    save_ui_settings,
    load_window_settings,
    save_window_settings,
    load_general_table_settings,
    save_general_table_settings,
)
from windows_blur import enable_eve_blur
from paths import USER_DATA_DIR
from health_check import collect_health_info

from row_renderer import (
    set_loading_row as render_loading_row,
    render_pilot_row,
    render_cyno_cell,
)

from window_resize import handle_resize_event
from general_table_options import show_general_table_options_dialog
from zkill_fit_popup import FittingPanelPopup
from app_fonts import APP_FONT_FAMILY


class EveLocalScanner(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EVE Local Scanner")
        self.setObjectName("RootWindow")
        self.resize(760, 440)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(250, 200)

        self.resize_margin = 8
        self._window_drag_active = False
        self._window_drag_offset = QPoint()

        self.user_settings = load_ui_settings()
        self.window_settings = load_window_settings()
        self.general_table_settings = load_general_table_settings()
        self._loading_window_geometry = False
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.timeout.connect(self.save_current_window_geometry)
        self._loading_general_column_widths = False
        self.ui_transparency = int(self.user_settings["transparency"])
        self.ui_alpha = self.transparency_to_alpha(self.ui_transparency)
        self.ui_blur = int(self.user_settings["blur"])
        self.ui_font_size = max(8, min(11, int(self.user_settings["font_size"])))
        self.ui_compact_zkill = 1 if int(self.user_settings.get("compact_zkill", 0)) else 0
        self.ui_frame_color = self.user_settings["frame_color"]
        self.ui_text_color = self.user_settings["text_color"]
        self.ui_bg_color = self.user_settings["bg_color"]


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
        self._loading_window_geometry = True
        self.apply_saved_window_geometry()
        if hasattr(self, "tabs") and hasattr(self.tabs, "update_compact_labels_for_width"):
            self.tabs.update_compact_labels_for_width(self.width(), force=True)
        self._loading_window_geometry = False

        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

        self.start_clipboard_timer()
        QTimer.singleShot(0, self.apply_default_always_on_top)


    def _is_window_drag_area(self, widget) -> bool:
        """Allow dragging from non-interactive empty UI areas.

        This makes the empty area to the right of tabs draggable, while not breaking
        table clicks, browser clicks, buttons, sliders, inputs, etc.
        """
        if widget is None:
            return False

        if widget in (self.main_panel, self.stack):
            return True

        # Top/title/tabs areas should drag.
        current = widget
        while current is not None:
            if current in (getattr(self, "title_bar", None), getattr(self, "tabs", None)):
                return True

            # Never start window drag from these interactive/content areas.
            if current in (
                getattr(self, "table", None),
                getattr(self, "general_page", None),
                getattr(self, "zkill_panel", None),
                getattr(self, "options_panel", None),
            ):
                return False

            current = current.parentWidget() if hasattr(current, "parentWidget") else None

        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            child = self.childAt(event.position().toPoint())

            if self._is_window_drag_area(child):
                self._window_drag_active = True
                self._window_drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._window_drag_active and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._window_drag_offset)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._window_drag_active = False
        super().mouseReleaseEvent(event)



    def show_health_check(self):
        try:
            text = collect_health_info()

            box = QMessageBox(self)
            box.setWindowTitle("Health Check")
            box.setText(text)
            box.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            box.setIcon(QMessageBox.Information)
            box.exec()

        except Exception as e:
            QMessageBox.warning(self, "Health Check", f"Failed to collect health info:\n{e}")

    def clear_local_data_cache(self):
        reply = QMessageBox.question(
            self,
            "Clear local data/cache",
            "Are you sure you want to delete cache, avatars and logs?\n\n"
            "Database, killmail archives and user settings will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Clear only disposable data:
        #   %LOCALAPPDATA%/EVE Local Intel Scanner/cache.json
        #   %LOCALAPPDATA%/EVE Local Intel Scanner/unavailable_archives.json
        #   %LOCALAPPDATA%/EVE Local Intel Scanner/cache/*
        #   %LOCALAPPDATA%/EVE Local Intel Scanner/avatars/*
        #   %LOCALAPPDATA%/EVE Local Intel Scanner/logs/*
        # Do not touch local_intel.sqlite, killmails/, user.json or window/table settings.
        removed = []

        def remove_file(path):
            try:
                if path.exists() and path.is_file():
                    path.unlink()
                    removed.append(str(path))
            except Exception as e:
                QMessageBox.warning(self, "Clear local data/cache", f"Failed to remove:\n{path}\n\n{e}")
                raise

        def clear_folder(folder):
            try:
                if not folder.exists():
                    return

                for child in folder.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                    removed.append(str(child))
            except Exception as e:
                QMessageBox.warning(self, "Clear local data/cache", f"Failed to clear folder:\n{folder}\n\n{e}")
                raise

        try:
            for name in ("cache.json", "unavailable_archives.json"):
                remove_file(USER_DATA_DIR / name)

            for folder_name in ("cache", "avatars", "logs"):
                clear_folder(USER_DATA_DIR / folder_name)

        except Exception:
            return

        if removed:
            QMessageBox.information(
                self,
                "Clear local data/cache",
                "Removed:\n" + "\n".join(removed[:80]) + ("\n..." if len(removed) > 80 else ""),
            )
        else:
            QMessageBox.information(
                self,
                "Clear local data/cache",
                "No cache/avatar/log files found.",
            )

    def apply_saved_window_geometry(self):
        settings = getattr(self, "window_settings", {}) or {}

        width = int(settings.get("width") or 760)
        height = int(settings.get("height") or 440)
        x = settings.get("x")
        y = settings.get("y")

        width = max(self.minimumWidth(), width)
        height = max(self.minimumHeight(), height)

        if x is None or y is None:
            self.resize(width, height)
            return

        try:
            self.setGeometry(int(x), int(y), width, height)
        except Exception:
            self.resize(width, height)

    def save_current_window_geometry(self):
        geo = self.geometry()

        save_window_settings(
            {
                "x": int(geo.x()),
                "y": int(geo.y()),
                "width": int(geo.width()),
                "height": int(geo.height()),
            }
        )

    def transparency_to_alpha(self, transparency):
        transparency = max(0, min(100, int(transparency)))

        # At 100% transparency a Qt rgba alpha of 0 makes the whole panel fully
        # invisible and can look broken. Keep 100% visually equal to 99%: almost
        # fully transparent, but still rendered and draggable/readable by blur.
        if transparency >= 99:
            transparency = 99

        return int(round(255 * (100 - transparency) / 100))

    def build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.main_panel = QFrame()
        self.main_panel.setObjectName("MainPanel")
        self.main_panel.setAttribute(Qt.WA_StyledBackground, True)

        outer_layout.addWidget(self.main_panel)

        layout = QVBoxLayout(self.main_panel)
        # Slightly tighter inner frame so the outside border feels thinner/cleaner.
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.title_bar = TitleBar(self)
        self.title_bar.top_button.blockSignals(True)
        self.title_bar.top_button.setChecked(True)
        self.title_bar.top_button.blockSignals(False)
        layout.addWidget(self.title_bar)

        self.tabs = EveTabs(self)
        self.tabs.tabChanged.connect(self.switch_tab)
        self.tabs.zkillModeChanged.connect(self.switch_zkill_mode)
        self.title_bar.set_tabs_widget(self.tabs)

        self.stack = QStackedWidget()
        self.stack.setObjectName("MainStack")
        self.stack.setAttribute(Qt.WA_StyledBackground, True)
        layout.addWidget(self.stack, 1)

        self.general_page = QWidget()
        self.general_page.setObjectName("GeneralPage")
        self.general_page.setAttribute(Qt.WA_StyledBackground, True)
        general_layout = QVBoxLayout(self.general_page)
        general_layout.setContentsMargins(0, 0, 0, 0)
        general_layout.setSpacing(0)

        self.status_label = QLabel("Status: ready")
        self.status_label.hide()

        self.table = IntelTable()
        self.setup_table()

        general_layout.addWidget(self.table, 1)

        self.zkill_panel = ZkillPanel(self)
        self.general_fit_popup = FittingPanelPopup(self)
        self.options_panel = OptionsPanel(self)
        self.options_panel.setObjectName("OptionsPage")
        self.options_panel.setAttribute(Qt.WA_StyledBackground, True)
        self.options_panel.settingsChanged.connect(self.apply_ui_settings)
        self.options_panel.healthCheckRequested.connect(self.show_health_check)
        self.options_panel.clearDataRequested.connect(self.clear_local_data_cache)
        self.options_panel.generalTableRequested.connect(self.show_general_table_options)
        self.options_panel.set_values(
            self.ui_transparency,
            self.ui_blur,
            self.ui_font_size,
            self.ui_compact_zkill,
            self.ui_frame_color,
            self.ui_text_color,
            self.ui_bg_color,
            emit=False,
        )

        self.stack.addWidget(self.general_page)
        self.stack.addWidget(self.zkill_panel)
        self.stack.addWidget(self.options_panel)

        # Custom border resizing is handled by window_resize.py.
        # Do not reserve a bottom row for QSizeGrip: it creates an ugly
        # permanent bottom gap, especially in the zKill tab.
        self.size_grip = QSizeGrip(self.main_panel)
        self.size_grip.setFixedSize(1, 1)
        self.size_grip.hide()

        self.apply_ui_settings(
            self.ui_transparency,
            self.ui_blur,
            self.ui_font_size,
            self.ui_compact_zkill,
            self.ui_frame_color,
            self.ui_text_color,
            self.ui_bg_color,
            persist=False,
        )

    def setup_table(self):
        self.table.setColumnCount(7)
        self.table.setHorizontalHeader(GeneralHeaderView(Qt.Horizontal, self.table))
        self.table.setHorizontalHeaderLabels(
            ["", "", "Name", "Danger", "Gang", "Corp/Ally", "Last Ships"]
        )

        for col in (2, 3, 4, 5, 6):
            header_item = self.table.horizontalHeaderItem(col)
            if header_item:
                header_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setMinimumSectionSize(6)
        self.table.horizontalHeader().setDefaultSectionSize(24)

        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setGridStyle(Qt.NoPen)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setAttribute(Qt.WA_StyledBackground, True)
        self.table.setAutoFillBackground(False)
        self.table.viewport().setAutoFillBackground(False)

        self.table.rowHovered.connect(self.on_table_row_hovered)
        self.table.mouseLeft.connect(self.on_table_mouse_left)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)

        self.table.setColumnWidth(0, 18)
        self.table.setColumnWidth(1, 14)

        header = self.table.horizontalHeader()
        header.setSectionsMovable(False)
        # Keep the last visible column filling all remaining window space.
        # User can still drag the previous separators; the last column expands
        # automatically instead of leaving an empty gap on the right.
        header.setStretchLastSection(True)
        self.table.horizontalScrollBar().setValue(0)

        for col in (2, 3, 4, 5, 6):
            header.setSectionResizeMode(col, QHeaderView.Interactive)

        # Initial widths. After this, user can drag every separator manually.
        self.apply_general_column_widths()
        self.apply_general_column_visibility()
        header.sectionResized.connect(self.on_general_column_resized)

        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setMinimumSectionSize(18)
        self.table.verticalHeader().setDefaultSectionSize(22)

    def apply_general_column_widths(self):
        self._loading_general_column_widths = True

        try:
            widths = (self.general_table_settings or {}).get("column_widths", {})

            defaults = {
                "2": 120,
                "3": 64,
                "4": 54,
                "5": 86,
                "6": 190,
            }

            for col_key, default_width in defaults.items():
                col = int(col_key)
                width = int(widths.get(col_key, default_width))
                self.table.setColumnWidth(col, max(6, width))

        finally:
            self._loading_general_column_widths = False
            self._reset_general_horizontal_offset()

    def get_general_visible_columns(self):
        visible = (self.general_table_settings or {}).get("visible_columns", {})
        defaults = {
            "3": True,
            "4": True,
            "5": True,
            "6": True,
        }
        return {
            key: bool(visible.get(key, default))
            for key, default in defaults.items()
        }

    def apply_general_column_visibility(self):
        visible = self.get_general_visible_columns()
        for col_key, is_visible in visible.items():
            self.table.setColumnHidden(int(col_key), not bool(is_visible))
        self._reset_general_horizontal_offset()
        self.table.viewport().update()
        self.table.horizontalHeader().viewport().update()

    def save_general_column_visibility(self, visible_columns: dict):
        current = dict(self.general_table_settings or {})
        current["visible_columns"] = {
            str(col): bool(visible_columns.get(str(col), True))
            for col in ("3", "4", "5", "6")
        }
        current["column_widths"] = current.get("column_widths") or self.get_general_column_widths()
        self.general_table_settings = current
        save_general_table_settings(self.general_table_settings)
        self.apply_general_column_visibility()

    def show_general_table_options(self):
        result = show_general_table_options_dialog(
            self,
            self.get_general_visible_columns(),
            font_size=self.ui_font_size,
            text_color=self.ui_text_color,
            frame_color=self.ui_frame_color,
        )
        if result is not None:
            self.save_general_column_visibility(result)

    def get_general_column_widths(self):
        return {
            str(col): int(self.table.columnWidth(col))
            for col in (2, 3, 4, 5, 6)
        }

    def save_general_column_widths(self):
        if getattr(self, "_loading_general_column_widths", False):
            return

        if not hasattr(self, "table"):
            return

        self.general_table_settings = {
            "column_widths": self.get_general_column_widths(),
            "visible_columns": self.get_general_visible_columns(),
        }
        save_general_table_settings(self.general_table_settings)

    def on_general_column_resized(self, logical_index, old_size, new_size):
        if logical_index not in (2, 3, 4, 5, 6):
            return

        # Save after the resize event is fully processed. This keeps user.json
        # stable and avoids fighting Qt while the user drags the separator.
        QTimer.singleShot(0, self.save_general_column_widths)

    def apply_ui_settings(
        self,
        transparency,
        blur=0,
        font_size=10,
        compact_zkill=0,
        frame_color="#161616",
        text_color="#d6d6d6",
        bg_color="#0b0b0b",
        persist=True,
    ):
        self.ui_transparency = max(0, min(100, int(transparency)))
        self.ui_alpha = self.transparency_to_alpha(self.ui_transparency)
        self.ui_blur = 1 if int(blur) else 0
        self.ui_font_size = max(8, min(11, int(font_size)))
        self.ui_compact_zkill = 1 if int(compact_zkill) else 0
        self.ui_frame_color = str(frame_color).lower()
        self.ui_text_color = str(text_color).lower()
        self.ui_bg_color = str(bg_color).lower()

        if persist:
            save_ui_settings(
                {
                    "transparency": self.ui_transparency,
                    "blur": self.ui_blur,
                    "font_size": self.ui_font_size,
                    "compact_zkill": self.ui_compact_zkill,
                    "frame_color": self.ui_frame_color,
                    "text_color": self.ui_text_color,
                    "bg_color": self.ui_bg_color,
                }
            )

        bg = QColor(self.ui_bg_color)
        frame = QColor(self.ui_frame_color)
        frame_alpha = 165

        self.setStyleSheet("""
            QWidget#RootWindow {
                background: transparent;
            }
        """)

        self.main_panel.setStyleSheet(f"""
            QFrame#MainPanel {{
                background-color: rgba({bg.red()}, {bg.green()}, {bg.blue()}, {self.ui_alpha});
                border: 1px solid rgba({frame.red()}, {frame.green()}, {frame.blue()}, {frame_alpha});
                border-radius: 7px;
            }}

            QStackedWidget#MainStack,
            QWidget#GeneralPage,
            QWidget#OptionsPage {{
                background-color: transparent;
                border: none;
            }}
        """)

        table_alpha = max(40, min(255, self.ui_alpha - 20))
        header_alpha = max(80, min(255, self.ui_alpha + 25))

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent;
                background-color: transparent;
                border: none;
                gridline-color: transparent;
                color: {self.ui_text_color};
                font-family: '{APP_FONT_FAMILY}'; font-size: {self.ui_font_size}pt;
                outline: none;
                selection-background-color: rgba(57, 199, 181, 85);
            }}

            QTableWidget::viewport {{
                background: transparent;
                background-color: transparent;
            }}

            QTableWidget::item {{
                background: transparent;
                border: none;
                padding: 0px 3px;
                color: {self.ui_text_color};
                font-family: '{APP_FONT_FAMILY}'; font-size: {self.ui_font_size}pt;
            }}

            QTableWidget::item:selected {{
                background: rgba(57, 199, 181, 85);
            }}

            QHeaderView {{
                background: transparent;
                border: none;
            }}

            QHeaderView::section {{
                background: transparent;
                background-color: transparent;
                color: {self.ui_text_color};
                border: none;
                border-bottom: none;
                padding: 1px 3px;
                font-family: '{APP_FONT_FAMILY}'; font-size: {self.ui_font_size}pt;
                font-weight: normal;
            }}

            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0px;
            }}

            QScrollBar::handle:vertical {{
                background: rgba(120, 130, 145, 95);
                min-height: 20px;
                border-radius: 3px;
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                width: 0px;
                background: transparent;
            }}

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
            }}

            QScrollBar:horizontal {{
                height: 0px;
                background: transparent;
            }}

            QScrollBar::handle:horizontal {{
                height: 0px;
                background: transparent;
            }}
        """)

        self.tabs.apply_colors(
            self.ui_bg_color,
            self.ui_frame_color,
            self.ui_text_color,
            self.ui_font_size,
        )

        if hasattr(self, "zkill_panel"):
            self.zkill_panel.apply_ui_settings(
                font_size=self.ui_font_size,
                text_color=self.ui_text_color,
                frame_color=self.ui_frame_color,
                compact_zkill=self.ui_compact_zkill,
            )

        self.title_bar.title.setStyleSheet(f"""
            QLabel {{
                color: {self.ui_text_color};
                font-family: '{APP_FONT_FAMILY}'; font-size: {self.ui_font_size}pt;
                font-weight: normal;
                background-color: transparent;
            }}
        """)

        self.apply_font_size(self.ui_font_size)
        self.update_existing_table_text_color(self.ui_text_color)
        self.apply_window_blur()

    def apply_font_size(self, font_size):
        font = self.font()
        font.setFamily(APP_FONT_FAMILY)
        font.setPointSize(int(font_size))
        self.setFont(font)

        app = QApplication.instance()
        if app:
            app_font = app.font()
            app_font.setFamily(APP_FONT_FAMILY)
            app_font.setPointSize(int(font_size))
            app.setFont(app_font)

        for widget in self.findChildren(QWidget):
            widget_font = widget.font()
            widget_font.setFamily(APP_FONT_FAMILY)
            widget_font.setPointSize(int(font_size))
            widget.setFont(widget_font)

        self.update_table_item_fonts(font_size)
        self.update_table_row_metrics()

        if hasattr(self, "zkill_panel"):
            self.zkill_panel.apply_ui_settings(
                font_size=int(font_size),
                text_color=getattr(self, "ui_text_color", "#d6d6d6"),
            )


    def update_table_row_metrics(self):
        metrics = QFontMetrics(self.table.font())
        row_height = max(18, metrics.height() + 4)
        header_height = max(20, metrics.height() + 6)

        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setMinimumSectionSize(row_height)
        self.table.verticalHeader().setDefaultSectionSize(row_height)
        self.table.horizontalHeader().setFixedHeight(header_height)

        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, row_height)


    def update_table_item_fonts(self, font_size):
        font = self.table.font()
        font.setFamily(APP_FONT_FAMILY)
        font.setPointSize(int(font_size))

        self.table.setFont(font)
        self.table.viewport().setFont(font)
        self.table.horizontalHeader().setFont(font)
        self.table.verticalHeader().setFont(font)

        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)

                if item is not None:
                    item.setFont(font)

                cell_widget = self.table.cellWidget(row, col)
                if cell_widget is not None:
                    cell_widget.setFont(font)

        self.update_table_row_metrics()
        self.table.viewport().update()
        header = self.table.horizontalHeader()
        if hasattr(header, "set_separator_color"):
            header.set_separator_color(self.ui_frame_color)
        self.table.horizontalHeader().update()

    def bg_rgb(self):
        color = QColor(self.ui_bg_color)
        return (color.red(), color.green(), color.blue())

    def apply_window_blur(self):
        try:
            enable_eve_blur(
                int(self.winId()),
                panel_alpha=self.ui_alpha,
                blur_percent=self.ui_blur,
                rgb=self.bg_rgb(),
            )
        except Exception as e:
            print("Blur apply error:", e)

    def reapply_current_ui_settings(self):
        try:
            self.apply_ui_settings(
                self.ui_transparency,
                self.ui_blur,
                self.ui_font_size,
                self.ui_compact_zkill,
                self.ui_frame_color,
                self.ui_text_color,
                self.ui_bg_color,
                persist=False,
            )

            if hasattr(self, "options_panel"):
                self.options_panel.apply_local_style()
                self.options_panel.update()

            self.update()
            self.main_panel.update()

        except Exception as e:
            print("Startup UI reapply error:", e)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.reapply_current_ui_settings)
        QTimer.singleShot(80, self.reapply_current_ui_settings)
        QTimer.singleShot(250, self.reapply_current_ui_settings)

    def update_existing_table_text_color(self, text_color):
        color = QColor(text_color)

        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)

                if item:
                    item.setForeground(color)

        self.table.viewport().update()


    def switch_tab(self, name):
        if name != "Zkill" and hasattr(self, "zkill_panel"):
            self.zkill_panel.close_fit_popup()

        if name != "General" and hasattr(self, "general_fit_popup"):
            self.general_fit_popup.hide_panel(force=True)

        if name == "General":
            self.stack.setCurrentWidget(self.general_page)
            return

        if name == "Zkill":
            self.stack.setCurrentWidget(self.zkill_panel)
            return

        if name == "Options":
            self.stack.setCurrentWidget(self.options_panel)
            return

    def switch_zkill_mode(self, mode):
        if hasattr(self, "zkill_panel"):
            self.zkill_panel.set_mode(mode)


    def schedule_window_geometry_save(self):
        if getattr(self, "_loading_window_geometry", False):
            return

        if not self.isVisible():
            return

        if hasattr(self, "_geometry_save_timer"):
            self._geometry_save_timer.start(250)

    def _reset_general_horizontal_offset(self):
        """Keep General table anchored to the left when the window is narrow."""
        try:
            if hasattr(self, "table") and self.table:
                self.table.horizontalScrollBar().setValue(0)
                self.table.viewport().update()
        except Exception:
            pass

    def _reposition_visible_fit_popups(self):
        try:
            if hasattr(self, "general_fit_popup") and self.general_fit_popup:
                self.general_fit_popup.follow_owner_position()
        except Exception:
            pass

        try:
            if hasattr(self, "zkill_panel") and self.zkill_panel:
                self.zkill_panel.reposition_fit_popup()
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reset_general_horizontal_offset()
        if hasattr(self, "tabs") and hasattr(self.tabs, "update_compact_labels_for_width"):
            self.tabs.update_compact_labels_for_width(self.width(), force=True)
        self._reposition_visible_fit_popups()
        self.schedule_window_geometry_save()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._reposition_visible_fit_popups()
        self.schedule_window_geometry_save()

    def start_clipboard_timer(self):
        """Watch clipboard changes without polling every 700ms.

        QApplication.clipboard().dataChanged is emitted when the user copies
        text with Ctrl+C in EVE/Windows. We debounce a little because clipboard
        data can arrive a few ms after the event.
        """
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.setSingleShot(True)
        self.clipboard_timer.timeout.connect(self.check_clipboard_background)

        clipboard = QApplication.clipboard()
        if clipboard:
            try:
                clipboard.dataChanged.connect(self.schedule_clipboard_check)
            except Exception as exc:
                print("Clipboard signal error:", exc)

    def schedule_clipboard_check(self):
        if hasattr(self, "clipboard_timer"):
            self.clipboard_timer.start(80)

    def read_clipboard_text(self):
        try:
            text = pyperclip.paste()

            if text is None:
                return ""

            return str(text).strip()

        except Exception as e:
            print("Clipboard error:", e)
            return ""

    def is_clipboard_candidate_for_local(self, text: str) -> bool:
        """Return True only for clipboard text that can realistically be EVE local.

        This prevents app-generated EFT fittings / other structured text from
        replacing General. EVE pilot names do not use brackets or most punctuation.
        """
        text = str(text or "")
        if not text.strip():
            return False

        forbidden_chars = set("[]{}<>|=,:;\t")
        if any(ch in forbidden_chars for ch in text):
            return False

        # EFT fits and similar exports usually contain module quantities or
        # section-like lines. Local chat pilot lists should be plain names.
        suspicious_tokens = (
            " x1", " x2", " x3", " x4", " x5",
            "damage:", "destroyed:", "dropped:", "total:",
            "ship:", "location:",
        )
        lowered = text.lower()
        if any(token in lowered for token in suspicious_tokens):
            return False

        # Allow normal EVE name characters: letters, numbers, spaces, apostrophe,
        # hyphen, dot, underscore and newlines.
        for ch in text:
            if ch.isalnum() or ch in " '\n\r-._":
                continue
            return False

        return True

    def check_clipboard_background(self):
        text = self.read_clipboard_text()

        if not text:
            return

        if text == self.last_clipboard_text:
            return

        if not self.is_clipboard_candidate_for_local(text):
            # Mark it as seen so Save Fit / EFT clipboard does not keep being
            # reprocessed every timer tick, but do not update General.
            self.last_clipboard_text = text
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

    def apply_default_always_on_top(self):
        """Always on top is enabled by default on every launch."""
        try:
            if hasattr(self, "title_bar") and hasattr(self.title_bar, "top_button"):
                self.title_bar.top_button.blockSignals(True)
                self.title_bar.top_button.setChecked(True)
                self.title_bar.top_button.blockSignals(False)
            self.force_windows_topmost(True)
        except Exception as exc:
            print("Default topmost error:", exc)

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
        QTimer.singleShot(0, self.apply_window_blur)

    def set_loading_row(self, row, pilot):
        render_loading_row(self, row, pilot)

    def update_table(self, pilots):
        self.table.setRowCount(len(pilots))
        self.update_table_row_metrics()

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
        self.update_table_row_metrics()

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

        # Cyan/teal hover like the active tab accent, not Windows-blue.
        active_color = QColor(57, 199, 181, 85)
        related_color = QColor(57, 199, 181, 38)

        related_rows = self.relations.get(row, [])

        highlight_rows = {
            row: active_color,
        }

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

    def _is_general_table_object(self, obj) -> bool:
        if not hasattr(self, "table") or self.table is None:
            return False

        table = self.table
        return obj in (
            table,
            table.viewport(),
            table.horizontalHeader(),
            table.verticalHeader(),
        )

    def eventFilter(self, obj, event):
        # General Last Ships fit popup: right click / wheel click closes it
        # instead of leaving it pinned on screen.
        if (
            event.type() == QEvent.MouseButtonPress
            and event.button() in (Qt.RightButton, Qt.MiddleButton)
            and hasattr(self, "general_fit_popup")
            and self.general_fit_popup.isVisible()
            and self._is_general_table_object(obj)
        ):
            self.general_fit_popup.hide_panel(force=True)
            event.accept()
            return True

        if handle_resize_event(self, obj, event):
            return True

        return super().eventFilter(obj, event)

    def open_in_zkill_tab(self, url, profile_hint: dict | None = None):
        self.tabs.set_active("Zkill")
        self.zkill_panel.load_url(url, profile_hint=profile_hint)

    def get_clicked_last_ship_index(self, row, col, ships):
        if not ships:
            return 0

        index = self.table.model().index(row, col)
        rect = self.table.visualRect(index)

        pos = self.table.viewport().mapFromGlobal(QCursor.pos())
        x = pos.x() - rect.x() - 3

        if x <= 0:
            return 0

        metrics = QFontMetrics(self.table.font())
        cursor_x = 0

        for i, ship in enumerate(ships):
            name = str(ship.get("display_name") or ship.get("name", "?"))
            name_width = metrics.horizontalAdvance(name)

            if cursor_x <= x <= cursor_x + name_width:
                return i

            cursor_x += name_width

            if i < len(ships) - 1:
                sep = " | "
                sep_width = metrics.horizontalAdvance(sep)

                if cursor_x <= x <= cursor_x + sep_width:
                    # Click on separator: choose the nearest ship.
                    left_distance = x - cursor_x
                    right_distance = (cursor_x + sep_width) - x
                    return i if left_distance <= right_distance else i + 1

                cursor_x += sep_width

        return max(0, len(ships) - 1)

    def open_last_ship_popup(self, ship):
        """Open the same native fitting popup used by the zKill table.

        Last Ships contains recent loss killmail ids from the local DB, so the
        popup can resolve the hash and full fit through the existing
        NativeFitFetchThread path.
        """
        if not ship:
            return

        killmail_id = ship.get("killmail_id")
        if not killmail_id:
            return

        row_data = dict(ship)
        row_data.setdefault("kind", "loss")
        row_data.setdefault("ship_name", ship.get("name") or ship.get("display_name") or "Ship")
        row_data.setdefault("ship_type_id", ship.get("ship_type_id"))

        if hasattr(self, "zkill_panel"):
            self.zkill_panel.close_fit_popup()

        self.general_fit_popup.show_for_row(row_data, self.table, pinned=True)

    def on_cell_double_clicked(self, row, col):
        item = self.table.item(row, col)

        if not item:
            return

        if col == 2:
            character_id = item.data(Qt.UserRole)

            if character_id:
                corp_item = self.table.item(row, 5)
                profile_hint = {
                    "character_name": item.text(),
                    "corp_ally": corp_item.text() if corp_item else "",
                }
                self.open_in_zkill_tab(
                    f"https://zkillboard.com/character/{character_id}/",
                    profile_hint=profile_hint,
                )

            return

        if col == 6:
            last_ships = item.data(Qt.UserRole)

            if not last_ships:
                return

            ship_index = self.get_clicked_last_ship_index(row, col, last_ships)
            ship = last_ships[ship_index]
            self.open_last_ship_popup(ship)
            return

    def closeEvent(self, event):
        if hasattr(self, "general_fit_popup"):
            self.general_fit_popup.hide_panel(force=True)
        if hasattr(self, "zkill_panel"):
            self.zkill_panel.close_fit_popup()

        self.save_general_column_widths()
        self.save_current_window_geometry()
        self.thread_pool.clear()
        self.cyno_pool.clear()
        self.relations_pool.clear()
        self.active_relation_workers.clear()

        event.accept()
