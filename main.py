import sys
import os

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-gpu "
    "--disable-dev-shm-usage "
    "--no-sandbox"
)

from PySide6.QtWidgets import QApplication

from style import apply_eve_style
from ui import EveLocalScanner


def cleanup():
    try:
        if os.path.exists("cache.json"):
            os.remove("cache.json")
            print("cache.json removed")
    except Exception as e:
        print("cleanup error:", e)


app = QApplication(sys.argv)

apply_eve_style(app)

window = EveLocalScanner()
window.show()

exit_code = app.exec()

cleanup()

sys.exit(exit_code)

