## 🚟 Notes for Developers

This file documents key implementation details, platform-specific workarounds, and lessons learned during the development of HoonyTools. It is intended to help future contributors maintain stability across platforms and understand why certain design choices were made.

Although HoonyTools now runs as a Python-based `.pyw` app by default, these EXE-specific workarounds remain valuable for any future signed `.exe` packaging (e.g., with PyInstaller + certificate signing).

---

### 🪟 Entry #1: Taskbar Icon Ownership and PyInstaller + Tkinter on Windows

A detailed breakdown of how we ensure HoonyTools shows the correct custom icon in the taskbar when bundled as an `.exe`.

#### Key Findings

- **Taskbar icon is owned by the *first visible Tkinter window*.**  
  We must call `Tk()` and make it visible **before** any splash screens or login prompts. Otherwise, the icon becomes permanently associated with the wrong window.
  
- **Destroying the original `Tk()` root window early (e.g., before GUI loads) causes the taskbar icon to revert to the default feather icon.**  
  To prevent this, we create `hidden_root = Tk()` and **never destroy it** until full exit.

- **`SetCurrentProcessExplicitAppUserModelID()` is required** to reliably attach the embedded `.ico` to the taskbar icon when bundled with PyInstaller.

- **Splash screens and modal popups cannot claim taskbar ownership.**  
  Only the main `Toplevel` window can do so, and it must be shown first.

---

#### Implementation Details

```python
# Inside launcher_gui.py

hidden_root = Tk()
hidden_root.withdraw()  # Keep root hidden but alive to retain taskbar icon

root = Toplevel(hidden_root)  # Main GUI window attached to hidden_root

# Set custom icon and app ID (required for taskbar ownership)
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
root.iconbitmap(default=icon_ico_path)  # .ico file embedded via PyInstaller
```

#### What Breaks It

Creating a splash screen or login window before showing the main GUI

Destroying the original Tk() instance before Toplevel is displayed

Using PhotoImage(...) without keeping a reference
(e.g., forgetting root.icon_img = icon_img) leads to silent icon failure

#### Safe Exit Pattern

```
def safe_exit():
    global is_gui_running
    is_gui_running = False
    try:
        root.destroy()
    except Exception:
        pass
    try:
        hidden_root.destroy()
    except Exception:
        pass
```

---

### 🐞 Entry #2: Loader crash (FA/SF files) and Tkinter thread violation

#### What Happened

When loading FA or SF `.dat` files using a loader, HoonyTools crashed with errors like:

> ❌ `Login prompt must be called from the main thread.`  
> ❌ `Toplevel()` window creation failed due to threading issues

This happened because the loader attempted to open a Tkinter login window (`Toplevel`) inside a background thread — which is not allowed by Tkinter on Windows.

#### What We Learned

- **Tkinter GUI elements must always be created from the main thread.**
- **`Toplevel()` windows used in login prompts must be attached to the `_default_root`.**
- Background loaders must receive the Oracle connection object **after login**, not initiate the login themselves.

#### Fix Implemented

- Moved the call to `get_db_connection()` into the **main thread** (within `run_selected()` in `HoonyTools.pyw`).
- The returned `conn` object is passed into the background loader thread — solving the crash.

---

### 🧾 Entry #3: Build scripts & packaging notes (this dev session)

- Build script: version sanitization (`build_pkg.bat`: prompt handling)
  - Issue: users typing `v1.2.3` or including leading/trailing spaces can produce incorrect `build\v...` folders (e.g., `vv1.2.3`) or unexpected paths.
  - Action: normalize input (trim whitespace, strip leading `v`/`V`) and validate basic semver characters when prompting for version.

- Build script: packaging robustness and 7‑Zip fallback (`build_pkg.bat`: 7-Zip detection)
  - Issue: current script exits if `7z.exe` is not found which breaks packaging on machines without 7‑Zip.
  - Action: fallback to PowerShell `Compress-Archive` or respect an explicitly set `SEVENZIP` env var; log which method is used.

- Build script: ZIP contents and stored paths (`build_pkg.bat`: archive creation)
  - Issue: archive may include unwanted parent paths depending on how 7‑Zip is invoked.
  - Action: `pushd "%RELEASE_DIR%"` then archive `*` so the ZIP root is the project tree; consider `-mx=9` for compression.

- EXE build: spec cleanup (`build_exe.bat`)
  - Note: modified to delete `HoonyTools.spec` only when `dist\HoonyTools.exe` exists. Keep spec on failure for debugging.

- End-user runtime expectations (packaged EXE)
  - EXE built with PyInstaller `--onefile` bundles the Python interpreter and most libs — end users do not need Python nor to run `requirements.txt`.
  - Caveats: native DLLs (MSVC redistributables), external runtimes, hidden imports, and AV/SmartScreen warnings may still affect portability.

- CI / automation considerations
  - Suggest adding `--no-pause` flags or `CI` / `NO_PAUSE` env var checks to skip interactive `pause` calls in `build_pkg.bat` and `build_exe.bat`.

- Cleanup & safety notes
  - The packaging scripts remove `libs\config.ini`, `__pycache__` directories, and `.gitkeep` files before zipping — document these to avoid surprises.

- Test checklist (release verification)
  1. Build on a clean Windows VM without Python installed, copy `dist\HoonyTools.exe` and run — ensure GUI/CLI works.
  2. If DLL errors occur, check for MSVC redistributable and missing native deps.
  3. Inspect ZIP contents to confirm expected file tree.

4. Confirm `HoonyTools.spec` is present when a build fails and removed on success.

---

### 🧪 Entry #4: Session credential handling and config.ini merge (2026-02-18)

Summary: During a development session to improve login UX, we found and fixed two related issues:

- A module-level ConfigParser was read at import time and later written back to disk when saving DWH credentials. If the GUI created or updated `libs/config.ini` after import, the stale parser would overwrite the file and remove newly added sections (for example, a saved user section). This was causing the user's saved credentials to disappear when the DWH password was saved later.
- DWH credentials were not being preserved in memory unless the user checked "Save password" (the code required `session.dwh_credentials.get("save")` to be True to reuse in-memory DWH creds), causing repeated prompts for DWH password within a single GUI session.

Actions taken:

1. When saving DWH credentials, re-read the on-disk config into a fresh `ConfigParser()` and update only the `[dwh]` section before writing. This prevents clobbering other sections added since module import.
2. Adjusted the GUI launcher to set `session.user_credentials = session.stored_credentials` after the initial prompt, ensuring user-scoped tools reuse the in-memory credentials for the running session.
3. Removed the `save == True` requirement for reusing in-memory DWH credentials so the app will reuse `session.dwh_credentials` for subsequent DWH actions in the same session even when the user did not check "Save password".

Result: `libs/config.ini` is now preserved and updated safely; DWH prompts only once per session (unless the user restarts the app), matching the behavior of user-scoped credentials.

Notes / follow-ups:

- Consider logging when an in-memory credential is reused vs read from disk for better diagnostics.
- `libs/setup_config.py` was updated to merge into existing config by default; `--force` remains available to overwrite the file intentionally.

---

### 📝 Entry #5: MV Manager, SQL MV Loader, and PK Designator Enhancements (2026-02-19)

Summary: This dev session added a shared MV log detection helper and improved tooling around materialized views and primary keys. The aim was safer detection, clearer UX for destructive actions, and centralized helpers to reduce duplication.

Changes and rationale:

- Added `libs/mv_log_utils.py` with:
  - `detect_tables_from_sql(sql_text)` — conservative extraction of table tokens from MV queries.
  - `get_dependent_mviews(cursor, table)` — helper to list materialized views that may depend on a master table.
  - `detect_existing_mlog(cursor, table)` — conservative detection that prefers `USER_*` dictionary views, falls back to `ALL_*`, and requires physical `MLOG$_<MASTER>` or resolvable `LOG_TABLE` verification before reporting a log as existing. Returns `diag` counters for debugging.

- SQL Materialized View Loader (`loaders/sql_mv_loader.py`):
  - Integrated `libs/mv_log_utils.detect_tables_from_sql` for base-table detection.
  - Show a compact existing-log dialog when a log is detected; added "Show debug info" button to collect helper meta and dictionary counts.
  - Conservative fallback: if helper reports exists but no columns/deps, verify the physical MLOG presence in `USER_TABLES` (and `ALL_TABLES` only for schema-qualified masters) before treating as existing.

- Materialized View Manager (`tools/mv_refresh_gui.py`):
  - New GUI to list user MVs, run COMPLETE refreshes, and manage MV logs (create, reuse, Drop & Recreate).
  - Removed FAST/FORCE options (unsupported). Only COMPLETE refresh offered.
  - Log creation UI: Log Type radios (`WITH ROWID` / `WITH PRIMARY KEY`) and `INCLUDING NEW VALUES` checkbox.
  - Uses `detect_existing_mlog` to surface existing logs; dialog requires checkbox acknowledgment before destructive changes.
  - Added "Show debug info" that collects `detect_existing_mlog` meta + dictionary counts to help diagnose false positives.
  - Preserve selection (sticky) after actions; center window on open; show `Refresh Type` and per-base `Current Log Type` in the info pane (blue, bolded label).

- Primary Key Designator (`tools/pk_designate_gui.py`):
  - Tool to list tables, detect PK candidates (with configurable DISTINCT threshold), run null/duplicate checks, and create PRIMARY KEY constraints with confirmation and naming heuristics.

Discoveries / gotchas:

- Stale `ALL_MVIEW_LOGS` or `ALL_*` entries can cause false-positive detection when the current user lacks visibility into physical MLOG tables owned by other schemas. We now prefer `USER_*` views and only consult `ALL_*` when the master is schema-qualified.
- Some environments restrict access to `USER_TAB_COLUMNS` or `USER_TABLES`, requiring graceful degradation (show "could not read columns" and surface diagnostic counters).
- ORA-12000 (materialized view log already exists) can be triggered when attempting CREATE without prior DROP; we now gate creates and offer Drop & Recreate flows or prompt on CREATE failures.

Next actions suggested:

1. Add unit tests for `libs/mv_log_utils.detect_existing_mlog` to cover cases: (a) user-owned MLOG present, (b) ALL_MVIEW_LOGS only, (c) LOG_TABLE resolvable to another schema, (d) no visibility / permission errors.
2. Cache per-MV detection results for the GUI session to reduce dictionary queries while navigating.
3. Consider moving per-base detection to a background thread to avoid blocking the UI for very large schemas.

---

### 🧭 Entry #6: Session Work — UI polish & DWH refresh robustness (2026-02-19)

Summary: This development session focused on improving the launcher UI (left-pane object lists, center toolbar) and making the DWH refresh flow robust across different Oracle client configurations (Thin vs Thick, tnsnames lookup). Highlights below document findings, challenges, and decisions made for future maintainers.

Findings
- The Oracle Thick client (when available) attempts to parse `tnsnames.ora` which can cause DPY-4026 errors if `ORACLE_HOME` is set but `tnsnames.ora` is missing. This often manifests only on the first connection attempt unless the client is initialized early.
- Loader tools historically called `get_db_connection()` from the main thread which both initializes the Oracle client and uses the dialog prompt flow; background workers that call `oracledb.connect()` directly can hit environment issues unless the client is initialized first.

Key changes implemented
- Added two scrollable object lists in the left pane: `User Objects` (auto-populate after login) and `DWH Objects` (populate on demand). These run database queries on background threads and use `root.after(0, ...)` to update UI components safely.
- Counters beside each LabelFrame title showing `X Objects` were added; they are positioned to avoid affecting Treeview column widths and update after refreshes.
- DWH refresh flow:
  - Pre-load saved `[dwh]` credentials from `libs/config.ini` into `session.dwh_credentials` at startup so refresh can use them without prompting.
  - Initialize the Oracle client early (call `oracledb.init_oracle_client()` where safe) to reduce DPY-4026 occurrences.
  - When a background connect detects a tns/tnsnames error (DPY-4026 or missing tnsnames), schedule a single main-thread login prompt and retry automatically with updated credentials. Use a module-level guard (`dwh_prompting`) to prevent multiple concurrent prompts.

Challenges
- Ensuring all UI dialogs are created on the main thread while allowing background workers to run DB queries required careful use of `root.after(0, ...)` and explicit session state updates.
- Multi-monitor + mixed-DPI environments complicate centering the main window. Several strategies were tried (Toplevel vs Tk root, Win32 SetWindowPos, monitor-from-cursor). We settled on centering based on the monitor containing the cursor with a fallback to primary monitor.

Notes for future maintenance
- If DPY-4026 continues to appear even with client init, prefer storing an EZCONNECT-style DSN (host:port/service) in `libs/config.ini` to avoid tnsnames lookups.
- When packaging as an EXE with a bundled Oracle Thick client, ensure `TNS_ADMIN` is set or provide a packaged `tnsnames.ora` for the target environment.
- Consider adding a small diagnostic mode (`--diag`) that logs the full ORA/oracledb error chain to help support teams triage connection issues quickly.

Testing checklist
1. With a valid `[dwh]` entry in `libs/config.ini`, restart the app and press DWH Refresh — no prompt should appear and objects should populate.
2. Corrupt the saved DWH DSN (or remove `tnsnames.ora`) and press DWH Refresh — a single login prompt should appear; on successful login the list should populate and `config.ini` updated if Save checked.
3. Ensure no background thread attempts to create UI elements directly (watch logs for "Login prompt must be called from the main thread.").

---

### 🛠 Entry #7: Fix — Ensure DWH connection closed on early exits (2026-02-19)

Findings

- The SQL Materialized View Loader (`loaders/sql_mv_loader.py`) could leave a live DWH connection open when the user checked "Load to DWH" and then cancelled or hit errors during the materialized-view-log flow. This happened regardless of whether DWH credentials were saved to `libs/config.ini` or only held in memory via `session.dwh_credentials`.

Actions taken

- Reworked `on_submit` in the SQL MV Loader to wrap the post-login flow in a `try/finally` and always close `cursor` and `conn` in the `finally` block. This guarantees connections are closed on early `return` paths and on exceptions.
- Added conservative initialization for diagnostic variables (e.g., `mlog_name = None`) to avoid linter warnings and accidental use of unbound variables in diagnostic codepaths.

Notes for developers

1. This fix covers both disk-saved credentials and session-only (in-memory) credentials — closure is performed on the connection object returned by `get_db_connection()` regardless of credential persistence.
2. If you add further early-returns in `on_submit` or similar flows, follow the pattern of opening the connection before the guarded `try` and closing in `finally` to avoid leaks.
3. Consider adding explicit connect/disconnect logging in `libs/oracle_db_connector.py` to make future investigations of leaked sessions easier (I can add this if desired).

Additional findings (close-button / WM_DELETE_WINDOW)

- During investigation we discovered an inconsistency between the launcher Exit button and the window manager close button (title-bar X). The Exit button called a `safe_exit()` routine that performs deterministic teardown and calls `sys.exit()`, while the WM_DELETE_WINDOW binding used `root.quit()` earlier in the launcher. `root.quit()` merely stops the Tk mainloop and does not perform the same cleanup, which could leave the process in an inconsistent state after certain loader/tool failures (for example, when a runner tool raises an exception or is closed unexpectedly).

- Fix applied in launcher (`HoonyTools.pyw`): removed the early `root.protocol("WM_DELETE_WINDOW", root.quit)` binding and bound `WM_DELETE_WINDOW` to `safe_exit()` after `safe_exit()` is defined. `safe_exit()` now does a best-effort `hidden_root.destroy()` if a hidden root exists and then calls `sys.exit()`.

- Developer notes:
  - When creating modal Toplevels in tools, prefer wiring an `on_close` that closes resources (DB connections, cursors) and calls any supplied `on_finish()` callback so the launcher can update UI state safely.
  - Search the codebase for other uses of `root.quit()` or early `WM_DELETE_WINDOW` bindings; they may need to be harmonized to avoid divergent shutdown behavior.
  - If you want the X to only hide the window instead of exiting the process, implement a `safe_hide()` that calls `root.withdraw()` and performs minimal cleanup without `sys.exit()` and bind WM_DELETE_WINDOW to that instead.
