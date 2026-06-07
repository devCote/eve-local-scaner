from PySide6.QtCore import QObject, QTimer
import shiboken6


class SpinnerManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.frames = ["◜", "◝", "◞", "◟"]
        self.frame_index = 0
        self.labels = {}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(120)

    def add(self, row, label):
        self.labels[row] = label

    def remove(self, row):
        self.labels.pop(row, None)

    def animate(self):
        if not self.labels:
            return

        self.frame_index = (self.frame_index + 1) % len(self.frames)
        frame = self.frames[self.frame_index]

        dead_rows = []

        for row, label in self.labels.items():
            try:
                if label is None or not shiboken6.isValid(label):
                    dead_rows.append(row)
                    continue

                label.setText(frame)

            except RuntimeError:
                dead_rows.append(row)

        for row in dead_rows:
            self.remove(row)

    def current_frame(self):
        return self.frames[self.frame_index]
