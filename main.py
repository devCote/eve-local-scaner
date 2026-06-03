import sys
from PySide6.QtWidgets import QApplication
from style import apply_eve_style
from ui import EveLocalScanner


app = QApplication(sys.argv)
apply_eve_style(app)

window = EveLocalScanner()
window.show()

sys.exit(app.exec())
