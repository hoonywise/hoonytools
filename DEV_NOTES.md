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

---

### 🗑️ Entry #14: Integrated Drop Button, Status Indicator & Oracle Object Handling (2026-02-20)

Summary: This session integrated the Object Dropper tool directly into the main GUI's left pane as Drop buttons, added comprehensive status indicator support, and resolved several Oracle-specific object handling challenges.

#### Key Implementation Details

**1. Drop Button Integration**

- Added "Drop" button to both User and DWH object panes in `_make_objects_frame()`.
- Enabled multi-select on Treeviews with `selectmode="extended"` for batch dropping.
- Created `_get_selected_objects(tree)` helper to extract all selected items as a list of dicts.
- The `drop_objects()` function in `object_cleanup_gui.py` handles the actual drop logic with confirmation dialog.

**2. Sortable Column Headers**

- Implemented `_make_sortable_tree(tv)` helper that binds click handlers to column headings.
- Sort state tracked per-column in a closure; clicking toggles between ascending (▲) and descending (▼).
- Headers update with arrow indicators to show current sort direction.
- Required updating `_recreate_tree()` to also call the sortable setup and preserve the new column name ("info" instead of "pk").

**3. Ctrl+A Select All**

- Added `_bind_select_all(tv)` helper that binds `<Control-a>` and `<Control-A>` to select all items.
- Uses `tv.selection_set(tv.get_children(''))` to select all rows.

**4. Oracle Object Type Challenges**

- **Materialized View dual entries**: Oracle creates both a `MATERIALIZED VIEW` and a `TABLE` object with the same name for each MV. Had to add an `EXISTS` subquery to exclude the TABLE entry when an MV exists, otherwise dropping would fail with `ORA-12083: must use DROP MATERIALIZED VIEW`.

- **MLOG tables**: Materialized view logs appear as TABLEs named `MLOG$_TABLENAME`. Detection done by checking if name starts with `MLOG$`. Must use `DROP MATERIALIZED VIEW LOG ON base_table` syntax, not `DROP TABLE`.

- **PK-backing indexes**: Indexes that back primary key constraints cannot be dropped directly without dropping the constraint first. Excluded these from the index list using `NOT EXISTS` subquery against `all_constraints`.

- **Drop order matters**: When batch-dropping a table and its MLOG together, the table must drop first (which auto-drops the MLOG). Implemented `_sort_objects_for_drop()` to order: TABLE → MATERIALIZED VIEW → VIEW → MVIEW LOG → INDEX → PRIMARY KEY.

- **Auto-skip dependent objects**: Track which tables are being dropped; skip INDEXes/MLOGs/PKs whose parent table is in the drop set to avoid "object doesn't exist" errors.

**5. Status Indicator Overhaul**

- **Problem**: Emoji-based status indicator (`🟢`/`🔴`) rendered as tiny grey circles with minimal color visibility on some systems due to font/emoji rendering differences.

- **Solution**: Replaced with a `tk.Canvas` widget containing a drawn oval (circle). Created a `StatusLight` wrapper class that implements `.config(text=...)` to maintain compatibility with existing code that sets emoji text.

- **Color mapping**:
  - `🟢` / `'idle'` → Green (#22c55e)
  - `🔴` / `'busy'` → Red (#ef4444)  
  - `⏳` / `'aborting'` → Amber (#f59e0b)

**6. Status Callback Pattern**

- Added `on_status_change` parameter to `drop_objects()` and `load_files_gui()`.
- Helper function `_set_main_status(status)` defined inside each function to safely call the callback.
- Callback called with `'busy'` when operation starts, `'aborting'` when abort requested, `'idle'` when complete.
- Includes `parent.update_idletasks()` and `parent.update()` to force UI refresh during synchronous operations.

#### Challenges Encountered

1. **Global vs local variable timing**: `status_light` widget is created late in `launch_tool_gui()` but drop handlers are defined earlier. Initially tried storing reference on `root._status_light` but simpler solution was using the global `status_light` variable directly since it's declared in the function's global scope.

2. **`_recreate_tree()` losing features**: This function recreates Treeviews when toggling themes. Had to update it to use new column name ("info"), enable multi-select, and call both `_make_sortable_tree()` and `_bind_select_all()` on the new tree.

3. **MLOG drop syntax**: Initial implementation tried `DROP TABLE` which fails with `ORA-32417`. Oracle requires `DROP MATERIALIZED VIEW LOG ON base_table_name` syntax. Had to extract base table name from MLOG object name (`MLOG$_TABLENAME` → `TABLENAME`).

4. **Force Drop scope**: `CASCADE CONSTRAINTS PURGE` only applies to TABLEs. The "Force Drop" button in the error dialog is only shown for TABLE objects.

#### Files Modified

| File | Changes |
|------|---------|
| `HoonyTools.pyw` | `_make_sortable_tree()`, `_bind_select_all()`, `_make_objects_frame()` (Drop button), `_recreate_tree()` updates, `_update_status_light()`, `StatusLight` class, updated refresh queries for INDEX/PK/MLOG |
| `tools/object_cleanup_gui.py` | `drop_objects()`, `_drop_table_indexes()`, `_show_error_dialog()`, `_sort_objects_for_drop()`, `_get_table_for_object()` |
| `loaders/excel_csv_loader.py` | `on_status_change` parameter, `_set_main_status()` helper, status callbacks in load/abort flows |

#### Follow-ups

1. Consider adding status indicator support to other tools (SQL View Loader, MV Manager, PK Designator).
2. The `_recreate_tree()` function is getting complex; may benefit from refactoring to use a shared configuration object.
3. Could add a "Select All of Type" feature (e.g., right-click to select all TABLEs).

---

### 🔄 Entry #15: v2.0.0 — Symmetric Dual-Schema Refactoring (2026-02-20)

Summary: This major release completely restructures HoonyTools' authentication and session management. The app now launches directly to the GUI without a mandatory login prompt, implements symmetric "schema1/schema2" architecture for identical handling of both database connections, and introduces a redesigned UI with a custom menu bar and "Word of God" verse pane.

#### Architecture Changes

**1. Unified Session Management**

- **Merged `libs/session.py` and `libs/dwh_session.py`** into a single unified `libs/session.py` (~337 lines).
- Session state stored in a `schemas` dict with symmetric structure:
  ```python
  schemas = {
      'schema1': {'credentials': None, 'label': 'Not Connected'},
      'schema2': {'credentials': None, 'label': 'Not Connected'}
  }
  ```
- Key API functions:
  - `get_credentials(schema)` — returns credentials dict or None
  - `set_credentials(schema, creds)` — stores credentials in memory
  - `register_connection(root, conn, schema)` — tracks connection for cleanup
  - `close_connections(root, schema=None)` — closes and cleans up connections
- Credentials dict uses `user` key (not `username`) for the username field.

**2. Simplified Database Connector**

- **Changed parameter from `force_shared=True/False` to `schema='schema1'|'schema2'`**.
- `get_db_connection(schema='schema1', root=None)` — returns connection or None.
- Modal login dialog with `grab_set()` to block interaction with parent windows.
- Thread-safe pattern: connection established on main thread BEFORE spawning worker threads (Tkinter dialogs must run on main thread).

**3. Config.ini Structure**

- Renamed sections from `[user]`/`[dwh]` to `[schema1]`/`[schema2]`:
  ```ini
  [schema1]
  user = hoonywise
  password = ...
  dsn = HOONYDB

  [schema2]
  user = dwh
  password = ...
  dsn = HOONYDB
  ```

#### GUI Changes

**1. Removed Mandatory Login**

- GUI now opens directly without login prompt.
- Each schema pane has on-demand authentication — credentials requested only when user interacts with that pane.

**2. Removed Toolbar Elements**

- Removed combobox (M.View Manager selector).
- Removed Run button.
- Removed Exit button.

**3. Added Custom Menu Bar**

- File menu with "M.View Manager" item.
- Dark mode support: menu background changes with theme toggle.
- Menu bar uses `before=verse_outer_frame` pack order to appear at top.

**4. Redesigned Verse Pane**

- LabelFrame titled "Word of God" with Previous/Next buttons.
- Fixed-height (50px) white content area with word-wrapped text.
- Auto-hide scrollbar on hover for long verses.
- Verse history for Previous/Next navigation.
- Dark mode affects only inner text area (white→black bg, black→white text).
- Text color: black in light mode, pure white in dark mode.

**Verse Pane Spacing Controls** (line references in hoonytools.pyw):
- Line 564: `verse_outer_frame.pack(..., padx=10, pady=(top, bottom))` — gap from window edge and above/below verse pane
- Line 568: `verse_labelframe = tk.LabelFrame(..., padx=6, pady=4)` — padding inside the LabelFrame
- Line 572: `verse_labelframe.pack(..., padx=(left, right))` — gap between outer frame and bordered pane

**5. Variable Renaming**

- All `user_*` variables renamed to `schema1_*`.
- All `dwh_*` variables renamed to `schema2_*`.
- Provides symmetric, schema-agnostic naming throughout codebase.

#### Files Modified

| File | Changes |
|------|---------|
| `libs/session.py` | **REWRITTEN** — Unified session management |
| `libs/oracle_db_connector.py` | **REWRITTEN** — New `schema=` parameter API with modal login |
| `libs/abort_manager.py` | Updated for new session API |
| `libs/dwh_session.py` | **DELETED** — Functionality merged into `libs/session.py` |
| `hoonytools.pyw` | Extensive changes (see GUI Changes above) |
| `tools/pk_designate_gui.py` | Updated to use new API |
| `tools/index_gui.py` | Updated to use new API |
| `tools/object_cleanup_gui.py` | Updated to use new API |
| `tools/mv_refresh_gui.py` | Updated to use new API |
| `loaders/sql_view_loader.py` | Credentials prompt before GUI |
| `loaders/sql_mv_loader.py` | Credentials prompt before GUI |
| `loaders/excel_csv_loader.py` | Credentials prompt before GUI, connection persists |
| `CHANGELOG.md` | v2.0.0 entry added |

#### Key Discoveries

1. **Duplicate prompt issue**: When user cancelled credentials, the connector returned but launcher called `refresh_schemaX_objects()` which prompted again. Fixed by checking `session.get_credentials()` before refreshing.

2. **Modal dialog grab**: Login dialog needed `grab_set()` to block interaction with parent windows during credential entry.

3. **Thread-safe connections**: Load GUI must establish connection on main thread BEFORE spawning worker thread — Tkinter dialogs cannot be created from background threads.

4. **Menu bar pack order**: Custom menu bar must use `before=verse_outer_frame` to appear at top of window.

5. **Auto-hide scrollbars**: Attempted for object list panes but rolled back as it "looked messy". Kept only for verse pane.

6. **`_recreate_tree()` function**: Called during dark mode toggle, must also implement auto-hide scrollbar if that feature is enabled for a pane.

7. **Malformed try-except blocks**: Found and fixed several broken try-except structures with duplicate/orphaned code in hoonytools.pyw.

#### Testing Checklist

1. **Launch without login**: Start HoonyTools — GUI should appear immediately without any login prompt.

2. **Schema1 on-demand auth**: Click on schema1 object list or use a tool targeting schema1 — login prompt should appear only then.

3. **Schema2 on-demand auth**: Click on schema2 object list — separate login prompt for schema2 credentials.

4. **Credential persistence**: Save credentials for both schemas, restart app — saved credentials should auto-populate login dialogs.

5. **File menu**: Verify "M.View Manager" appears in File menu and launches the MV Manager tool.

6. **Verse pane navigation**: Click Previous/Next buttons — verse should change and history should work correctly.

7. **Verse pane dark mode**: Toggle dark mode — only the verse text area should change colors (not the LabelFrame border or buttons).

8. **All tools functional**: Test each tool (PK Designator, Index Tool, Object Cleanup, MV Manager) — all should work with new API.

9. **All loaders functional**: Test each loader (SQL View, SQL MV, Excel/CSV) — credentials should be requested before GUI opens.

#### Migration Notes for Developers

- Replace `force_shared=True` with `schema='schema2'`.
- Replace `force_shared=False` with `schema='schema1'`.
- Replace `session.user_credentials` with `session.get_credentials('schema1')`.
- Replace `session.dwh_credentials` with `session.get_credentials('schema2')`.
- Replace `dwh_session.register_connection()` with `session.register_connection(root, conn, 'schema2')`.
- Replace `dwh_session.cleanup()` with `session.close_connections(root, 'schema2')`.

---

### ⚙️ Entry #16: Settings Menu GUI Implementation (2026-02-20)

This session focused on creating a comprehensive Settings GUI (`libs/settings.py`) with a category-based navigation pattern similar to IDE preferences dialogs.

#### Architecture Decisions

1. **Category-Content Pattern**: Left pane shows categories (Treeview), right pane dynamically loads content based on selection. Content builders are registered in a `CATEGORIES` dictionary, making it easy to add new categories later.

2. **`entry_refs` Dictionary**: Central storage for widget references, allowing cross-function access to entry fields, theme callbacks, and parent window references. System keys are prefixed with `_` (e.g., `_parent`, `_status_label`, `_win`).

3. **Preserved References on Category Switch**: When switching categories, `entry_refs.clear()` is called to reset widget references, but system references (`_parent`, `_status_label`, `_win`) are preserved to maintain functionality.

#### Key Challenges & Solutions

1. **Login Popup Still Appearing After Settings Save**
   - **Problem**: User saves credentials in Settings, but tools still showed login popup.
   - **Root Cause**: Settings saved to `config.ini` but didn't update `session.schemas` memory. `get_db_connection()` checks memory first, finds `None`, shows popup.
   - **Solution**: After saving to config.ini, call `session.set_credentials()` to update memory, or `session.clear_credentials()` if fields are blanked.

2. **Status Message Not Appearing**
   - **Problem**: "Settings saved" message wasn't visible after clicking Apply.
   - **Root Cause**: `entry_refs.clear()` in `_on_category_select()` was removing `_status_label` reference.
   - **Solution**: Preserve system references when clearing entry_refs:
   ```python
   preserved = {
       '_parent': entry_refs.get('_parent'),
       '_status_label': entry_refs.get('_status_label'),
       '_win': entry_refs.get('_win'),
   }
   entry_refs.clear()
   entry_refs.update(preserved)
   ```

3. **Dark Mode Toggle Not Working in Appearance Panel**
   - **Problem**: Checking/unchecking Dark Mode checkbox had no effect.
   - **Root Cause**: `_on_dark_mode_toggle()` used local `parent` variable captured at function definition, but after category switch the reference was stale.
   - **Solution**: Always retrieve parent from `entry_refs.get('_parent')` inside the callback function.

4. **Dark Mode Syncing Between Settings and View Menu**
   - **Challenge**: Dark Mode checkbox in Settings must sync bidirectionally with View → Dark Mode menu.
   - **Solution**: 
     - Exposed `root._dark_mode_var` and `root._toggle_dark` on the main window
     - Settings reads initial state from `parent._dark_mode_var.get()`
     - On toggle, Settings calls `parent._toggle_dark()` which updates the menu and triggers theme callbacks
     - Theme callbacks notify Settings dialog to update its own appearance

5. **Connection Fields Dark Mode — Too Much Black**
   - **Problem**: Initial implementation made entire Connections pane black (labels, frames, checkbuttons).
   - **Solution**: Simplified to only style Entry widgets (Username, Password, DSN fields), leaving labels and frames with default grey appearance.

#### Implementation Details

**Status Bar Pattern**:
```python
# Pack status bar FIRST with side='bottom' so it stays at bottom
status_frame = tk.Frame(win, bg='SystemButtonFace')
status_frame.pack(side='bottom', fill='x')

# Then pack main content to fill remaining space
main_paned.pack(fill='both', expand=True)
```

**Auto-Hide Status Message**:
```python
def _show_status_message(message, error=False):
    status_label.config(text=message, fg='#005a9e')  # Bold blue
    win.after(3000, lambda: status_label.config(text=''))  # Clear after 3s
```

**Theme Callback Chain**:
1. User toggles Dark Mode in Settings
2. `_on_dark_mode_toggle()` calls `parent._toggle_dark()`
3. `_toggle_dark()` applies theme and notifies all registered callbacks
4. Settings' `_apply_theme()` callback receives notification
5. `_apply_theme()` updates category pane AND calls `_conn_apply_theme()` if Connections panel exists

#### Files Created/Modified

| File | Changes |
|------|---------|
| `libs/settings.py` | **NEW** — Complete Settings GUI (~800 lines) |
| `HoonyTools.pyw` | Added `_launch_settings()`, `_exit_app()`, exposed theme vars, keyboard shortcut |

#### Testing Checklist

1. **Open Settings**: File → Settings or `Ctrl+Alt+S` — dialog should open centered
2. **Category Navigation**: Click Connections, then Appearance — content should swap
3. **Save Credentials**: Enter Schema 1 credentials, click Apply — "Settings saved" message should appear
4. **Credentials Persist**: Close Settings, use a tool — should NOT show login popup
5. **Dark Mode Toggle**: Check Dark Mode in Appearance — main GUI should update immediately
6. **Bidirectional Sync**: Toggle View → Dark Mode — Settings checkbox should reflect change when reopened
7. **Connection Fields Theme**: In dark mode, entry fields should be black with white text
8. **Validation**: Enter partial credentials (e.g., only username) — should show validation error
9. **Cancel Discards**: Make changes, click Cancel — changes should not be saved
10. **Exit Menu**: File → Exit — application should close cleanly

---

### 🧹 Entry #17: Code Cleanup Attempt — Lessons Learned (2026-02-20)

Summary: This session attempted a comprehensive code cleanup including dead code removal, unused file deletion, and utility function consolidation. While some changes were successfully applied, a regression was introduced that required manual rollback of most changes.

#### The Big Oops 🚨

After completing Phase 3 (consolidating duplicate utility functions into a shared `libs/gui_utils.py` module), a critical regression was discovered: **the application began prompting for credentials even when they were already saved in Settings**. The expected behavior was that saved credentials would be loaded at startup and tools would connect without prompting.

The user had to manually rollback changes to restore proper credential handling. Investigation did not conclusively identify the root cause — the changes appeared correct and the credential flow code was not directly modified. Possible causes include:
- Import order side effects from the new `gui_utils.py` module
- Subtle interaction between module loading and `session.load_saved_credentials()` timing
- An unrelated concurrent change that was conflated with the cleanup work

**Lesson learned**: When making sweeping refactoring changes across multiple files, test incrementally after each phase rather than batching all changes together. This would have identified which specific change caused the regression.

#### What Was Attempted

**Phase 1: Dead Code Removal**
- Removed `process_queued_errors()` and `_error_queue` from `libs/oracle_db_connector.py`
- Simplified `show_error_safe()` to log errors from background threads instead of queueing
- Removed `_get_current_user()` from `libs/mv_log_utils.py`
- Removed `select_sheets_gui()` (~76 lines) from `loaders/excel_csv_loader.py`
- Removed `show_replace_column_selector()` (deprecated) from `loaders/excel_csv_loader.py`

**Phase 2: Unused File Deletion**
- Deleted `libs/layout_definitions.py` (457 lines) — confirmed unused via grep
- Deleted `libs/setup_config.py` (55 lines) — obsolete CLI setup script
- Kept `libs/bible_books.py` — initially thought unused but discovered it IS used by HoonyTools.pyw for bible verse display

**Phase 3: Utility Function Consolidation (caused regression)**
- Created `libs/gui_utils.py` with shared functions:
  - `center_window(window, width, height)` — center a Tkinter window on screen
  - `quote_ident(name)` — quote an Oracle identifier for safe SQL use
  - `detect_dark_from_style()` — detect if dark mode is active via ttk style
  - `ensure_dialog_parent(parent)` — return a Toplevel attached to parent or new Tk
- Updated 8 files to import from `libs/gui_utils.py` instead of defining locally

#### What Was Successfully Applied (kept after rollback)

- **Dark mode button styling**: Login dialog buttons now apply dark mode styling using the shared helper
- **Splash screen character fix**: Fixed invalid/garbled character display
- **Deleted `libs/layout_definitions.py`**: 457 lines of unused layout constants

#### Potentially Unused Functions Discovered

During the cleanup analysis, the following functions/code were identified as potentially dead but NOT removed due to the rollback:

**`libs/oracle_db_connector.py`**:
- `process_queued_errors()` — error queue system for background threads (never called after initial cleanup)
- `_error_queue` — Queue object supporting the above

**`libs/mv_log_utils.py`**:
- `_get_current_user()` — helper to get Oracle username (no callers found)

**`loaders/excel_csv_loader.py`**:
- `select_sheets_gui()` (~76 lines) — legacy Excel sheet selector dialog (replaced by new loader GUI)
- `show_replace_column_selector()` — deprecated column selector (marked as such in comments)
- `load_multiple_files()` — legacy multi-file loader flow (replaced by `load_files_gui()`)

**`HoonyTools.pyw`** (top of file):
- `apply_dark_theme()` (~30 lines) — full-window dark mode function (never called, remnant of older approach)
- `apply_light_theme()` (~30 lines) — counterpart to above (never called)

**`libs/layout_definitions.py`** (DELETED):
- Entire file (457 lines) — layout constants not imported anywhere

**`libs/setup_config.py`** (attempted deletion, status unknown after rollback):
- Entire file (55 lines) — obsolete CLI script for initial config setup

#### Duplicate Code Patterns Found

These functions were duplicated across multiple files and could be consolidated in a future cleanup:

| Function | Files Where Duplicated |
|----------|----------------------|
| `center_window()` | `HoonyTools.pyw`, `tools/pk_designate_gui.py`, `tools/object_cleanup_gui.py` |
| `_quote_ident()` / `quote_ident()` | `tools/index_gui.py`, `tools/pk_designate_gui.py` |
| `_detect_dark_from_style()` / `_detect_dark_mode()` | `oracle_db_connector.py`, `sql_mv_loader.py`, `sql_view_loader.py`, `mv_refresh_gui.py`, `object_cleanup_gui.py`, `pk_designate_gui.py` |
| `_ensure_dialog_parent()` | `tools/index_gui.py`, `tools/pk_designate_gui.py` |

#### Recommendations for Future Cleanup Attempts

1. **Test after each file modification** — Don't batch multiple file changes before testing
2. **Start with the lowest-risk changes** — Delete unused files first, then dead functions, then refactor
3. **Create a feature branch** — Allows easy rollback without affecting main development
4. **Use git stash or commits** — Save working state before each phase
5. **Check import order** — Python module imports can have side effects; verify startup sequence
6. **Add logging to credential flow** — Would help diagnose why credentials weren't being recognized

#### Files Modified (before rollback)

- `HoonyTools.pyw` — Removed `process_queued_errors` import/call
- `libs/oracle_db_connector.py` — Removed dead code, imported from gui_utils
- `libs/mv_log_utils.py` — Removed `_get_current_user()`
- `libs/gui_utils.py` — **CREATED** (may have been deleted in rollback)
- `loaders/excel_csv_loader.py` — Removed dead functions, imported from gui_utils
- `loaders/sql_mv_loader.py` — Imported from gui_utils
- `loaders/sql_view_loader.py` — Imported from gui_utils
- `tools/index_gui.py` — Imported from gui_utils
- `tools/object_cleanup_gui.py` — Imported from gui_utils
- `tools/pk_designate_gui.py` — Imported from gui_utils
- `tools/mv_refresh_gui.py` — Imported from gui_utils

#### Files Deleted (status after rollback)

- `libs/layout_definitions.py` — 457 lines, confirmed safe to delete
- `libs/setup_config.py` — 55 lines, status unknown after rollback

---

### 🔄 Entry #18: MV Manager Multi-Select UX Improvements (2026-02-20)

Summary: This session focused on improving the multi-select user experience in the Materialized View Manager, including better visual feedback for selections, Reset buttons, single-click refresh, and improved result display formatting.

#### Findings

1. **Tkinter Listbox exportselection behavior**: By default, `exportselection=True` causes selecting in one Listbox to clear selections in another (X11 selection model). Setting `exportselection=False` on both User and DWH listboxes allows selections to persist across both panes simultaneously.

2. **Session label widget registration**: `session.py` provides `register_label_widget(schema, widget)` which stores widget references so session can automatically update them when labels change. Previously the MV Manager updated labels manually via `update_user_header()`/`update_dwh_header()` helpers but didn't register them with session.

3. **Two-click confirmation pattern**: The original `do_refresh()` used a `confirm_pending` flag stored in `root._last_selected` to require users to click "Refresh MV" twice. While intended to prevent accidental mass refreshes, user feedback indicated this was unintuitive and the single-click pattern was preferred.

#### Challenges

1. **Reset button command timing**: Reset buttons are created before `on_select()` is defined in the code. Using `command=lambda: (mview_listbox_user.selection_clear(0, tk.END), on_select(None, source='user'))` works because the lambda captures `on_select` by name (late binding), not by value at definition time.

2. **Right pane clearing**: When selections are cleared (total == 0), the original code just returned early without updating the UI. Added explicit clearing of both `info_text` and `sql_text` to provide visual feedback that nothing is selected.

3. **Result display separation**: The original refresh results dumped everything into `info_text` (top-right). User wanted brief summary at top and detailed list at bottom. Required restructuring the summary generation to split between the two panes.

#### Implementation Details

**Reset Button Pattern**:
```python
btn_reset_user = tk.Button(
    user_btn_frame, 
    text="Reset", 
    width=8, 
    command=lambda: (
        mview_listbox_user.selection_clear(0, tk.END), 
        on_select(None, source='user')
    )
)
```
The lambda tuple executes both operations: clear selection, then trigger on_select to update UI.

**Multi-Select Display Format**:
```python
mv_lines = []
if user_count:
    mv_lines.append("User MVs:")
    for i in user_sel:
        mv_lines.append(f"  - {mview_listbox_user.get(i)}")
if dwh_count:
    if mv_lines:
        mv_lines.append("")  # Blank line separator
    mv_lines.append("DWH MVs:")
    for i in dwh_sel:
        mv_lines.append(f"  - {mview_listbox_dwh.get(i)}")
sql_text.insert(tk.END, '\n'.join(mv_lines))
```

**Refresh Result Split**:
```python
# Brief summary in top-right
info_text.delete('1.0', tk.END)
info_text.insert(tk.END, f"Refresh complete: {len(success)} succeeded, {len(failures)} failed")

# Detailed list in bottom-right  
sql_text.delete('1.0', tk.END)
details = []
if success:
    details.append("Succeeded:")
    for mv in success:
        details.append(f"  - {mv}")
if failures:
    if details:
        details.append("")
    details.append("Failed:")
    for mv, err in failures:
        details.append(f"  - {mv}: {err}")
sql_text.insert(tk.END, '\n'.join(details))
```

#### Files Modified

| File | Changes |
|------|---------|
| `tools/mv_refresh_gui.py` | Added Reset buttons, session.register_label_widget calls, multi-select list display in sql_text, removed two-click confirmation, split refresh results between info_text and sql_text, added empty selection clearing |

#### Testing Checklist

1. **Reset buttons**: Click Reset in User pane — selections should clear and right panes should empty
2. **Multi-select display**: Select 3+ MVs across both panes — bottom pane should show grouped list with names
3. **Single-click refresh**: Select MVs and click Refresh MV once — should proceed immediately without confirmation step
4. **Result display**: After refresh completes — top pane shows "Refresh complete: X succeeded, Y failed", bottom pane shows detailed Succeeded/Failed lists
5. **Empty selection**: Click Reset or deselect all — both right panes should be empty
6. **Ctrl+A still works**: Focus User listbox, press Ctrl+A — all items should select
7. **Cross-pane selection**: Select items in User, then Ctrl+click items in DWH — both selections should persist

#### UX Rationale

- **Reset vs Clear**: "Reset" was chosen over "Clear" to match common UI terminology for returning to initial state
- **Grouped list format**: Indented bullet format (`  - MV_NAME`) provides clear visual hierarchy and easy scanning
- **Blank line separator**: Empty line between User MVs and DWH MVs sections improves readability
- **Brief top / detailed bottom**: Follows common log viewer pattern where summary is at top and details below

---

### 🔄 Entry #19: Auto-Refresh, Tool Callbacks & UI Consistency (2026-02-21)

Summary: This session focused on improving user experience with automatic object pane refresh, ensuring tools trigger refresh on close, fixing MV Loader connection handling, and achieving UI consistency between View and MV Loaders. Also added view options (WITH READ ONLY / WITH CHECK OPTION) and fixed a threading error on force quit.

#### Findings

1. **View DML Operations**: Regular Oracle views (not materialized views) can support INSERT, UPDATE, DELETE operations that modify the underlying base table(s). This works for simple views (single table, no aggregates/GROUP BY). `WITH READ ONLY` blocks this, `WITH CHECK OPTION` validates results stay visible in the view.

2. **Tkinter `root.after()` in Threads**: When a background thread calls `root.after()` after the main Tk loop has been destroyed (e.g., during force quit), it raises `RuntimeError: main thread is not in main loop`. The fix is to check a flag (`is_gui_running`) before attempting to schedule UI updates.

3. **MV Loader vs View Loader Connection Handling**: The MV Loader was closing the connection in `on_submit()` finally block, preventing consecutive MV creations. View Loader only closes the cursor, not the connection. The connection is properly cleaned up when the window is destroyed via `session.register_connection()`.

4. **Tkinter Pack Centering**: To align multiple rows (e.g., name entry + buttons) so they share the same visual center, they must be packed into a common parent container. Each row is then centered within that container.

5. **Forward Reference in Button Command**: When a button is created before the function it should call is defined (e.g., `btn_close` before `on_close()`), you can either:
   - Create button without command, then call `btn.config(command=on_close)` after the function is defined
   - Use a lambda that captures by name (late binding): `command=lambda: on_close()`

#### Challenges

1. **`on_finish` Callback Placement**: Different tools had different structures for their main loop (`wait_window()` vs `mainloop()`). The `on_finish` callback needed to be called in a `finally` block after the main loop completes, or when `on_close()` is called for the MV Manager pattern.

2. **MV Manager Close Button**: The `on_close()` function is defined late in the file (after all UI setup). Had to create the button without a command first, then configure it after `on_close()` is defined.

3. **Entry Field Alignment**: The user wanted the entry field (black bar) to align symmetrically with the two buttons below. Simply centering both rows independently didn't achieve this because the label ("View Name:") added asymmetry. Solution: use a shared container frame for both rows.

4. **Threading Race Condition**: The `is_gui_running` flag must be set to `False` in `safe_exit()` before `root.destroy()` is called. Worker threads check this flag before calling `root.after()`. However, there's still a small race window where a thread could pass the check and then have `root` destroyed before `after()` completes. Wrapping in `try/except` handles this edge case.

#### Implementation Details

**Auto-Refresh on Startup**:
```python
def _auto_refresh_on_startup():
    """Auto-refresh object panes if saved credentials exist (not a brand new launch)."""
    if session.get_credentials('schema1'):
        refresh_schema1_objects()
    if session.get_credentials('schema2'):
        refresh_schema2_objects()

root.after(100, _auto_refresh_on_startup)
```
The 100ms delay ensures the window is fully realized before starting background refresh threads.

**Threading Error Fix Pattern**:
```python
# Before (crashes on force quit):
root.after(0, lambda: _populate_treeview(schema1_tree, rows))

# After (safe):
if is_gui_running:
    try:
        root.after(0, lambda: _populate_treeview(schema1_tree, rows))
    except Exception:
        pass
```

**Shared Container for Alignment**:
```python
# Both rows inside same container ensures symmetric centering
control_container = tk.Frame(builder_window)
control_container.pack(pady=8)

name_row = tk.Frame(control_container)
name_row.pack(pady=(0, 15))
# ... label and entry ...

btn_frame = tk.Frame(control_container)
btn_frame.pack()
# ... buttons ...
```

**Late Button Command Configuration**:
```python
# Create button without command
btn_close = tk.Button(btn_frame, text="Close", width=10)
btn_close.pack(side="right", padx=6)

# ... later, after on_close() is defined ...

btn_close.config(command=on_close)
```

#### Oracle View Options Explained

| Option | Purpose | Use Case |
|--------|---------|----------|
| `WITH READ ONLY` | Blocks all DML (INSERT/UPDATE/DELETE) through the view | Reporting views, security |
| `WITH CHECK OPTION` | Allows DML but validates results stay visible in view | Data integrity, partitioned access |

These are mutually exclusive - a view cannot have both. The implementation gives precedence to READ ONLY if somehow both are checked.

#### Files Modified

| File | Changes |
|------|---------|
| `HoonyTools.pyw` | `_auto_refresh_on_startup()`, `on_finish` callbacks for load/pk tools, `is_gui_running` checks in worker threads |
| `loaders/sql_view_loader.py` | UI overhaul (geometry, centering, shared container), "Close" label, "Create" label, `read_only_var`/`check_option_var` checkboxes |
| `loaders/sql_mv_loader.py` | Removed `conn.close()` from finally, UI centering, shared container, "Close" label, "Create" label, Query Rewrite on separate row |
| `loaders/excel_csv_loader.py` | Added `on_finish=None` parameter, `finally` block to call it |
| `tools/pk_designate_gui.py` | Added `on_finish=None` parameter, call after session cleanup |
| `tools/mv_refresh_gui.py` | Added `btn_close`, late-bound command configuration |

#### Testing Checklist

1. **Auto-refresh on startup**: Save credentials via Settings, restart app — both panes should auto-populate
2. **Fresh launch**: Delete `config.ini`, launch app — panes should remain empty (no auto-refresh)
3. **Tool close refresh**: Open any tool, close it — relevant pane(s) should refresh
4. **Consecutive MV creation**: Open MV Loader, create MV, create another MV without reopening — should work
5. **Force quit during refresh**: Click refresh, immediately close window — no traceback in console
6. **View options**: Create view with READ ONLY checked — verify DML fails; create with CHECK OPTION — verify constraint works
7. **UI alignment**: Open View Loader and MV Loader — entry fields should align with button rows below

#### UX Rationale

- **Close vs Cancel**: "Close" better communicates that the dialog can be reopened; "Cancel" implies aborting an in-progress operation
- **Create vs Create View/MV**: Shorter label reduces button width, and context is already clear from the dialog title
- **Centered layouts**: Provides a cleaner, more professional appearance; easier to scan visually
- **Query Rewrite on separate row**: Separates the "optional enhancement" from the core MV parameters (Build/Refresh/Trigger)

---

### 📁 Entry #20: Import SQL File Feature for View & MV Loaders (2026-02-21)

Summary: Added an "Import SQL" button to both SQL View Loader and SQL MV Loader that allows users to load SQL queries from `.sql` files and auto-populates the view/MV name based on the filename with appropriate prefix.

#### Feature Details

1. **File Dialog**: Opens native file chooser filtered for `.sql` files (with "All Files" fallback)
2. **Content Loading**: Reads file as UTF-8, clears existing text, inserts file content
3. **Name Auto-Fill**: Extracts filename (without extension), adds prefix, converts to uppercase:
   - View Loader: `sales.sql` → `V_SALES`
   - MV Loader: `sales.sql` → `MV_SALES`
4. **Error Handling**: Shows error messagebox with system chime (`builder_window.bell()`) if file read fails

#### Implementation Notes

**Function placement**: The `load_sql_from_file()` function is defined inside `run_sql_view_loader()` / `run_sql_mv_loader()` (not at module level) because it needs access to `sql_text`, `view_name_entry`/`mv_name_entry`, and `builder_window` which are local to those functions.

**Button styling**: Added to `_all_buttons` list so it receives dark mode styling when theme changes.

**System chime**: `builder_window.bell()` triggers the system error sound on Windows. Wrapped in try/except in case the window is in an invalid state.

**Encoding**: Only UTF-8 is supported. If users have SQL files in other encodings (e.g., Latin-1, Windows-1252), they'll see an error. This is intentional to keep the implementation simple — UTF-8 is the modern standard.

**Naming convention**: The `V_` and `MV_` prefixes follow common Oracle naming conventions that distinguish views and materialized views from tables at a glance. Uppercase conversion aligns with Oracle's case-insensitive object names (stored uppercase in data dictionary).

#### Code Pattern

```python
def load_sql_from_file():
    """Open file dialog, load SQL content, and auto-fill view/MV name from filename."""
    from tkinter import filedialog
    import os

    filepath = filedialog.askopenfilename(
        title="Select SQL File",
        filetypes=[("SQL Files", "*.sql"), ("All Files", "*.*")],
        parent=builder_window
    )
    if filepath:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            # Clear and insert content
            sql_text.delete('1.0', tk.END)
            sql_text.insert('1.0', content)

            # Auto-fill name from filename with prefix
            filename = os.path.basename(filepath)
            name_without_ext = os.path.splitext(filename)[0]
            view_name = f"V_{name_without_ext}".upper()  # or MV_ for MV loader
            view_name_entry.delete(0, tk.END)
            view_name_entry.insert(0, view_name)
        except Exception as e:
            _safe_messagebox('showerror', "Error", f"Failed to read file:\n{e}", dlg=builder_window)
            try:
                builder_window.bell()  # System chime
            except Exception:
                pass
```

#### Files Modified

| File | Changes |
|------|---------|
| `loaders/sql_view_loader.py` | Added `load_sql_from_file()`, "Import SQL" button in name_row |
| `loaders/sql_mv_loader.py` | Added `load_sql_from_file()`, "Import SQL" button in name_row |

#### Testing Checklist

1. **Basic import**: Create `test_query.sql` with valid SQL, click Import SQL, select file → text area should show content, name should be `V_TEST_QUERY` or `MV_TEST_QUERY`
2. **Uppercase conversion**: File named `My_View.sql` → should become `V_MY_VIEW`
3. **Special characters in filename**: File named `sales-2024.sql` → should become `V_SALES-2024` (hyphen preserved)
4. **Cancel dialog**: Click Import SQL, then Cancel → nothing should change
5. **Invalid file**: Try to open a binary file → should show error popup with chime
6. **Non-UTF8 file**: Create file with non-UTF8 encoding → should show error popup with chime
7. **Empty file**: Import empty `.sql` file → text area cleared, name still auto-filled
8. **Overwrite existing**: Enter text manually, then import file → should replace existing text and name
9. **Dark mode styling**: Toggle dark mode → Import SQL button should match other buttons

#### UX Rationale

- **V_ and MV_ prefixes**: Common Oracle naming convention that distinguishes views from tables at a glance
- **Uppercase**: Oracle object names are case-insensitive and conventionally uppercase in data dictionaries
- **Button placement**: Next to name field creates visual association between "import file" and "set name"
- **UTF-8 only**: Simplifies implementation; modern SQL files should be UTF-8
- **System chime on error**: Provides audio feedback when file read fails, especially useful if error dialog appears behind other windows

---

### Entry #21: Auto-Refresh Object Panes After Settings Save (v2.1.5)

When users enter credentials via Settings (File → Settings) and save, the object panes should automatically refresh to show the connected schema's objects. Previously, users had to manually click Refresh after saving credentials.

#### Problem

1. User opens HoonyTools for the first time (no `config.ini`)
2. User enters Schema 1 and Schema 2 credentials in Settings
3. User clicks OK or Apply
4. **Issue**: Schema labels updated, but object panes remained empty until manual Refresh
5. **Additional issue**: Schema 2's dynamic label wasn't updating at all after Settings save

#### Root Cause Analysis

1. **Label not updating**: `session.set_credentials()` updated `schemas[schema]['label']` but did NOT call `update_label_widget()` to actually refresh the GUI label widget.

2. **No auto-refresh trigger**: Settings had no way to trigger the main GUI's refresh functions after saving credentials.

#### Solution

**Part 1: Auto-update label widgets when credentials are set**

In `libs/session.py`, `set_credentials()` now calls `update_label_widget(schema)` after updating the label:

```python
def set_credentials(schema, credentials):
    ...
    if credentials and credentials.get('user'):
        schemas[schema]['label'] = credentials['user']
        update_label_widget(schema)  # <-- Added
    ...
```

This ensures the GUI label updates immediately whenever credentials are set from any source.

**Part 2: Trigger refresh from Settings**

1. In `HoonyTools.pyw`, expose refresh callbacks on root:
```python
root._refresh_schema1 = refresh_schema1_objects
root._refresh_schema2 = refresh_schema2_objects
```

2. In `libs/settings.py`, call these callbacks after saving credentials:
```python
if _parent:
    if hasattr(_parent, '_refresh_schema1') and s1_user_val and s1_pass_val and s1_dsn_val:
        try:
            _parent._refresh_schema1()
        except Exception:
            pass
    if hasattr(_parent, '_refresh_schema2') and s2_user_val and s2_pass_val and s2_dsn_val:
        try:
            _parent._refresh_schema2()
        except Exception:
            pass
```

Only triggers refresh if complete credentials were provided (all three fields non-empty).

#### Files Modified

| File | Changes |
|------|---------|
| `libs/session.py` | `set_credentials()` now calls `update_label_widget(schema)` |
| `HoonyTools.pyw` | Exposed `_refresh_schema1` and `_refresh_schema2` on root |
| `libs/settings.py` | Call parent's refresh callbacks after saving credentials |

#### Design Notes

- **Callback pattern**: Using `hasattr()` checks makes this backwards-compatible; Settings won't crash if launched from a different parent window that lacks refresh callbacks.
- **Conditional refresh**: Only refreshes schemas with complete credentials, avoiding unnecessary connection attempts for empty/partial entries.
- **Label widget registration**: The `register_label_widget()` / `update_label_widget()` pattern allows any code that sets credentials to automatically update the GUI without needing direct widget references.

---

### Entry #22: Known Edge Case - Brief GUI Freeze on Immediate Tool Launch After Settings Save (v2.1.5)

#### Observed Behavior

On a fresh launch (no `config.ini`), if the user:
1. Enters credentials via Settings (File → Settings)
2. Clicks OK
3. **Immediately** clicks File → M.View Manager (within ~1-2 seconds)

The main GUI may freeze briefly ("Not Responding") before recovering and opening the MV Manager correctly.

#### Root Cause

When Settings saves credentials:
1. `session.set_credentials()` updates session memory (synchronous, fast)
2. `_refresh_schema1()` and `_refresh_schema2()` are triggered, spawning **background threads** to connect and fetch objects
3. If the user immediately opens MV Manager, it calls `get_db_connection()` on the **main thread**
4. Both the refresh threads AND MV Manager are trying to initialize Oracle client / connect simultaneously
5. The main thread blocks during Oracle client initialization and connection, causing the freeze

The `get_db_connection()` call in `mv_refresh_gui.py` (line 25) runs synchronously before the GUI is shown:
```python
conn = get_db_connection()  # Blocks main thread during connection
```

#### Why This Is Acceptable

1. **Extremely unlikely scenario**: User must be on fresh launch, enter credentials via Settings (not login prompt), AND immediately click MV Manager
2. **MV Manager is not commonly used**: It's a niche tool for materialized view management, not a primary workflow
3. **Graceful recovery**: The freeze resolves on its own and MV Manager opens correctly
4. **Credentials ARE set correctly**: The session memory is updated before the freeze occurs

#### Potential Future Fix (If Needed)

If this becomes a repeated user complaint, consider refactoring MV Manager to:
- Show the GUI window first with a "Connecting..." state
- Connect to the database in a background thread
- Update the GUI when connection completes

This would follow the same pattern as the main GUI's object pane refresh. However, this is a significant refactoring effort (~1300+ lines in `mv_refresh_gui.py`) with risk of introducing new bugs.

#### Decision

**Leave as-is** for now. The edge case is rare, the behavior recovers gracefully, and the risk of refactoring outweighs the benefit. Document for future reference.

#### Related Fix

In `libs/settings.py`, the `set_credentials()` calls were moved **outside** the try/except block to ensure credentials are always set to session memory, even if the refresh triggers fail. This prevents the login prompt from appearing when it shouldn't.

---

### 🎨 Entry #15: Dark Mode Pattern for Tkinter Dialogs (Pane-Only)

#### Summary

Dark mode in HoonyTools follows a **pane-only** approach: only ScrolledText widgets (text content panes) get dark background styling. Dialog chrome (window background, labels, frames, buttons, checkboxes) stays in the system default grey.

This matches how the main GUI's object panes work - the treeviews are dark, but the surrounding UI stays standard.

#### Detection

Use the centralized helper in `libs/gui_utils.py`:

```python
from libs.gui_utils import is_dark_mode_active, DARK_BG, DARK_FG, DARK_INSERT_BG

_is_dark = is_dark_mode_active()
```

The detection checks ttk Style lookup for `Pane.Treeview` or `Treeview` background. Black background (#000000, #000, 'black') indicates dark mode.

#### Pattern for Dialog Dark Mode (Pane-Only)

1. **Detect once** at dialog creation and store in `_is_dark` flag
2. **Apply ONLY to ScrolledText widgets** immediately after creation:
   ```python
   if _is_dark:
       deps_box.config(bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_INSERT_BG)
       ddl_box.config(bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_INSERT_BG)
   ```
3. **Do NOT style**: dialog window, labels, frames, buttons, checkboxes - leave them in default grey

#### What NOT to Do

Do NOT apply dark mode to:
- `dlg.config(bg=DARK_BG)` — dialog background
- Label widgets — they stay default
- Frame widgets — they stay default
- Button widgets — they stay default
- Checkbutton widgets — they stay default

#### Color Constants

| Constant | Value | Usage |
|----------|-------|-------|
| `DARK_BG` | `#000000` | Background for ScrolledText panes only |
| `DARK_FG` | `#ffffff` | Foreground text color for panes |
| `DARK_INSERT_BG` | `#ffffff` | Text cursor (insertbackground) |
| `DARK_BTN_BG` | `#333333` | Reserved for future use |
| `DARK_BTN_ACTIVE_BG` | `#222222` | Reserved for future use |

#### Future Customization

The `libs/gui_utils.py` module is kept for future flexibility. If we later decide to style dialog chrome (e.g., dark grey instead of default grey), the helpers and constants are ready to use.

#### Files Using This Pattern

- `loaders/sql_mv_loader.py` — "Existing MV Log" dialog (deps_box, ddl_box)
- `tools/mv_refresh_gui.py` — Compact "Existing MV Log" dialog (deps_box, ddl_box)

---

### 📋 Entry #16: Cleaner Error Logging (logger.error vs logger.exception)

#### Summary

Use `logger.error()` instead of `logger.exception()` when logging errors that will be displayed in the GUI log pane. This keeps error messages concise and user-friendly.

#### The Problem

`logger.exception()` automatically includes the full Python traceback, which clutters the log pane with verbose technical details that aren't helpful to users:

```
2026-02-21 03:43:48 - ERROR - ❌ Error creating materialized view: ORA-12006: ...
Traceback (most recent call last):
  File "C:\...\sql_mv_loader.py", line 965, in on_submit
    cursor.execute(ddl)
  ... (10+ more lines)
```

#### The Solution

Use `logger.error()` instead - it logs only the error message:

```python
# Before (verbose traceback in log pane)
logger.exception("❌ Error creating materialized view: %s", e)

# After (clean single-line error)
logger.error("❌ Error creating materialized view: %s", e)
```

Result:
```
2026-02-21 03:43:48 - ERROR - ❌ Error creating materialized view: ORA-12006: materialized view or zonemap "DWH"."MV_SETUP_SALES_TEST1" already exists
```

#### When to Use Each

| Method | Use Case |
|--------|----------|
| `logger.error()` | User-facing errors shown in GUI log pane |
| `logger.exception()` | Debug/development logs where full traceback is needed |

#### Files Updated

- `loaders/sql_mv_loader.py` — Changed 4 occurrences from `logger.exception()` to `logger.error()`

---

### 🐛 Entry #17: Settings Tab-Switching Credential Bug

#### Summary

When the Settings dialog switches between category tabs (e.g., from Connections to Appearance), the entry widget references are cleared. If `_save()` is then called (via OK or Apply), it would incorrectly treat credentials as empty and clear them from session memory.

#### The Bug

In `_on_category_select()` at lines 714-721:
```python
# Clear entry refs for fresh build, but preserve system references
preserved = {
    '_parent': entry_refs.get('_parent'),
    '_status_label': entry_refs.get('_status_label'),
    '_win': entry_refs.get('_win'),
}
entry_refs.clear()  # <-- Clears schema1_user, schema1_pass, etc!
entry_refs.update(preserved)
```

Then in `_save()`:
```python
s1_user = entry_refs.get('schema1_user')  # Returns None!
if s1_user and s1_pass and s1_dsn:
    s1_user_val = s1_user.get().strip()
else:
    # s1_user_val stays as ''
    pass

# Later...
if s1_user_val and s1_pass_val and s1_dsn_val:
    session.set_credentials(...)
else:
    session.clear_credentials('schema1')  # <-- BUG: Credentials wiped!
```

#### Symptoms

1. User opens Settings (Connections panel loads)
2. User switches to Appearance tab (entry refs cleared)
3. User toggles dark mode and clicks OK/Apply
4. `session.clear_credentials()` is called for both schemas
5. All tools now show login popup

#### The Fix

In `_save()`, when entry widgets don't exist, read current values from `config.ini` instead of treating them as empty:

```python
if s1_user and s1_pass and s1_dsn:
    # Entry widgets exist (on Connections tab) - read from them
    s1_user_val = s1_user.get().strip()
    ...
else:
    # Entry widgets don't exist (on different tab) - preserve existing config.ini values
    if cfg.has_section('schema1'):
        s1_user_val = cfg.get('schema1', 'user', fallback='')
        s1_pass_val = cfg.get('schema1', 'password', fallback='')
        s1_dsn_val = cfg.get('schema1', 'dsn', fallback='')
```

#### Files Updated

- `libs/settings.py` — Fixed `_save()` to preserve credentials when entry widgets don't exist

---

### 🎨 Entry #18: Theme System Architecture with Full Chrome Theming (v2.1.8)

**Problem:** The simple Dark Mode toggle (on/off) was too limiting. Users wanted options between pure black and system light, similar to how VS Code offers multiple theme presets. Additionally, the initial "pane-only" approach was incomplete - users wanted the entire UI to be themed, not just content panes.

**Solution:** Implemented a comprehensive theme system with:
- 7 preset themes spanning the spectrum from darkest to lightest
- **22 color keys** for full UI customization
- Full chrome theming for the entire UI (buttons, labels, frames, menus, etc.)

#### Theme System Design

**Core principle: Full chrome theming.** All UI elements are themed, not just content panes. Each preset defines colors for every UI element type, creating a cohesive visual experience.

**Preset themes (dark to light):**
1. **Pure Black** (`#000000` window) — What Dark Mode used to be
2. **Midnight** (`#010409` window) — GitHub Dark style
3. **Charcoal** (`#181818` window) — VS Code Dark style
4. **Slate** (`#252525` window) — Softer dark
5. **Graphite** (`#313335` window) — Medium grey (IntelliJ style)
6. **Silver** (`#c0c0c0` window) — Light grey, distinctly different from System Light
7. **System Light** (`SystemButtonFace`) — Windows default, respects high contrast

**Complete color keys (22 total):**
```python
COLOR_KEYS = [
    # Content panes
    'pane_bg', 'pane_fg', 'select_bg', 'insert_bg',
    # Window chrome
    'window_bg', 'border_bg',
    # Labels
    'label_bg', 'label_fg',
    # LabelFrame
    'labelframe_bg', 'labelframe_fg',
    # Buttons
    'button_bg', 'button_fg', 'button_active_bg', 'button_active_fg',
    # Entry fields
    'entry_bg', 'entry_fg',
    # Menu
    'menu_bg', 'menu_fg', 'menu_active_bg', 'menu_active_fg',
    # Checkbox/Radio
    'checkbox_bg', 'checkbox_fg', 'checkbox_select',
    # Scrollbar
    'scrollbar_bg', 'scrollbar_fg',
]
```

#### Implementation Components

**1. `libs/gui_utils.py` — Theme infrastructure:**

Per-widget styling functions:
```python
apply_theme_to_pane(widget)      # ScrolledText, Text
apply_theme_to_window(widget)    # Tk, Toplevel, Frame
apply_theme_to_label(widget)     # Label
apply_theme_to_labelframe(widget)
apply_theme_to_button(widget)    # Button
apply_theme_to_entry(widget)     # Entry
apply_theme_to_menu(widget)      # Menu
apply_theme_to_checkbox(widget)  # Checkbutton, Radiobutton
apply_theme_to_scrollbar(widget)
apply_theme_to_widget(widget, widget_type='auto')  # Auto-detect
```

TTK and option database configuration:
```python
configure_ttk_styles(style)      # Treeview, TCombobox, TButton, etc.
configure_root_options(root)     # *Listbox.*, *Button.*, *Menu.*, etc.
```

**2. `HoonyTools.pyw` — Unified `apply_full_theme()`:**

Replaced separate `apply_current_theme()` and `_restore_light_theme()` with a single unified function that:
- Calls `gui_utils.configure_ttk_styles()` and `configure_root_options()`
- Applies theme to root window, menu bar, verse pane, all buttons
- Recreates Treeview widgets with appropriate style
- Registers with `gui_utils.register_theme_callback()` for live updates

**3. Settings dialog (`libs/settings.py`):**
- Registers `_apply_theme` callback with `gui_utils`
- On theme change, applies theme to entire Settings dialog (window, frames, buttons, category tree, content area)

**4. Child dialogs (`sql_mv_loader.py`, `mv_refresh_gui.py`):**
- Register with `gui_utils.register_theme_callback()`
- Apply full chrome theming using `gui_utils.apply_theme_to_*()` functions
- Unregister callback on window destroy

#### Color Relationship Philosophy

**Independent values, not derived.** Each color key in a preset is explicitly defined, allowing for:
- Full customization freedom when custom colors are implemented
- No hidden dependencies between color keys
- Preset serves as starting template for customization

For example, `label_bg` could be different from `window_bg` if the user wants it that way.

#### View Menu Removal

The View menu (which only contained Dark Mode toggle) was removed entirely. Theme selection is now exclusively in Settings > Appearance. This simplifies the UI and centralizes all settings in one place.

#### Backward Compatibility

- `gui_utils.is_dark_mode_active()` now calls `is_dark_theme()` internally
- `set_panes_dark()` / `set_panes_light()` legacy functions still work
- Legacy constants (`DARK_BG`, `DARK_FG`, etc.) preserved for any external code
- `apply_dark_mode_to_widget()` and `style_dialog_for_dark_mode()` still work

#### Future Phases

**Phase 2 (Custom Colors):**
- Enable "Customize..." button in Settings > Appearance
- Color pickers (hex entry + `tkinter.colorchooser.askcolor()`)
- Custom overrides stored in `[theme.custom]` section
- Live preview panel showing all 22 color keys grouped logically
- Reset to preset button

#### Files Updated

- `libs/gui_utils.py` — 22 color keys, 7 fully-defined presets, per-widget styling functions
- `libs/settings.py` — Full chrome theming, registered with gui_utils callbacks
- `HoonyTools.pyw` — New unified `apply_full_theme()`, removed View menu
- `loaders/sql_mv_loader.py` — Full chrome theming for MV Builder dialog
- `tools/mv_refresh_gui.py` — Uses `gui_utils` theme API
