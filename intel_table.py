from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QTableWidget, QStyledItemDelegate, QStyle, QHeaderView


class GeneralHeaderView(QHeaderView):
    """Header with separators only after visible data columns.

    Empty icon columns stay clean. Separators are drawn only after:
    Name, Danger, Gang, Corp/Ally. Last Ships has no right border.
    """

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.separator_columns = {2, 3, 4, 5}
        self.separator_color = QColor("#2b4f4b")

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


class RowHighlightDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        table = self.parent()
        row = index.row()

        color = None

        if hasattr(table, "highlight_rows"):
            color = table.highlight_rows.get(row)

        if color:
            option.textElideMode = Qt.ElideRight

            painter.save()
            painter.fillRect(option.rect, color)
            painter.restore()

            option.state &= ~QStyle.State_Selected
            option.state &= ~QStyle.State_HasFocus

        super().paint(painter, option, index)


class IntelTable(QTableWidget):
    rowHovered = Signal(int)
    mouseLeft = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideRight)

        self.last_hover_row = None
        self.highlight_rows = {}

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover, True)
        self.viewport().installEventFilter(self)

        self.setItemDelegate(RowHighlightDelegate(self))

    def _lock_horizontal_offset(self):
        """Hard-lock hidden horizontal scrolling to the left edge.

        Qt can still move the hidden horizontal scrollbar when the user clicks
        a far-right cell/current index. Since the bar is hidden, this looks like
        the first columns are pushed outside the app. General should never move
        horizontally, so reset immediately and once more after the event loop.
        """
        try:
            bar = self.horizontalScrollBar()
            if bar.value() != 0:
                bar.setValue(0)
                self.viewport().update()
        except Exception:
            pass

    def _lock_horizontal_offset_later(self):
        self._lock_horizontal_offset()
        QTimer.singleShot(0, self._lock_horizontal_offset)

    def scrollTo(self, index, hint=QTableWidget.EnsureVisible):
        # Let Qt handle vertical movement if needed, then undo only horizontal
        # movement. This keeps row navigation normal but prevents left shift.
        super().scrollTo(index, hint)
        self._lock_horizontal_offset_later()

    def currentChanged(self, current, previous):
        super().currentChanged(current, previous)
        self._lock_horizontal_offset_later()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._lock_horizontal_offset_later()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._lock_horizontal_offset_later()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self._lock_horizontal_offset_later()

    def set_highlight_rows(self, rows):
        self.highlight_rows = rows or {}
        self.viewport().update()

    def clear_highlight_rows(self):
        self.highlight_rows = {}
        self.viewport().update()

    def eventFilter(self, obj, event):
        if obj == self.viewport():
            if event.type() in (
                QEvent.MouseMove,
                QEvent.HoverMove,
                QEvent.Enter,
            ):
                pos = self.get_event_pos(event)
                index = self.indexAt(pos)

                if index.isValid():
                    row = index.row()
                    if row != self.last_hover_row:
                        self.last_hover_row = row
                        self.rowHovered.emit(row)

            elif event.type() == QEvent.Leave:
                if self.last_hover_row is not None:
                    self.last_hover_row = None
                    self.mouseLeft.emit()

        if obj == self.viewport():
            self._lock_horizontal_offset()

        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        self._lock_horizontal_offset()
        index = self.indexAt(event.pos())

        if index.isValid():
            row = index.row()
            if row != self.last_hover_row:
                self.last_hover_row = row
                self.rowHovered.emit(row)

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._lock_horizontal_offset()
        if self.last_hover_row is not None:
            self.last_hover_row = None
            self.mouseLeft.emit()
        super().leaveEvent(event)

    def get_event_pos(self, event):
        if hasattr(event, "position"):
            return event.position().toPoint()

        return event.pos()
