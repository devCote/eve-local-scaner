import os
import sys

# IMPORTANT: QtWebEngine/Chromium flags must be set before QApplication
# and before any QWebEngineView/QWebEnginePage is created/imported.
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
    "--disable-gpu "
    "--disable-gpu-compositing "
    "--disable-gpu-rasterization "
    "--disable-accelerated-2d-canvas "
    "--disable-accelerated-video-decode "
    "--disable-dev-shm-usage "
    "--use-angle=swiftshader "
    "--no-sandbox"
)

# Force Qt to use software OpenGL. This helps remove GLES3/GPUInfo console errors.
os.environ["QT_OPENGL"] = "software"

from PySide6.QtWidgets import QApplication

from style import apply_eve_style
from ui import EveLocalScanner


def main() -> int:
    app = QApplication(sys.argv)

    apply_eve_style(app)

    window = EveLocalScanner()
    window.show()

    exit_code = app.exec()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
