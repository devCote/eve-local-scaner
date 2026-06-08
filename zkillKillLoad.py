# zKillboard killmail page cleanup/styling for EVE Local Intel Scanner.
# Applies only to https://zkillboard.com/kill/*


def get_kill_script() -> str:
    return r"""
(function () {
    const path = window.location.pathname;

    const oldCharStyle = document.getElementById("eve-local-zkill-style");
    if (oldCharStyle) oldCharStyle.remove();

    const oldView = document.getElementById("eve-local-zkill-view");
    if (oldView) oldView.remove();

if (/^\/kill\/\d+\/?/.test(path)) {
    const oldStyle = document.getElementById("eve-local-zkill-kill-style");
    if (oldStyle) oldStyle.remove();

    const removeNode = (node) => {
        if (node && node.parentNode) node.parentNode.removeChild(node);
    };

    const removeAll = (selector) => {
        document.querySelectorAll(selector).forEach(removeNode);
    };

    const cleanKillPage = () => {
        removeAll("#navibar");
        removeAll("#zkb-message");
        removeAll(".pbcen");
        removeAll(".pbsep");
        removeAll(".pbblock");
        removeAll("#otherBannerDiv");
        removeAll("#highlightContent");
        removeAll(".publift");
        removeAll(".adrow");
        removeAll("#detailadrow");
        removeAll(".footer");
        removeAll("#comments");
        removeAll("#commentrow");
        removeAll("#disqus_thread");
        removeAll(".modal-backdrop");
        removeAll("#iframed");
        removeAll("#eveworkbench");
        removeAll("#favorite");
        removeAll("#sponsor");

        // Верхняя навигация страницы килла: оставить только Export.
        const detailNav = document.querySelector("#detail-navibar");
        if (detailNav) {
            detailNav.querySelectorAll("li.nav-item").forEach((li) => {
                const text = (li.textContent || "").replace(/\s+/g, " ").trim();
                if (!/^Export\b/i.test(text)) {
                    li.remove();
                }
            });

            detailNav.querySelectorAll("ul.navbar-nav").forEach((ul) => {
                if (!ul.textContent.match(/Export/i)) ul.remove();
            });

            const container = detailNav.querySelector(".container-fluid");
            if (container) {
                container.style.justifyContent = "flex-end";
                container.style.paddingLeft = "0";
                container.style.paddingRight = "0";
            }
        }

        // Убрать Save Fit возле фиттинга, но не трогать Import Fit внутри Export dropdown.
        document.querySelectorAll("a, button").forEach((el) => {
            const text = (el.textContent || "").replace(/\s+/g, " ").trim();
            if (text === "Save Fit") {
                const wrap = el.closest("span") || el;
                removeNode(wrap);
            }
        });

        // Убрать зеленые Verified / EVEShip.Fit / EVE Workbench, если zKill заново добавил блок.
        document.querySelectorAll("a.green").forEach((a) => {
            const text = (a.textContent || "").toLowerCase();
            if (text.includes("verified") || text.includes("eveship") || text.includes("workbench")) {
                const box = a.closest("#eveworkbench") || a.parentElement;
                removeNode(box);
            }
        });

        // Убрать Insurance + login + promo после Items.
        document.querySelectorAll("h1,h2,h3,h4,h5").forEach((h) => {
            const text = (h.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
            if (text.includes("insurance") && text.includes("possible")) {
                const parent = h.closest("center") || h.parentElement;
                removeNode(parent);
            }
        });

        document.querySelectorAll('img[src*="ssologin"], img[src*="mdpromo"], a[href*="markeedragon"], a[href*="ccpoauth2"]').forEach((el) => {
            const parent = el.closest("center") || el.closest("div") || el;
            removeNode(parent);
        });

        // После таблицы involved убрать хвост: related/footer/ads/comments, но сами Final Blow и Involved оставить.
        const details = document.querySelector("#details");
        if (details) {
            let foundInvolved = false;
            Array.from(details.children).forEach((child) => {
                const txt = (child.textContent || "").toLowerCase();
                if (txt.includes("involved") || child.querySelector("tr.attacker")) {
                    foundInvolved = true;
                    return;
                }
                if (foundInvolved) {
                    if (!child.querySelector("tr.attacker") && !txt.includes("final blow") && !txt.includes("top damage")) {
                        child.remove();
                    }
                }
            });
        }

        window.scrollTo(0, 0);
    };

    const style = document.createElement("style");
    style.id = "eve-local-zkill-kill-style";
    style.innerHTML = `
        html,
        body {
            background: #000 !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }

        body {
            color: #d7dbe0 !important;
            font-family: "Droid Sans", "Segoe UI", Arial, sans-serif !important;
        }

        .content,
        .page-shell,
        .page-shell.nobackground,
        span.pagecontent {
            display: block !important;
            width: 100% !important;
            max-width: none !important;
            margin: 0 !important;
            padding: 0 !important;
            background: #000 !important;
        }

        #detail-navibar {
            display: block !important;
            width: 100% !important;
            margin: 0 0 4px 0 !important;
            padding: 0 !important;
            background: #050607 !important;
            border-bottom: 1px solid #252b31 !important;
        }

        #detail-navibar .container-fluid {
            min-height: 26px !important;
        }

        #detail-navibar .nav-link {
            padding: 4px 8px !important;
            color: #d7dbe0 !important;
        }

        #detail-navibar .nav-link:hover,
        #detail-navibar .dropdown.show .nav-link {
            color: #ffffff !important;
            background: rgba(35, 45, 52, 0.9) !important;
        }

        #Fitting_Panel {
            margin-top: 0 !important;
        }

        #eveworkbench,
        #favorite,
        #sponsor,
        .pbcen,
        .pbsep,
        .pbblock,
        .publift,
        .adrow,
        #detailadrow,
        #otherBannerDiv,
        #highlightContent,
        .footer,
        #comments,
        #commentrow,
        #disqus_thread,
        #iframed,
        .modal-backdrop {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
            height: 0 !important;
            max-height: 0 !important;
            overflow: hidden !important;
        }

        a.btn.btn-sm.btn-primary[onclick*="saveFitting"] {
            display: none !important;
        }

        .row {
            margin-left: 0 !important;
            margin-right: 0 !important;
        }

        .col-lg-8,
        .col-lg-4,
        .col-lg-5,
        .col-lg-2 {
            padding-left: 0 !important;
            padding-right: 0 !important;
        }

        table.table {
            margin-bottom: 0 !important;
            border-color: #252b31 !important;
        }

        .table > :not(caption) > * > * {
            background-color: #111 !important;
            border-color: #252b31 !important;
            color: #d7dbe0 !important;
        }

        .table-striped > tbody > tr:nth-of-type(odd) > * {
            background-color: #151515 !important;
        }

        .item_dropped,
        .item_dropped a {
            color: #00cc22 !important;
        }

        .item_destroyed,
        .item_destroyed a {
            color: #ff2222 !important;
        }

        a {
            color: #00aeff !important;
            text-decoration: none !important;
        }

        a:hover {
            color: #ffffff !important;
            text-decoration: underline !important;
        }

        /* Same dark EVE scrollbar as character pages */
        ::-webkit-scrollbar {
            width: 10px !important;
            height: 10px !important;
            background: #050607 !important;
        }

        ::-webkit-scrollbar-track {
            background: #050607 !important;
            border-left: 1px solid #252b31 !important;
        }

        ::-webkit-scrollbar-thumb {
            background: #5e646b !important;
            border-radius: 8px !important;
            border: 2px solid #050607 !important;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #88909a !important;
        }

        ::-webkit-scrollbar-corner {
            background: #050607 !important;
        }
    `;
    document.head.appendChild(style);

    cleanKillPage();
    setTimeout(cleanKillPage, 400);
    setTimeout(cleanKillPage, 1200);
    setTimeout(cleanKillPage, 2500);
    return;
}

})();
    """
