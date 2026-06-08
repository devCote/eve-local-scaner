from PySide6.QtCore import QUrl, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
)

from zkillCharLoad import get_character_script
from zkillKillLoad import get_kill_script

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import (
        QWebEngineUrlRequestInterceptor,
        QWebEngineProfile,
        QWebEnginePage,
    )

    WEBENGINE_AVAILABLE = True

except Exception:
    QWebEngineView = None
    QWebEngineUrlRequestInterceptor = None
    QWebEngineProfile = None
    QWebEnginePage = None
    WEBENGINE_AVAILABLE = False


class AdBlocker(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.blocked_hosts = [
            "googlesyndication.com",
            "googleadservices.com",
            "doubleclick.net",
            "adservice.google.com",
            "pagead2.googlesyndication.com",
            "securepubads.g.doubleclick.net",
            "googletagservices.com",
            "googletagmanager.com",
            "google-analytics.com",
            "analytics.google.com",
            "facebook.net",
            "ads-twitter.com",
            "amazon-adsystem.com",
            "static.cloudflareinsights.com",
        ]

        self.blocked_url_parts = [
            "/ads?",
            "/ads/",
            "googleads",
            "googletag",
            "doubleclick",
            "pubads",
            "pagead",
            "adservice",
            "analytics",
            "beacon.min.js",
            "cloudflareinsights",
            "markeedragon",
            "patreon",
        ]

    def interceptRequest(self, info):
        url = info.requestUrl().toString().lower()
        host = info.requestUrl().host().lower()

        for blocked_host in self.blocked_hosts:
            if blocked_host in host:
                info.block(True)
                return

        for blocked_part in self.blocked_url_parts:
            if blocked_part in url:
                info.block(True)
                return


class QuietWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        # Убираем мусор из консоли от JS сайта / рекламы
        return


class ZkillPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.home_url = "https://zkillboard.com/"
        self.browser = None
        self.profile = None
        self.page = None
        self.adblocker = None

        self.build_ui()

    def build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(3)

        self.back_button = QPushButton("<")
        self.forward_button = QPushButton(">")
        self.reload_button = QPushButton("R")
        self.home_button = QPushButton("Home")

        for button in [
            self.back_button,
            self.forward_button,
            self.reload_button,
            self.home_button,
        ]:
            button.setFixedHeight(20)

        self.url_input = QLineEdit()
        self.url_input.setFixedHeight(20)
        self.url_input.returnPressed.connect(self.load_from_input)

        top_bar.addWidget(self.back_button)
        top_bar.addWidget(self.forward_button)
        top_bar.addWidget(self.reload_button)
        top_bar.addWidget(self.home_button)
        top_bar.addWidget(self.url_input, 1)

        layout.addLayout(top_bar)

        if WEBENGINE_AVAILABLE:
            self.browser = QWebEngineView()

            self.profile = QWebEngineProfile.defaultProfile()
            self.adblocker = AdBlocker(self)
            self.profile.setUrlRequestInterceptor(self.adblocker)

            self.page = QuietWebPage(self.profile, self.browser)
            self.browser.setPage(self.page)

            self.back_button.clicked.connect(self.browser.back)
            self.forward_button.clicked.connect(self.browser.forward)
            self.reload_button.clicked.connect(self.browser.reload)
            self.home_button.clicked.connect(lambda: self.load_url(self.home_url))

            self.browser.urlChanged.connect(self.on_url_changed)
            self.browser.loadFinished.connect(self.on_page_loaded)

            layout.addWidget(self.browser, 1)

            self.load_url(self.home_url)

        else:
            warning = QLabel(
                "QtWebEngine не найден.\n\n"
                "Установи:\n"
                "pip install PySide6 PySide6-Addons\n\n"
                "После этого вкладка Zkill станет встроенным браузером."
            )
            warning.setStyleSheet("""
                QLabel {
                    color: #C7C9CC;
                    background-color: rgba(8, 9, 11, 200);
                    padding: 12px;
                    border: 1px solid #333840;
                }
            """)
            layout.addWidget(warning, 1)

        self.setStyleSheet("""
            QLineEdit {
                background-color: rgba(8, 9, 11, 230);
                color: #D0D2D5;
                border: 1px solid #343840;
                padding-left: 6px;
                font-size: 8pt;
            }

            QPushButton {
                background-color: rgba(24, 26, 30, 210);
                color: #BFC3C8;
                border: 1px solid #343840;
                padding: 0px 6px;
                font-size: 8pt;
            }

            QPushButton:hover {
                background-color: rgba(42, 46, 54, 240);
                color: #FFFFFF;
                border: 1px solid #69707A;
            }
        """)

    def load_from_input(self):
        self.load_url(self.url_input.text().strip())

    def load_url(self, url):
        if not url:
            return

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        self.url_input.setText(url)

        if self.browser:
            self.browser.setUrl(QUrl(url))

    def on_url_changed(self, url):
        self.url_input.setText(url.toString())

    def on_page_loaded(self, ok):
        if not ok:
            return

        self.inject_clean_zkill_css()

        # zKill часто догружает killlist через JS, поэтому повторяем очистку
        QTimer.singleShot(800, self.inject_clean_zkill_css)
        QTimer.singleShot(1800, self.inject_clean_zkill_css)
        QTimer.singleShot(3200, self.inject_clean_zkill_css)


    def inject_clean_zkill_css(self):
        if not self.browser:
            return

        path = self.browser.url().path()

        if path.startswith("/character/"):
            self.browser.page().runJavaScript(get_character_script())
            return

        if path.startswith("/kill/"):
            self.browser.page().runJavaScript(get_kill_script())
            return

        cleanup_script = r"""
        (function () {
            const ids = [
                "eve-local-zkill-style",
                "eve-local-zkill-kill-style",
                "eve-local-zkill-view"
            ];

            for (const id of ids) {
                const el = document.getElementById(id);
                if (el) el.remove();
            }
        })();
        """
        self.browser.page().runJavaScript(cleanup_script)
