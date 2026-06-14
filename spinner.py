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

    def _sync_timer(self):
        if self.labels:
            if not self.timer.isActive():
                self.timer.start(120)
        elif self.timer.isActive():
            self.timer.stop()

    def add(self, row, label):
        self.labels[row] = label
        self._sync_timer()

    def remove(self, row):
        self.labels.pop(row, None)
        self._sync_timer()

    def animate(self):
        if not self.labels:
            self._sync_timer()
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

        self._sync_timer()

    def current_frame(self):
        return self.frames[self.frame_index]
