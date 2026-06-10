from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


class ClipboardWatcher:
    def __init__(self, callback):
        self.callback = callback
        self.last_text = ""

        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.on_changed)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.read_clipboard)

    def on_changed(self):
        self.timer.start(700)

    def read_clipboard(self):
        text = self.clipboard.text().strip()

        if not text:
            return

        if text == self.last_text:
            return

        self.last_text = text
        self.callback(text)
