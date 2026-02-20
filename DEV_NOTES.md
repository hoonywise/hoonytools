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

---

### 🧩 Entry #8: This development session — Focus behavior & DWH session refinements (2026-02-19)

Summary: During this session I focused on two related issues: tool windows becoming hidden behind the main application after modal messageboxes/confirmation dialogs, and ensuring shared DWH connections are auto-registered and reliably cleaned up.

Findings

- Several Toplevels did not pass `parent=` to `messagebox.*` calls; on some Windows setups this allowed the main app window to steal focus and leave the tool window hidden after the modal dialog closed.
- Some modules already used topmost hacks (lift + attributes('-topmost', True/False)) effectively; others lacked a consistent pattern and needed the small helper to restore stacking reliably.
- Auto-registering shared DWH connections at creation time is convenient but must be best-effort to avoid import cycles or masking connection errors.

Changes made

- Added local helpers `ensure_root_on_top()` / `ensure_builder_on_top()` in affected modules to briefly set `-topmost` then clear it and used them after messagebox calls.
- Updated `loaders/sql_view_loader.py` and `tools/object_cleanup_gui.py` to pass `parent=...` for messagebox calls where appropriate, and to call the `ensure_*_on_top()` helper afterward. Messagebox calls are wrapped in try/except with fallbacks.
- Modified `libs/oracle_db_connector.py` to lazily import `libs.dwh_session` and perform a best-effort `dwh_session.register_connection(root, conn)` when `force_shared=True` and a `root` is supplied. Registration failures are logged and ignored so connection returns are not blocked.
- Ensured `dwh_session.cleanup(root)` is invoked where connections are closed so the central session manager can clear in-memory credentials if `[dwh]` is not present in `libs/config.ini`.

Issues encountered / notes for follow-up

1. While editing `tools/object_cleanup_gui.py` I briefly removed the file and restored it from HEAD before applying updates — everything was restored but review the file once more in your IDE to confirm there are no unintended whitespace/indentation changes.
2. There are remaining messagebox call sites across the repo (I found 61 occurrences during grep). I applied conservative fixes to the most user‑visible tools; a full repo-wide automatic rewrite was not performed to avoid accidental behavior changes. If you want full consistency I can prepare a patch that updates all occurrences (I recommend reviewing changes before committing).
3. LSP/static-analysis warnings appeared for some edits (notably `_default_root` references and a few unbound-variable linter hints). These are non-fatal but a linter pass would tidy them; I used guarded constructs (e.g., `getattr(tk, '_default_root', None)`) in places to reduce false positives.

Testing suggestions

1. Open SQL View Loader and trigger missing-SQL and success flows — ensure the builder reappears on top after dismissing dialogs.
2. Run MV Manager and SQL MV Loader flows (create MV, create logs, refresh) and confirm the Toplevels behave correctly after confirmations/errors.
3. Run object cleanup and delete-row flows and confirm dialogs are parented and the root regains topmost stacking afterwards.

Next steps (optional)

1. Do a controlled repo-wide sweep to parent all messagebox calls used inside Toplevels and standardize on `ensure_*_on_top()` helper usage. I can generate a patch and a summary of changes for review.
2. Run a linter (flake8/ruff/mypy) and fix the remaining diagnostics; I can apply low-risk fixes automatically.
3. Add unit tests for `dwh_session` behaviors to verify cleanup clears in-memory credentials only when `[dwh]` section is absent in `libs/config.ini`.

---

### 🧪 Entry #9: Abort & Prompt Robustness (2026-02-19)

Summary: This session hardened the abort flow across the Excel/CSV loader and the launcher so user and DWH loads can be cancelled without blocking the GUI or leaving created/staging tables behind.

Findings

- Background threads can block indefinitely when waiting for a main-thread prompt; previously this stalled abort flows and left partial state in the database.
- Forcibly closing a worker's DB connection (to interrupt a blocking DB call) commonly causes oracledb to raise DPY-1001 (`not connected`) in later worker operations — this is expected and should not be logged as ERROR in abort flows.
- Race between primary cleanup (using the worker's cursor) and fallback cleanup (opening a fresh connection) caused confusing duplicate DROP attempts; tracking must be updated when a drop succeeds.

Changes made

- Added `abort_manager.register_prompt_event(ev)` and `abort_manager.cancel_prompt_event()` to allow the launcher to wake workers waiting on prompts.
- `call_ui()` in `loaders/excel_csv_loader.py` now registers a prompt Event and polls with a short timeout so worker threads can detect aborts while waiting for main-thread dialogs.
- `HoonyTools.pyw` `abort_process()` now cancels registered prompt events in addition to destroying active prompt windows and attempting to close registered DB connections. Closing DWH connections happens in a background thread so the GUI doesn't block.
- `libs/abort_manager.cleanup_on_abort()` made idempotent and defensive: logs created_tables, downgrades DPY-1001 to DEBUG when expected, clears created table tracking after attempts, and performs a best-effort fallback drop using saved session credentials when the worker's connection is closed.
- When a cursor-based DROP succeeds, the table is removed from `created_tables` so the fallback loop does not attempt a duplicate DROP.

Challenges

- Synchronization: `created_tables` is a shared set mutated by worker threads and cleanup logic; a future improvement is to guard it with a `threading.Lock` to avoid subtle races.
- Prompt/event race: care required to clear the registered Event once the prompt completes, as both the main thread and the worker may try to clear it.

Developer notes / follow-ups

1. Consider adding a small lock around `created_tables` mutations (`register_created_table`, `cleanup_on_abort`, and fallback loop) to eliminate race windows.
2. Sweep remaining DPY codes (e.g., DPY-4026) and normalize expected-driver errors via `abort_manager.is_expected_disconnect()` or a new helper to centralize downgrade decisions.
3. Add more instrumentation to fallback cleanup: log which credentials were used, and detailed per-table drop results to aid post-mortem in rare failures.

---

### 🧩 Entry #10: Pane-only dark mode + dialog parenting sweep (2026-02-20)

Summary: This session focused on two related UI quality issues: avoiding white->black flashes when pane-only dark mode is active, and ensuring dialogs remain properly modal and parented to the active tool window.

Findings

- Tk/ttk style lookups are applied at widget creation time for text widgets. If the SQL editor or entry fields are created with default colors and then reconfigured, you can see a visible flash when dark mode is already enabled.
- Unparented messagebox dialogs can cause focus and stacking glitches; the tool window can end up behind the launcher after the dialog closes unless dialogs are parented and (optionally) the tool is lifted after the prompt.

Changes made

- SQL View/MV loaders now detect pane-only dark mode before creating content widgets and create the SQL editor and MV name entry with the correct initial colors to avoid the flash.
- Added a shared `safe_messagebox(...)` helper in the loaders package and switched major tools to use it (MV Manager, Object Cleanup, PK Designate, Excel/CSV loader).
- Added a local safe messagebox wrapper in `libs/oracle_db_connector.py` for queued errors and login validation.

Challenges / notes

- Some modules rely on `_default_root` or UI globals; static analysis may flag these as unknown. We used guarded patterns elsewhere (`getattr(tk, '_default_root', None)`) to keep lint noise down.
- If you expand the safe messagebox sweep, ensure you pass the correct `dlg` (inner dialog vs main tool window) so prompts stay modal to the right window.

Follow-ups

1. Consider extracting the safe messagebox helper into `libs/ui_utils.py` if other non-loader modules need it (avoid circular imports).
2. Run a linter pass after UI edits to catch unbound-variable warnings introduced by large refactors.
