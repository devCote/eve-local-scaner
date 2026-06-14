"""Compact Qt tables for zKill API data. No QtWebEngine/Chromium."""

from __future__ import annotations

from app_fonts import APP_FONT_FAMILY

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
)

from user_settings import load_zkill_table_settings, save_zkill_table_settings


_KIND_ROLE = Qt.UserRole + 41




class ZKillHeaderView(QHeaderView):
    """zKill header with subtle separators only between visible columns."""

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        # Draw separators after Date, Ship and Location. Opponent has no right border.
        self.separator_columns = {0, 1, 2}
        self.separator_color = QColor("#3D424A")

    def set_separator_color(self, color):
        self.separator_color = QColor(color)
        self.viewport().update()

    def paintSection(self, painter, rect, logicalIndex):
        super().paintSection(painter, rect, logicalIndex)

        if logicalIndex not in self.separator_columns:
            return

        painter.save()
        painter.setPen(QPen(self.separator_color, 1))
        x = rect.right()
        painter.drawLine(x, rect.top() + 3, x, rect.bottom() - 3)
        painter.restore()

class _ResultRowDelegate(QStyledItemDelegate):
    """Paint kill/loss backgrounds with full-row hover and no click selection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Base backgrounds: dark, readable and not too bright.
        self.kill_bg = QColor(18, 91, 67, 125)
        self.loss_bg = QColor(105, 35, 41, 135)
        # Hover backgrounds are a little brighter, but stay in the same
        # kill/loss family instead of turning the row blue/cyan.
        self.kill_hover_bg = QColor(31, 132, 98, 155)
        self.loss_hover_bg = QColor(142, 49, 57, 165)
        self.neutral_hover_bg = QColor(57, 199, 181, 70)

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # No pressed/selected color. Clicking rows must not create a visual
        # selection rectangle or Windows-blue highlight.
        opt.state &= ~QStyle.State_Selected
        opt.state &= ~QStyle.State_MouseOver

        table = self.parent()
        hover_row = getattr(table, "_hover_row", -1)
        hover_col = getattr(table, "_hover_col", -1)
        row_hovered = index.row() == hover_row
        cell_hovered = row_hovered and index.column() == hover_col

        kind = str(index.data(_KIND_ROLE) or "").lower()
        if row_hovered:
            if kind == "kill":
                bg = self.kill_hover_bg
            elif kind == "loss":
                bg = self.loss_hover_bg
            else:
                bg = self.neutral_hover_bg
        elif kind == "kill":
            bg = self.kill_bg
        elif kind == "loss":
            bg = self.loss_bg
        else:
            bg = None

        if bg is not None:
            painter.save()
            painter.fillRect(option.rect, bg)
            painter.restore()

        # Hover changes only the row background / text color. No bold font.
        if cell_hovered:
            opt.palette.setColor(QPalette.ColorRole.Text, QColor("#FFFFFF"))

        super().paint(painter, opt, index)


class KillsLossesTable(QTableWidget):
    killmailActivated = Signal(int)
    columnWidthsChanged = Signal(dict)
    shipHovered = Signal(dict)
    shipHoverLeft = Signal()
    shipClicked = Signal(dict)
    popupCloseRequested = Signal()

    def __init__(self, parent=None, show_kind: bool = False, default_kind: str | None = None):
        super().__init__(parent)
        self.rows_data: list[dict] = []
        # Kept for backward compatibility, but the visual Type column is removed.
        self.show_kind = False
        self.default_kind = str(default_kind or "").lower().strip()
        self._font_size = max(7, self.font().pointSize() or 10)
        self._text_color = "#C9CDD2"
        self._frame_color = "#3D424A"
        self._accent_color = "#39C7B5"
        self._hover_row = -1
        self._hover_col = -1
        self._kill_text = QColor("#D7F5E3")
        self._loss_text = QColor("#F2D4D6")
        self._loading_column_widths = False
        self._user_resized_columns = False
        self._column_settings = load_zkill_table_settings()

        self.setColumnCount(4)
        self.setHorizontalHeader(ZKillHeaderView(Qt.Horizontal, self))
        self.setHorizontalHeaderLabels(["Date", "Ship", "Location", "Opponent"])

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setAlternatingRowColors(False)
        self.setSortingEnabled(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)
        self.setShowGrid(False)
        self.setFrameShape(QTableWidget.NoFrame)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(17)
        self.verticalHeader().setMinimumSectionSize(15)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.cellDoubleClicked.connect(self._on_double_clicked)

        self._delegate = _ResultRowDelegate(self)
        self.setItemDelegate(self._delegate)

        header = self.horizontalHeader()
        # Opponent column should fill the remaining table width, like Last Ships in General.
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(26)
        header.setSectionsMovable(False)
        header.setSectionsClickable(False)
        for col in range(self.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.sectionResized.connect(self._on_column_resized)

        for col in range(self.columnCount()):
            item = self.horizontalHeaderItem(col)
            if item:
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.apply_ui_settings(font_size=self._font_size, text_color=self._text_color)
        self._reset_horizontal_offset()

    def _reset_horizontal_offset(self):
        """Keep compact zKill table anchored left while horizontal scrollbar is hidden."""
        try:
            self.horizontalScrollBar().setValue(0)
            self.viewport().update()
        except Exception:
            pass

    def apply_ui_settings(self, font_size: int | None = None, text_color: str | None = None, frame_color: str | None = None):
        """Apply global UI font/color/frame color to the zKill compact table."""
        if font_size is not None:
            try:
                self._font_size = max(7, min(11, int(font_size)))
            except Exception:
                self._font_size = max(7, self._font_size)

        if text_color:
            self._text_color = str(text_color)
        if frame_color:
            self._frame_color = str(frame_color)

        # Normal zKill text must follow Options -> Text color.
        # Kill/loss state is shown by row background, not by hardcoded text color.
        text_qcolor = QColor(self._text_color)
        if text_qcolor.isValid():
            self._kill_text = QColor(text_qcolor)
            self._loss_text = QColor(text_qcolor)
            for row in range(self.rowCount()):
                for col in range(self.columnCount()):
                    item = self.item(row, col)
                    if item:
                        item.setForeground(text_qcolor)

        header_obj = self.horizontalHeader()
        if hasattr(header_obj, "set_separator_color"):
            header_obj.set_separator_color(self._frame_color)

        font = self.font()
        font.setFamily(APP_FONT_FAMILY)
        font.setPointSize(int(self._font_size))
        self.setFont(font)
        self.viewport().setFont(font)
        self.horizontalHeader().setFont(font)
        self.verticalHeader().setFont(font)

        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    item.setFont(font)

        self.setStyleSheet(f"""
            QTableWidget {{
                gridline-color: transparent;
                background-color: transparent;
                alternate-background-color: transparent;
                color: {self._text_color};
                border: 0px;
                font-family: '{APP_FONT_FAMILY}'; font-size: {self._font_size}pt;
                selection-background-color: transparent;
                selection-color: #FFFFFF;
            }}
            QTableWidget::item {{
                padding-left: 4px;
                padding-right: 6px;
                padding-top: 0px;
                padding-bottom: 0px;
                border: 0px;
                background-color: transparent;
                font-family: '{APP_FONT_FAMILY}'; font-size: {self._font_size}pt;
            }}
            QTableWidget::item:hover {{
                background-color: transparent;
                color: #FFFFFF;
            }}
            QTableWidget::item:selected {{
                background-color: transparent;
                color: #FFFFFF;
            }}
            QHeaderView {{
                background-color: transparent;
                border: 0px;
            }}
            QHeaderView::section {{
                background-color: transparent;
                color: {self._text_color};
                padding-left: 4px;
                padding-right: 6px;
                padding-top: 0px;
                padding-bottom: 1px;
                border: 0px;
                font-family: '{APP_FONT_FAMILY}'; font-size: {self._font_size}pt;
                font-weight: normal;
                text-align: left;
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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
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
        self._update_row_metrics()
        self._apply_column_sizes()
        self.viewport().update()
        self.horizontalHeader().update()

    def _update_row_metrics(self):
        row_height = max(17, self.fontMetrics().height() + 3)
        header_height = max(18, self.fontMetrics().height() + 4)
        self.verticalHeader().setMinimumSectionSize(row_height)
        self.verticalHeader().setDefaultSectionSize(row_height)
        self.horizontalHeader().setFixedHeight(header_height)
        for row in range(self.rowCount()):
            self.setRowHeight(row, row_height)

    def _resolve_row_kind(self, row_data: dict) -> str:
        # Kills and Losses tabs know their type even if the incoming row doesn't.
        kind = str(row_data.get("kind") or row_data.get("type") or row_data.get("result") or "").lower().strip()
        if kind in ("kill", "kills", "killed"):
            return "kill"
        if kind in ("loss", "losses", "lost"):
            return "loss"
        if self.default_kind in ("kill", "loss"):
            return self.default_kind
        return ""

    def load_data(self, data_rows: list[dict]):
        self.rows_data = list(data_rows or [])
        self.setRowCount(len(self.rows_data))

        for row_idx, row_data in enumerate(self.rows_data):
            if not isinstance(row_data, dict):
                row_data = {}

            kind = self._resolve_row_kind(row_data)
            if kind and not row_data.get("kind"):
                # Keep internal row data consistent for double-click/future logic.
                row_data = dict(row_data)
                row_data["kind"] = kind
                self.rows_data[row_idx] = row_data

            self._set_item(row_idx, 0, self._compact_date(row_data.get("date", "")), kind)
            self._set_item(row_idx, 1, row_data.get("ship_name", "Unknown"), kind)
            self._set_item(row_idx, 2, row_data.get("location", ""), kind)
            self._set_item(row_idx, 3, row_data.get("opponent", "Unknown"), kind)

        self._apply_column_sizes()
        self._update_row_metrics()
        self._reset_horizontal_offset()
        self.viewport().update()


    def mouseMoveEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        new_row = index.row() if index.isValid() else -1
        new_col = index.column() if index.isValid() else -1
        if new_row != self._hover_row or new_col != self._hover_col:
            old_row = self._hover_row
            self._hover_row = new_row
            self._hover_col = new_col
            if old_row >= 0:
                self.viewport().update(self.visualRect(self.model().index(old_row, 0)).united(
                    self.visualRect(self.model().index(old_row, self.columnCount() - 1))
                ))
            if new_row >= 0:
                self.viewport().update(self.visualRect(self.model().index(new_row, 0)).united(
                    self.visualRect(self.model().index(new_row, self.columnCount() - 1))
                ))

            # Hover only updates visual row/cell highlighting now.
            # Fitting popup is opened by click, not hover.
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        old_row = self._hover_row
        self._hover_row = -1
        self._hover_col = -1
        if old_row >= 0:
            self.viewport().update(self.visualRect(self.model().index(old_row, 0)).united(
                self.visualRect(self.model().index(old_row, self.columnCount() - 1))
            ))
        # Do not close fitting popup when mouse leaves the table.
        # It closes only when the mouse exits the popup itself.
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        button = event.button()

        if button in (Qt.RightButton, Qt.MiddleButton):
            # Right click / wheel click must never open the fit popup.
            # They close the current popup instead.
            self.popupCloseRequested.emit()
            self.clearSelection()
            self.setCurrentItem(None)
            event.accept()
            return

        if button == Qt.LeftButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and index.row() < len(self.rows_data):
                # Open fitting popup from ANY cell in the row, not only Ship.
                self.shipClicked.emit(dict(self.rows_data[index.row()] or {}))

        # Keep double-click activation, but do not leave a selected row behind.
        super().mousePressEvent(event)
        self.clearSelection()
        self.setCurrentItem(None)

    def resizeEvent(self, event):
        # Do not auto-reset column widths on window resize.
        # User-dragged zKill header sizes should stay exactly where they are,
        # like the General table. But always keep hidden horizontal offset at 0.
        super().resizeEvent(event)
        self._reset_horizontal_offset()

    def _compact_date(self, value: str) -> str:
        value = str(value or "").strip()
        # Supported inputs:
        #   2026-06-09 14:56 -> 06-09 14:56
        #   26-06-09 14:56   -> 06-09 14:56
        if len(value) >= 14 and value[4] == "-" and value[7] == "-":
            return value[5:16]
        if len(value) >= 12 and value[2] == "-" and value[5] == "-":
            return value[3:14]
        return value

    def _text_width(self, text: str) -> int:
        return self.fontMetrics().horizontalAdvance(str(text or ""))

    def _column_text_width(self, col: int) -> int:
        header = self.horizontalHeaderItem(col)
        max_width = self._text_width(header.text() if header else "")
        for row in range(self.rowCount()):
            item = self.item(row, col)
            if item:
                max_width = max(max_width, self._text_width(item.text()))
        return max_width + 8

    def _apply_column_sizes(self):
        # Saved/user-controlled widths first. If no user widths exist yet,
        # use compact content-aware defaults once, then let the header drag
        # handles behave like General.
        self._loading_column_widths = True
        try:
            widths = (self._column_settings or {}).get("column_widths", {})
            if widths:
                for col in range(self.columnCount()):
                    saved = widths.get(str(col))
                    if saved is not None:
                        self.setColumnWidth(col, max(26, int(saved)))
                return

            width = max(0, self.viewport().width())
            date_w = max(88, min(112, self._column_text_width(0)))
            ship_w = max(72, min(180, self._column_text_width(1)))
            location_w = max(60, min(100, self._column_text_width(2)))
            opponent_w = max(110, width - date_w - ship_w - location_w - 1) if width > 0 else 160

            self.setColumnWidth(0, date_w)
            self.setColumnWidth(1, ship_w)
            self.setColumnWidth(2, location_w)
            self.setColumnWidth(3, opponent_w)
        finally:
            self._loading_column_widths = False

    def _current_column_widths(self) -> dict[str, int]:
        return {str(col): int(self.columnWidth(col)) for col in range(self.columnCount())}

    def _save_column_widths(self):
        if getattr(self, "_loading_column_widths", False):
            return
        widths = self._current_column_widths()
        self._column_settings = {"column_widths": widths}
        save_zkill_table_settings(self._column_settings)
        self.columnWidthsChanged.emit(widths)

    def apply_external_column_widths(self, widths: dict):
        if not isinstance(widths, dict):
            return

        self._loading_column_widths = True
        try:
            clean: dict[str, int] = {}
            for col in range(self.columnCount()):
                value = widths.get(str(col))
                if value is None:
                    value = widths.get(col)
                if value is None:
                    continue
                try:
                    value = max(26, int(value))
                except Exception:
                    continue
                clean[str(col)] = value
                self.setColumnWidth(col, value)
            if clean:
                self._column_settings = {"column_widths": clean}
        finally:
            self._loading_column_widths = False

    def _on_column_resized(self, logical_index: int, old_size: int, new_size: int):
        if getattr(self, "_loading_column_widths", False):
            return
        if logical_index < 0 or logical_index >= self.columnCount():
            return
        self._user_resized_columns = True
        QTimer.singleShot(0, self._save_column_widths)

    def clear_data(self):
        self.rows_data = []
        self.setRowCount(0)

    def _set_item(self, row: int, col: int, value: str, kind: str = ""):
        item = QTableWidgetItem(str(value or ""))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        item.setFont(self.font())
        item.setData(_KIND_ROLE, kind)
        text_qcolor = QColor(self._text_color)
        if text_qcolor.isValid():
            item.setForeground(text_qcolor)
        self.setItem(row, col, item)

    def _on_double_clicked(self, row: int, col: int):
        if row < 0 or row >= len(self.rows_data):
            return
        killmail_id = int(self.rows_data[row].get("killmail_id") or 0)
        if killmail_id:
            self.killmailActivated.emit(killmail_id)
