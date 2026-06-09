# zKillboard character page rebuild for EVE Local Intel Scanner.
# Applies only to https://zkillboard.com/character/*
#
# Important:
# This script intentionally DOES NOT try to keep styling the original zKill DOM.
# It reads data from the original page, creates one clean local view, and hides the
# original zKill content. This prevents old/new CSS mixing and removes double UI.


def get_character_script() -> str:
    return r"""
(function () {
    const path = window.location.pathname;
    if (!/^\/(?:character|alliance|corporation|region|system)\/\d+\/?/.test(path)) {
    return;
    }

    const CHARACTER_STYLE_ID = "eve-local-zkill-character-style-v5-desktop";
    const CHARACTER_VIEW_ID = "eve-local-zkill-character-view";

    function removeElement(el) {
        if (el && el.parentNode) el.parentNode.removeChild(el);
    }

    function removeById(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function absoluteHref(href) {
        if (!href) return "#";
        try { return new URL(href, window.location.origin).href; }
        catch (_) { return href; }
    }

    function safeText(el) {
        return (el && el.textContent ? el.textContent : "").replace(/\s+/g, " ").trim();
    }

    function cleanHtmlFromCell(el) {
        if (!el) return "";
        const clone = el.cloneNode(true);
        clone.querySelectorAll("script,style,.ttooltip,[rel='tooltip'] .ttooltip").forEach(removeElement);
        clone.querySelectorAll("a").forEach((a) => {
            a.setAttribute("href", absoluteHref(a.getAttribute("href")));
            a.removeAttribute("onclick");
            a.removeAttribute("target");
        });
        return clone.innerHTML.trim();
    }

    function cleanInfoHtml(el) {
        if (!el) return "";
        const clone = el.cloneNode(true);
        clone.querySelectorAll(
            '[id^="tracker-remove-"],#tracker-add,#tracker-none,#track-entity,.fa-plus,.fa-minus,script,style'
        ).forEach(removeElement);
        clone.querySelectorAll("a").forEach((a) => {
            a.setAttribute("href", absoluteHref(a.getAttribute("href")));
            a.removeAttribute("onclick");
            a.removeAttribute("target");
        });
        return clone.innerHTML.trim();
    }

    function getCharacterId() {
        const m = path.match(/^\/character\/(\d+)/);
        if (m) return m[1];
        if (typeof entityID !== "undefined") return String(entityID);
        return "";
    }

    function getActivePage() {
        if (/\/kills\/?/.test(path)) return "kills";
        if (/\/losses\/?/.test(path)) return "losses";
        return "overview";
    }

    function forceDesktopSourceDom() {
        // zKill uses Bootstrap responsive blocks. In a narrow embedded QWebEngine
        // it exposes mobile markup. We do not want mobile layout here, so remove
        // the mobile-only pieces from the source DOM before rebuilding our view.
        document.querySelectorAll(
            '.d-table-row.d-md-none, .d-md-none:not(.nav-item), .nav-mobile-shell .d-md-none'
        ).forEach(removeElement);

        // User requested: do not load/render the right stats column:
        // <div class="col-12 col-md-6 float-end" ...>...</div>
        document.querySelectorAll('.overview-top > .col-12.col-md-6.float-end').forEach(removeElement);

        // Keep desktop fields available even when the webview is narrow.
        document.querySelectorAll('.d-none.d-md-table-cell, .d-none.d-md-block, .d-none.d-md-flex').forEach((el) => {
            el.classList.remove('d-none');
        });
    }

    function getHeaderData() {
        const characterId = getCharacterId();
        const portrait =
            document.querySelector('.overview-top img[src*="/characters/"][src*="portrait"]') ||
            document.querySelector('img[src*="images.evetech.net/characters/"][src*="portrait"]') ||
            document.querySelector('meta[property="og:image"], meta[name="twitter:image"]');

        let portraitSrc = "";
        if (portrait) {
            portraitSrc = portrait.getAttribute("src") || portrait.getAttribute("content") || "";
            portraitSrc = portraitSrc.replace(/size=\d+/, "size=128");
        }
        if (!portraitSrc && characterId) {
            portraitSrc = `https://images.evetech.net/characters/${characterId}/portrait?size=128`;
        }

        const nameEl = document.querySelector('[itemprop="name"]');
        const corpEl = document.querySelector('[itemprop="corporation"]');
        const allianceEl = document.querySelector('[itemprop="alliance"]');
        const secEl = document.querySelector('[itemprop="sec_status"]');
        const birthdayEl = document.querySelector('[itemprop="birthday"]');

        let nameHtml = cleanInfoHtml(nameEl);
        if (!nameHtml) {
            const title = (document.title || "").split("|")[0].trim();
            nameHtml = title || "Unknown";
        }

        return {
            characterId,
            portraitSrc,
            nameHtml,
            corpHtml: cleanInfoHtml(corpEl) || "-",
            allianceHtml: cleanInfoHtml(allianceEl) || "-",
            secHtml: cleanInfoHtml(secEl) || "-",
            birthdayHtml: cleanInfoHtml(birthdayEl) || "-"
        };
    }

    function getStatsHtml() {
        // Keep only the compact progress bars block. Do not keep full statsbox table.
        const candidates = Array.from(document.querySelectorAll("table.alltime-ranks"));
        const table = candidates.find((t) => t.querySelector(".progress"));
        if (!table) return "";

        const clone = table.cloneNode(true);
        clone.querySelectorAll("script,style").forEach(removeElement);
        clone.querySelectorAll("a").forEach((a) => {
            a.setAttribute("href", absoluteHref(a.getAttribute("href")));
            a.removeAttribute("onclick");
        });
        return clone.outerHTML;
    }

    function getPagerHtml() {
        const pager = document.querySelector('.float-end.d-flex.align-items-center.gap-2');
        if (!pager || !pager.querySelector(".pagination")) return "";

        const clone = pager.cloneNode(true);
        clone.querySelectorAll("script,style").forEach(removeElement);
        clone.querySelectorAll("input").forEach((input) => {
            input.removeAttribute("id");
            input.removeAttribute("onclick");
            input.removeAttribute("onchange");
            input.setAttribute("readonly", "readonly");
        });
        clone.querySelectorAll("a").forEach((a) => {
            a.setAttribute("href", absoluteHref(a.getAttribute("href")));
            a.removeAttribute("onclick");
        });
        return clone.outerHTML;
    }

    function makeTabs(characterId, active) {
        const base = `/character/${characterId}/`;
        const tabs = [
            ["overview", "Overview", base],
            ["kills", "Kills", `${base}kills/`],
            ["losses", "Losses", `${base}losses/`],
        ];

        return `
            <div class="els-zkb-tabs">
                ${tabs.map(([key, label, href]) => `
                    <a class="els-zkb-tab ${active === key ? "active" : ""}" href="${href}">${label}</a>
                `).join("")}
            </div>
        `;
    }

    function extractKillRows() {
        const rows = [];
        const sourceRows = Array.from(document.querySelectorAll("#killlist tbody tr"));

        for (const row of sourceRows) {
            if (row.classList.contains("tr-date")) {
                const dateText = safeText(row).replace(/^\s+|\s+$/g, "");
                if (dateText) rows.push({ type: "date", date: dateText });
                continue;
            }

            if (!row.classList.contains("tr-killmail")) continue;

            const cells = row.children;
            if (!cells || cells.length < 5) continue;

            const timeCell = cells[0];
            const shipCell = row.querySelector("td.icon") || cells[1];
            const locationCell = row.querySelector("td.location") || cells[2];
            const victimCell = row.querySelector("td.victim");
            const finalCell = row.querySelector("td.finalBlow");

            const time = safeText(timeCell.querySelector(".float-end")) || safeText(timeCell).split(/\s+/)[0] || "";
            const priceEl = timeCell.querySelector('a[href*="/kill/"] span[raw], a[href*="/kill/"] span');
            const price = safeText(priceEl);
            const killLinkEl = timeCell.querySelector('a[href*="/kill/"]') || row.querySelector('a[href*="/kill/"]');
            const killHref = absoluteHref(killLinkEl ? killLinkEl.getAttribute("href") : "#");

            const img = shipCell ? shipCell.querySelector("img.shipImageRender, img[src*='/types/'][src*='render'], img[src*='/types/']") : null;
            let shipSrc = img ? img.getAttribute("src") : "";
            if (shipSrc) shipSrc = shipSrc.replace(/size=\d+/, "size=64");
            const shipAlt = img ? (img.getAttribute("alt") || "Ship") : "Ship";

            const pip = shipCell ? shipCell.querySelector("img.pip") : null;
            let pipSrc = pip ? pip.getAttribute("src") : "";
            if (pipSrc && /pip_tech1/i.test(pipSrc)) pipSrc = "";

            const characterId = getCharacterId();
            const activePage = getActivePage();
            let result = "kill";

            // zKill does not always give reliable row classes on character overview
            // after the page is loaded in a narrow embedded browser. Decide losses
            // by page type first, then by victim cell containing this character.
            if (activePage === "losses") {
                result = "loss";
            } else if (activePage === "kills") {
                result = "kill";
            } else if (row.classList.contains("lossloss") || row.classList.contains("loss")) {
                result = "loss";
            } else if (victimCell && characterId) {
                const victimOwnLink = victimCell.querySelector(`a[href*="/character/${characterId}/"]`);
                if (victimOwnLink) result = "loss";
            }

            rows.push({
                type: "killmail",
                result,
                time,
                price,
                killHref,
                shipSrc,
                shipAlt,
                pipSrc,
                locationHtml: cleanHtmlFromCell(locationCell),
                victimHtml: cleanHtmlFromCell(victimCell),
                finalHtml: cleanHtmlFromCell(finalCell),
            });
        }

        return rows;
    }

    function rowToHtml(row) {
        if (row.type === "date") {
            return `<tr class="els-date-row"><th colspan="5"><em>${row.date}</em></th></tr>`;
        }

        const resultClass = row.result === "loss" ? "els-loss-row" : "els-kill-row";
        const resultIcon = row.result === "loss" ? "✕" : "✓";
        const pipHtml = row.pipSrc ? `<img class="els-ship-pip" src="${row.pipSrc}" alt="">` : "";
        const shipHtml = row.shipSrc
            ? `<a class="els-ship-link" href="${row.killHref}"><span class="els-ship-box"><img class="els-ship-img" src="${row.shipSrc}" alt="${row.shipAlt}">${pipHtml}</span></a>`
            : "";

        return `
            <tr class="${resultClass}">
                <td class="els-time-cell">
                    <div><span class="els-result-icon">${resultIcon}</span><span class="els-time">${row.time || ""}</span></div>
                    ${row.price ? `<a class="els-price" href="${row.killHref}">${row.price}</a>` : ""}
                </td>
                <td class="els-ship-cell">${shipHtml}</td>
                <td class="els-location-cell">${row.locationHtml || ""}</td>
                <td class="els-victim-cell">${row.victimHtml || ""}</td>
                <td class="els-final-cell">${row.finalHtml || ""}</td>
            </tr>
        `;
    }

    function installLinkHandler() {
        const view = document.getElementById(CHARACTER_VIEW_ID);
        if (!view || view.dataset.elsLinksReady === "1") return;
        view.dataset.elsLinksReady = "1";

        // QWebEngine sometimes does not follow links reliably inside a DOM rebuilt
        // with innerHTML while zKill scripts are still changing the page. Use one
        // delegated click handler and navigate explicitly.
        view.addEventListener("click", function (event) {
            const link = event.target.closest("a[href]");
            if (!link || !view.contains(link)) return;

            const href = link.getAttribute("href");
            if (!href || href === "#" || href.startsWith("javascript:")) return;

            event.preventDefault();
            event.stopPropagation();
            window.location.href = absoluteHref(href);
        }, true);
    }

    function buildView() {
        const header = getHeaderData();
        const active = getActivePage();
        const rows = extractKillRows();
        const pagerHtml = getPagerHtml();
        const listTitle = active === "losses" ? "Losses" : "Kills";

        let view = document.getElementById(CHARACTER_VIEW_ID);
        if (!view) {
            view = document.createElement("div");
            view.id = CHARACTER_VIEW_ID;
            document.body.appendChild(view);
        }

        view.innerHTML = `
            <div class="els-char-root">
                <div class="els-char-top">
                    <div class="els-char-info-block">
                        <img class="els-char-portrait" src="${header.portraitSrc}" alt="portrait">
                        <table class="els-char-info-table">
                            <tbody>
                                <tr><th>Character:</th><td>${header.nameHtml}</td></tr>
                                <tr><th>Corporation:</th><td>${header.corpHtml}</td></tr>
                                <tr><th>Alliance:</th><td>${header.allianceHtml}</td></tr>
                                <tr><th>Sec. Status:</th><td>${header.secHtml}</td></tr>
                                <tr><th>Birthday:</th><td>${header.birthdayHtml}</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                ${makeTabs(header.characterId, active)}

                <div class="els-list-toolbar">
                    <div class="els-list-title">${listTitle}</div>
                    <div class="els-pager-wrap">${pagerHtml}</div>
                </div>

                <table class="els-kill-table">
                    <colgroup>
                        <col class="els-col-time">
                        <col class="els-col-ship">
                        <col class="els-col-location">
                        <col class="els-col-victim">
                        <col class="els-col-final">
                    </colgroup>
                    <thead>
                        <tr>
                            <th class="els-time-head">Time</th>
                            <th class="els-ship-head">Ship</th>
                            <th class="els-location-head">Location</th>
                            <th class="els-victim-head">Victim</th>
                            <th class="els-final-head">Final Blow</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.length ? rows.map(rowToHtml).join("") : `<tr><td colspan="5" class="els-empty">No killmails loaded yet...</td></tr>`}
                    </tbody>
                </table>
            </div>
        `;

        installLinkHandler();
    }

    function applyStyle() {
        [
            "eve-local-zkill-style",
            "eve-local-zkill-character-style",
            "eve-local-zkill-kill-style",
            "eve-local-zkill-kill-style-v2",
            "eve-local-zkill-style-v2",
            "eve-local-zkill-style-v3",
            CHARACTER_STYLE_ID,
        ].forEach(removeById);

        const style = document.createElement("style");
        style.id = CHARACTER_STYLE_ID;
        style.textContent = `
            html, body {
                background: #000 !important;
                color: #d7dbe0 !important;
                margin: 0 !important;
                padding: 0 !important;
                width: 100% !important;
                min-height: 100% !important;
                overflow-x: auto !important;
                overflow-y: auto !important;
                font-family: "Droid Sans", "Segoe UI", Arial, sans-serif !important;
                font-size: 11px !important;
            }

            body > *:not(#${CHARACTER_VIEW_ID}) {
                display: none !important;
                visibility: hidden !important;
            }

            #${CHARACTER_VIEW_ID} {
                display: block !important;
                visibility: visible !important;
                width: 100% !important;
                min-height: 100% !important;
                background: #000 !important;
                box-sizing: border-box !important;
            }

            * { box-sizing: border-box !important; }
            a { color: #00bfff !important; text-decoration: none !important; }
            a:hover { color: #ffffff !important; text-decoration: underline !important; }

            ::-webkit-scrollbar { width: 10px; height: 10px; background: #050607; }
            ::-webkit-scrollbar-thumb { background: #5e646b; border-radius: 8px; border: 2px solid #050607; }
            ::-webkit-scrollbar-thumb:hover { background: #88909a; }
            ::-webkit-scrollbar-corner { background: #050607; }

            .els-char-root {
                width: 100% !important;
                min-width: 0 !important;
                max-width: none !important;
                min-height: 100% !important;
                padding: 4px 5px 7px 5px !important;
                background: #000 !important;
            }

            .els-char-top {
                display: flex !important;
                align-items: flex-start !important;
                gap: 0 !important;
                width: 100% !important;
                padding: 0 0 5px 0 !important;
                border-bottom: 1px solid #252b31 !important;
            }

            .els-char-info-block {
                display: flex !important;
                align-items: flex-start !important;
                gap: 7px !important;
                min-width: 0 !important;
                flex: 1 1 auto !important;
                width: 100% !important;
            }

            .els-char-portrait {
                width: 86px !important;
                height: 86px !important;
                min-width: 86px !important;
                object-fit: cover !important;
                border-radius: 3px !important;
                background: #111 !important;
            }

            .els-char-info-table {
                border-collapse: collapse !important;
                background: transparent !important;
                margin: 0 !important;
                min-width: 0 !important;
            }

            .els-char-info-table th,
            .els-char-info-table td {
                border: none !important;
                background: transparent !important;
                padding: 1px 4px !important;
                line-height: 1.25 !important;
                vertical-align: top !important;
                color: #d7dbe0 !important;
                white-space: nowrap !important;
            }

            .els-char-info-table th {
                color: #ffffff !important;
                font-weight: 700 !important;
                text-align: left !important;
            }

            .els-char-stats {
                flex: 0 1 48% !important;
                min-width: 230px !important;
                max-width: 50% !important;
                opacity: 0.86 !important;
                padding-top: 1px !important;
            }

            .els-char-stats table,
            .els-char-stats tbody,
            .els-char-stats tr,
            .els-char-stats td {
                background: transparent !important;
                border: none !important;
                color: #d7dbe0 !important;
                padding: 2px 3px !important;
                margin: 0 !important;
            }

            .els-char-stats .progress {
                height: 13px !important;
                background: #111820 !important;
                border-radius: 0 !important;
                margin: 0 !important;
                overflow: hidden !important;
            }

            .els-char-stats .progress-bar {
                font-size: 10px !important;
                line-height: 13px !important;
                color: #dce9ed !important;
                box-shadow: none !important;
            }

            .els-char-stats .red { color: #ff3030 !important; }
            .els-char-stats .green { color: #00c020 !important; }

            .els-zkb-tabs {
                display: flex !important;
                align-items: center !important;
                gap: 0 !important;
                margin: 5px 0 6px 0 !important;
                border-bottom: 1px solid #1b2228 !important;
                background: #030405 !important;
                height: 25px !important;
            }

            .els-zkb-tab {
                display: flex !important;
                align-items: center !important;
                height: 25px !important;
                padding: 0 9px !important;
                color: #cdd4db !important;
                border-bottom: 1px solid transparent !important;
            }

            .els-zkb-tab.active {
                color: #ffffff !important;
                border-bottom-color: #00b899 !important;
            }

            .els-list-toolbar {
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
                min-height: 25px !important;
                gap: 8px !important;
                margin: 0 0 4px 0 !important;
            }

            .els-list-title {
                color: #ffffff !important;
                font-weight: 700 !important;
                opacity: 0.9 !important;
            }

            .els-pager-wrap {
                display: flex !important;
                justify-content: flex-end !important;
                align-items: center !important;
                min-width: 0 !important;
            }

            .els-pager-wrap .float-end,
            .els-pager-wrap .d-flex {
                float: none !important;
                display: flex !important;
                align-items: center !important;
                gap: 5px !important;
            }

            .els-pager-wrap input {
                width: 70px !important;
                height: 23px !important;
                background: #071018 !important;
                color: #d7dbe0 !important;
                border: 1px solid #26333d !important;
                border-radius: 3px !important;
                text-align: center !important;
                font-size: 11px !important;
            }

            .els-pager-wrap ul.pagination {
                display: flex !important;
                gap: 2px !important;
                margin: 0 !important;
                padding: 0 !important;
                list-style: none !important;
            }

            .els-pager-wrap .page-link {
                display: block !important;
                min-width: 22px !important;
                height: 23px !important;
                line-height: 21px !important;
                text-align: center !important;
                padding: 0 5px !important;
                background: #071018 !important;
                color: #d7dbe0 !important;
                border: 1px solid #26333d !important;
                border-radius: 2px !important;
            }

            .els-pager-wrap .active .page-link {
                background: #00665c !important;
                border-color: #00b899 !important;
                color: #ffffff !important;
            }

            .els-kill-table {
                width: 100% !important;
                min-width: 0 !important;
                table-layout: fixed !important;
                border-collapse: collapse !important;
                margin: 0 !important;
                background: #000 !important;
                border: 1px solid #222a31 !important;
            }

            .els-kill-table th {
                background: #151b20 !important;
                color: #ffffff !important;
                font-weight: 400 !important;
                text-align: left !important;
                border: 1px solid #313b45 !important;
                padding: 2px 3px !important;
                line-height: 1.05 !important;
            }

            .els-kill-table td {
                color: #d7dbe0 !important;
                border: 1px solid rgba(80, 90, 98, 0.35) !important;
                padding: 2px 3px !important;
                vertical-align: top !important;
                line-height: 1.12 !important;
                overflow: hidden !important;
            }
            .els-col-time { width: 70px !important; }
            .els-col-ship { width: 54px !important; }
            .els-col-location { width: 86px !important; }
            .els-col-victim { width: auto !important; }
            .els-col-final { width: auto !important; }

            .els-time-head,
            .els-ship-head,
            .els-location-head,
            .els-victim-head,
            .els-final-head {
                min-width: 0 !important;
                max-width: none !important;
            }

            .els-ship-head { text-align: center !important; }

            .els-date-row th {
                background: #171c21 !important;
                color: #ffffff !important;
                font-weight: 700 !important;
                font-size: 11px !important;
                padding: 3px 5px !important;
                border: 1px solid #222a31 !important;
            }

            .els-kill-row { background: #002f0a !important; }
            .els-loss-row { background: #4a0000 !important; }
            .els-kill-row:hover { background: #00440f !important; }
            .els-loss-row:hover { background: #650000 !important; }
            .els-time-cell {
                width: 70px !important;
                min-width: 70px !important;
                max-width: 70px !important;
                white-space: nowrap !important;
                color: #ffffff !important;
                font-weight: 700 !important;
            }

            .els-result-icon {
                color: #dcebed !important;
                font-weight: 700 !important;
                display: inline-block !important;
                width: 14px !important;
                margin-right: 1px !important;
            }

            .els-price {
                display: block !important;
                color: #00bfff !important;
                margin-left: 16px !important;
                margin-top: 2px !important;
                font-weight: 400 !important;
            }
            .els-ship-cell {
                width: 54px !important;
                min-width: 0 !important;
                max-width: none !important;
                padding: 1px !important;
                text-align: center !important;
                vertical-align: middle !important;
                overflow: visible !important;
            }

            .els-ship-link,
            .els-ship-box {
                display: inline-block !important;
                width: 50px !important;
                height: 50px !important;
                position: relative !important;
                overflow: hidden !important;
                vertical-align: middle !important;
            }

            .els-ship-img {
                display: block !important;
                width: 50px !important;
                height: 50px !important;
                object-fit: cover !important;
                border-radius: 3px !important;
            }

            .els-ship-pip {
                position: absolute !important;
                top: 0 !important;
                left: 0 !important;
                width: 12px !important;
                height: 12px !important;
                max-width: 12px !important;
                max-height: 12px !important;
                z-index: 3 !important;
            }
            .els-location-cell {
                width: auto !important;
                min-width: 0 !important;
                max-width: none !important;
                white-space: normal !important;
                word-break: normal !important;
                overflow-wrap: anywhere !important;
            }

            .els-victim-cell,
            .els-final-cell {
                white-space: normal !important;
                word-break: normal !important;
                overflow-wrap: anywhere !important;
            }
            .els-victim-cell,
            .els-final-cell {
                width: auto !important;
                min-width: 0 !important;
                max-width: none !important;
            }

            .els-empty {
                text-align: center !important;
                padding: 18px !important;
                color: #8d98a4 !important;
                background: #040506 !important;
            }

        `;
        document.head.appendChild(style);
    }

    // Full reset: remove every old custom view/style first, then rebuild one clean view.
    [
        "eve-local-zkill-view",
        "eve-local-zkill-character-view",
        "eve-local-zkill-style",
        "eve-local-zkill-character-style",
        "eve-local-zkill-kill-style",
        "eve-local-zkill-style-v2",
        "eve-local-zkill-style-v3",
        CHARACTER_STYLE_ID,
    ].forEach(removeById);

    forceDesktopSourceDom();
    buildView();
    applyStyle();
})();
    """
