# EVE Local Intel Scanner architecture

## Runtime flow

1. `main.py` starts the app, checks/updates the local SQLite intel database, then imports `ui.py`.
2. `ui.py` owns the main window, General table, Options page, and zKill panel switching.
3. `worker.py` resolves pilots from clipboard data using ESI/zKill/local DB helpers.
4. `zkill_panel.py` and `zkill_viewer.py` render the native API zKill view without QtWebEngine.
5. `zkill_fit_popup.py` only paints the fitting popup now. Fetching/export logic was split out.

## Refactor boundaries

- `app_http_client.py`: shared requests.Session, User-Agent, timeout, retries.
- `zkill_fit_fetcher.py`: killmail/hash/images/type names loading for fitting popup.
- `zkill_fit_export.py`: EFT text export for Save Fit.
- `zkill_fit_utils.py`: shared fitting popup constants/formatting helpers.
- `general_table_options.py`: General Table options dialog.
- `legacy/browser_viewer/`: old browser/QWebEngine implementation kept as backup only.
- `tools/`: local DB/debug/test/benchmark scripts moved out of runtime root.

## Browser status

The runtime app does not import `QWebEngineView` or create a Chromium widget.
The PyInstaller spec explicitly excludes QtWebEngine and pyppeteer.
