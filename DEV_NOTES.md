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

---

### 🎨 Entry #11: Dark mode persistence + selection highlight improvements (2026-02-20)

Summary: This session added persistent dark mode preference storage to `libs/config.ini`, fixed an invisible menu checkbutton indicator, and changed the dark mode selection highlight from grey to blue across the launcher and all themed tool windows.

Findings

- Dark mode state (`dark_mode_var`) was a `BooleanVar` defaulting to `False` on every launch with no persistence mechanism. The `libs/config.ini` file was already created during first GUI launch (regardless of whether the user saves login credentials), making it a natural location for storing UI preferences without adding new files.
- `configparser` is a Python standard library module — no addition to `requirements.txt` needed.
- The custom in-window menu bar registered the "Dark Mode" item as a `('command', ...)` type, which renders as a plain text menu item with no indicator dot. The `_mb()` helper already had a `'check'` code path for checkbuttons, but it contained a latent bug: when `icmd` was a tuple `(command, variable)`, the whole tuple was passed as `command=` (not callable), and the variable was extracted correctly but the command was lost. Fixed by unpacking `cmd, var = icmd[0], icmd[1]`.
- The `selectcolor` property on tkinter `Menu` widgets controls the checkbutton/radiobutton indicator color. Default is typically black or dark, which is invisible on a black menu background. Setting `selectcolor='#ffffff'` in dark mode and `'#000000'` in light mode resolves this.
- Dark mode selection highlight was `#444444` (dark grey) across all widgets — nearly indistinguishable from the `#000000` background when selecting text or tree items. The `DARK_THEME` dict already defined `selection_bg: '#2a6bd6'` but it was unused in `set_panes_dark()`; all hardcoded values used `#444444` instead.
- An inconsistency existed between initial `log_text` creation (used `DARK_THEME["border"]` = `#222222` for `selectbackground`) and runtime toggle in `set_panes_dark()` (used `#444444`). Both were changed to use `DARK_THEME["selection_bg"]` = `#2a6bd6`.
- The `logtype` tag in `tools/mv_refresh_gui.py` uses `foreground='#66ccff'` (dark mode) or `foreground='blue'` (light mode). Both colors have poor contrast against the `#2a6bd6` selection background. Adding `selectforeground='#ffffff'` to the tag configuration in both modes ensures the text switches to white when highlighted.

Changes made

- `HoonyTools.pyw`:
  - Added `from configparser import ConfigParser` import.
  - Added `_save_dark_mode_pref(is_dark)` helper that safely reads `libs/config.ini`, adds/updates `[preferences] dark_mode`, and writes back without clobbering credential sections (same read-then-write pattern used by DWH credential save).
  - Added `_save_dark_mode_pref(dark_mode_var.get())` call at the end of `_toggle_dark()`.
  - Added startup restore block before `root.mainloop()` that reads `[preferences] dark_mode` from config.ini and applies dark mode if `true`.
  - Changed custom menu "Dark Mode" from `('command', ...)` to `('check', ..., (_toggle_dark, dark_mode_var))`.
  - Fixed `_mb()` check-type handler to correctly unpack `(cmd, var)` from tuple.
  - Added `selectcolor='#ffffff'` to `view_menu` and custom submenus in `set_panes_dark()`; `selectcolor='#000000'` in `set_panes_light()`.
  - Changed 6 dark mode `selectbackground` values from `#444444` to `#2a6bd6` (Treeview style.map x2, log_text x2, Listbox option_add, combobox popup).
  - Fixed initial `log_text` creation to use `DARK_THEME["selection_bg"]` instead of `DARK_THEME["border"]`.

- `loaders/sql_view_loader.py`: Changed 2 dark mode `selectbackground` from `#444444` to `#2a6bd6` (`_apply_theme` and initial creation).

- `loaders/sql_mv_loader.py`: Changed 2 dark mode `selectbackground` from `#444444` to `#2a6bd6` (`_apply_theme` and initial creation).

- `tools/mv_refresh_gui.py`: Changed 2 dark mode `selectbackground` from `#444444` to `#2a6bd6`. Added `selectforeground='#ffffff'` to `logtype` tag in 3 places (dark toggle, light toggle, on-demand re-apply) so the blue text remains readable when selected.

Challenges / notes

- The `_save_dark_mode_pref` helper must re-read `config.ini` from disk before writing (not reuse the module-level `ConfigParser` from `oracle_db_connector.py`) to avoid clobbering credential sections that may have been updated since import. This follows the same pattern established in Entry #4 for DWH credential saving.
- Loaders and tools with dark mode support (`sql_view_loader`, `sql_mv_loader`, `mv_refresh_gui`, `pk_designate_gui`) did not need changes for persistence — they already detect the current theme dynamically from the ttk `Pane.Treeview` style or via `register_theme_callback`. When the main GUI starts in dark mode, child windows pick it up automatically.
- Tools without any dark mode support (`object_cleanup_gui.py`, `excel_csv_loader.py`) remain unchanged — adding dark mode to them is a separate effort.
- The `selectforeground` property on tkinter text tags overrides the foreground color only when that text range is selected. Setting it to an empty string (`''`) resets it to the widget default; setting it to `'#ffffff'` forces white text on selection. We use `'#ffffff'` in both dark and light modes for the `logtype` tag since both `#66ccff` and `blue` have poor contrast against `#2a6bd6`.

Follow-ups

1. Consider adding more UI preferences to the `[preferences]` section (e.g., window geometry, last-used tool, font size) now that the infrastructure exists.
2. Add dark mode support to `tools/object_cleanup_gui.py` and `loaders/excel_csv_loader.py` for full visual consistency.
3. The `apply_dark_theme()` and `apply_light_theme()` functions defined at the top of `HoonyTools.pyw` (lines 32-90) are never called at runtime — they are remnants of an older full-window dark mode approach. Consider removing them or repurposing them if full-window dark mode is planned.

---

### 🔧 Entry #12: Data Loader Overhaul + Index Tool (2026-02-20)

Summary: This session delivered a major overhaul of the Excel/CSV loader, replacing the old popup-driven flow with a structured dialog that supports tight VARCHAR2 sizing, user-controlled indexing, and integrated abort functionality. A new Index Management Tool was also created.

#### Findings

- **Composite index key length limits**: Oracle has a maximum index key length (~6397 bytes for 8KB block size). The old loader created ALL columns as VARCHAR2(4000), making composite indexes impossible (2 columns = 8000 bytes). The new `_compute_col_sizes()` function calculates tight sizes based on actual data: `max(20, ceil(max_byte_length * 1.2))`.

- **Critical bug discovered**: The `_execute_load()` function in the new loader GUI defined `_worker()` and `_load_one_table()` but never actually spawned the worker thread. The `threading.Thread(target=_worker, daemon=True).start()` call was missing, causing the Load button to silently do nothing.

- **Oracle MERGE restriction (ORA-38104)**: Oracle MERGE cannot update columns used in the ON clause. The old `merge_with_checks()` returned `{"ok": False}` when key columns appeared in the update set during dry_run, blocking upsert operations. Fixed to automatically exclude key columns and log an info message instead.

- **Tkinter selection persistence challenge**: When switching between files in the loader treeview, the `<<TreeviewSelect>>` event fires and `_on_file_select()` repopulates all listboxes, losing user selections. Solved by storing selections per-file in the `file_entries` dict and restoring them on re-selection.

- **Batch mode column consistency**: In batch mode (single table from multiple files), all files must have identical columns. The index listbox should show the same columns regardless of which file is selected, so we skip repopulating when `batch_mode_var == 1` and the listbox already has items.

#### Challenges

- **Abort button relocation**: Moving the Abort button from the main launcher into the loader required replicating the abort logic (`abort_manager.set_abort()`, DWH connection closure, prompt event cancellation, connection closure, monitor thread). The loader's abort handler is scoped to the loader dialog and doesn't touch the main launcher UI.

- **DPY-1001 noise during abort**: When abort closes the worker's connection, subsequent operations (like index creation) raise DPY-1001. These are expected during abort and should not spam ERROR logs. Used `abort_manager.is_expected_disconnect(e)` to downgrade to debug level.

- **Upsert listbox scrollbars**: The original upsert key_list and upd_list had no scrollbars, making them unusable with many columns. Added scrollbar frames following the pattern used for idx_list.

- **Window sizing for dynamic content**: The upsert configuration pane is hidden by default and shown when Upsert mode is selected. Without resizing, it gets clipped. Added dynamic `win.geometry()` calls in `_toggle_upsert_frame()` to expand/shrink the window.

- **FocusOut auto-rename**: Users often forget to click "Apply Rename" after editing the table name field. Binding `<FocusOut>` to `_apply_rename()` triggers on every focus loss, including when clicking other UI elements. This works well but could cause issues if `_apply_rename()` had side effects beyond updating the entry — currently safe since it only updates `file_entries` and refreshes the treeview.

#### Architecture decisions

- **Per-file vs. global selections**: Index selections are stored per-file (`file_entries[i]['index_selections']`) so each file can have different index columns in separate mode. In batch mode, a single selection applies to the merged table. Upsert selections follow the same pattern.

- **SQL Preview for Create New**: Unlike Append/Replace/Upsert which operate on existing tables, Create New drops and creates fresh. Added a preview showing CREATE TABLE DDL (with actual column sizes from tight sizing) and sample INSERT to match the preview behavior of other modes.

- **Abort state management**: The loader's `_on_worker_done()` callback re-enables the Load button and disables Abort. The abort monitor thread's `_reenable()` callback also does this if abort completes first. Both paths call `abort_manager.reset()` to clear state for the next operation.

#### Code patterns established

1. **Selection persistence pattern**:
   ```python
   def _save_selections():
       cidx = _current_file_idx[0]
       if cidx is not None and cidx < len(file_entries):
           file_entries[cidx]['index_selections'] = [idx_list.get(i) for i in idx_list.curselection()]
   
   def _on_file_select(event=None):
       _save_selections()  # Save before switching
       # ... populate listbox ...
       # Restore saved selections
       saved = entry.get('index_selections', [])
       for i, item in enumerate(all_items):
           if item in saved:
               idx_list.selection_set(i)
   ```

2. **Main-thread UI from worker pattern**:
   ```python
   result = [None]
   ev = threading.Event()
   def _show():
       result[0] = show_sql_preview(win, title, summary, sql)
       ev.set()
   win.after(0, _show)
   ev.wait()
   if not result[0]:
       return  # User cancelled
   ```

3. **Abort-aware loop pattern**:
   ```python
   for idx_col in index_cols_to_create:
       if getattr(abort_manager, 'should_abort', False):
           logger.info('Abort requested')
           break
       try:
           create_index_if_columns_exist(cursor, schema, tbl_name, [idx_col])
       except Exception as e:
           if abort_manager.is_expected_disconnect(e):
               logger.debug(f'Index creation interrupted: {idx_col}')
           else:
               logger.warning(f'Failed to create index: {e}')
   ```

#### Testing notes

1. **Create New with preview**: Add a CSV, select Create New mode, check Preview SQL, click Load. Verify CREATE TABLE DDL shows correct VARCHAR2 sizes and the preview dialog appears.

2. **Index selection persistence**: Add two CSVs, select index columns for file 1, switch to file 2, select different columns, switch back to file 1. Verify file 1's selections are restored.

3. **Upsert flow**: Load a CSV with ID column, select Upsert mode, choose ID as key, select all other columns for update. Verify the MERGE preview shows key excluded from SET clause.

4. **Abort during index creation**: Load a large file with index columns selected, click Load, then immediately click Abort. Verify no DPY-1001 errors in the log (only debug level).

5. **Batch mode index persistence**: Add two CSVs with identical columns, select batch mode, select index columns, switch between files. Verify selections persist (same columns shown, same selections maintained).

#### Follow-ups

1. Consider adding dark mode support to the loader GUI for visual consistency with other tools.
2. The `create_index_if_columns_exist()` function creates composite indexes from a list. For the loader's per-column indexing, we call it with single-element lists. Consider adding a dedicated `create_single_index()` helper for clarity.
3. The old `load_multiple_files()` function and `select_sheets_gui()` are now dead code but remain in the file. Consider removing them in a cleanup pass.
4. Add validation for batch mode: warn if files have different row counts or data types that might cause issues when merged.

---

### 🎨 Entry #13: SQL Preview Window Dark Mode (2026-02-20)

Summary: Added pane-only dark mode support to the SQL preview window in `loaders/excel_csv_loader.py`. This window is used by all loader flows (create new, append, replace, upsert) to show formatted SQL before execution.

Findings

- The `show_sql_preview` function (line 762) creates all SQL preview windows — a single function serves all 9 call sites across the legacy and new loader flows.
- The original implementation had zero dark mode awareness: the Text widget used default Tk colors (white background, black text) regardless of the main GUI's theme state.
- The file already had a `_theme_cb` for the `load_files_gui` dialog's entry widgets (lines 2645-2664), but it did not cover the preview window.

Implementation

- Added the same `Pane.Treeview` style background check used by `sql_view_loader.py` and `sql_mv_loader.py` to detect dark mode at preview window creation time.
- Applied **pane-only** theming: only the Text widget (`txt`) receives dark colors (`bg='#000000'`, `fg='#e6e6e6'`, `insertbackground='#ffffff'`, `selectbackground='#2a6bd6'`). The Toplevel frame, summary Label, button Frame, and Buttons all remain system default grey.
- Added a `_apply_preview_theme(enable_dark)` callback that updates only the Text widget. Registered on `parent.register_theme_callback` (or `parent.master.register_theme_callback` as fallback) for live toggle support.
- Unregistered callback on `<Destroy>` event to avoid memory leaks and stale references.

Challenges / notes

- Initial implementation applied dark colors to the entire window (Toplevel, Frames, Labels, Buttons), but user feedback clarified that only the SQL pane should change — matching the "pane-only" dark mode approach used in the main GUI.
- The simplification reduced the color palette from 9 variables to 4 (`_txt_bg`, `_txt_fg`, `_sel_bg`, `_ins_bg`) and removed all button/frame styling code.
- The `selectforeground='#ffffff'` is applied in both dark and light modes so selected text is always readable against the `#2a6bd6` selection background.

Follow-ups

1. The main `load_files_gui` dialog still uses default colors for most widgets (Treeviews, column preview). Consider extending pane-only dark mode to those as well for full consistency.
2. Entry #11 noted `excel_csv_loader.py` as not having dark mode support — this entry partially addresses that (preview window only, not the main loader dialog).
