# 📝 Changelog

All notable changes to **HoonyTools** will be documented in this file.

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
