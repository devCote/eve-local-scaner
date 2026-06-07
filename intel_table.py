from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import QTableWidget


class IntelTable(QTableWidget):
    rowHovered = Signal(int)
    mouseLeft = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.last_hover_row = None

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().setAttribute(Qt.WA_Hover, True)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj == self.viewport():
            if event.type() in (
                QEvent.MouseMove,
                QEvent.HoverMove,
                QEvent.Enter,
            ):
                pos = self._event_pos(event)
                index = self.indexAt(pos)

                if index.isValid():
                    row = index.row()

                    if row != self.last_hover_row:
                        self.last_hover_row = row
                        self.rowHovered.emit(row)

            elif event.type() == QEvent.Leave:
                self.last_hover_row = None
                self.mouseLeft.emit()

        return super().eventFilter(obj, event)

    def _event_pos(self, event):
        if hasattr(event, "position"):
            return event.position().toPoint()

        return event.pos()
