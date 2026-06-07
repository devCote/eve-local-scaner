from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QStyledItemDelegate, QStyle


class RowHighlightDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        table = self.parent()

        row = index.row()
        color = None

        if hasattr(table, "highlight_rows"):
            color = table.highlight_rows.get(row)

        if color:
            painter.save()
            painter.fillRect(option.rect, color)
            painter.restore()

            # убираем системное выделение, чтобы оно не перебивало наш цвет
            option.state &= ~QStyle.State_Selected
            option.state &= ~QStyle.State_HasFocus

        super().paint(painter, option, index)


class IntelTable(QTableWidget):
    rowHovered = Signal(int)
    mouseLeft = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.last_hover_row = None
        self.highlight_rows = {}

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover, True)
        self.viewport().installEventFilter(self)

        self.setItemDelegate(RowHighlightDelegate(self))

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
                    self.last_hover_row = row
                    self.rowHovered.emit(row)

            elif event.type() == QEvent.Leave:
                self.last_hover_row = None
                self.mouseLeft.emit()

        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        index = self.indexAt(event.pos())

        if index.isValid():
            row = index.row()
            self.last_hover_row = row
            self.rowHovered.emit(row)

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.last_hover_row = None
        self.mouseLeft.emit()
        super().leaveEvent(event)

    def get_event_pos(self, event):
        if hasattr(event, "position"):
            return event.position().toPoint()

        return event.pos()
