from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QWidget


def get_resize_edges(window, pos):
    edges = Qt.Edges()

    x = pos.x()
    y = pos.y()
    w = window.width()
    h = window.height()
    m = window.resize_margin

    if x <= m:
        edges |= Qt.LeftEdge

    if x >= w - m:
        edges |= Qt.RightEdge

    if y <= m:
        edges |= Qt.TopEdge

    if y >= h - m:
        edges |= Qt.BottomEdge

    return edges


def update_resize_cursor(window, edges):
    if not edges:
        window.unsetCursor()
        return

    left = bool(edges & Qt.LeftEdge)
    right = bool(edges & Qt.RightEdge)
    top = bool(edges & Qt.TopEdge)
    bottom = bool(edges & Qt.BottomEdge)

    if (left and top) or (right and bottom):
        window.setCursor(Qt.SizeFDiagCursor)
    elif (right and top) or (left and bottom):
        window.setCursor(Qt.SizeBDiagCursor)
    elif left or right:
        window.setCursor(Qt.SizeHorCursor)
    elif top or bottom:
        window.setCursor(Qt.SizeVerCursor)
    else:
        window.unsetCursor()


def handle_resize_event(window, obj, event):
    if not isinstance(obj, QWidget):
        return False

    if obj.window() != window:
        return False

    if event.type() == QEvent.MouseMove:
        if not window.isMaximized():
            local_pos = event.position().toPoint()
            window_pos = obj.mapTo(window, local_pos)

            edges = get_resize_edges(window, window_pos)
            update_resize_cursor(window, edges)

        return False

    if event.type() == QEvent.MouseButtonPress:
        if event.button() == Qt.LeftButton and not window.isMaximized():
            local_pos = event.position().toPoint()
            window_pos = obj.mapTo(window, local_pos)

            edges = get_resize_edges(window, window_pos)

            if edges:
                handle = window.windowHandle()

                if handle:
                    handle.startSystemResize(edges)
                    return True

        return False

    if event.type() == QEvent.Leave:
        window.unsetCursor()
        return False

    return False
