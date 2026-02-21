# 📝 Changelog

All notable changes to **HoonyTools** will be documented in this file.

---

## 🚀 v2.1.0 — Settings Menu GUI (2026-02-20)

This release introduces a comprehensive Settings GUI accessible via the File menu, enabling users to configure application preferences without editing config files directly.

### Added

- **Settings GUI** (`libs/settings.py`): New modal settings dialog with category-based navigation:
  - Left pane: Dark-mode-compatible category list using `ttk.Treeview`
  - Right pane: Scrollable content area with category-specific settings
  - Bottom buttons: OK, Cancel, Apply (OK applies and closes, Cancel discards, Apply saves but keeps window open)
  - Non-invasive status message at bottom showing "Settings saved" in bold blue text, auto-hides after 3 seconds

- **Connections Category**: Configure Schema 1 and Schema 2 database credentials:
  - Username, Password (with "Show password" toggle), and DSN fields for each schema
  - Validation ensures all three fields are filled if any are provided
  - Credentials saved to `config.ini` and loaded into session memory immediately
  - Eliminates login popup if credentials are pre-configured in Settings

- **Appearance Category**: Theme configuration:
  - Dark Mode checkbox that applies immediately without requiring OK/Apply
  - Syncs bidirectionally with View → Dark Mode menu toggle

- **File Menu Updates**:
  - Added "Settings" menu item (launches Settings GUI)
  - Added separator line between tools and exit
  - Added "Exit" menu item (cleanly closes application)

- **Keyboard Shortcut**: `Ctrl+Alt+S` opens Settings dialog (PyCharm-style)

- **Dark Mode Support for Settings**:
  - Category pane follows dark/light theme
  - Connection entry fields (Username, Password, DSN) switch between black/white backgrounds

### Changed

- **Session Memory Integration**: When credentials are saved via Settings, they are immediately loaded into `session.schemas` memory, preventing unnecessary login popups when using tools.

- **Menu Bar Separator Support**: Updated `_mb()` function to handle `'separator'` menu item type.

### Files Touched

- `libs/settings.py` — **NEW** (~800 lines): Complete Settings GUI implementation
- `HoonyTools.pyw` — Added `_launch_settings()`, `_exit_app()`, exposed `root._dark_mode_var` and `root._toggle_dark`, added keyboard binding, updated `file_items`

---

## 🚀 v2.0.0 — Major Refactoring: Unified Session, Streamlined UI, Word of God Verse Pane (2026-02-20)

This major release delivers a comprehensive refactoring of credential handling, removes the toolbar combobox in favor of direct menu and button access, and introduces an elegant Bible verse display pane.

### Added

- **File Menu**: New "File" menu added to the menu bar (leftmost position) with "M.View Manager" item for launching the Materialized View Manager tool.
- **"Word of God" Verse Pane**: Elegant Bible verse display replacing the simple centered label:
  - LabelFrame with "Word of God" title styled consistently with object panes
  - Fixed-height white content area with word-wrapped verse text
  - **Previous/Next buttons** for manual navigation through verse history
  - Auto-hide scrollbar appears on hover for long verses
  - Verse history tracking — navigate back to previously shown verses
  - Auto-rotation every ~78 seconds (adds to history)
  - Dark mode support (only inner text area changes, border/title unchanged)
- **Unified Session Management**: New `libs/session.py` replaces separate user and DWH session modules:
  - Symmetric dual-schema support (`schema1` and `schema2`)
  - Dynamic pane labels showing "Not Connected" until authenticated, then username
  - Centralized credential storage and connection tracking
  - `session.get_credentials()`, `session.set_credentials()`, `session.register_connection()`, `session.close_connections()` API
- **On-Demand Authentication**: GUI opens directly without mandatory login prompt; credentials requested only when a tool needs database access.
- **Credentials-First Pattern**: Tools prompt for credentials BEFORE showing their GUI, preventing empty tool windows on cancel.

### Changed

- **Database Connector API**: Changed `force_shared=True/False` parameter to `schema='schema1'|'schema2'` for clarity.
- **Config.ini Structure**: Now uses `[schema1]` and `[schema2]` sections instead of `[user]` and `[dwh]`.
- **Tool Access**: All tools now accessed via left pane buttons or File menu instead of toolbar combobox.
- **Object Pane Labels**: Dynamic labels show connection status — "Not Connected" or authenticated username.
- **Object Count Labels**: Repositioned to right edge of pane title area for better alignment with dynamic schema labels.

### Removed

- **Toolbar Combobox**: Removed the "Select Tool" dropdown and associated `_CustomCombobox` class (~200 lines).
- **Run Button**: No longer needed since tools are launched directly from buttons/menus.
- **Exit Button**: Users now close the application using the window X button (which still performs full cleanup via `safe_exit()`).
- **`libs/dwh_session.py`**: Functionality merged into unified `libs/session.py`.
- **`TOOLS` Dictionary**: Tool registry removed; tools wired directly to buttons/menus.
- **Dark Mode Combobox Styling**: Removed ~150 lines of combobox theming code from `set_panes_dark()` and `set_panes_light()`.

### Fixed

- **Duplicate Credentials Prompt**: Fixed issue where canceling credentials prompted again due to `refresh_schemaX_objects()` being called in `on_finish` callback.
- **Malformed Try-Except Blocks**: Fixed several broken try-except structures in `hoonytools.pyw` with duplicate/orphaned code.
- **Menu Bar Dark Mode**: File menu now properly toggles with View and Help menus in dark mode.

### Files Touched

- `HoonyTools.pyw` — Major refactoring: removed toolbar, added File menu, Word of God verse pane, unified session integration
- `libs/session.py` — **REWRITTEN** (~337 lines): Unified session management for both schemas
- `libs/oracle_db_connector.py` — **REWRITTEN**: New `schema=` parameter API with modal login dialog
- `libs/abort_manager.py` — Updated for new session API
- `libs/dwh_session.py` — **DELETED**: Merged into `libs/session.py`
- `tools/pk_designate_gui.py` — Updated to use new session/connector API
- `tools/index_gui.py` — Updated to use new session/connector API
- `tools/object_cleanup_gui.py` — Updated to use new session/connector API
- `tools/mv_refresh_gui.py` — Updated to use new session/connector API
- `loaders/sql_view_loader.py` — Credentials prompt before GUI, uses pre-established connection
- `loaders/sql_mv_loader.py` — Credentials prompt before GUI, uses pre-established connection
- `loaders/excel_csv_loader.py` — Credentials prompt before GUI, connection persists for multiple loads

---

## 🚀 v1.5.5 — Integrated Drop Button & Status Indicator (2026-02-20)

This release integrates the Object Dropper functionality directly into the main GUI's left pane, adds comprehensive status indicator support, and introduces sortable column headers with multi-select capability.

### Added

- **Drop Button in Object Panes**: New "Drop" button added to both User and DWH object panes, replacing the standalone Object Dropper tool from the combobox.
- **Multi-Select Support**: Object lists now support Ctrl+click and Shift+click for selecting multiple objects to drop in a single operation.
- **Ctrl+A Select All**: Press Ctrl+A while focused on an object list to select all items.
- **Sortable Column Headers**: Click any column header (Name, Type, Info) to sort ascending (▲); click again to sort descending (▼).
- **INDEX Objects in List**: User-created indexes (excluding system and PK-backing indexes) now appear in the object list with `Table: TABLE_NAME` in the Info column.
- **PRIMARY KEY Objects in List**: Primary key constraints now appear as droppable objects with `Table: TABLE_NAME` in the Info column.
- **MVIEW LOG Objects in List**: Materialized view logs (MLOG$...) now appear with type "MVIEW LOG" and can be dropped individually.
- **Smart Drop Order**: When batch-dropping, TABLEs are dropped first (auto-dropping their indexes/MLOGs), then other objects. Dependent objects selected alongside their parent table are auto-skipped.
- **Force Drop Option**: Error dialog includes "Force Drop" button for TABLEs that uses `CASCADE CONSTRAINTS PURGE` to handle foreign key dependencies.
- **Status Indicator**: Canvas-based colored circle replaces emoji indicator for better visibility:
  - 🟢 Green: Idle
  - 🔴 Red: Busy (loading/dropping)
  - 🟡 Amber: Aborting
- **Status Indicator for Data Loader**: The Excel/CSV loader now updates the main GUI's status indicator during load operations and abort processing.

### Changed

- **Column Renamed**: "PK" column renamed to "Info" for broader use (shows PK columns for tables, parent table for indexes/PKs/MLOGs).
- **Info Column Format**: Tables with primary keys show `PK: col1, col2`; indexes/PKs/MLOGs show `Table: TABLE_NAME`.
- **Object Dropper Removed from Combobox**: The "☑ Object Dropper" entry has been removed from the tool selector; functionality is now integrated into Drop buttons.
- **MV Backing Tables Excluded**: Tables that are backing tables for Materialized Views are now excluded from the list (only the MV entry is shown).

### Fixed

- **ORA-12083 Error**: Materialized Views are no longer incorrectly identified as TABLEs, preventing "must use DROP MATERIALIZED VIEW" errors.
- **ORA-32417 Error**: MLOG objects are now properly dropped using `DROP MATERIALIZED VIEW LOG ON table_name` instead of `DROP TABLE`.
- **Status Indicator Visibility**: Replaced emoji-based status indicator with canvas-drawn circle for consistent, visible colors across all systems.

### Files touched

- `HoonyTools.pyw` — Added Drop buttons, sortable headers, Ctrl+A, status indicator overhaul, updated refresh queries
- `tools/object_cleanup_gui.py` — Added `drop_objects()`, `_drop_table_indexes()`, `_show_error_dialog()`, `_sort_objects_for_drop()` functions
- `loaders/excel_csv_loader.py` — Added `on_status_change` parameter and status callbacks for load/abort operations

---

## 🚀 v1.5.1 — SQL Preview Window Dark Mode (2026-02-20)

This patch adds pane-only dark mode support to the SQL preview window in the Excel/CSV loader.

### Added

- SQL preview window (`show_sql_preview`) now detects pane-only dark mode via the `Pane.Treeview` ttk style check and applies dark colors to the SQL text area.
- Theme callback registered on the parent window so toggling dark mode while the preview is open updates the SQL text area live.

### Changed

- Only the SQL text area (Text widget) is themed — the window frame, summary label, and buttons remain system default grey, consistent with the pane-only dark mode approach used elsewhere.

### Files touched

- `loaders/excel_csv_loader.py` — `show_sql_preview` function (lines 762-930)

---

## 🚀 v1.5.0 — Data Loader Overhaul + Index Tool (2026-02-20)

This release delivers a complete overhaul of the Excel/CSV loader with a new structured dialog, tight VARCHAR2 sizing for index-friendly columns, inline index selection, and integrated abort functionality. The auto-indexing of PIDM/TERM/STUDENT_ID columns has been removed in favor of user-controlled indexing.

### Added

- **New Index Management Tool** (`tools/index_gui.py`): Full-featured dialog for managing table indexes with column byte-size display, existing index listing, individual/composite index creation modes, key size pre-validation, and drop index support.
- **Structured Data Loader GUI** (`load_files_gui()`): Replaces the old popup-driven flow with a comprehensive dialog featuring:
  - File list treeview with Add/Remove/Clear controls
  - Excel sheet picker for multi-sheet workbooks
  - Batch mode options (separate tables vs. single merged table)
  - VARCHAR2 sizing toggle (tight sizing with 20% buffer vs. fixed 4000)
  - Load mode selection (Create New / Append / Replace / Upsert)
  - Column preview with max length, Oracle size, and sample values
  - **Index column selection**: Multi-select listbox to choose columns for individual index creation after loading
  - **Upsert configuration**: Key column and update column selectors with scrollbars
  - SQL preview for all load modes including Create New
  - Integrated Abort button (moved from main launcher toolbar)
- **Per-file selection persistence**: Index selections and upsert key/update selections are saved per-file and restored when switching between files in the loader.
- **Auto-apply table rename**: Table name changes are automatically applied when the user tabs out or presses Enter in the rename field.
- **SQL Preview for Create New mode**: Shows CREATE TABLE DDL with column definitions and sample INSERT statement before execution.

### Changed

- **Removed auto-indexing**: The automatic creation of indexes on PIDM/TERM/STUDENT_ID columns in `create_table()` has been removed. Users now explicitly select which columns to index via the loader GUI.
- **Removed special-case column sizing**: The hardcoded VARCHAR2(9) for PIDM/STUDENT_ID and VARCHAR2(6) for TERM fallbacks have been removed from `_col_def()`. All columns now use tight sizing from data analysis or fall back to VARCHAR2(4000).
- **Abort button relocated**: The Abort button has been moved from the main HoonyTools toolbar into the Data Loader dialog where it's contextually relevant. It enables during load operations and handles DWH vs. User schema connections appropriately.
- **Upsert MERGE behavior**: Key columns are now automatically excluded from the update set (Oracle ORA-38104 restriction) instead of failing with an error. An info message is logged when this occurs.
- **Window resizing for Upsert mode**: The loader dialog expands from 860px to 1000px height when Upsert mode is selected to accommodate the configuration pane.

### Fixed

- **Critical bug**: `_execute_load()` was missing the `threading.Thread(target=_worker, daemon=True).start()` call, causing the Load button to do nothing.
- **DPY log noise during abort**: Index creation failures during abort now use `abort_manager.is_expected_disconnect()` to downgrade DPY-1001 errors to debug level.
- **Upsert key column error**: Fixed "Removed key columns from update set" error that blocked upsert operations. Key columns are now silently excluded from updates as required by Oracle MERGE.
- **File list not clearing**: The file list pane now clears automatically after successful load completion.

### Files touched

- `loaders/excel_csv_loader.py` — Major refactor: `load_files_gui()`, `_compute_col_sizes()`, `create_table()` changes, `merge_with_checks()` fix, selection persistence, abort integration
- `tools/index_gui.py` — New file for index management tool
- `HoonyTools.pyw` — Added Index/Load buttons to object panes, removed Abort button from toolbar, removed Excel/CSV Loader from TOOLS dict

---

## 🚀 v1.4.6 — Dark mode persistence + selection highlight improvements (2026-02-20)

This patch adds persistent dark mode preference storage and improves dark mode visual fidelity across the launcher and tool windows.

### Added

- Dark mode preference now persists across sessions via a `[preferences]` section in `libs/config.ini`. Toggling dark mode writes `dark_mode = true/false`; on next launch the saved preference is restored automatically before `mainloop()`.
- Selection highlight in dark mode changed from grey (`#444444`) to blue (`#2a6bd6`) across all themed widgets (Treeviews, log text, SQL editors, Listbox popups) for improved visibility.
- `logtype` tag (the "Current Log Type" label in MV Manager) now switches to white `selectforeground` when highlighted, in both dark and light modes, so the blue text remains readable against the blue selection background.

### Changed

- Custom in-window "Dark Mode" menu item changed from a plain command to a proper `checkbutton` with indicator dot; also fixed the `_mb()` check-type handler to correctly extract command and variable from a tuple.
- `selectcolor` (checkbutton indicator dot) set to white (`#ffffff`) in dark mode and black (`#000000`) in light mode on both the native `view_menu` and custom in-window submenus, so the toggle indicator is always visible.

### Fixed

- Dark mode menu checkbutton indicator was invisible (black dot on black background) because the custom menu used a `'command'` type instead of `'check'` type — no indicator was rendered at all. Now renders a proper checkbutton with a white dot in dark mode.
- Inconsistency in initial `log_text` dark selection color (`#222222` from `DARK_THEME["border"]`) vs runtime toggle (`#444444`); both now use `#2a6bd6` via `DARK_THEME["selection_bg"]`.

### Files touched

- `HoonyTools.pyw` — `ConfigParser` import, `_save_dark_mode_pref()` helper, persistence in `_toggle_dark()`, startup restore, `selectcolor` on menus, selection highlight color updates (7 locations), custom menu `'check'` type fix
- `loaders/sql_view_loader.py` — dark mode `selectbackground` updated (2 locations)
- `loaders/sql_mv_loader.py` — dark mode `selectbackground` updated (2 locations)
- `tools/mv_refresh_gui.py` — dark mode `selectbackground` updated (2 locations), `logtype` tag `selectforeground` added (3 locations)

---

## 🚀 v1.4.5 — Pane-only dark mode + modal dialog hygiene (2026-02-20)

This patch refines pane-only dark mode behavior for SQL loaders and hardens dialog parenting so tool windows remain properly modal to the launcher.

### Added

- Shared `safe_messagebox(...)` helper (loaders package) to centralize parented messageboxes with safe fallbacks.

### Changed

- SQL View and SQL MV loaders now apply dark mode only to the content panes (SQL editor + MV name entry), detect theme before widget creation to avoid flash, and register theme callbacks when available (polling fallback retained).
- Messageboxes across MV Manager, Object Cleanup, PK Designate, and Excel/CSV loader now use parented calls for proper modality.
- Oracle connector uses a safe messagebox wrapper for queued errors and login validation.

### Fixed

- Modal dialogs now consistently parent to the active tool window or dialog, reducing focus/stacking issues after prompts.

### Files touched (high level)

- `loaders/sql_view_loader.py`, `loaders/sql_mv_loader.py`, `loaders/__init__.py`
- `tools/mv_refresh_gui.py`, `tools/object_cleanup_gui.py`, `tools/pk_designate_gui.py`
- `loaders/excel_csv_loader.py`, `libs/oracle_db_connector.py`

---

## 🚀 v1.4.0 — Abort & Prompt Robustness Improvements (2026-02-19)

This release improves the Excel/CSV loader and launcher Abort flow so UI remains responsive and cleanup is robust for both user and shared DWH logins.

### Added

- `abort_manager.register_prompt_event()` / `abort_manager.cancel_prompt_event()` to allow background workers waiting on main-thread prompts to be unblocked when the user clicks Abort.

### Changed

- UI prompt scheduling redesigned: `call_ui(...)` now registers a prompt Event when called from a background thread and polls the result so workers can be woken by Abort. This prevents worker threads from becoming permanently blocked while waiting for main-thread dialogs.
- The launcher `abort_process()` now also cancels any registered prompt Event in addition to destroying active prompt windows and attempting to close registered DB connections.
- `cleanup_on_abort()` in `libs/abort_manager.py` hardened: idempotent, defensive, and logs created tables at start of cleanup. It now downgrades expected DPY-1001 (driver "not connected") exceptions to DEBUG when seen in abort/worker contexts.
- The Excel/CSV loader now runs heavy DB work in a background thread and registers the worker connection with `abort_manager` so abort can attempt a best-effort close.

### Fixed

- Prevent noisy ERROR/WARNING logs during normal abort flows by centralizing DPY-1001 handling in `abort_manager.is_expected_disconnect()` and downgrading expected occurrences to DEBUG.
- Resolved race where fallback cleanup attempted to DROP a table that had already been dropped by the primary cleanup; successfully-dropped tables are now removed from the tracking set to avoid duplicate DROP attempts.
- Avoid `grab_set()` usage on login/preview dialogs which could prevent Abort from being processed; dialogs are now transient/topmost/focused without modal grabs.
- Make hidden-root destruction on early login cancel defensive to prevent NameError when `hidden_root` is absent.

### Files touched (high level)

- `libs/abort_manager.py` — added prompt-event helpers, improved cleanup_on_abort, added is_expected_disconnect usage and created_tables tracking hardening
- `loaders/excel_csv_loader.py` — `call_ui` prompt scheduling changes, background worker launch, per-chunk abort checks, created/staging table registration via `abort_manager`
- `libs/oracle_db_connector.py` — login prompt scheduling now registers/clears prompt Events and no longer uses `grab_set()`
- `HoonyTools.pyw` — `abort_process()` cancels prompt Event, defensive `hidden_root` handling

### Notes

- The abort flow now attempts a best-effort fallback cleanup by opening a fresh connection using saved session credentials when the worker connection has been closed to interrupt it. This is best-effort and will log failures when credentials are unavailable or the drop fails.
- Further improvements recommended: sweep remaining driver error codes for similar downgrade semantics (e.g. DPY-4026) and add per-drop fallback instrumentation for rare failures.

---

## 🚀 v1.3.7 — Focus & DWH session reliability fixes (2026-02-19)

This patch improves Toplevel/dialog focus and stacking behavior after messageboxes, and makes shared DWH connection registration and cleanup more robust.

### Added

- `ensure_root_on_top()` / `ensure_builder_on_top()` helpers: briefly set a Toplevel as `-topmost` then clear it so tool windows reliably reappear above the main application after modal dialogs.

### Changed

- Parent messagebox dialogs to their Toplevel where applicable (`parent=builder_window`), and call the small `ensure_*_on_top()` helper afterwards to restore stacking. This prevents hidden tool windows after confirmation dialogs.
- Use safe try/except wrappers around `lift()` / `.attributes()` and parented messagebox calls to avoid failures in environments where those attributes are unsupported.

### Fixed

- Auto-register shared DWH connections returned by `get_db_connection(force_shared=True, root=...)` within `libs/oracle_db_connector.py` using a lazy import of `libs.dwh_session`. Registration is best-effort and will not prevent returning the connection on failure.
- Added `dwh_session.cleanup(root)` usage points to ensure registered shared DWH connections are closed and in-memory DWH credentials cleared where appropriate.

### Files touched

- `loaders/sql_view_loader.py` — parented messageboxes, added `ensure_builder_on_top()`, safer DWH register/cleanup calls.
- `tools/object_cleanup_gui.py` — restored from HEAD and updated dialogs to be parented; added `ensure_root_on_top()` helper and called it after dialogs.
- `loaders/sql_mv_loader.py`, `tools/mv_refresh_gui.py`, `libs/oracle_db_connector.py` — earlier session edits (auto-registration and topmost handling) integrated into this release.

### Notes

- Changes are conservative and wrapped with try/except so they are safe on platforms without full support for `-topmost` or when `tk._default_root` is unavailable to static analysis. Please run a linter/IDE pass for remaining non-fatal diagnostics.
- Manual verification: open the SQL View Loader and MV Manager flows and confirm dialogs are parented and their windows reappear on top after dismissing messageboxes.


---

## 🚀 v1.3.6 — Fix: Ensure DWH connection always closed on early exits (2026-02-19)

This patch fixes a connection leak in the SQL Materialized View Loader when the "Load to DWH" (shared login) option is used but the user cancels or errors out during the materialized-view-log creation flow.

### Fixed

- Wrap the SQL MV Loader `on_submit` flow with a `try/finally` so any `conn` opened by `get_db_connection(force_shared=True)` is always closed, including on early `return` paths and dialog cancellations.
- Close cursors and connections reliably even when DWH credentials are only stored in-memory (`session.dwh_credentials`) and not written to `libs/config.ini`.

### Notes

- This resolves the case where a failed DWH attempt could leave a live connection and later cause unexpected behavior even when the user unchecks the DWH option on a subsequent run.
- No user-visible changes beyond more predictable connection behavior; logging added to help future diagnostics.

### Hotfix

    - Fix: Ensure the main window close button (title-bar X) performs the same full cleanup as the `Exit` button. Previously the X binding used `root.quit`, which only stopped the Tk mainloop and could leave the process in an inconsistent state after certain tool failures. The X now calls the launcher's `safe_exit()` routine so the GUI and any hidden root are destroyed and the process exits reliably.

### Notes (runtime)

- This change harmonizes WM_DELETE_WINDOW behavior with the explicit Exit button, preventing situations where closing a tool then hitting the X on the launcher appeared to do nothing. If you prefer the X to only hide the window (not exit the process), we can adjust to a gentler behavior.

---

## 🚀 v1.3.5 — UI & DWH Refresh Improvements (2026-02-19)

This patch contains several UI improvements and fixes to the DWH refresh/login flow implemented during the current development session.

### Added / Fixed

- Left-pane object lists: two scrollable lists were added to the main launcher — `User Objects` (populated at launch) and `DWH Objects` (populate on demand via Refresh). They run DB queries on background threads and update the UI safely on the main thread.
- Object counters: compact `X Objects` counters placed beside each LabelFrame title. Counters are positioned to avoid changing tree widths and update after refreshes.
- DWH refresh robustness:
  - Prefer saved DWH credentials from `libs/config.ini` or in-memory `session.dwh_credentials` and attempt background connects without prompting.
  - On tns/tnsnames failures (DPY-4026 / missing tnsnames.ora), schedule a single main-thread login prompt to repair credentials and retry automatically.
  - Initialize the Oracle client early and pre-load saved DWH creds after GUI launch to reduce transient tns lookups.
  - Avoid repeated login prompts and noisy stacktraces for common environment errors; display a friendly status and retry flow instead.
- UI alignment and layout:
  - Centered the toolbar (Select Tool + dropdown + Run/Abort/Exit) across the full launcher window.
  - Adjusted left pane padding to align object lists with the log area top.
  - Removed the small legend beneath the toolbar as requested.

### Notes

- Background DB connections still run in worker threads; all UI dialogs (login prompts) are scheduled on the main thread to remain Tk-safe.
- If your DWH DSN is a TNS name and the Oracle Thick client is used, ensure `tnsnames.ora` or `TNS_ADMIN` is configured. Alternatively use an EZCONNECT style DSN (host:port/service) to bypass tnsnames lookup.


### Fixed

- Prevent raw ORA-12000 popups by gating creates with existing-log dialogs and offering Drop & Recreate flows.
- Avoid false positives caused by stale or permission-limited dictionary entries by requiring physical verification and adding debug instrumentation.
- Graceful handling of KeyboardInterrupt/force-quit while MV Manager GUI is open (clean shutdown and resource cleanup).

### Notes

- Debug info buttons write diagnostic counts and helper meta; consider collecting these when filing issues.
- Next recommended steps: add unit tests for `libs/mv_log_utils.py` and optionally cache per-MV detection results to reduce repeated dictionary reads.

---

## 🚀 v1.3.0 — Materialized View Manager & Loader Improvements (2026-02-19)

This release adds safer, centralized materialized-view-log detection and management across the SQL MV Loader and the new Materialized View Manager.

### Added

- Shared helper `libs/mv_log_utils.py` with:
  - `detect_tables_from_sql(sql_text)` — conservative table extraction
  - `get_dependent_mviews(cursor, table)` — dependency lookup across USER_/ALL_DEPENDENCIES
  - `detect_existing_mlog(cursor, table)` — conservative, diagnostic-rich MLOG detection
- Materialized View Manager `tools/mv_refresh_gui.py`:
  - Browse user MVs, request COMPLETE refresh, create/reuse/drop MV logs
  - Compact existing-log dialog with DDL preview, dependency list, and debug info
  - Log type selection (WITH ROWID / WITH PRIMARY KEY) and INCLUDING NEW VALUES option
  - Sticky selection after actions and centered window on open
  - Show Refresh Type (ON DEMAND / ON COMMIT) and per-base Current Log Type in info pane
- SQL Materialized View Loader `loaders/sql_mv_loader.py` integrated the shared helper for base-table detection and safer existing-log handling; UI improvements and wider window geometry
- Primary Key Designator tool `tools/pk_designate_gui.py` — UI to inspect tables and safely add/remove PRIMARY KEY constraints (ALTER TABLE flows with confirmation and dependency checks)

### Changed

- Conservative detection: we now only report an existing materialized view log when a physical `MLOG$_<MASTER>` or a resolvable `LOG_TABLE` can be verified; detection returns diagnostic counters to aid debugging.
- Existing-log flows require explicit checkbox acknowledgement before destructive Drop & Recreate; canceling the dialog prevents accidental CREATE attempts.
- Removed FAST/FORCE refresh options from UIs (unsupported in this environment); only COMPLETE refresh offered.

---

## 🚀 v1.2.2 — Rename Table Cleanup → Object Cleanup; MV / MLOG / PK support (2026-02-18)

This release renames the old Table Cleanup tool to a more capable Object Cleanup tool and extends its capabilities to handle Oracle objects beyond simple tables and views.

### Highlights

- Atomic rename: canonical implementation moved to `tools/object_cleanup_gui.py` and the launcher now imports from it (tool shown in the launcher as **Object Dropper**). The deprecated `tools/table_cleanup_gui.py` file was removed from the tree.
- Added explicit support for dropping MATERIALIZED VIEWs (`DROP MATERIALIZED VIEW`) and materialized view logs (MLOG$ objects) via `DROP MATERIALIZED VIEW LOG ON "schema"."base_table"`.
- Added ability to drop PRIMARY KEY constraints (ALTER TABLE ... DROP CONSTRAINT ...) by listing constraint entries in the selector.
- UI behavior improvements: when a MATERIALIZED VIEW and TABLE share a name the UI prefers the MATERIALIZED VIEW (to avoid accidental drops of the wrong object); object list is deduplicated and sorted deterministically; mouse-wheel scrolling is bound/unbound on enter/leave to avoid Tk errors after window close.

### Notes

- Launcher: `HoonyTools.pyw` now registers the tool as **"☑ Object Dropper"** and imports `drop_user_tables` / `delete_dwh_rows` from `tools.object_cleanup_gui`.
- Backwards compatibility: any scripts or packaged artifacts that referenced the old filename were updated (build/test copies in `build/` and `test_zip/` were adjusted); recommend running smoke tests and CI before shipping.
- Safety: drops still require user confirmation. Test against a development DB before running destructive operations in production.

---

## 🚀 v1.2.1 — Fix: Preserve saved user creds & session DWH reuse (2026-02-18)

Small but important fixes to ensure credentials are not accidentally overwritten and that DWH logins are reused in-memory during a GUI session.

### Fixes

- Prevent `libs/config.ini` from being clobbered when saving DWH credentials by re-reading and merging the on-disk config before writing.
- Ensure the GUI login populates `session.user_credentials` so user-scoped tools don't re-prompt within the same session.
- Allow in-memory reuse of DWH credentials for the running session even when "Save password" is unchecked (so users are not repeatedly prompted during the same GUI run).

### Notes

- `libs/setup_config.py` now merges DWH changes into an existing `libs/config.ini` by default; `--force` still overwrites the file.

---

## 🚀 v1.2.0 – Formatted SQL Preview, Copy & Save (2026-02-18)

This release adds a formatted SQL preview for loader operations with convenient copy and save actions, and robustness improvements to the preview UI.

### Enhancements

- Add formatted SQL preview for `APPEND` / `REPLACE` / `UPSERT` flows in the Excel/CSV loader
- Preview is shown by default (Preview SQL checkbox default: checked)
- Preview window displays readable, line-broken SQL with monospace font and scrollbars
- Add `Copy SQL` button to copy formatted SQL to clipboard
- Add `Save to .sql` button to persist the preview to a file via Save dialog
- Upsert flow now loads a temporary staging table and runs `merge_with_checks(..., dry_run=True)` to produce accurate counts and MERGE SQL; staging is dropped after preview or execution
- Avoid fragile `grab_set()` usage; preview windows and selectors are resilient to focus/grab failures and are centered on the primary monitor

### Fixes

- Prevent crashes caused by `grab_set()` failures on some platforms by wrapping grab calls in try/except
- Ensure preview Toplevels are centered (withdraw/deiconify pattern) so they appear reliably on the primary display

---

## 🔖 v1.1.1 — Credential Isolation Update (2025-04-21)

This release completes a foundational enhancement for multi-schema workflows across all HoonyTools utilities.

### Enhancements

- **Session memory now isolates credentials for DWH and user schema logins**
  - Prevents accidental schema switching when tools are used in mixed order
  - Supports seamless switching between user and DWH tools during the same session
- `session.user_credentials` and `session.dwh_credentials` now independently store logins
- `session.stored_credentials` is used only for displaying the current active user in the footer

### Technical Details

- Refactored `get_db_connection()` in `oracle_db_connector.py` to ensure:
  - `force_shared=True` always uses `session.dwh_credentials`
  - `force_shared=False` always uses `session.user_credentials`
  - Config saving logic is respected per schema and optional per login
- All tools already support schema-scoped connections and require no modification

### Tested Scenarios

- Skipping login at launch, using DWH tool first, then switching to user schema — works correctly
- Save password on either schema — isolated and respected
- UI and credential status display behave as expected

### UI Enhancements

- Added **"Check for Updates"** menu item under Help, linking to the GitHub Releases page
- Cleaned up the **About HoonyTools** popup (removed internal dev notes for a cleaner look)
- Confirmed keyboard shortcut **Alt + H** works to access Help menu (underline behavior is system-controlled)

---

## 🚀 v1.1.0 – Login System Overhaul, Thread Safety, and Versioned Packaging

This milestone release introduces a secure and consistent login flow, thread-safe execution, session-based memory, and a modernized build system with versioned output.

### Login System Enhancements

- New login prompt with **"Save password"** checkbox
- Credentials saved only if explicitly checked
- If unchecked, login prompt will appear every time
- `config.ini` entries are **auto-removed** when checkbox is unchecked
- Unified login logic across **SCFF**, **MIS**, **Excel**, and **Cleanup** tools

### Thread-Safe Oracle Connections

- MIS loader refactored to accept a passed Oracle connection instead of initializing its own
- All login windows are created on the **main thread**, resolving previous crash issues with large files (e.g., FA and SF)
- Eliminated ghost windows and thread violations

### Config & Session Behavior

- Oracle credentials now persist **per user/schema** only when saved
- Session memory used during a single runtime without forcing save
- Prompt respects session status and login method

### Packaging Overhaul

- Output now goes to `build\v1.1.0\HoonyTools\...`
- Distributable ZIP is created at `dist\HoonyTools_v1.1.0.zip`
- All files are placed inside a top-level `HoonyTools/` folder in the archive
- `libs/config.ini` is automatically **excluded** from the ZIP

### Documentation Updates

- Updated `README.md` and `README.txt` to include:
  - Folder structure
  - Login behavior with checkbox
  - Developer note on threading fix for MIS loaders
- Clarified usage of `HoonyTools.pyw` as the new launcher
- Tools list updated to include **SQL View Loader**

### Notable Fixes

- Resolved crash when loading FA/SF files due to Tkinter thread violations
- `get_db_connection()` now always executes in the main thread

---

## 🔁 v1.0.3 – Switch to Python Launcher + ZIP Packaging

This release replaces the standalone `.exe` launcher with a Python-based GUI runner (`.pyw` + `run.bat`), allowing HoonyTools to be distributed cleanly as a ZIP without triggering antivirus or requiring expensive code signing.

### Key Changes

- Switched from EXE to `.pyw` launcher (`HoonyTools.pyw`)
- GUI now runs silently via `pythonw`
- Included `run.bat` for terminal-free launching on Windows
- EXE and PyInstaller packaging removed

### Packaging Method Updated

- New structure: `dist/HoonyTools_v1.0.3.zip`
- ZIP contains clean folder layout under `HoonyTools/`
- `RELEASE/` folder excluded from Git
- Build script (`build_pkg.bat`) introduced for repeatable packaging

### Documentation Update

- `README.md` rewritten to match ZIP-based installation and usage
- Setup guidance for Python 3.13+
- Included folder structure and launcher behavior
- New `README.txt` added for Windows users

### Notes

- All original GUI functionality remains intact
- EXE-free model avoids SmartScreen warnings
- Ideal for Python-capable teams, schools, or secure organizations

---

## [v1.0.2] – Auto Indexing + Terminology Cleanup

### New Features

- Added automatic index creation for common keys:
  - SCFF Loader: indexes `STUDENT_ID` and `ACYR`
  - MIS Loader: indexes `GI90_RECORD_CODE`, `GI01_DISTRICT_COLLEGE_ID`, `GI03_TERM_ID`
  - Excel/CSV Loader: indexes `PIDM`, `TERM`, `STUDENT_ID` (if columns exist)

### Enhancements

- Shortened key field types to prevent `ORA-01450` (max key length exceeded)
- Index creation now runs even if table already exists (with safe error handling)
- Added user notice in Excel sheet loader GUI: indexable columns will be indexed
- Optional CSV rename prompt added to match Excel sheet behavior

### Terminology Cleanup

- Replaced all references to “Aid Year” with “academic year (ACYR)”
- Updated README and SCFF loader logic to explain 2324 → 2023 `ACYR` conversion for Banner compatibility

### Docs

- Added 📈 Automatic Indexing section to README
- Clarified SCFF loader behavior and folder logic

---

## [v1.0.1] – ACYR Terminology Fix and Licensing Clarification

This release fixes a mislabeling issue across SCFF-related scripts and documentation, where `AIDY` (Aid Year) was mistakenly used instead of the correct term `ACYR` (Academic Year). All relevant code, UI labels, and documentation have been updated to reflect this correction.

In addition, licensing language has been refined across the splash screen, README, and LICENSE files to replace "institutional use" with the more neutral term "enterprise use." This ensures clarity while encouraging responsible adoption within larger teams or departments.

🔧 Changes Included:

- Renamed all references of `AIDY` to `ACYR` across:
  - `scff_data_loader.py`
  - `launcher_gui.py`
  - `table_cleanup_gui.py` (now renamed to `object_cleanup_gui.py` — backward-compatible wrapper preserved)
  - `README.md`
- Updated UI labels and logs for consistent terminology
- Reworded licensing language to refer to "enterprise use" instead of "institutional use"
- Splash screen text updated to reflect softer messaging

✅ This update aligns the SCFF tools with naming standards and improves the user experience and adoption clarity for workplace environments.

---

## [v1.0.0] – Initial Public Release: Your Oracle-powered data Swiss Army knife

HoonyTools v1.0.0 is now live!

This marks the first public release of HoonyTools — a portable, no-install Python utility suite designed for analysts and data teams working with Oracle.

🔧 Highlights

- **SQL View Loader**  
  Create or replace Oracle views directly from pasted SQL, with support for your own schema or shared DWH.

- **SCFF Loader**  
  Automatically ingests SCFF text files by ACYR. Supports rollback on abort and skips blank/duplicate lines.

- **MIS Loader**  
  Parses fixed-width `.dat` files using dynamic layouts and loads them into safe `_IN` tables. Auto-detects TERM.

- **Excel/CSV Loader**  
  Uploads Excel sheets or CSVs as new tables with custom names. Supports multiple tabs and blank row cleanup.

- **Table Cleanup Tools**  
  Delete SCFF and MIS records by ACYR or TERM. Also includes general-purpose safe table cleanup by schema.

- **Session Login Support**  
  Shared login popup at launch with support for session or DWH schema use across all tools.

- **Abort-Safe Execution**  
  Tools track new tables and rollback inserts on abort, keeping your Oracle schema clean.

🧭 GUI Tool Legend

| Icon | Meaning                      |
|------|------------------------------|
| ✅   | Uses your Oracle session login |
| 🔒   | Uses shared DWH schema login  |
| 🆕   | New in this version           |
