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
