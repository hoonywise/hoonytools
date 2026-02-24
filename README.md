<table>
  <tr>
    <td><img src="https://www.gravatar.com/avatar/cbae675632b5840c0a7dd177e61c8634?s=80" alt="Hoonywise Logo" width="50"></td>
    <td><h1 style="margin-left: 10px;">HoonyTools</h1></td>
  </tr>
</table>

Created by Jihoon Ahn [@hoonywise](https://github.com/hoonywise)  
Contact: hoonywise@proton.me

[![](https://img.shields.io/badge/license-Custom-gold)](LICENSE.md)
[![](https://img.shields.io/badge/Donate-PayPal-blue)](https://www.paypal.com/donate/?hosted_button_id=NJSTAENDWQLXS)
---

> HoonyTools is an all-in-one Python-based toolkit for loading, transforming, and managing data in Oracle databases. It supports dual schema connections with customizable DSN configurations. Compatible with **Windows**, **macOS**, and **Linux**.
> 
> Key features: create and drop views, materialized views, MV logs, indexes, and primary keys. Includes an Excel/CSV Loader for importing external data and a Materialized View Manager for log creation and MV refresh operations.  

---

![Main GUI](assets/main_gui_65.png)

---

## 🧑‍💻 Quick Start

### Both EXE and Python PYW Versions Available

HoonyTools now runs either as a standalone EXE or directly as a Python GUI app.

**First-Time Setup:**

- EXE users:

1. Download the latest `HoonyTools.exe` from the [Releases](https://github.com/hoonywise/HoonyTools/releases) page.
2. Place the file in a folder of your choice.
3. Launch the app by double-clicking `HoonyTools.exe`.

- PYW users:

1. Download the latest `HoonyTools_vX.X.X_python.zip` from the [Releases](https://github.com/hoonywise/HoonyTools/releases) page.
2. Unzip the file to a folder of your choice.
3. Ensure [Python 3.13+](https://www.python.org/downloads/) is installed
4. Open a terminal in the unzipped folder and run:  
   ```
   pip install -r requirements.txt
   ```
5. Launch the app by double-clicking `HoonyTools.pyw'.

✅ This launches the GUI with **no terminal window**

---

## 🗂️ Folder Structure

> EXE version will create the necessary folders automatically.

After unzipping `HoonyTools_vX.X.X_python.zip`, you should see:

```
HoonyTools/
├── HoonyTools.pyw                  # Main launcher (double-click this)
├── README.txt                      # Quickstart user guide
├── LICENSE.md                      # Licensing terms
├── CHANGELOG.md                    # Release notes
├── requirements.txt                # (Optional) Python modules if running from source)
├── build_pkg.py                    # Cross-platform build & package script
├── libs/                           # Shared utility modules (Oracle, config, logging, etc.)
│   ├── config.ini                  # Created at first login if "Save password" is checked
│   ├── paths.py                    # Filepaths for domain-specific folders
│   ├── mv_log_utils.py             # MV log detection helpers used by loaders and tools
│   ├── pk_designate_settings.json  # Persisted settings for PK Designator
│   ├── oracle_db_connector.py      # Oracle connection helper (get_db_connection)
│   ├── session.py                  # Session memory for credentials and states
│   ├── abort_manager.py            # Coordinated abort/cleanup helper used by loaders
│   ├── table_utils.py              # Common table utilities (DDL helpers)
│   ├── gui_utils.py                # Shared GUI utility functions
│   ├── settings.py                 # Settings GUI for credentials and appearance
│   ├── bible_books.py              # Small lookup for book names (Word of God feature)
│   └── en_kjv.json                 # Embedded JSON data for KJV text (Word of God feature)
├── loaders/                        # Loaders (Excel, CSV, SQL, etc.)
│   ├── excel_csv_loader.py         # Excel/CSV Loader GUI (APPEND/REPLACE/UPSERT, preview)
│   ├── sql_view_loader.py          # SQL View Loader (create view from pasted SQL)
│   └── sql_mv_loader.py            # SQL Materialized View Loader (creates MVs, offers MV log creation)
├── tools/                          # Data tools and object management
│   ├── object_cleanup_gui.py       # Object Cleanup (drop tables/views/mviews/mlogs/pks)
│   ├── mv_refresh_gui.py           # Materialized View Manager (refresh, create/reuse/drop logs)
│   ├── pk_designate_gui.py         # Primary Key Designator (inspect tables, create PKs safely)
│   └── index_gui.py                # Index Manager (create/drop indexes on tables and MVs)
└── assets/                         # Icons and splash images
```

---

## 🛠️ Setup Requirements

To run HoonyTools, you’ll need the following installed and configured:

---

### ✅ Python 3.13 or Higher

1. Install from the official site:  
   👉 [https://www.python.org/downloads/](https://www.python.org/downloads/)

2. During installation, make sure to check:  
   ✅ “Add Python to PATH”

---

### 🧩 Required Python Packages

Once Python is installed, run the following from the HoonyTools folder:

```
pip install -r requirements.txt
```

This installs all required libraries including:

- `oracledb` (for Oracle connectivity)
- `pandas`, `openpyxl` (for Excel/CSV processing)
- `pystray`, `Pillow` (for GUI tray features and icon support)
- `pywin32` (Windows only — installed automatically via platform marker)
- `pyobjc-core`, `pyobjc-framework-Cocoa` (macOS only — for system tray support)

---

### 🛢️ Oracle Instant Client

To connect to Oracle databases, the **Oracle Instant Client** must be installed and properly configured:

1. **Add the Instant Client folder to your system PATH**  
   Example:
   ```
   C:\oracle\instantclient_21_13
   ```

2. **Create a `tnsnames.ora` file** inside your Oracle `network/admin` folder  
   or set the `TNS_ADMIN` environment variable to point to it.

   This file defines named DSNs such as `DWHDB_DB` used by HoonyTools.

   Example entry:
   ```
   DWHDB_DB =
     (DESCRIPTION =
       (ADDRESS = (PROTOCOL = TCP)(HOST = your.hostname.edu)(PORT = 1521))
       (CONNECT_DATA =
         (SERVICE_NAME = XEPDB1)
       )
     )
   ```

3. **Test with `sqlplus` or `tnsping`**  
   Example:
   ```
   sqlplus your_username@DWHDB_DB
   ```

If you can connect via `sqlplus`, HoonyTools will work too.

📥 [Download Oracle Instant Client](https://www.oracle.com/database/technologies/instant-client/downloads.html)

---

## 🚀 How to Launch

Simply double-click `HoonyTools.pyw` or 'HoonyTools.exe' to launch the application.

This file opens without a terminal window and starts the GUI immediately.

---

### 🧭 GUI Usage

Once launched, the GUI gives access to all tools via an intuitive interface:

- **Two Object Panes**: View and manage objects in your User schema and the shared DWH schema
- **Per-Pane Actions**: Refresh, Load, Drop, View, M.View, P.Key, Index buttons for each schema
- **Auto-Refresh**: Object panes automatically refresh on startup if saved credentials exist
- **Tool Close Refresh**: Panes refresh automatically when any tool GUI is closed
- **Menu Bar**:
  - `File → M.View Manager` — Open the Materialized View Manager
  - `File → Settings` — Configure credentials and appearance (`Ctrl+Alt+S`)
  - `File → Exit` — Close the application
  - `Help → About` — Version and contact info
- **Status Indicator**: Green (idle) / Red (busy) light shows current operation status
- **Console Log**: View real-time operation logs and messages
- **Word of God**: Displays a daily Bible verse at the top of the main window with Previous/Next navigation

You can run as often as needed — no admin rights or elevated privileges required.

---

## 🛠 Available Tools (7)

### 1. SQL View Loader
- Instantly create Oracle views from pasted SQL queries.
- **Import SQL** button to load queries from `.sql` files (auto-fills view name with `V_` prefix, e.g., `sales.sql` → `V_SALES`).
- Optional `WITH READ ONLY` or `WITH CHECK OPTION` constraints.

### 2. SQL Materialized View Loader
- Create materialized views from pasted SQL and optionally create required materialized view logs.
- **Import SQL** button to load queries from `.sql` files (auto-fills MV name with `MV_` prefix, e.g., `sales.sql` → `MV_SALES`).
- Offers log creation UI with `WITH ROWID` / `WITH PRIMARY KEY` and `INCLUDING NEW VALUES` options.
- Configurable options: Build mode (IMMEDIATE/DEFERRED), Refresh Method (COMPLETE), Refresh Trigger (ON DEMAND/ON COMMIT), and Enable Query Rewrite.

### 3. Materialized View Manager
- Browse existing materialized views in both User and DWH schemas.
- Request COMPLETE refreshes (single or multi-select).
- Manage materialized view logs: create, reuse, or Drop & Recreate.
- Shows refresh type (ON DEMAND / ON COMMIT) and per-base current log types.
- FAST refresh is intentionally not offered due to environment dependencies.

### 4. Primary Key Designator
- Inspect tables and detect PK candidates (single-column or composite).
- Run safe null/duplicate checks before creating constraints.
- Add PRIMARY KEY constraints with confirmation and configurable constraint naming.

### 5. Index Manager
- Create and drop indexes on tables and materialized views.
- Select columns for new indexes and view existing indexes.
- Supports both User schema and DWH schema objects.

### 6. Excel/CSV Loader
- Load Excel (`.xlsx`) or CSV files into Oracle from a local file picker.
- Auto-maps column headers and preserves datatypes.
- Provides loading modes:
  - **APPEND** — Load into existing tables or create new ones
  - **REPLACE** — Truncate existing tables before loading
  - **UPSERT** — Merge records based on selected unique keys
- **Formatted SQL Preview** (default ON):
  - Preview generated SQL before execution
  - Includes `Copy SQL` and `Save to .sql` actions
  - Upsert `MERGE` uses a temporary staging table with dry-run validation

### 7. Object Cleanup
- Drop tables, views, materialized views, materialized view logs, and primary key constraints.
- Works with both User schema and DWH schema.
- Prefers materialized views when an underlying table shares the same name to avoid failures.
- ⚠️ **Use with caution** — these actions are destructive and irreversible.

---

## ✨ Features

### Settings
- Access via `File → Settings` or keyboard shortcut `Ctrl+Alt+S`.
- **Connections**: Configure Schema 1 (User) and Schema 2 (DWH) database credentials:
  - Enter Username, Password, and DSN for each schema
  - Credentials are saved to `libs/config.ini` and loaded into session memory
  - Eliminates login popups when credentials are pre-configured
- **Appearance**: Theme selection and splash screen controls

### Theme System
- **16 themes** including popular styles: Pure Black, Midnight, Dracula, One Dark, Monokai, Charcoal, Nord, Solarized, and more
- **Custom colors**: Customize individual UI elements (buttons, labels, menus, panes, etc.)
- Applies to the entire UI including all tool dialogs
- Theme preference persists across sessions

### Splash Screen Controls
- Toggle splash screen on/off
- Adjust splash opacity (0-100%)

---

## ⚙️ Configuring Credentials via Settings

Instead of entering credentials at each login prompt, you can pre-configure them in Settings:

1. Launch HoonyTools and go to `File → Settings` (or press `Ctrl+Alt+S`)
2. In the **Connections** category:
   - **Schema 1 (User)**: Enter your personal Oracle username, password, and DSN
   - **Schema 2 (DWH)**: Enter the shared DWH schema credentials (if applicable)
3. Click **OK** or **Apply** to save

Once configured:
- Object panes will auto-refresh on startup using saved credentials
- Tools will connect automatically without prompting for login
- To update credentials later, simply return to Settings

> 💡 **Tip:** You can also check "Save password" in the login popup when prompted. This saves credentials to `libs/config.ini` for future sessions.

---

## 🌐 Platform Compatibility

HoonyTools runs on **Windows**, **macOS**, and **Linux**. The GUI, theme system, and all tools work across all three platforms.

| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| GUI & all 7 tools | Full | Full | Full |
| Theme system (16 presets + custom) | Full | Full | Full |
| Window icons | `.ico` + `.png` | `.png` | `.png` |
| System tray icon | Full | Requires `pyobjc` (auto-installed) | Requires `python3-xlib` or AppIndicator |
| Color picker (custom swatch persistence) | Full (16-slot Windows API) | Basic (tkinter) | Basic (tkinter) |
| Splash fade animation | Full | Full | May skip on Wayland |
| Multi-monitor DPI-aware centering | Full | Primary monitor | Primary monitor |
| Build script | `build_exe.bat` or `build_pkg.py` | `build_pkg.py` | `build_pkg.py` |

**macOS/Linux notes:**
- Platform-specific dependencies are handled automatically via `requirements.txt` markers — just run `pip install -r requirements.txt` on any platform.
- On macOS, launch with `python3 HoonyTools.pyw`. The `.pyw` extension has no special meaning on macOS/Linux (it runs the same as `.py`).
- On Linux, ensure `tkinter` is installed (`sudo apt install python3-tk` on Debian/Ubuntu, `sudo dnf install python3-tkinter` on Fedora).

---

## 🔨 Building & Packaging

A cross-platform Python build script is included for building standalone binaries and packaging source releases.

```bash
# Build EXE + package source ZIP (most common)
python build_pkg.py 2.2.2

# Build a standalone binary only
python build_pkg.py exe

# Package source ZIP only (skip EXE build)
python build_pkg.py 2.2.2 --mode package
```

> Platform-specific scripts (`build_exe.bat`, `build_exe.sh`, `build_pkg.bat`) are also available for Windows and macOS/Linux respectively.

---

## 📌 Notes for Users

- Ensure your **Oracle Instant Client** is properly installed and configured (see setup section above).
- You must be connected to your institution’s network or VPN if the Oracle database is not publicly accessible.
- All tools require a valid Oracle **DSN (Data Source Name)** such as `DWHDB_DB`. You may define your own DSN in `tnsnames.ora` to point to your organization’s database.
  - The first time you run a tool that connects to Oracle, you will be prompted for your **username, password, and DSN**.  
  - A **"Save password"** checkbox is available in the login popup. If checked, your credentials will be saved in `libs/config.ini` for future GUI launches. If unchecked, it will only store for the duration of the current session.
  - The Object Cleanup tool is destructive; when in doubt, take a backup or verify with your DBA before dropping objects or constraints.
- **Use caution when working with production databases**. Certain tools (e.g., loaders and Object Cleanup) can delete and overwrite data.
- For best results, always review your files before running a loader, and monitor the logging window for any errors or warnings.

> 🧠 **Note:** This toolset interacts directly with the Oracle Data Warehouse (DWH). Ensure you understand the impact of any actions, particularly when loading data with loaders or using cleanup tools.

> 💡 **Tip:** To reset your saved DWH credentials (e.g., if the DSN or password changes), simply delete the `libs/config.ini` file. The next time you launch a DWH-related tool, HoonyTools will prompt you to enter new login information and ask whether to save it again.

---

## 📜 License

HoonyTools is free for individual, non-commercial use.  
Use across departments or organizations may require a license.

📩 **For enterprise use or questions, contact:**  
**[hoonywise@proton.me](mailto:hoonywise@proton.me)**

For full terms, see [LICENSE.md](LICENSE.md).
