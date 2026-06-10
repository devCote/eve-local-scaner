import traceback
import json
from pathlib import Path

from PySide6.QtCore import QUrl, QTimer, Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QLabel,
)

from paths import EXE_DIR, SOURCE_DIR, BUNDLE_DIR

ZKILL_DEBUG = False

def zkill_log(message: str):
    if ZKILL_DEBUG:
        print(message)


class ZkillPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.home_url = "https://zkillboard.com/"
        self.pending_url = self.home_url

        self.browser = None
        self.profile = None
        self.page = None
        self.adblocker = None
        self.placeholder = None

        self.main_layout = None
        self.browser_loaded = False

        # zKill updates parts of the page after loadFinished. In installed exe
        # this can reset custom DOM/CSS back to default later, so keep
        # re-applying external loaders while a supported zKill page is open.

        self.QWebEngineView = None
        self.QWebEngineProfile = None
        self.QWebEnginePage = None
        self.QWebEngineUrlRequestInterceptor = None

        self.build_ui()

    def build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(3)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(3)

        self.back_button = QPushButton("<")
        self.forward_button = QPushButton(">")
        self.reload_button = QPushButton("R")
        self.home_button = QPushButton("Home")
        self.unload_button = QPushButton("Unload")

        for button in (
            self.back_button,
            self.forward_button,
            self.reload_button,
            self.home_button,
            self.unload_button,
        ):
            button.setFixedHeight(20)

        self.url_input = QLineEdit()
        self.url_input.setFixedHeight(20)
        self.url_input.setText(self.home_url)
        self.url_input.returnPressed.connect(self.load_from_input)

        top_bar.addWidget(self.back_button)
        top_bar.addWidget(self.forward_button)
        top_bar.addWidget(self.reload_button)
        top_bar.addWidget(self.home_button)
        top_bar.addWidget(self.unload_button)
        top_bar.addWidget(self.url_input, 1)

        self.main_layout.addLayout(top_bar)

        self.placeholder = QLabel(
            "Zkill browser is not loaded.\n\n"
            "Open this tab to start QtWebEngine/Chromium only when needed."
        )
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("""
            QLabel {
                color: #8F959C;
                background-color: rgba(8, 9, 11, 120);
                border: 1px solid #252A31;
                padding: 14px;
            }
        """)
        self.main_layout.addWidget(self.placeholder, 1)

        self.back_button.clicked.connect(self.safe_back)
        self.forward_button.clicked.connect(self.safe_forward)
        self.reload_button.clicked.connect(self.safe_reload)
        self.home_button.clicked.connect(lambda: self.load_url(self.home_url))
        self.unload_button.clicked.connect(self.unload_browser)

        self.update_buttons()

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

    def load_webengine(self) -> bool:
        if self.QWebEngineView:
            return True

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import (
                QWebEngineProfile,
                QWebEnginePage,
                QWebEngineUrlRequestInterceptor,
            )

            self.QWebEngineView = QWebEngineView
            self.QWebEngineProfile = QWebEngineProfile
            self.QWebEnginePage = QWebEnginePage
            self.QWebEngineUrlRequestInterceptor = QWebEngineUrlRequestInterceptor
            return True

        except Exception as e:
            print("[ZKILL] QtWebEngine import failed:", e)
            return False

    def make_adblocker_class(self):
        base_class = self.QWebEngineUrlRequestInterceptor

        class AdBlocker(base_class):
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

        return AdBlocker

    def make_page_class(self):
        base_class = self.QWebEnginePage

        class QuietWebPage(base_class):
            def javaScriptConsoleMessage(self, level, message, line_number, source_id):
                message = str(message)
                if "ELS" in message or "ZKILL" in message or "loader" in message.lower():
                    print(f"[ZKILL JS] {message}")

        return QuietWebPage

    def ensure_browser_loaded(self):
        if self.browser_loaded:
            return True

        if not self.load_webengine():
            self.placeholder.setText(
                "QtWebEngine not found.\n\n"
                "Install:\n"
                "pip install PySide6 PySide6-Addons"
            )
            return False

        self.placeholder.setText("Loading QtWebEngine browser...")
        self.placeholder.repaint()

        self.browser = self.QWebEngineView()

        self.profile = self.QWebEngineProfile.defaultProfile()

        AdBlocker = self.make_adblocker_class()
        self.adblocker = AdBlocker(self)
        self.profile.setUrlRequestInterceptor(self.adblocker)

        QuietWebPage = self.make_page_class()
        self.page = QuietWebPage(self.profile, self.browser)
        self.browser.setPage(self.page)

        self.browser.urlChanged.connect(self.on_url_changed)
        self.browser.loadFinished.connect(self.on_page_loaded)

        if self.placeholder:
            self.main_layout.removeWidget(self.placeholder)
            self.placeholder.hide()

        self.main_layout.addWidget(self.browser, 1)
        self.browser_loaded = True
        self.update_buttons()

        self.load_url(self.pending_url or self.home_url)
        return True

    def unload_browser(self):
        if not self.browser:
            return

        current_url = self.browser.url().toString()
        if current_url:
            self.pending_url = current_url

        self.browser.setUrl(QUrl("about:blank"))
        self.browser.deleteLater()

        self.browser = None
        self.page = None
        self.profile = None
        self.adblocker = None
        self.browser_loaded = False

        if self.placeholder:
            self.placeholder.setText(
                "Zkill browser unloaded.\n\n"
                "Open/load a zKill URL to start QtWebEngine again."
            )
            self.placeholder.show()
            self.main_layout.addWidget(self.placeholder, 1)

        self.update_buttons()

    def update_buttons(self):
        loaded = bool(self.browser_loaded and self.browser)

        self.back_button.setEnabled(loaded)
        self.forward_button.setEnabled(loaded)
        self.reload_button.setEnabled(loaded)
        self.unload_button.setEnabled(loaded)

        self.home_button.setEnabled(True)
        self.url_input.setEnabled(True)

    def safe_back(self):
        if self.ensure_browser_loaded() and self.browser:
            self.browser.back()

    def safe_forward(self):
        if self.ensure_browser_loaded() and self.browser:
            self.browser.forward()

    def safe_reload(self):
        if self.ensure_browser_loaded() and self.browser:
            self.browser.reload()

    def load_from_input(self):
        self.load_url(self.url_input.text().strip())

    def load_url(self, url):
        if not url:
            return

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        self.pending_url = url
        self.url_input.setText(url)

        if self.ensure_browser_loaded() and self.browser:
            self.browser.setUrl(QUrl(url))

    def on_url_changed(self, url):
        url_text = url.toString()
        if url_text:
            self.pending_url = url_text
            self.url_input.setText(url_text)

    def on_page_loaded(self, ok):
        if not ok:
            return

        self.inject_global_zkill_css()
        self.inject_external_zkill_loader()

        # zKill sometimes fills the page shortly after loadFinished.
        # Apply twice at the beginning, then MutationObserver handles later DOM refreshes.
        for ms in (250, 900):
            QTimer.singleShot(ms, self.inject_global_zkill_css)
            QTimer.singleShot(ms, self.inject_external_zkill_loader)

    def get_external_loader_path(self, filename: str):
        candidates = [
            EXE_DIR / filename,
            SOURCE_DIR / filename,
            BUNDLE_DIR / filename,
            Path.cwd() / filename,
            EXE_DIR / "_internal" / filename,
            BUNDLE_DIR / "_internal" / filename,
        ]

        for path in candidates:
            if path.exists():
                return path

        return None

    def get_loader_for_current_path(self):
        if not self.browser:
            return None

        path = self.browser.url().path()

        if path.startswith("/kill/"):
            return "zkillKillLoad.py"

        if (
            path.startswith("/character/")
            or path.startswith("/corporation/")
            or path.startswith("/alliance/")
            or path.startswith("/region/")
            or path.startswith("/system/")
        ):
            return "zkillCharLoad.py"

        return None

    def run_js(self, script_text: str, label: str):
        if not self.browser or not script_text:
            return

        # Wrap raw JS so top-level "return;" inside your old loaders does not break.
        wrapped = f"""
        (function() {{
            try {{
                {script_text}

                try {{
                    document.documentElement.setAttribute("data-els-zkill-custom", "1");
                }} catch (_) {{}}
            }} catch (e) {{
                console.error("[ELS loader error {label}] " + (e && e.stack ? e.stack : e));
            }}
        }})();
        """
        self.browser.page().runJavaScript(wrapped)

    def run_external_python_loader(self, path: Path) -> bool:
        if not self.browser:
            return False

        code = path.read_text(encoding="utf-8", errors="ignore")

        def call_loader_function(name, fn):
            """Try to run one loader function in all compatible ways."""
            if not callable(fn):
                return False

            if name.startswith("__"):
                return False

            # skip imported Qt/PySide classes and obvious classes
            if isinstance(fn, type):
                return False

            # 1 arg: browser
            try:
                result = fn(self.browser)
                if isinstance(result, str) and result.strip():
                    self.run_js(result, f"{path.name}.{name}(browser)")
                zkill_log(f"[ZKILL] loader function used: {path.name}.{name}(browser)")
                return True
            except TypeError:
                pass
            except Exception:
                traceback.print_exc()
                return True

            # 2 args: browser, page
            try:
                result = fn(self.browser, self.browser.page())
                if isinstance(result, str) and result.strip():
                    self.run_js(result, f"{path.name}.{name}(browser,page)")
                zkill_log(f"[ZKILL] loader function used: {path.name}.{name}(browser,page)")
                return True
            except TypeError:
                pass
            except Exception:
                traceback.print_exc()
                return True

            # 0 args: may return JS string
            try:
                result = fn()
                if isinstance(result, str) and result.strip():
                    self.run_js(result, f"{path.name}.{name}()")
                    zkill_log(f"[ZKILL] loader function used: {path.name}.{name}()")
                    return True
            except TypeError:
                pass
            except Exception:
                pass

            return False

        # First try Python loader mode.
        try:
            namespace = {
                "__file__": str(path),
                "__name__": f"eve_local_loader_{path.stem}",
                "browser": self.browser,
                "page": self.browser.page(),
                "QTimer": QTimer,
                "QUrl": QUrl,
            }

            before_keys = set(namespace.keys())
            exec(compile(code, str(path), "exec"), namespace, namespace)

            # 1) Direct known script variables.
            for attr_name in (
                "SCRIPT",
                "JS",
                "SCRIPT_TEXT",
                "script_text",
                "js_text",
                "CHAR_SCRIPT",
                "KILL_SCRIPT",
                "CHAR_JS",
                "KILL_JS",
            ):
                value = namespace.get(attr_name)
                if isinstance(value, str) and value.strip():
                    self.run_js(value, f"{path.name}.{attr_name}")
                    zkill_log(f"[ZKILL] loader variable used: {path.name}.{attr_name}")
                    return True

            # 2) Known function names first.
            known_names = (
                "apply",
                "load",
                "run",
                "inject",
                "main",
                "apply_script",
                "inject_script",
                "load_script",
                "inject_clean_zkill_css",
                "inject_global_zkill_css",
                "inject_zkill_css",
                "inject_char_css",
                "inject_kill_css",
                "apply_zkill_style",
                "apply_char_style",
                "apply_kill_style",
                "get_script",
                "get_js",
                "build_script",
                "build_js",
            )

            for function_name in known_names:
                fn = namespace.get(function_name)
                if call_loader_function(function_name, fn):
                    return True

            # 3) Auto-call every user-defined callable from this loader file.
            # This fixes old zkillCharLoad.py files where the function had a custom name.
            for name, value in list(namespace.items()):
                if name in before_keys or name.startswith("__"):
                    continue

                if callable(value) and call_loader_function(name, value):
                    zkill_log(f"[ZKILL] auto loader function used: {path.name}.{name}")
                    return True

            # 4) Auto-run any large JS-looking string variable with any name.
            for name, value in list(namespace.items()):
                if name.startswith("__"):
                    continue

                if isinstance(value, str) and len(value.strip()) > 50:
                    if any(marker in value for marker in ("document.", "window.", "querySelector", "(function", "const ", "let ")):
                        self.run_js(value, f"{path.name}.{name}")
                        zkill_log(f"[ZKILL] auto JS variable used: {path.name}.{name}")
                        return True

            print(f"[ZKILL] python loader executed but did not expose callable/JS: {path}")
            print("[ZKILL] Fix loader format: add def apply(browser): ... or SCRIPT = <JS string>")
            return False

        except SyntaxError:
            # Raw JS saved as .py.
            self.run_js(code, path.name)
            zkill_log(f"[ZKILL] raw JS loader used: {path.name}")
            return True

        except Exception as e:
            # If Python execution failed, still try raw JS if it looks like JS.
            text = code.strip()
            if any(marker in text for marker in ("document.", "window.", "querySelector", "(function", "const ", "let ")):
                self.run_js(text, path.name)
                zkill_log(f"[ZKILL] raw JS fallback used after python error: {path.name}")
                return True

            print(f"[ZKILL] loader error {path}: {e}")
            traceback.print_exc()
            return False




    def get_external_loader_javascript(self, path: Path) -> str | None:
        """Return JS from zkillCharLoad.py / zkillKillLoad.py when possible.

        This supports loader files that expose:
        - get_character_script()
        - get_kill_script()
        - get_script()
        - get_js()
        - SCRIPT / JS / SCRIPT_TEXT variables

        If a loader is only apply(browser) and does not expose JS, MutationObserver
        cannot reuse it inside the page, so normal direct injection still works.
        """
        try:
            code = path.read_text(encoding="utf-8", errors="ignore")

            # Raw JS saved as .py
            stripped = code.strip()
            if (
                len(stripped) > 50
                and not stripped.startswith(("from ", "import ", "def ", "class "))
                and any(marker in stripped for marker in ("document.", "window.", "querySelector", "(function", "const ", "let "))
            ):
                return stripped

            namespace = {
                "__file__": str(path),
                "__name__": f"eve_local_loader_script_{path.stem}",
                "browser": self.browser,
                "page": self.browser.page() if self.browser else None,
                "QTimer": QTimer,
                "QUrl": QUrl,
            }

            exec(compile(code, str(path), "exec"), namespace, namespace)

            # Known variables first.
            for attr_name in (
                "SCRIPT",
                "JS",
                "SCRIPT_TEXT",
                "script_text",
                "js_text",
                "CHAR_SCRIPT",
                "KILL_SCRIPT",
                "CHAR_JS",
                "KILL_JS",
            ):
                value = namespace.get(attr_name)
                if isinstance(value, str) and value.strip():
                    return value

            # Known no-arg functions.
            for function_name in (
                "get_character_script",
                "get_kill_script",
                "get_script",
                "get_js",
                "build_script",
                "build_js",
                "script",
                "js",
            ):
                fn = namespace.get(function_name)
                if callable(fn):
                    try:
                        value = fn()
                        if isinstance(value, str) and value.strip():
                            return value
                    except TypeError:
                        pass
                    except Exception:
                        pass

            # Any no-arg function returning large JS.
            for name, value in list(namespace.items()):
                if name.startswith("__") or not callable(value) or isinstance(value, type):
                    continue

                try:
                    result = value()
                    if isinstance(result, str) and len(result.strip()) > 50:
                        if any(marker in result for marker in ("document.", "window.", "querySelector", "(function", "const ", "let ")):
                            return result
                except Exception:
                    pass

            # Any large JS-looking string variable.
            for name, value in list(namespace.items()):
                if name.startswith("__"):
                    continue

                if isinstance(value, str) and len(value.strip()) > 50:
                    if any(marker in value for marker in ("document.", "window.", "querySelector", "(function", "const ", "let ")):
                        return value

        except SyntaxError:
            return path.read_text(encoding="utf-8", errors="ignore")

        except Exception:
            if "ZKILL_DEBUG" in globals() and ZKILL_DEBUG:
                traceback.print_exc()

        return None

    def install_dom_observer_for_loader(self, path: Path):
        """Install MutationObserver inside zKill page.

        This removes the need for constant Python timers. The observer reacts only
        when zKill changes the DOM and re-applies the custom loader if the default
        page comes back.
        """
        if not self.browser:
            return False

        loader_js = self.get_external_loader_javascript(path)
        if not loader_js:
            return False

        loader_js_json = json.dumps(loader_js)

        observer_script = f"""
        (function () {{
            if (window.__ELS_ZKILL_OBSERVER_INSTALLED__) {{
                return true;
            }}

            window.__ELS_ZKILL_OBSERVER_INSTALLED__ = true;
            window.__ELS_ZKILL_APPLYING__ = false;
            window.__ELS_ZKILL_APPLY_TIMER__ = null;

            const loaderCode = {loader_js_json};

            function hasCustomView() {{
                return !!document.querySelector("#eve-local-zkill-character-view") ||
                       !!document.querySelector("#eve-local-zkill-view") ||
                       !!document.querySelector("#eve-local-zkill-kill-style") ||
                       !!document.querySelector("#eve-local-zkill-character-style-v5-desktop") ||
                       !!document.querySelector(".eve-zkill-card");
            }}

            function defaultZkillVisible() {{
                return !!document.querySelector("#killlist") ||
                       !!document.querySelector(".navbar") ||
                       !!document.querySelector(".top-menu") ||
                       !!document.querySelector(".dropdown-menu") ||
                       !!document.querySelector("footer");
            }}

            function applyELSLoader(reason) {{
                if (window.__ELS_ZKILL_APPLYING__) {{
                    return;
                }}

                window.__ELS_ZKILL_APPLYING__ = true;

                try {{
                    (new Function(loaderCode))();

                    try {{
                        document.documentElement.setAttribute("data-els-zkill-custom", "1");
                        document.documentElement.setAttribute("data-els-zkill-reason", reason || "observer");
                    }} catch (_) {{}}

                }} catch (e) {{
                    console.error("[ELS MutationObserver loader error] " + (e && e.stack ? e.stack : e));

                }} finally {{
                    setTimeout(function () {{
                        window.__ELS_ZKILL_APPLYING__ = false;
                    }}, 250);
                }}
            }}

            function scheduleCheck(reason) {{
                if (window.__ELS_ZKILL_APPLY_TIMER__) {{
                    clearTimeout(window.__ELS_ZKILL_APPLY_TIMER__);
                }}

                window.__ELS_ZKILL_APPLY_TIMER__ = setTimeout(function () {{
                    window.__ELS_ZKILL_APPLY_TIMER__ = null;

                    if (defaultZkillVisible() && !hasCustomView()) {{
                        applyELSLoader(reason || "dom-change");
                    }}
                }}, 120);
            }}

            const observer = new MutationObserver(function () {{
                scheduleCheck("mutation");
            }});

            observer.observe(document.documentElement || document.body, {{
                childList: true,
                subtree: true,
            }});

            window.__ELS_ZKILL_OBSERVER__ = observer;

            // One immediate check after observer install.
            scheduleCheck("install");

            return true;
        }})();
        """

        self.browser.page().runJavaScript(observer_script)
        return True

    def inject_external_zkill_loader(self) -> bool:
        filename = self.get_loader_for_current_path()

        if not filename:
            return False

        path = self.get_external_loader_path(filename)

        if not path:
            print(f"[ZKILL] external loader not found: {filename}")
            return False

        ok = self.run_external_python_loader(path)

        if ok:
            self.install_dom_observer_for_loader(path)

        return ok

    def inject_global_zkill_css(self):
        if not self.browser:
            return

        script = r"""
        (function () {
            const oldStyle = document.getElementById("eve-local-global-zkill-style");
            if (oldStyle) {
                oldStyle.remove();
            }

            const style = document.createElement("style");
            style.id = "eve-local-global-zkill-style";
            style.textContent = `
                html,
                body {
                    background: #000000 !important;
                    scrollbar-color: #4c535c #08090b !important;
                    scrollbar-width: thin !important;
                }

                * {
                    scrollbar-color: #4c535c #08090b !important;
                    scrollbar-width: thin !important;
                }

                ::-webkit-scrollbar {
                    width: 9px !important;
                    height: 9px !important;
                    background: #08090b !important;
                }

                ::-webkit-scrollbar-track {
                    background: #08090b !important;
                    border: 1px solid #15181d !important;
                }

                ::-webkit-scrollbar-thumb {
                    background: #4c535c !important;
                    border: 1px solid #222831 !important;
                    border-radius: 2px !important;
                }

                ::-webkit-scrollbar-thumb:hover {
                    background: #6b737d !important;
                }

                ::-webkit-scrollbar-corner {
                    background: #08090b !important;
                }

                body {
                    overflow-x: auto !important;
                }
            `;

            document.head.appendChild(style);
        })();
        """

        self.browser.page().runJavaScript(script)
