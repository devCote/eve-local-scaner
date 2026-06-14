def get_consent_script() -> str:
    return r"""
(function () {
    if (window.__ELS_CONSENT_CLEANER_INSTALLED__) {
        window.__ELS_RUN_CONSENT_CLEANER__ && window.__ELS_RUN_CONSENT_CLEANER__();
        return;
    }

    window.__ELS_CONSENT_CLEANER_INSTALLED__ = true;

    function textOf(el) {
        return (el && (el.innerText || el.textContent || el.value || "") || "").trim().toLowerCase();
    }

    function clickConsentButtons() {
        const buttons = Array.from(document.querySelectorAll("button, a, input[type='button'], input[type='submit']"));

        for (const btn of buttons) {
            const txt = textOf(btn);

            if (
                txt === "agree" ||
                txt === "i agree" ||
                txt === "accept" ||
                txt === "accept all" ||
                txt === "allow all" ||
                txt.includes("agree") ||
                txt.includes("accept")
            ) {
                try {
                    btn.click();
                } catch (e) {}
            }
        }
    }

    function removeBlockingOverlays() {
        const selectors = [
            ".fc-consent-root",
            ".fc-dialog-container",
            ".fc-dialog-overlay",
            ".fc-ab-root",
            ".fc-ab-dialog",
            ".fc-whitelist-root",
            ".fc-footer-buttons-container",
            ".qc-cmp2-container",
            ".qc-cmp2-main",
            ".qc-cmp-cleanslate",
            "#qc-cmp2-ui",
            "#qc-cmp2-container",
            ".modal-backdrop",
            ".modal",
            "[id^='googlefc']",
            "[class*='fc-'] iframe",
            "iframe[src*='fundingchoices']",
            "iframe[src*='google']"
        ];

        for (const selector of selectors) {
            document.querySelectorAll(selector).forEach(el => {
                try {
                    el.remove();
                } catch (e) {
                    el.style.setProperty("display", "none", "important");
                    el.style.setProperty("pointer-events", "none", "important");
                    el.style.setProperty("visibility", "hidden", "important");
                }
            });
        }

        document.documentElement.style.setProperty("overflow", "auto", "important");
        document.body.style.setProperty("overflow", "auto", "important");
        document.body.style.setProperty("pointer-events", "auto", "important");
    }

    function removeAdblockOverlay() {
        const all = Array.from(document.querySelectorAll("div, section, aside"));

        for (const el of all) {
            const txt = textOf(el);

            if (
                txt.includes("support us by disabling your ad blocker") ||
                txt.includes("disable my adblocker") ||
                txt.includes("ad blocker")
            ) {
                try {
                    el.remove();
                } catch (e) {
                    el.style.setProperty("display", "none", "important");
                    el.style.setProperty("pointer-events", "none", "important");
                }
            }
        }
    }

    function clean() {
        clickConsentButtons();
        removeBlockingOverlays();
        removeAdblockOverlay();
    }

    window.__ELS_RUN_CONSENT_CLEANER__ = clean;

    clean();

    let tries = 0;
    const timer = setInterval(function () {
        clean();
        tries += 1;

        if (tries > 40) {
            clearInterval(timer);
        }
    }, 250);
})();
"""