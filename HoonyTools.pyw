import tkinter as tk
from tkinter import scrolledtext, ttk
import tkinter.font as tkfont
import logging
import threading
from io import StringIO
import ctypes
import sys
from pathlib import Path
from PIL import Image, ImageTk
import pystray
from pystray import MenuItem as item
import json
import random
import webbrowser
from configparser import ConfigParser

APP_VERSION = "1.5.1"


# Theme helpers
DARK_THEME = {
    "bg": "#000000",
    "panel": "#0b0b0b",
    "border": "#222222",
    "fg": "#e6e6e6",
    "accent_green": "#39ff14",
    "muted": "#7a7a7a",
    "selection_bg": "#2a6bd6",
}


def apply_dark_theme(root, accent="white"):
    try:
        from tkinter import ttk as _ttk
    except Exception:
        _ttk = None

    bg = DARK_THEME["bg"]
    panel = DARK_THEME["panel"]
    border = DARK_THEME["border"]
    fg = DARK_THEME["fg"] if accent == "white" else DARK_THEME["accent_green"]
    muted = DARK_THEME["muted"]
    sel = DARK_THEME["selection_bg"]

    try:
        root.configure(bg=bg)
    except Exception:
        pass

    if _ttk:
        style = _ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

    # Create the initial combobox so it's present at startup (light mode by default)
    try:
        _recreate_tool_menu(use_pane_style=False)
    except Exception:
        pass
        try:
            style.configure("Treeview", background=panel, fieldbackground=panel, foreground=fg, rowheight=20)
            style.map("Treeview", background=[("selected", sel)], foreground=[("selected", "white")])
            style.configure("TCombobox", fieldbackground=panel, background=panel, foreground=fg)
            style.configure("TButton", background=panel, foreground=fg)
            style.map("TButton", background=[("active", border)])
        except Exception:
            pass

    try:
        root.option_add('*Menu.background', panel)
        root.option_add('*Menu.foreground', fg)
        root.option_add('*Menu.activeBackground', border)
        root.option_add('*Menu.activeForeground', fg)
        root.option_add('*Label.background', bg)
        root.option_add('*Label.foreground', fg)
        root.option_add('*Frame.background', bg)
        root.option_add('*Button.background', panel)
        root.option_add('*Button.foreground', fg)
    except Exception:
        pass

    try:
        root._dark_theme = {"bg": bg, "panel": panel, "border": border, "fg": fg, "muted": muted, "sel": sel}
    except Exception:
        pass


def apply_light_theme(root):
    # Restore light-ish defaults; not exhaustive but improves readability
    try:
        root.configure(bg="#f0f0f0")
    except Exception:
        pass
    try:
        root.option_add('*Menu.background', '#d0d0d0')
        root.option_add('*Menu.foreground', 'black')
        root.option_add('*Menu.activeBackground', '#ffffff')
        root.option_add('*Menu.activeForeground', 'black')
        root.option_add('*Label.background', '#f0f0f0')
        root.option_add('*Label.foreground', '#444444')
        root.option_add('*Frame.background', '#f0f0f0')
        root.option_add('*Button.background', '#f0f0f0')
        root.option_add('*Button.foreground', 'black')
    except Exception:
        pass
    try:
        if hasattr(root, '_dark_theme'):
            delattr(root, '_dark_theme')
    except Exception:
        pass

# Safely climb until we find the project root folder
project_name = "HoonyTools"
path = Path(__file__).resolve()
while path.name != project_name and path.parent != path:
    path = path.parent
if str(path) not in sys.path:
    sys.path.append(str(path))

logger = logging.getLogger(__name__)
logger.debug(f"Project root resolved as: {path}")

# Add shared HoonyTools path manually
from libs.paths import PROJECT_PATH as base_path, ASSETS_PATH
for p in [path, base_path]:
    if str(p) not in sys.path:
        sys.path.append(str(p))

from libs import abort_manager
# load_files_gui is imported lazily by pane Load button handlers
# from loaders.excel_csv_loader import load_files_gui
from loaders.sql_view_loader import run_sql_view_loader
from loaders.sql_mv_loader import run_sql_mv_loader
# drop_user_tables moved to integrated Drop buttons - import drop_objects on-demand in handlers
from tools.pk_designate_gui import main as pk_designate_main
from libs.bible_books import book_lookup

should_abort = False
auto_scroll_enabled = True
is_gui_running = True
# Guard to prevent scheduling multiple DWH login prompts concurrently
dwh_prompting = False

# Load Bible JSON from libs/en_kjv.json with robust lookup (works in dev and PyInstaller bundles)
BIBLE_VERSES = []

def _find_data_file(name):
    """Return the first existing candidate Path for the data file or None.

    Order of candidates:
    - PyInstaller temp folder (sys._MEIPASS) when frozen
    - PROJECT_PATH / libs (base_path)
    - the script directory /libs
    - current working directory /libs
    """
    candidates = []
    try:
        if getattr(sys, 'frozen', False):
            # PyInstaller extracted temp folder
            meipass = getattr(sys, '_MEIPASS', None)
            if meipass:
                candidates.append(Path(meipass) / name)
                candidates.append(Path(meipass) / 'libs' / name)
    except Exception:
        pass

    # base_path from config (PROJECT_PATH) should point to the project root in dev
    try:
        candidates.append(base_path / 'libs' / name)
    except Exception:
        pass

    # Also check the exe directory (useful for non-extracted builds or when running from dist folder)
    try:
        candidates.append(Path(sys.executable).parent / 'libs' / name)
    except Exception:
        pass

    candidates.append(Path(__file__).resolve().parent / 'libs' / name)
    candidates.append(Path.cwd() / 'libs' / name)

    for p in candidates:
        try:
            if p.exists():
                logger.info(f"Found data file {name} at: {p}")
                return p
        except Exception:
            continue

    logger.warning(f"Data file {name} not found in candidates: {candidates}")
    return None


json_path = _find_data_file('en_kjv.json')
if json_path is not None:
    try:
        with open(json_path, encoding='utf-8-sig') as f:
            books = json.load(f)
            for book in books:
                book_abbrev = book.get('abbrev', '').lower()
                book_name = book_lookup.get(book_abbrev, book_abbrev.upper())
                chapters = book.get('chapters', [])
                for chapter_index, chapter in enumerate(chapters, start=1):
                    if not isinstance(chapter, list):
                        continue
                    for verse_index, verse in enumerate(chapter, start=1):
                        BIBLE_VERSES.append(f"{book_name} {chapter_index}:{verse_index} - {verse}")
        logger.info(f"Loaded {len(BIBLE_VERSES)} Bible verses from {json_path}.")
    except Exception as e:
        logger.exception(f"Failed to load Bible verses from {json_path}: {e}")
else:
    logger.warning('Bible JSON not found; bible features disabled.')
    # Try pkgutil fallback (useful when en_kjv.json was bundled as a package resource)
    try:
        import pkgutil
        data = pkgutil.get_data('libs', 'en_kjv.json')
        if data:
            try:
                books = json.loads(data.decode('utf-8-sig'))
                for book in books:
                    book_abbrev = book.get('abbrev', '').lower()
                    book_name = book_lookup.get(book_abbrev, book_abbrev.upper())
                    chapters = book.get('chapters', [])
                    for chapter_index, chapter in enumerate(chapters, start=1):
                        if not isinstance(chapter, list):
                            continue
                        for verse_index, verse in enumerate(chapter, start=1):
                            BIBLE_VERSES.append(f"{book_name} {chapter_index}:{verse_index} - {verse}")
                logger.info(f"Loaded {len(BIBLE_VERSES)} Bible verses from package resource libs/en_kjv.json")
            except Exception as e:
                logger.exception(f"pkgutil fallback: failed to parse en_kjv.json: {e}")
    except Exception:
        pass

def get_random_verse():
    return random.choice(BIBLE_VERSES) if BIBLE_VERSES else "📖 Verse not available"

def validate_required_folders():
    # Startup should be clean; loaders that need folders should create them when executed.
    return True

def center_window(window, width, height):
    # Center on the monitor that contains the cursor (DPI-aware when possible)
    try:
        window.geometry(f"{width}x{height}")
    except Exception:
        pass

    window.update_idletasks()
    try:
        window.update()
    except Exception:
        pass

    w = window.winfo_width() or width
    h = window.winfo_height() or height

    try:
        if sys.platform.startswith("win"):
            import ctypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

            user32 = ctypes.windll.user32
            pt = POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                MONITOR_DEFAULTTONEAREST = 2
                hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
                if hmon:
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)
                    if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                        left = mi.rcWork.left
                        top = mi.rcWork.top
                        mon_w = mi.rcWork.right - mi.rcWork.left
                        mon_h = mi.rcWork.bottom - mi.rcWork.top

                        x = int(left + (mon_w - w) / 2)
                        y = int(top + (mon_h - h) / 2)

                        try:
                            window.geometry(f"{w}x{h}+{x}+{y}")
                        except Exception:
                            pass

                        # Force native positioning
                        try:
                            hwnd = int(window.winfo_id())
                            SWP_NOSIZE = 0x0001
                            SWP_NOZORDER = 0x0004
                            SWP_SHOWWINDOW = 0x0040
                            user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
                        except Exception:
                            pass
                        return
    except Exception:
        pass

    # Fallback: center on primary screen
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    x = (screen_w // 2) - (w // 2)
    y = (screen_h // 2) - (h // 2)
    try:
        window.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass

def abort_process():
    abort_manager.set_abort(True)
    logger.warning("⛔ Abort requested by user.")
    # Best-effort UI updates and attempt to interrupt blocking DB calls.
    try:
        # Update status light if present
        if 'status_light' in globals() and getattr(status_light, 'winfo_exists', lambda: False)():
            try:
                status_light.config(text="⏹️ Aborting...")
            except Exception:
                pass

        # Disable Run control to avoid starting another operation while aborting
        try:
            if 'run_btn' in globals() and run_btn:
                run_btn.config(state='disabled')
        except Exception:
            pass
        try:
            if 'tool_menu' in globals() and tool_menu:
                try:
                    tool_menu.config(state='disabled')
                except Exception:
                    pass
        except Exception:
            pass

        # Attempt to close any registered DWH connections on this root to help
        # unblock DB calls. Close them in a background thread so the main GUI
        # does not freeze if the close operation blocks or is slow.
        try:
            from libs import dwh_session
            import threading as _thr
            def _close_dwh():
                try:
                    if 'root' in globals():
                        dwh_session.close_dwh_connection(root)
                except Exception:
                    logger.debug('Failed to close DWH connection in background', exc_info=True)
            _thr.Thread(target=_close_dwh, daemon=True).start()
        except Exception:
            pass

        # Attempt to close any active login/prompt windows that were parented
        # to the launcher root (for example DWH login Toplevel). Destroying
        # these windows will release any grabs and prevent the main GUI from
        # remaining unusable after abort.
        try:
            # Also signal any worker waiting on a prompt Event to wake immediately
            try:
                abort_manager.cancel_prompt_event()
            except Exception:
                pass
            if 'root' in globals():
                try:
                    win = getattr(root, '_active_prompt_window', None)
                    if win is not None:
                        try:
                            try:
                                win.grab_release()
                            except Exception:
                                pass
                            win.destroy()
                        except Exception:
                            try:
                                # As a fallback, withdraw the window
                                win.withdraw()
                            except Exception:
                                pass
                        try:
                            delattr(root, '_active_prompt_window')
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass

        # Best-effort close of the worker connection to interrupt blocking DB operations
        try:
            try:
                abort_manager.close_registered_connection()
            except Exception:
                pass
        except Exception:
            pass

        # Monitor abort flag and re-enable UI when cleared by workers
        def _monitor_abort():
            import time
            try:
                # Wait until either the abort flag is cleared by the worker (reset)
                # or cleanup_on_abort has completed (cleanup_done). Add a safety
                # timeout so the launcher does not remain disabled indefinitely
                # if the worker thread gets stuck.
                max_wait = 30.0  # seconds
                waited = 0.0
                step = 0.2
                while True:
                    try:
                        should = getattr(abort_manager, 'should_abort', False)
                        done = getattr(abort_manager, 'cleanup_done', False)
                    except Exception:
                        should = False
                        done = False
                    if not should or done:
                        break
                    if waited >= max_wait:
                        logger.warning("Abort monitor timed out waiting for worker cleanup; forcing reset and re-enabling UI")
                        try:
                            abort_manager.reset()
                        except Exception:
                            pass
                        break
                    time.sleep(step)
                    waited += step
            except Exception:
                pass

            def _reenable():
                try:
                    if 'status_light' in globals() and getattr(status_light, 'winfo_exists', lambda: False)():
                        status_light.config(text="🟢")
                except Exception:
                    pass
                try:
                    if 'run_btn' in globals() and run_btn:
                        run_btn.config(state='normal')
                except Exception:
                    pass
                try:
                    if 'tool_menu' in globals() and tool_menu:
                        try:
                            tool_menu.config(state='readonly')
                        except Exception:
                            pass
                except Exception:
                    pass

            try:
                if 'root' in globals():
                    try:
                        root.after(0, _reenable)
                    except Exception:
                        _reenable()
                else:
                    _reenable()
            except Exception:
                pass

        import threading
        threading.Thread(target=_monitor_abort, daemon=True).start()
    except Exception:
        pass

def run_selected():
    global should_abort
    should_abort = False
    tool_name = selected_tool.get()
    logger.info(f"Run button pressed for tool: {tool_name}")
    log_text.delete(1.0, tk.END)
    status_light.config(text="⏳")     

    def run_and_update_with_conn(conn):
        try:
            logger.info(f"🚀 Running: {tool_name}")
            try:
                TOOLS[tool_name](conn)
            except TypeError:
                # fallback: call without conn if callable doesn't accept it
                TOOLS[tool_name]()
        except Exception as e:
            logger.exception(f"❌ Error running {tool_name}: {e}")
        finally:
            status_light.config(text="🟢")

    # If selected tool is missing or None, inform the user
    if tool_name not in TOOLS or TOOLS.get(tool_name) is None:
        try:
            from tkinter import messagebox
            messagebox.showwarning("Tool Unavailable", f"Selected tool is not available: {tool_name}")
        except Exception:
            logger.warning(f"Selected tool is not available: {tool_name}")
        status_light.config(text="🟢")
        return

    

    # For everything else
    def run_and_update():
        try:
            # Tools that accept an on_finish callback should be called with it so the launcher
            # can update its status light. Treat SQL View and SQL Materialized View loaders
            # the same way.
            if tool_name in ("☑ SQL View Loader", "☑ SQL Materialized View Loader"):
                # Pass launcher root as parent so loaders can register theme callbacks
                try:
                    TOOLS[tool_name](root, on_finish=lambda: status_light.config(text="🟢"))
                except TypeError:
                    # fallback for older signatures
                    try:
                        TOOLS[tool_name](on_finish=lambda: status_light.config(text="🟢"))
                    except Exception:
                        TOOLS[tool_name]()
            else:
                try:
                    # Prefer passing launcher root to tools when supported so dialogs are parented correctly
                    TOOLS[tool_name](root)
                except TypeError:
                    try:
                        TOOLS[tool_name]()
                    except TypeError:
                        # Last resort: call without args
                        TOOLS[tool_name]()
                status_light.config(text="🟢")
        except KeyboardInterrupt:
            # User or system interrupted the tool; attempt graceful cleanup and avoid
            # letting KeyboardInterrupt propagate into Tk's callback machinery.
            try:
                logger.info(f"Tool run interrupted by KeyboardInterrupt: {tool_name}")
            except Exception:
                pass
            try:
                status_light.config(text="🟢")
            except Exception:
                pass
            return
        except Exception as e:
            logger.exception(f"❌ Error running {tool_name}: {e}")
            try:
                status_light.config(text="🟢")
            except Exception:
                pass

    run_and_update()

def stream_logs():
    global is_gui_running
    if not is_gui_running or not log_text.winfo_exists():
        return  # Stop logging loop if GUI is closed

    try:
        text = log_stream.getvalue()
        log_text.insert(tk.END, text)

        if auto_scroll_enabled:
            log_text.see(tk.END)

        log_stream.truncate(0)
        log_stream.seek(0)

        from libs.oracle_db_connector import process_queued_errors
        process_queued_errors(root)

    except tk.TclError:
        return  # Window or widget was destroyed

    log_text.after(500, stream_logs)


def show_splash():
    splash = tk.Tk()
    splash.overrideredirect(True)
    center_window(splash, 420, 260)
    splash.attributes('-alpha', 0.0)

    # === HoonyTools Logo + Title ===
    try:
        hoony_logo_path = ASSETS_PATH / "assets" / "hoonywise_300.png"
        hoony_img = Image.open(hoony_logo_path).resize((36, 36))
        hoony_logo = ImageTk.PhotoImage(hoony_img)

        logo_title_frame = tk.Frame(splash)
        logo_title_frame.pack(pady=(40, 10))

        tk.Label(logo_title_frame, image=hoony_logo).pack(side="left", padx=(0, 10))
        tk.Label(logo_title_frame, text="HoonyTools Launcher", font=("Arial", 16, "bold")).pack(side="left")

        splash.hoony_logo = hoony_logo  # Prevent garbage collection
    except:
        tk.Label(splash, text="HoonyTools Launcher", font=("Arial", 18, "bold")).pack(pady=(40, 10))

    # === Created by hoonywise ===
    footer_top = tk.Label(
        splash,
        text="Created by hoonywise · hoonywise@proton.me",
        font=("Arial", 9, "italic"),
        fg="#444444"
    )
    footer_top.pack(side="bottom", pady=(0, 2))

    footer_version = tk.Label(
        splash,
        text=f"v{APP_VERSION}",
        font=("Arial", 9, "bold"),
        fg="#444444"
    )
    footer_version.pack(side="bottom", pady=(0, 12))

    def fade_in(alpha=0.0):
        if alpha < 1.0:
            splash.attributes('-alpha', alpha)
            splash.after(30, lambda: fade_in(alpha + 0.05))
        else:
            splash.after(3000, fade_out)  # hold full splash (logo + labels) for 3s

    def fade_out(alpha=1.0):
        if alpha > 0.0:
            splash.attributes('-alpha', alpha)
            splash.after(14, lambda: fade_out(alpha - 0.7))
        else:
            splash.destroy()
            
    fade_in()
    splash.mainloop()

def launch_tool_gui():
    from libs.oracle_db_connector import prompt_credentials
    from libs import session  # 👈 NEW


    
    global root, selected_tool, log_text, log_stream, status_light, run_btn, tool_menu

    # Create the main Tk root directly and keep it hidden while login dialog appears.
    root = tk.Tk()
    root.withdraw()
    # NOTE: Do not bind WM_DELETE_WINDOW here because safe_exit (defined later)
    # performs full cleanup. Bind the protocol to safe_exit after it's defined.

    # Set Windows AppUserModelID for taskbar icon
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
            icon_ico_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
            root.iconbitmap(default=icon_ico_path)
        except Exception as e:
            print(f"⚠️ Failed to set taskbar icon: {e}")

    # Keep the main window hidden while the login dialog is shown
    # This prevents geometry nudging issues on some systems. The main
    # window will be deiconified and centered after a successful login.
    root.withdraw()

    # 4️⃣ 🔐 Prompt for login
    session.stored_credentials = prompt_credentials()
    # Also populate user_credentials so user-scoped tools don't re-prompt
    if session.stored_credentials:
        try:
            session.user_credentials = session.stored_credentials
        except Exception:
            pass
    # Load saved DWH creds from config.ini (if present) so refresh can use them immediately
    try:
        from libs import oracle_db_connector as _ob
        if _ob.config and _ob.config.has_section("dwh"):
            sec = _ob.config["dwh"]
            try:
                session.dwh_credentials = {"username": sec.get("username"), "password": sec.get("password"), "dsn": sec.get("dsn")}
            except Exception:
                pass
    except Exception:
        pass
    if not session.stored_credentials:
        try:
            root.destroy()
        except Exception:
            pass
        try:
            if 'hidden_root' in globals() and getattr(hidden_root, 'winfo_exists', lambda: False)():
                try:
                    hidden_root.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        return
    
    # ✅ After login success: show and center the main window
    root.deiconify()
    # Ensure the window is realized, then center it on the primary monitor
    try:
        root.update()
    except Exception:
        pass
    center_window(root, 1280, 960)  # Resize to full GUI and center on screen
    try:
        root.lift()
        root.focus_force()
    except Exception:
        pass
    root.title("HoonyTools Launcher")

    # === Bible Verse Row (centered across the entire window) ===
    verse_frame = tk.Frame(root)
    verse_frame.pack(fill="x", padx=10, pady=(0, 8))

    # === Main content: two-column layout (left object lists, right main UI) ===
    content_frame = tk.Frame(root)
    content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # Left pane for object lists (fixed width)
    left_pane = tk.Frame(content_frame, width=360)
    # fill both so the left pane stretches vertically and the two child frames
    # can share vertical space equally
    # reduce top padding so the left pane top lines up with the log area
    left_pane.pack(side="left", fill="both", padx=(6, 10), pady=(6,0))
    left_pane.config(width=360)

    # Right pane for existing UI (tools, log, status)
    right_pane = tk.Frame(content_frame)
    right_pane.pack(side="left", fill="both", expand=True)

    verse_label = tk.Label(
        verse_frame,
        text=get_random_verse(),
        font=("Arial", 9, "italic"),
        fg=getattr(root, "_dark_theme", {}).get("muted", "#444444"),
        anchor="center",
        justify="center",
        wraplength=1000
    )
    verse_label.pack(fill="x")

    # 🔁 Optionally refresh verse every 60 seconds
    def rotate_verse():
        verse_label.config(text=get_random_verse())
        root.after(77777, rotate_verse)  

    rotate_verse()    
        
    # Horizontal divider below verse
    tk.Frame(root, height=1, bg=getattr(root, "_dark_theme", {}).get("border", "#ccc")).pack(fill="x", padx=10, pady=(5, 10))    

    # ✅ Set GUI icon (.ico for taskbar)
    icon_ico_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
    root.iconbitmap(default=icon_ico_path)

    # ✅ Set window icon (.png for title bar)
    icon_path = ASSETS_PATH / "assets" / "hoonywise_300.png"
    icon_img = tk.PhotoImage(file=icon_path)
    root.iconphoto(False, icon_img)
    root.icon_img = icon_img  # Prevents garbage collection

    # === Load Logo Assets ===
    assets_path = base_path / "assets"
    # Initialize Oracle client early and load saved DWH creds into session if present
    try:
        from libs import oracle_db_connector as _ob, session as _session
        if _ob.config and _ob.config.has_section("dwh"):
            sec = _ob.config["dwh"]
            try:
                _session.dwh_credentials = {"username": sec.get("username"), "password": sec.get("password"), "dsn": sec.get("dsn")}
            except Exception:
                pass
        try:
            import oracledb as _orac
            try:
                _orac.init_oracle_client()
                logger.info("✅ Oracle client initialized (Thick mode if available)")
            except Exception:
                logger.info("ℹ️ Oracle client init skipped or unavailable; proceeding with Thin mode")
        except Exception:
            pass
    except Exception:
        pass
    
    # --- Helper: make treeview columns sortable by clicking headers
    def _make_sortable_tree(tv):
        """Enable sorting by clicking column headers. Shows sort direction with arrows."""
        # Store sort state per column
        sort_state = {}  # col -> bool (True = descending, False = ascending)
        
        def sort_column(col):
            # Toggle sort direction
            reverse = sort_state.get(col, False)
            sort_state[col] = not reverse
            
            # Get all items with their values
            data = []
            for child in tv.get_children(''):
                vals = tv.item(child)['values']
                col_idx = list(tv['columns']).index(col)
                val = vals[col_idx] if col_idx < len(vals) else ''
                data.append((val, child))
            
            # Sort (case-insensitive for strings)
            def sort_key(x):
                v = x[0]
                if v is None:
                    return ''
                return str(v).lower()
            data.sort(key=sort_key, reverse=reverse)
            
            # Rearrange items in treeview
            for index, (val, child) in enumerate(data):
                tv.move(child, '', index)
            
            # Update all headers - reset others, show arrow on sorted column
            col_titles = {'name': 'Name', 'type': 'Type', 'info': 'Info'}
            for c in tv['columns']:
                base_title = col_titles.get(c, c.title())
                if c == col:
                    arrow = ' \u25bc' if reverse else ' \u25b2'  # ▼ or ▲
                    tv.heading(c, text=base_title + arrow)
                else:
                    tv.heading(c, text=base_title)
        
        # Bind click handlers to each column header
        for col in tv['columns']:
            tv.heading(col, command=lambda c=col: sort_column(c))
    
    # --- Helper: bind Ctrl+A to select all items in treeview
    def _bind_select_all(tv):
        """Enable Ctrl+A to select all items in the treeview."""
        def select_all(event):
            # Select all items in the treeview
            all_items = tv.get_children('')
            if all_items:
                tv.selection_set(all_items)
            return "break"  # Prevent default behavior
        
        tv.bind('<Control-a>', select_all)
        tv.bind('<Control-A>', select_all)  # Handle caps lock
    
    # --- Helper: create object list frame in left pane
    def _make_objects_frame(parent, title):
        frame = tk.LabelFrame(parent, text=title, padx=6, pady=6)
        # allow frames to share available vertical space equally
        frame.pack(fill="both", pady=(0, 8), expand=True)

        # Top bar inside the LabelFrame: Refresh button near the left (next to title)
        # Add left padding so the button is visually separated from the frame border
        top_bar = tk.Frame(frame)
        top_bar.pack(fill="x", anchor="n", padx=8, pady=(0, 8))
        refresh_btn = tk.Button(top_bar, text="Refresh", width=10)
        refresh_btn.pack(side="left", padx=(0, 8))
        index_btn = tk.Button(top_bar, text="Index", width=10)
        index_btn.pack(side="left", padx=(0, 8))
        load_btn = tk.Button(top_bar, text="Load", width=10)
        load_btn.pack(side="left", padx=(0, 8))
        drop_btn = tk.Button(top_bar, text="Drop", width=10)
        drop_btn.pack(side="left", padx=(0, 8))
        status_lbl = tk.Label(top_bar, text="", font=("Arial", 8), fg=getattr(parent.master, "_dark_theme", {}).get("muted", "#444444"))
        status_lbl.pack(side="left")

        # Content area (treeview + scrollbar) sits below the top bar and expands
        content_area = tk.Frame(frame)
        content_area.pack(fill="both", expand=True)

        # Lock treeview width to avoid auto-resize when labels change
        # Third column `info` shows PK columns for tables or parent table for indexes
        # selectmode="extended" enables multi-select with Ctrl+click and Shift+click
        tv = ttk.Treeview(content_area, columns=("name", "type", "info"), show="headings", selectmode="extended")
        tv.heading("name", text="Name")
        tv.heading("type", text="Type")
        tv.heading("info", text="Info")
        tv.column("name", width=160, anchor="w", stretch=False)
        tv.column("type", width=120, anchor="center", stretch=False)
        tv.column("info", width=160, anchor="w", stretch=False)
        vs = tk.Scrollbar(content_area, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        tv.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        return frame, tv, refresh_btn, index_btn, load_btn, drop_btn, status_lbl

    # Ensure Treeview style is configured before creating tree widgets so
    # style settings are honored by backends (especially on Windows ttk).
    try:
        pre_style = ttk.Style()
        try:
            pre_style.theme_use('clam')
        except Exception:
            pass
        try:
            # Default (light) appearance for Pane.Treeview; setters below will
            # override when user enables pane-only dark mode.
            pre_style.configure('Pane.Treeview', background='white', fieldbackground='white', foreground='black', rowheight=20)
            pre_style.configure('Treeview.Heading', background='#e8e8e8', foreground='black')
        except Exception:
            pass
    except Exception:
        pre_style = None

    # Create the two object panes in the left_pane (stacked, share vertical space)
    user_frame, user_tree, user_refresh_btn, user_index_btn, user_load_btn, user_drop_btn, user_status = _make_objects_frame(left_pane, "User Objects")
    dwh_frame, dwh_tree, dwh_refresh_btn, dwh_index_btn, dwh_load_btn, dwh_drop_btn, dwh_status = _make_objects_frame(left_pane, "DWH Objects")
    
    # Enable sortable column headers for both treeviews
    _make_sortable_tree(user_tree)
    _make_sortable_tree(dwh_tree)
    
    # Enable Ctrl+A to select all for both treeviews
    _bind_select_all(user_tree)
    _bind_select_all(dwh_tree)

    # Keep cached row data so we can recreate trees when toggling theme
    user_rows = []
    dwh_rows = []

    # Prevent the left pane from auto-resizing when internal labels change
    left_pane.pack_propagate(False)

    # Create external count labels aligned to the right of each object frame
    # Use grid placement so they don't affect the inner frame widths
    user_count_label = tk.Label(left_pane, text="", font=("Arial", 8), fg=getattr(left_pane, "_dark_theme", {}).get("muted", "#444444"))
    dwh_count_label = tk.Label(left_pane, text="", font=("Arial", 8), fg=getattr(left_pane, "_dark_theme", {}).get("muted", "#444444"))
    # start with a placeholder placement; we'll position these next to the LabelFrame titles
    user_count_label.place(x=0, y=0)
    dwh_count_label.place(x=0, y=0)

    # hide the internal status labels created inside each frame to avoid them resizing the frame
    try:
        user_status.pack_forget()
    except Exception:
        pass
    try:
        dwh_status.pack_forget()
    except Exception:
        pass

    # Make the two left frames share the available vertical space equally
    # Place frames into grid so rowconfigure can control their weights
    left_pane.grid_rowconfigure(0, weight=1)
    left_pane.grid_rowconfigure(1, weight=1)
    # prevent the count label column from expanding; let column 0 (frames) take all extra space
    left_pane.grid_columnconfigure(0, weight=1)
    left_pane.grid_columnconfigure(1, weight=0)
    # Re-pack the frames using grid so they share the vertical space
    user_frame.pack_forget()
    dwh_frame.pack_forget()
    # add left padding so the object frames sit a few pixels in from the left border
    user_frame.grid(row=0, column=0, sticky="nsew", pady=(0,8), padx=(14,0))
    dwh_frame.grid(row=1, column=0, sticky="nsew", padx=(14,0))

    # Position the object-count labels next to each LabelFrame title (top-left header area)
    def position_count_labels(event=None):
        try:
            left_pane.update_idletasks()
            import tkinter.font as tkfont
            default_font = tkfont.nametofont("TkDefaultFont")

            # User frame title placement
            ux = user_frame.winfo_x()
            uy = user_frame.winfo_y()
            user_title = user_frame.cget("text")
            title_w = default_font.measure(user_title)
            # small left offset inside the LabelFrame border (~8 px), then a small gap
            user_count_label.place(x=ux + 8 + title_w + 8, y=uy - 2)

            # DWH frame title placement
            dx = dwh_frame.winfo_x()
            dy = dwh_frame.winfo_y()
            dwh_title = dwh_frame.cget("text")
            dwh_title_w = default_font.measure(dwh_title)
            dwh_count_label.place(x=dx + 8 + dwh_title_w + 8, y=dy - 2)
        except Exception:
            pass

    left_pane.bind('<Configure>', position_count_labels)
    root.after(100, position_count_labels)

    # Utility to populate a treeview from rows [(name, type), ...]
    def _populate_treeview(tv, rows):
        try:
            tv.delete(*tv.get_children())
        except Exception:
            pass
        for row in rows:
            # rows may be tuples of (name, type) or (name, type, pk)
            try:
                name = row[0]
                obj_type = row[1]
                pk = row[2] if len(row) > 2 else ""
            except Exception:
                continue
            # Insert with a consistent tag so we can theme row backgrounds later
            try:
                tv.insert("", "end", values=(name, obj_type, pk or ""), tags=("row",))
            except Exception:
                tv.insert("", "end", values=(name, obj_type, pk or ""))

        # cache rows for possible rebuild
        try:
            if tv is user_tree:
                nonlocal user_rows
                user_rows = list(rows)
            elif tv is dwh_tree:
                nonlocal dwh_rows
                dwh_rows = list(rows)
        except Exception:
            pass

    # Recreate a Treeview widget under the current style and repopulate it.
    # use_pane_style: when True, create with 'Pane.Treeview' style alias.
    def _recreate_tree(old_tv, use_pane_style=False):
        parent = old_tv.master
        cols = ("name", "type", "info")
        widths = {}
        try:
            for c in cols:
                widths[c] = old_tv.column(c, option='width')
        except Exception:
            widths = {}
        try:
            y0 = old_tv.yview()[0]
        except Exception:
            y0 = 0.0
        try:
            sel = old_tv.selection()
        except Exception:
            sel = ()

        # destroy existing children (tree + scrollbar)
        try:
            for ch in list(parent.winfo_children()):
                try:
                    ch.destroy()
                except Exception:
                    pass
        except Exception:
            pass

        # create the new tree using Pane.Treeview when requested, with multi-select enabled
        try:
            style_name = 'Pane.Treeview' if use_pane_style else ''
            new_tv = ttk.Treeview(parent, columns=cols, show="headings", style=style_name, selectmode="extended")
        except Exception:
            new_tv = ttk.Treeview(parent, columns=cols, show="headings", selectmode="extended")

        try:
            new_tv.heading("name", text="Name")
            new_tv.heading("type", text="Type")
            new_tv.heading("info", text="Info")
            new_tv.column("name", width=widths.get('name', 160), anchor="w", stretch=False)
            new_tv.column("type", width=widths.get('type', 120), anchor="center", stretch=False)
            new_tv.column("info", width=widths.get('info', 160), anchor="w", stretch=False)
        except Exception:
            pass
        
        # Enable sortable column headers
        try:
            _make_sortable_tree(new_tv)
        except Exception:
            pass
        
        # Enable Ctrl+A to select all
        try:
            _bind_select_all(new_tv)
        except Exception:
            pass

        try:
            vs = tk.Scrollbar(parent, orient="vertical", command=new_tv.yview)
            new_tv.configure(yscrollcommand=vs.set)
            new_tv.pack(side="left", fill="both", expand=True)
            vs.pack(side="right", fill="y")
        except Exception:
            new_tv.pack(fill="both", expand=True)

        try:
            rows = user_rows if old_tv is user_tree else dwh_rows if old_tv is dwh_tree else []
        except Exception:
            rows = []

        try:
            for r in rows:
                try:
                    new_tv.insert("", "end", values=(r[0], r[1], r[2] if len(r) > 2 else ""), tags=("row",))
                except Exception:
                    try:
                        new_tv.insert("", "end", values=(r[0], r[1], ""))
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            new_tv.update_idletasks()
            new_tv.yview_moveto(y0)
        except Exception:
            pass
        try:
            if sel:
                for s in sel:
                    try:
                        new_tv.selection_add(s)
                    except Exception:
                        pass
        except Exception:
            pass

        return new_tv

    # Background refreshers
    def refresh_user_objects():
        user_status.config(text="Loading...")
        def worker():
            from libs.oracle_db_connector import get_db_connection
            conn = get_db_connection(force_shared=False)
            if not conn:
                root.after(0, lambda: user_status.config(text="No connection"))
                return
            try:
                cur = conn.cursor()
                owner = conn.username.upper()
                
                # Query for tables, views, materialized views with PK info
                # Exclude TABLEs that are backing tables for materialized views (same name as an MV)
                cur.execute("""
                    SELECT ao.object_name,
                           ao.object_type,
                           (
                             SELECT LISTAGG(acc.column_name, ', ') WITHIN GROUP (ORDER BY acc.position)
                             FROM all_constraints ac
                             JOIN all_cons_columns acc
                               ON ac.owner = acc.owner AND ac.constraint_name = acc.constraint_name
                             WHERE ac.owner = ao.owner
                               AND ac.table_name = ao.object_name
                               AND ac.constraint_type = 'P'
                           ) AS primary_key_cols
                    FROM all_objects ao
                    WHERE ao.owner = :owner
                    AND ao.object_type IN ('TABLE','VIEW','MATERIALIZED VIEW')
                    AND NOT (
                        ao.object_type = 'TABLE' 
                        AND EXISTS (
                            SELECT 1 FROM all_objects mv 
                            WHERE mv.owner = ao.owner 
                            AND mv.object_name = ao.object_name 
                            AND mv.object_type = 'MATERIALIZED VIEW'
                        )
                    )
                    ORDER BY ao.object_type, ao.object_name
                """, [owner])
                obj_rows = cur.fetchall()
                
                # Query for user-created indexes (excluding system and PK-backing indexes)
                cur.execute("""
                    SELECT ai.index_name,
                           'INDEX' AS object_type,
                           ai.table_name
                    FROM all_indexes ai
                    WHERE ai.owner = :owner
                      AND ai.index_name NOT LIKE 'SYS_%'
                      AND ai.index_name NOT LIKE 'BIN$%'
                      AND NOT EXISTS (
                        SELECT 1 FROM all_constraints ac
                        WHERE ac.owner = ai.owner
                          AND ac.constraint_type = 'P'
                          AND ac.index_name = ai.index_name
                      )
                    ORDER BY ai.index_name
                """, [owner])
                idx_rows = cur.fetchall()
                
                # Query for primary key constraints (as droppable objects)
                cur.execute("""
                    SELECT ac.constraint_name,
                           'PRIMARY KEY' AS object_type,
                           ac.table_name
                    FROM all_constraints ac
                    WHERE ac.owner = :owner
                      AND ac.constraint_type = 'P'
                    ORDER BY ac.table_name, ac.constraint_name
                """, [owner])
                pk_rows = cur.fetchall()
                
                # Format rows for display: (name, type, info)
                # For tables/views/mvs: info = "PK: col1, col2" or empty
                # For indexes: info = "Table: TABLE_NAME"
                # For PKs: info = "Table: TABLE_NAME"
                # For MLOGs: type = "MVIEW LOG", info = "Table: BASE_TABLE"
                formatted_rows = []
                for name, obj_type, pk_cols in obj_rows:
                    # Detect MLOG tables (materialized view logs) - they start with MLOG$
                    if obj_type == 'TABLE' and name.upper().startswith('MLOG$'):
                        # Extract base table name from MLOG$_TABLENAME or MLOG$TABLENAME
                        base_table = name[5:].lstrip('_')  # Remove MLOG$ and optional underscore
                        formatted_rows.append((name, 'MVIEW LOG', f"Table: {base_table}"))
                    else:
                        info = f"PK: {pk_cols}" if pk_cols else ""
                        formatted_rows.append((name, obj_type, info))
                for idx_name, obj_type, table_name in idx_rows:
                    info = f"Table: {table_name}" if table_name else ""
                    formatted_rows.append((idx_name, obj_type, info))
                for pk_name, obj_type, table_name in pk_rows:
                    info = f"Table: {table_name}" if table_name else ""
                    formatted_rows.append((pk_name, obj_type, info))
                
                rows = formatted_rows
            except Exception as e:
                rows = []
                logger.exception(f"Failed to list user objects: {e}")
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            # If no rows found, show friendly message in status
            if not rows:
                # update external count label and tree
                root.after(0, lambda: (_populate_treeview(user_tree, rows), user_count_label.config(text="No Objects")))
            else:
                root.after(0, lambda: (_populate_treeview(user_tree, rows), user_count_label.config(text=f"{len(rows)} Objects")))
        threading.Thread(target=worker, daemon=True).start()

    def refresh_dwh_objects():
        dwh_status.config(text="Loading...")

        # Helper: spawn a worker that connects using explicit credentials (no UI prompts)
        def _start_worker_with_creds(creds):
            def worker():
                import oracledb
                # Ensure Oracle client is initialized (helps tnsnames resolution in thick mode)
                try:
                    oracledb.init_oracle_client()
                except Exception:
                    # init may fail or be unnecessary (thin mode); ignore
                    pass
                rows = []
                cur = None
                conn = None
                try:
                    conn = oracledb.connect(user=creds["username"], password=creds["password"], dsn=creds["dsn"])
                    cur = conn.cursor()
                    
                    # Query for tables, views, materialized views with PK info
                    # Exclude TABLEs that are backing tables for materialized views (same name as an MV)
                    cur.execute("""
                        SELECT ao.object_name,
                               ao.object_type,
                               (
                                 SELECT LISTAGG(acc.column_name, ', ') WITHIN GROUP (ORDER BY acc.position)
                                 FROM all_constraints ac
                                 JOIN all_cons_columns acc
                                   ON ac.owner = acc.owner AND ac.constraint_name = acc.constraint_name
                                 WHERE ac.owner = ao.owner
                                   AND ac.table_name = ao.object_name
                                   AND ac.constraint_type = 'P'
                               ) AS primary_key_cols
                        FROM all_objects ao
                        WHERE ao.owner = :owner
                        AND ao.object_type IN ('TABLE','VIEW','MATERIALIZED VIEW')
                        AND NOT (
                            ao.object_type = 'TABLE' 
                            AND EXISTS (
                                SELECT 1 FROM all_objects mv 
                                WHERE mv.owner = ao.owner 
                                AND mv.object_name = ao.object_name 
                                AND mv.object_type = 'MATERIALIZED VIEW'
                            )
                        )
                        ORDER BY ao.object_type, ao.object_name
                    """, ["DWH"])
                    obj_rows = cur.fetchall()
                    
                    # Query for user-created indexes (excluding system and PK-backing indexes)
                    cur.execute("""
                        SELECT ai.index_name,
                               'INDEX' AS object_type,
                               ai.table_name
                        FROM all_indexes ai
                        WHERE ai.owner = :owner
                          AND ai.index_name NOT LIKE 'SYS_%'
                          AND ai.index_name NOT LIKE 'BIN$%'
                          AND NOT EXISTS (
                            SELECT 1 FROM all_constraints ac
                            WHERE ac.owner = ai.owner
                              AND ac.constraint_type = 'P'
                              AND ac.index_name = ai.index_name
                          )
                        ORDER BY ai.index_name
                    """, ["DWH"])
                    idx_rows = cur.fetchall()
                    
                    # Query for primary key constraints (as droppable objects)
                    cur.execute("""
                        SELECT ac.constraint_name,
                               'PRIMARY KEY' AS object_type,
                               ac.table_name
                        FROM all_constraints ac
                        WHERE ac.owner = :owner
                          AND ac.constraint_type = 'P'
                        ORDER BY ac.table_name, ac.constraint_name
                    """, ["DWH"])
                    pk_rows = cur.fetchall()
                    
                    # Format rows for display: (name, type, info)
                    # For tables/views/mvs: info = "PK: col1, col2" or empty
                    # For indexes: info = "Table: TABLE_NAME"
                    # For PKs: info = "Table: TABLE_NAME"
                    # For MLOGs: type = "MVIEW LOG", info = "Table: BASE_TABLE"
                    formatted_rows = []
                    for name, obj_type, pk_cols in obj_rows:
                        # Detect MLOG tables (materialized view logs) - they start with MLOG$
                        if obj_type == 'TABLE' and name.upper().startswith('MLOG$'):
                            # Extract base table name from MLOG$_TABLENAME or MLOG$TABLENAME
                            base_table = name[5:].lstrip('_')  # Remove MLOG$ and optional underscore
                            formatted_rows.append((name, 'MVIEW LOG', f"Table: {base_table}"))
                        else:
                            info = f"PK: {pk_cols}" if pk_cols else ""
                            formatted_rows.append((name, obj_type, info))
                    for idx_name, obj_type, table_name in idx_rows:
                        info = f"Table: {table_name}" if table_name else ""
                        formatted_rows.append((idx_name, obj_type, info))
                    for pk_name, obj_type, table_name in pk_rows:
                        info = f"Table: {table_name}" if table_name else ""
                        formatted_rows.append((pk_name, obj_type, info))
                    
                    rows = formatted_rows
                except Exception as e:
                    rows = []
                    err_text = str(e)
                    # Treat certain errors as expected environment/tns issues and avoid noisy stacktraces.
                    if ("DPY-4026" in err_text) or ("tnsnames" in err_text.lower()) or isinstance(e, FileNotFoundError):
                        # Informational: tnsnames/tns error detected; prompt the user to repair DWH login.
                        logger.info(f"DWH connect encountered tns/tnsnames issue; will prompt user: {err_text}")
                        # Update status label and schedule a single main-thread prompt to repair DWH creds/config if not already prompting
                        try:
                            try:
                                root.after(0, lambda: dwh_status.config(text="Prompting for DWH login..."))
                            except Exception:
                                pass
                            from libs import session as _session
                            global dwh_prompting
                            if not dwh_prompting:
                                dwh_prompting = True
                                def prompt_and_retry():
                                    try:
                                        from libs.oracle_db_connector import get_db_connection
                                        conn2 = get_db_connection(force_shared=True, root=root)
                                        if conn2:
                                            try:
                                                conn2.close()
                                            except Exception:
                                                pass
                                            if _session.dwh_credentials:
                                                # retry using new creds
                                                _start_worker_with_creds(_session.dwh_credentials)
                                    finally:
                                        try:
                                            # allow future prompts
                                            dwh_prompting = False
                                        except Exception:
                                            pass
                                try:
                                    root.after(0, prompt_and_retry)
                                except Exception:
                                    dwh_prompting = False
                        except Exception:
                            logger.warning("Failed to schedule DWH login prompt after tns error.")
                    else:
                        # Unexpected errors: log stacktrace so we can diagnose
                        logger.exception(f"Failed to list DWH objects: {e}")
                finally:
                    try:
                        if cur:
                            cur.close()
                    except Exception:
                        pass
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass

                if not rows:
                    root.after(0, lambda: (_populate_treeview(dwh_tree, rows), dwh_count_label.config(text="No Objects"), dwh_status.config(text="")))
                else:
                    root.after(0, lambda: (_populate_treeview(dwh_tree, rows), dwh_count_label.config(text=f"{len(rows)} Objects"), dwh_status.config(text="")))

            threading.Thread(target=worker, daemon=True).start()

        # Decide whether we can use saved creds (no UI) or need to prompt on the main thread
        from libs import session
        from libs import oracle_db_connector as ob

        creds = None
        if session.dwh_credentials and session.dwh_credentials.get("username", "").lower() == "dwh":
            creds = session.dwh_credentials
        elif ob.config.has_section("dwh"):
            section = ob.config["dwh"]
            if section.get("username") and section.get("password") and section.get("dsn"):
                creds = {
                    "username": section.get("username"),
                    "password": section.get("password"),
                    "dsn": section.get("dsn")
                }

        if creds:
            # Use the saved credentials from session or config.ini in a background thread
            _start_worker_with_creds(creds)
            return

        # No saved creds: prompt on the main thread (get_db_connection will schedule a dialog via root)
        from libs.oracle_db_connector import get_db_connection
        conn = get_db_connection(force_shared=True, root=root)
        if not conn:
            root.after(0, lambda: dwh_status.config(text="Not logged in"))
            return

        # If get_db_connection returned a connection, close it and use the stored session credentials
        try:
            conn.close()
        except Exception:
            pass

        # session.dwh_credentials should have been set by get_db_connection when prompting
        creds = session.dwh_credentials if session.dwh_credentials else None
        if not creds:
            root.after(0, lambda: dwh_status.config(text="No credentials"))
            return

        _start_worker_with_creds(creds)

    # Wire buttons
    user_refresh_btn.config(command=refresh_user_objects)
    dwh_refresh_btn.config(command=refresh_dwh_objects)

    # --- Index button handlers ---
    def _get_selected_object(tree):
        """Return (name, type) from the currently selected treeview row, or (None, None)."""
        sel = tree.selection()
        if not sel:
            return None, None
        item = tree.item(sel[0])
        vals = item.get('values', ())
        if len(vals) < 2:
            return None, None
        return str(vals[0]), str(vals[1])

    def launch_index_user():
        name, obj_type = _get_selected_object(user_tree)
        if not name:
            from tkinter import messagebox
            messagebox.showwarning('No Selection', 'Please select an object in the User Objects pane first.', parent=root)
            return
        if obj_type and obj_type.upper() == 'VIEW':
            from tkinter import messagebox
            messagebox.showwarning('Not Supported', 'Indexes cannot be created on views. Please select a table or materialized view.', parent=root)
            return
        # Determine user schema from session credentials
        from libs import session as _sess
        owner = None
        if _sess.stored_credentials:
            owner = _sess.stored_credentials.get('username', '').upper()
        if not owner:
            try:
                from libs.oracle_db_connector import get_db_connection
                conn = get_db_connection(force_shared=False, root=root)
                if conn:
                    owner = conn.username.upper()
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                pass
        if not owner:
            from tkinter import messagebox
            messagebox.showerror('Error', 'Could not determine user schema.', parent=root)
            return
        from tools.index_gui import main as index_main
        index_main(parent=root, schema=owner, object_name=name, object_type=obj_type)

    def launch_index_dwh():
        name, obj_type = _get_selected_object(dwh_tree)
        if not name:
            from tkinter import messagebox
            messagebox.showwarning('No Selection', 'Please select an object in the DWH Objects pane first.', parent=root)
            return
        if obj_type and obj_type.upper() == 'VIEW':
            from tkinter import messagebox
            messagebox.showwarning('Not Supported', 'Indexes cannot be created on views. Please select a table or materialized view.', parent=root)
            return
        from tools.index_gui import main as index_main
        index_main(parent=root, schema='DWH', object_name=name, object_type=obj_type)

    user_index_btn.config(command=launch_index_user)
    dwh_index_btn.config(command=launch_index_dwh)

    # --- Load button handlers ---
    def launch_load_user():
        from loaders.excel_csv_loader import load_files_gui
        load_files_gui(parent=root, schema_choice='user')

    def launch_load_dwh():
        from loaders.excel_csv_loader import load_files_gui
        load_files_gui(parent=root, schema_choice='dwh')

    user_load_btn.config(command=launch_load_user)
    dwh_load_btn.config(command=launch_load_dwh)

    # --- Drop button handlers ---
    def _get_selected_objects(tree):
        """Return list of (name, type, info) tuples from all selected treeview rows."""
        selections = tree.selection()
        if not selections:
            return []
        result = []
        for sel in selections:
            item = tree.item(sel)
            vals = item.get('values', ())
            if len(vals) >= 2:
                name = str(vals[0])
                obj_type = str(vals[1])
                info = str(vals[2]) if len(vals) > 2 else ''
                result.append({'name': name, 'type': obj_type, 'info': info})
        return result

    # Status callback function - uses global status_light
    def _update_status_light(status):
        """Update the status light indicator. Called during drop operations."""
        try:
            global status_light
            if status == 'busy':
                status_light.config(text="🔴")
            else:  # idle
                status_light.config(text="🟢")
            # Force UI update during synchronous operations
            root.update_idletasks()
            root.update()
        except Exception:
            pass

    def launch_drop_user():
        """Handle Drop button click for User schema."""
        objects = _get_selected_objects(user_tree)
        if not objects:
            from tkinter import messagebox
            messagebox.showwarning('No Selection', 'Please select one or more objects to drop.', parent=root)
            return
        
        # Get schema name from session credentials
        from libs import session as _sess
        owner = None
        if _sess.stored_credentials:
            owner = _sess.stored_credentials.get('username', '').upper()
        if not owner:
            try:
                from libs.oracle_db_connector import get_db_connection
                conn = get_db_connection(force_shared=False, root=root)
                if conn:
                    owner = conn.username.upper()
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                pass
        if not owner:
            from tkinter import messagebox
            messagebox.showerror('Error', 'Could not determine user schema.', parent=root)
            return
        
        # Call the drop function with status callback
        from tools.object_cleanup_gui import drop_objects
        drop_objects(
            schema_choice='user',
            schema_name=owner,
            objects=objects,
            parent_window=root,
            on_complete=lambda: refresh_user_objects(),
            on_status_change=_update_status_light
        )

    def launch_drop_dwh():
        """Handle Drop button click for DWH schema."""
        objects = _get_selected_objects(dwh_tree)
        if not objects:
            from tkinter import messagebox
            messagebox.showwarning('No Selection', 'Please select one or more objects to drop.', parent=root)
            return
        
        # Call the drop function with status callback
        from tools.object_cleanup_gui import drop_objects
        drop_objects(
            schema_choice='dwh',
            schema_name='DWH',
            objects=objects,
            parent_window=root,
            on_complete=lambda: refresh_dwh_objects(),
            on_status_change=_update_status_light
        )

    user_drop_btn.config(command=launch_drop_user)
    dwh_drop_btn.config(command=launch_drop_dwh)

    # Top toolbar (centered): tool selector + buttons
    # Create the toolbar at the root level and pack it before the main content_frame
    # so it centers across the entire window (including the left pane).
    top_toolbar = tk.Frame(root)
    # pack before the already-created content_frame so it appears between the verse and content
    top_toolbar.pack(fill="x", pady=(0, 6), before=content_frame)
    toolbar_inner = tk.Frame(top_toolbar)
    toolbar_inner.pack(anchor="center")
    # Give the toolbar some extra top padding so it visually lines up with the log
    toolbar_inner.configure(pady=6)

    # Layout will use grid inside toolbar_inner to ensure deterministic
    # placement: label (col0), combobox (col1), buttons (col2).
    tk.Label(
        toolbar_inner,
        text="Select Tool:",
        font=("Arial", 12, "bold")
    ).grid(row=0, column=0, padx=(0, 10))

    # Tool selector and buttons
    selected_tool = tk.StringVar()

    # Helper to recreate the toolbar combobox under a specified style so
    # theme changes are honored across backends (some ttk widgets only
    # pick up style at creation time).
    def _recreate_tool_menu(use_pane_style=False):
        global tool_menu, selected_tool
        parent = toolbar_inner
        values = list(TOOLS.keys())
        # attempt to preserve current selection index/value
        cur_idx = None
        try:
            cur_idx = tool_menu.current()
        except Exception:
            try:
                val = selected_tool.get()
                cur_idx = values.index(val) if val in values else 0
            except Exception:
                cur_idx = 0

        try:
            try:
                logger.debug("DESTROYING existing tool_menu (if any)")
            except Exception:
                pass
            tool_menu.destroy()
        except Exception:
            pass

        # If ttk.Combobox is unreliable on this platform, use a small
        # custom combobox implementation that uses a Toplevel + Listbox
        # popup. This guarantees consistent popup behavior and styling.
        class _CustomCombobox:
            def __init__(self, master, textvariable, values, width=22, font=None, state='readonly', style=None):
                self.master = master
                self.var = textvariable
                self.values = list(values)
                self._dark = False
                self.frame = tk.Frame(master)
                # Use a normal Entry so background/foreground changes apply
                # reliably across platforms. Prevent typing by blocking key events.
                self.entry = tk.Entry(self.frame, textvariable=self.var, width=width, font=font, state='normal', relief='sunken')
                # Prevent user edits (readonly behavior)
                try:
                    self.entry.bind('<Key>', lambda e: 'break')
                except Exception:
                    pass
                self.entry.pack(side='left')
                # Use a neutral grey arrow button background so the arrow remains
                # visually consistent in both themes. Keep it non-focused.
                self.btn = tk.Button(self.frame, text='\u25BC', width=2, command=self._on_button, takefocus=False, relief='raised', bd=1)
                try:
                    self.btn.config(bg='#c0c0c0', fg='black')
                except Exception:
                    pass
                self.btn.pack(side='left')
                self._popup = None
                self._bindings = {}

            def grid(self, **kw):
                return self.frame.grid(**kw)

            def pack(self, **kw):
                return self.frame.pack(**kw)

            def destroy(self):
                try:
                    if self._popup and getattr(self._popup, 'winfo_exists', lambda: False)():
                        try:
                            self._popup.destroy()
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    self.frame.destroy()
                except Exception:
                    pass

            def bind(self, sequence, func, add=None):
                # Bind to the entry widget; store handler for possible removal
                try:
                    self.entry.bind(sequence, func, add=add if add else None)
                except Exception:
                    try:
                        self.frame.bind(sequence, func, add=add if add else None)
                    except Exception:
                        pass

            def current(self, idx):
                try:
                    if idx is None:
                        return
                    v = self.values[idx]
                    self.var.set(v)
                except Exception:
                    pass

            def get(self):
                return self.var.get()

            def cget(self, key):
                if key == 'style':
                    return None
                try:
                    return self.entry.cget(key)
                except Exception:
                    return None

            def configure(self, **kw):
                try:
                    self.entry.configure(**kw)
                except Exception:
                    pass

            def _on_button(self):
                # show popup
                if self._popup and getattr(self._popup, 'winfo_exists', lambda: False)():
                    try:
                        self._popup.destroy()
                    except Exception:
                        pass
                    return
                try:
                    x = self.frame.winfo_rootx()
                    y = self.frame.winfo_rooty() + self.frame.winfo_height()
                    self._popup = tk.Toplevel(self.frame)
                    self._popup.wm_overrideredirect(True)
                    self._popup.wm_geometry(f"+{x}+{y}")
                    lb = tk.Listbox(self._popup, exportselection=False)
                    # Make the popup list wider than the entry so long names are visible.
                    try:
                        ew = self.entry.cget('width')
                        try:
                            ew = int(ew)
                        except Exception:
                            ew = None
                        if ew:
                            desired = min(max(ew + 6, 30), 120)  # chars, clamp to reasonable range
                            lb.config(width=desired)
                    except Exception:
                        pass
                    # Use same font as entry for consistent sizing
                    try:
                        f = self.entry.cget('font')
                        if f:
                            lb.config(font=f)
                    except Exception:
                        pass
                    for v in self.values:
                        lb.insert('end', v)
                    lb.pack()
                    try:
                        # Apply popup colors consistent with entry colors
                        if getattr(self, '_dark', False):
                            lb.config(bg='#000000', fg='#ffffff', selectbackground='#2a6bd6')
                        else:
                            lb.config(bg='white', fg='black', selectbackground='#2a6bd6')
                    except Exception:
                        pass
                    def on_select(evt=None):
                        try:
                            sel = lb.curselection()
                            if sel:
                                val = lb.get(sel[0])
                                self.var.set(val)
                                # generate virtual event
                                try:
                                    self.frame.event_generate('<<ComboboxSelected>>')
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        try:
                            self._popup.destroy()
                        except Exception:
                            pass
                    lb.bind('<Double-Button-1>', lambda e: on_select())
                    lb.bind('<Return>', lambda e: on_select())
                    # Single click release should also confirm selection
                    lb.bind('<ButtonRelease-1>', lambda e: on_select())
                    lb.bind('<<ListboxSelect>>', lambda e: None)
                    # click outside closes popup
                    def on_focus_out(ev=None):
                        try:
                            if self._popup and getattr(self._popup, 'winfo_exists', lambda: False)():
                                self._popup.destroy()
                        except Exception:
                            pass
                    self._popup.bind('<FocusOut>', on_focus_out)
                    # give focus to popup so clicks register
                    try:
                        self._popup.focus_force()
                        try:
                            lb.focus_set()
                        except Exception:
                            pass
                    except Exception:
                        pass
                except Exception:
                    pass

            # helper to set dark/light colors
            def set_colors(self, dark=False):
                try:
                    self._dark = bool(dark)
                    if self._dark:
                        # Entry background, text and caret color
                        try:
                            self.entry.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff', disabledbackground='#000000')
                        except Exception:
                            pass
                        # Keep arrow button neutral grey so it remains visible on both themes
                        try:
                            self.btn.config(bg='#c0c0c0', fg='black')
                        except Exception:
                            pass
                    else:
                        try:
                            self.entry.config(bg='white', fg='black', insertbackground='black', disabledbackground='white')
                        except Exception:
                            pass
                        try:
                            self.btn.config(bg='#c0c0c0', fg='black')
                        except Exception:
                            pass
                except Exception:
                    pass

        # end _CustomCombobox

        style_name = 'Pane.TCombobox' if use_pane_style else 'TCombobox'
        try:
            # helper: clear visual selection and move focus after use so the
            # toolbar combobox doesn't keep a highlighted selection.
            def _clear_combobox_selection(w):
                try:
                    try:
                        w.selection_clear()
                    except Exception:
                        pass
                    try:
                        w.icursor('end')
                    except Exception:
                        pass
                    try:
                        if 'run_btn' in globals() and run_btn:
                            run_btn.focus_set()
                        else:
                            root.focus_force()
                    except Exception:
                        try:
                            root.focus_force()
                        except Exception:
                            pass
                    # Small state flip can clear lingering native selection highlights
                    try:
                        prev_state = None
                        try:
                            prev_state = w.cget('state')
                        except Exception:
                            prev_state = None
                        try:
                            w.configure(state='disabled')
                            root.update_idletasks()
                        except Exception:
                            pass
                        try:
                            if prev_state is not None:
                                w.configure(state=prev_state)
                        except Exception:
                            pass
                    except Exception:
                        pass
                except Exception:
                    pass

            # Use custom combobox for reliable popup behavior
            try:
                tool_menu = _CustomCombobox(parent, textvariable=selected_tool, values=values, width=22, font=("Arial", 11))
                try:
                    tool_menu.grid(row=0, column=1)
                except Exception:
                    tool_menu.pack(side='left')
                try:
                    logger.debug("CREATED toolbar custom combobox (tool_menu)")
                except Exception:
                    pass
                # bind selection event to clear selection visual
                try:
                    parent_ref = tool_menu.frame
                    parent_ref.bind('<<ComboboxSelected>>', lambda e: _clear_combobox_selection(tool_menu.entry), add='+')
                except Exception:
                    pass
                try:
                    if cur_idx is not None and 0 <= cur_idx < len(values):
                        tool_menu.current(cur_idx)
                    else:
                        tool_menu.current(0)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            # fallback: create without explicit style
            try:
                try:
                    tool_menu = _CustomCombobox(parent, textvariable=selected_tool, values=values, width=22, font=("Arial", 11))
                    try:
                        tool_menu.grid(row=0, column=1)
                    except Exception:
                        tool_menu.pack(side='left')
                    try:
                        if cur_idx is not None:
                            tool_menu.current(cur_idx)
                        else:
                            tool_menu.current(0)
                    except Exception:
                        pass
                except Exception:
                    pass
            except Exception:
                pass

    # Ensure a toolbar combobox exists at startup. Some backends only apply
    # style at widget creation time, and earlier code sometimes recreated
    # the combobox only when toggling themes. Create it here once so the
    # control is present immediately after the toolbar is built.
    try:
        _recreate_tool_menu(use_pane_style=False)
        try:
            logger.info("Initial toolbar combobox created at startup")
        except Exception:
            pass
    except Exception:
        try:
            logger.exception("Initial toolbar combobox creation failed")
        except Exception:
            pass

    btn_frame = tk.Frame(toolbar_inner)
    # Use grid to place the button frame in column 2 so we avoid mixing
    # pack and grid in the same parent (toolbar_inner uses grid for children).
    btn_frame.grid(row=0, column=2, padx=12)

    # Keep references to these controls so handlers can disable/enable them
    run_btn = tk.Button(btn_frame, text="Run", width=10, command=lambda: run_selected())
    run_btn.pack(side="left", padx=7)

    def safe_exit():
        global is_gui_running
        is_gui_running = False
        try:
            root.destroy()
        except Exception:
            pass
        # Best-effort: if a hidden_root exists, destroy it to avoid leaving
        # an orphaned Tk root that could interfere with future WM events.
        try:
            if 'hidden_root' in globals() and getattr(hidden_root, 'winfo_exists', lambda: False)():
                try:
                    hidden_root.destroy()
                except Exception:
                    pass
        except Exception:
            pass
        # ❌ DO NOT rely on hidden_root being present in other modules — prefer
        # explicit lifecycle management. Exit the process now.
        sys.exit()

    tk.Button(btn_frame, text="Exit", width=10, command=safe_exit).pack(side="left", padx=7)

    # Ensure the window manager close button performs the same cleanup
    try:
        root.protocol("WM_DELETE_WINDOW", safe_exit)
    except Exception:
        pass

    # Removed global Ctrl+C abort binding to avoid interfering with clipboard copy.
    # Keyboard shortcuts should not override platform copy behavior.

    # Divider between toolbar and content
    tk.Frame(right_pane, height=1, bg=getattr(root, "_dark_theme", {}).get("border", "#ccc")).pack(fill="x", padx=10, pady=(8, 12))

    # Place the log area in the right pane (narrower because left pane uses space)
    log_text = scrolledtext.ScrolledText(right_pane, width=80, height=25)
    log_text.pack(padx=10, pady=(0, 5), fill="both", expand=True)
    try:
        # Default to light log colors; only change when user enables pane dark mode
        if getattr(root, '_dark_theme', None):
            lt = getattr(root, "_dark_theme", {})
            log_text.config(bg=lt.get("panel", "#0b0b0b"), fg=lt.get("fg", "#e6e6e6"), insertbackground=lt.get("fg", "#e6e6e6"), selectbackground=lt.get("selection_bg", "#2a6bd6"))
        else:
            log_text.config(bg='white', fg='black', insertbackground='black')
    except Exception:
        pass
    
    # === Status Bar (under verse) ===
    tk.Frame(root, height=1, bg=getattr(root, "_dark_theme", {}).get("border", "#ccc")).pack(fill="x", padx=10)
    status_bar = tk.Frame(root)
    status_bar.pack(side="bottom", fill="x", padx=10, pady=(0, 5))

    tk.Label(
        status_bar,
        text=f"Logged in as: {session.stored_credentials['username']} @ {session.stored_credentials['dsn']}",
        font=("Arial", 8),
        anchor="w",
        justify="left"
    ).pack(side="left")

    # Status indicator using a canvas circle for better visibility
    status_canvas = tk.Canvas(status_bar, width=16, height=16, highlightthickness=0)
    status_canvas.pack(side="right", padx=10)
    # Draw a filled circle (oval) - green by default
    status_circle = status_canvas.create_oval(2, 2, 14, 14, fill="#22c55e", outline="#16a34a")
    
    # Create a wrapper label that holds reference to canvas for compatibility with existing code
    class StatusLight:
        def __init__(self, canvas, circle_id):
            self.canvas = canvas
            self.circle_id = circle_id
        def config(self, text=None, **kwargs):
            # Map emoji text to colors
            if text == "🔴":
                self.canvas.itemconfig(self.circle_id, fill="#ef4444", outline="#dc2626")
            elif text == "🟢":
                self.canvas.itemconfig(self.circle_id, fill="#22c55e", outline="#16a34a")
            elif text == "⏳":
                self.canvas.itemconfig(self.circle_id, fill="#f59e0b", outline="#d97706")  # amber/yellow
            elif text == "⏹️ Aborting...":
                self.canvas.itemconfig(self.circle_id, fill="#f59e0b", outline="#d97706")
        def winfo_exists(self):
            try:
                return self.canvas.winfo_exists()
            except:
                return False
    
    status_light = StatusLight(status_canvas, status_circle)

    def on_scroll(*args):
        global auto_scroll_enabled
        if float(log_text.yview()[1]) >= 0.999:
            auto_scroll_enabled = True
        else:
            auto_scroll_enabled = False

    log_text.config(yscrollcommand=lambda *args: [on_scroll(*args), log_text.yview_moveto(args[0])])
    
    # Setup root logger
    # Ensure stdout/stderr use UTF-8 where supported to avoid encode errors
    import sys as _sys
    if hasattr(_sys.stdout, "reconfigure"):
        try:
            _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # Setup root logger
    log_stream = StringIO()
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Defensive filter to sanitize log messages for handlers that may use
    # legacy encodings (prevents UnicodeEncodeError when messages contain emoji)
    class SafeLogFilter(logging.Filter):
        def __init__(self, encoding="utf-8"):
            super().__init__()
            self.encoding = encoding

        def sanitize(self, s: str) -> str:
            try:
                s.encode(self.encoding)
                return s
            except Exception:
                return s.encode(self.encoding, "replace").decode(self.encoding)

        def filter(self, record: logging.LogRecord) -> bool:
            try:
                # Convert the rendered message and place it in record.msg
                record.msg = self.sanitize(str(record.getMessage()))
                record.args = ()
            except Exception:
                pass
            return True

    # GUI handler (writes to in-memory stream)
    stream_handler = logging.StreamHandler(log_stream)
    stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    stream_handler.addFilter(SafeLogFilter())

    # File handler (explicitly use UTF-8)
    log_file = base_path / "HoonyTools.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    file_handler.addFilter(SafeLogFilter())


    # Reset handlers to avoid duplicates
    logger.handlers.clear()
    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
    
    for mod in [
        "abort_manager",
        "oracle_db_connector",
        "table_utils",
        "excel_csv_loader",
        "sql_view_loader",
        "object_cleanup_gui",
    ]:
        logging.getLogger(mod).propagate = True
        logging.getLogger(mod).handlers.clear()
        logging.getLogger(mod).addHandler(stream_handler)
        logging.getLogger(mod).addHandler(file_handler)
        logging.getLogger(mod).setLevel(logging.INFO)    

    stream_logs()
    
    # ✅ Validate after GUI + log area are ready
    if not validate_required_folders():
        root.destroy()
        return
    
    def setup_tray_icon():
        def on_exit(icon, item):
            icon.stop()
            root.quit()

        tray_icon_path = ASSETS_PATH / "assets" / "hoonywise_32x32.png"
        if tray_icon_path.exists():
            tray_img = Image.open(tray_icon_path)
            tray_icon = pystray.Icon("HoonyTools", tray_img, "HoonyTools", menu=(item("Exit", on_exit),))
            tray_icon.run()

    # 🧠 Start it in the background so GUI stays responsive
    threading.Thread(target=setup_tray_icon, daemon=True).start()    
    
    import traceback
    def excepthook(type, value, tb):
        print("💥 Uncaught Exception:")
        traceback.print_exception(type, value, tb)

    sys.excepthook = excepthook    
    
    def show_about_popup():
        from tkinter import messagebox
        messagebox.showinfo(
            "About HoonyTools",
            f"HoonyTools v{APP_VERSION}\n\nCreated by hoonywise\n\nFor enterprise use, contact hoonywise@proton.me"
        )

    # Add menu bar with "View" toggles and "Help > About"
    menu_bar = tk.Menu(root)
    view_menu = tk.Menu(menu_bar, tearoff=0)

    # Pane-only dark toggle: only affects the two object treeviews and the log pane
    try:
        style = ttk.Style()
    except Exception:
        style = None

    # store originals so we can restore
    try:
        pane_orig = getattr(root, '_pane_orig', {})
    except Exception:
        pane_orig = {}

    # Helper: safe tree info (avoid calling widget cget('background') which
    # may raise on some ttk backends). Prefer style.lookup values.
    def _tree_info(tv):
        try:
            sty = None
            try:
                sty = tv.cget('style')
            except Exception:
                sty = None
            st = ttk.Style()
            bg = None
            fg = None
            try:
                if sty:
                    bg = st.lookup(sty, 'fieldbackground') or st.lookup(sty, 'background')
                    fg = st.lookup(sty, 'foreground')
                if not bg:
                    bg = st.lookup('Treeview', 'fieldbackground') or st.lookup('Treeview', 'background')
                if not fg:
                    fg = st.lookup('Treeview', 'foreground')
            except Exception:
                pass
            return f"style={sty} bg={bg} fg={fg}"
        except Exception as e:
            return f"error:{e}"

    def set_panes_dark():
        nonlocal user_tree, dwh_tree
        # Record original theme/style/lookups the first time so we can
        # reliably restore them later. Also capture per-item tags and
        # master background colors.
        try:
            if style:
                try:
                    # Save current theme
                    if not pane_orig.get('orig_theme'):
                        pane_orig['orig_theme'] = style.theme_use()
                except Exception:
                    pass
                # Save lookup values for Treeview and Pane.Treeview
                try:
                    if not pane_orig.get('orig_tree_lookup'):
                        pane_orig['orig_tree_lookup'] = {
                            'background': style.lookup('Treeview', 'background'),
                            'fieldbackground': style.lookup('Treeview', 'fieldbackground'),
                            'foreground': style.lookup('Treeview', 'foreground'),
                        }
                except Exception:
                    pane_orig['orig_tree_lookup'] = {}
                try:
                    if not pane_orig.get('orig_pane_lookup'):
                        pane_orig['orig_pane_lookup'] = {
                            'background': style.lookup('Pane.Treeview', 'background'),
                            'fieldbackground': style.lookup('Pane.Treeview', 'fieldbackground'),
                            'foreground': style.lookup('Pane.Treeview', 'foreground'),
                        }
                except Exception:
                    pane_orig['orig_pane_lookup'] = {}
                try:
                    # Save heading colors too (some backends use a separate heading style)
                    if not pane_orig.get('orig_heading_lookup'):
                        pane_orig['orig_heading_lookup'] = {
                            'background': style.lookup('Treeview.Heading', 'background'),
                            'foreground': style.lookup('Treeview.Heading', 'foreground'),
                        }
                except Exception:
                    pane_orig['orig_heading_lookup'] = {}

        except Exception:
            pass

        # Save per-item tags so we can restore after recreating
        try:
            if not pane_orig.get('user_item_tags'):
                tags = {}
                try:
                    for it in list(user_tree.get_children()):
                        try:
                            tags[it] = tuple(user_tree.item(it).get('tags') or ())
                        except Exception:
                            tags[it] = ()
                except Exception:
                    tags = {}
                pane_orig['user_item_tags'] = tags
        except Exception:
            pass
        try:
            if not pane_orig.get('dwh_item_tags'):
                tags = {}
                try:
                    for it in list(dwh_tree.get_children()):
                        try:
                            tags[it] = tuple(dwh_tree.item(it).get('tags') or ())
                        except Exception:
                            tags[it] = ()
                except Exception:
                    tags = {}
                pane_orig['dwh_item_tags'] = tags
        except Exception:
            pass
        # Save current combobox style so we can restore it later
        try:
            if 'tool_menu' in globals() and not pane_orig.get('tool_menu_style'):
                try:
                    pane_orig['tool_menu_style'] = tool_menu.cget('style')
                except Exception:
                    pane_orig['tool_menu_style'] = None
        except Exception:
            pass

        # Save master backgrounds
        try:
            if not pane_orig.get('user_master_bg'):
                pane_orig['user_master_bg'] = user_tree.master.cget('bg')
        except Exception:
            pass
        try:
            if not pane_orig.get('dwh_master_bg'):
                pane_orig['dwh_master_bg'] = dwh_tree.master.cget('bg')
        except Exception:
            pass

        # Now apply dark style settings and recreate the trees using Pane.Treeview
        try:
            if style:
                try:
                    style.theme_use('clam')
                except Exception:
                    pass
                try:
                    style.configure('Treeview', background='#000000', fieldbackground='#000000', foreground='#ffffff', rowheight=18)
                    style.configure('Pane.Treeview', background='#000000', fieldbackground='#000000', foreground='#ffffff', rowheight=18)
                    style.map('Treeview', background=[('selected', '#2a6bd6')], foreground=[('selected', '#ffffff')])
                    style.map('Pane.Treeview', background=[('selected', '#2a6bd6')], foreground=[('selected', '#ffffff')])
                    # Explicitly configure heading style as well; on Windows the
                    # heading often needs its own configure call to update at runtime.
                    try:
                        style.configure('Treeview.Heading', background='#000000', foreground='#ffffff')
                    except Exception:
                        # Some backends expose the heading as 'Heading' element
                        try:
                            style.configure('Heading', background='#000000', foreground='#ffffff')
                        except Exception:
                            pass
                except Exception:
                    pass
                # Configure a pane-specific Combobox style and apply it to the toolbar combobox
                try:
                    style.configure('Pane.TCombobox', fieldbackground='#000000', background='#000000', foreground='#ffffff')
                    # map readonly state colors explicitly
                    try:
                        # Map common states so the combobox stays dark when focused
                        style.map('Pane.TCombobox', fieldbackground=[('readonly', '#000000'), ('focus', '#000000')], foreground=[('readonly', '#ffffff'), ('focus', '#ffffff')])
                    except Exception:
                        pass
                except Exception:
                    pass
                # Best-effort: set Listbox option defaults so native popups (which
                # sometimes use Listbox widgets) inherit dark colors.
                try:
                    root.option_add('*Listbox.background', '#000000')
                    root.option_add('*Listbox.foreground', '#ffffff')
                    root.option_add('*Listbox.selectBackground', '#2a6bd6')
                    pane_orig['listbox_options_set'] = True
                except Exception:
                    pass
                # Style the top menu bar for pane-only dark mode
                try:
                    root.option_add('*Menu.background', '#000000')
                    root.option_add('*Menu.foreground', '#ffffff')
                    root.option_add('*Menu.activeBackground', '#222222')
                    root.option_add('*Menu.activeForeground', '#ffffff')
                    try:
                        menu_bar.config(background='#000000', foreground='#ffffff', activebackground='#222222', activeforeground='#ffffff')
                        try:
                            view_menu.config(selectcolor='#ffffff')
                        except Exception:
                            pass
                    except Exception:
                        pass
                    # If using the custom in-window menu, style its frame/menubuttons too
                    try:
                        if 'custom_menu_frame' in globals() and getattr(custom_menu_frame, 'winfo_exists', lambda: False)():
                            try:
                                custom_menu_frame.config(bg='#000000')
                            except Exception:
                                pass
                            try:
                                # custom_view/custom_help are tuples: (mb, menu)
                                for t in ('custom_view', 'custom_help'):
                                    try:
                                        mb, m = globals().get(t, (None, None))
                                        if mb:
                                            try:
                                                mb.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')
                                            except Exception:
                                                pass
                                        if m:
                                            try:
                                                m.config(bg='#000000', fg='#ffffff', selectcolor='#ffffff')
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception:
                    pass
                # Recreate the combobox under Pane.TCombobox so backends that
                # only honor style at creation time will show the dark colors.
                try:
                    _recreate_tool_menu(use_pane_style=True)
                    # If our custom combobox is used, ensure it applies dark colors
                    try:
                        if 'tool_menu' in globals() and hasattr(tool_menu, 'set_colors'):
                            try:
                                tool_menu.set_colors(dark=True)
                            except Exception:
                                pass
                    except Exception:
                        pass
                except Exception:
                    try:
                        tool_menu.configure(style='Pane.TCombobox')
                    except Exception:
                        pass
        except Exception:
            pass

        # Recreate trees under the new Pane.Treeview style so backend honors fieldbackground
        try:
            try:
                user_tree = _recreate_tree(user_tree, use_pane_style=True)
            except Exception:
                pass
            try:
                dwh_tree = _recreate_tree(dwh_tree, use_pane_style=True)
            except Exception:
                pass
        except Exception:
            pass

        # Set master backgrounds and darken log
        try:
            try:
                user_tree.master.config(bg='#000000')
            except Exception:
                pass
            try:
                dwh_tree.master.config(bg='#000000')
            except Exception:
                pass
        except Exception:
            pass

        try:
            if 'log_text' in globals():
                if not pane_orig.get('log'):
                    pane_orig['log'] = (log_text.cget('bg'), log_text.cget('fg'), log_text.cget('insertbackground'))
                try:
                    log_text.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff', selectbackground='#2a6bd6')
                except Exception:
                    pass
        except Exception:
            pass

        try:
            root._pane_orig = pane_orig
        except Exception:
            pass

        # Debug write
        try:
            dbg = base_path / 'theme_debug.log'
            with open(dbg, 'a', encoding='utf-8') as df:
                df.write(f"SET DARK: user_tree.style={getattr(user_tree, 'cget', lambda k: None)('style')} bg={getattr(user_tree, 'cget', lambda k: None)('background')} fg={getattr(user_tree, 'cget', lambda k: None)('foreground')}\n")
                try:
                    its = list(user_tree.get_children())
                    df.write(f"SET DARK: user_tree items={len(its)} sample_tags={[user_tree.item(its[0]).get('tags') if its else None]}\n")
                except Exception:
                    pass
                df.write(f"SET DARK: dwh_tree.style={getattr(dwh_tree, 'cget', lambda k: None)('style')} bg={getattr(dwh_tree, 'cget', lambda k: None)('background')} fg={getattr(dwh_tree, 'cget', lambda k: None)('foreground')}\n")
        except Exception:
            pass

        # Log text: remember originals and set dark colors
        try:
            if 'log_text' in globals():
                if not pane_orig.get('log'):
                    pane_orig['log'] = (log_text.cget('bg'), log_text.cget('fg'), log_text.cget('insertbackground'))
                log_text.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff', selectbackground='#2a6bd6')
        except Exception:
            pass

        try:
            root._pane_orig = pane_orig
        except Exception:
            pass

        # Debug: write status to debug log
        try:
            dbg = base_path / 'theme_debug.log'
            with open(dbg, 'a', encoding='utf-8') as df:
                df.write(f"SET DARK: user_tree.style={getattr(user_tree, 'cget', lambda k: None)('style')} bg={getattr(user_tree, 'cget', lambda k: None)('background')} fg={getattr(user_tree, 'cget', lambda k: None)('foreground')}\n")
                try:
                    its = list(user_tree.get_children())
                    df.write(f"SET DARK: user_tree items={len(its)} sample_tags={[user_tree.item(its[0]).get('tags') if its else None]}\n")
                except Exception:
                    pass
                df.write(f"SET DARK: dwh_tree.style={getattr(dwh_tree, 'cget', lambda k: None)('style')} bg={getattr(dwh_tree, 'cget', lambda k: None)('background')} fg={getattr(dwh_tree, 'cget', lambda k: None)('foreground')}\n")
        except Exception:
            pass

    def set_panes_light():
        nonlocal user_tree, dwh_tree
        # First, if we recorded the original theme or style lookups, restore
        # them so newly-created Treeviews are created under the original rules.
        try:
            if style:
                try:
                    po = getattr(root, '_pane_orig', {}) or {}
                except Exception:
                    po = {}
                try:
                    orig_theme = po.get('orig_theme')
                    if orig_theme:
                        try:
                            style.theme_use(orig_theme)
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    # restore Treeview lookups if we captured them
                    ot = po.get('orig_tree_lookup') or {}
                    if ot:
                        try:
                            style.configure('Treeview', background=ot.get('background') or '', fieldbackground=ot.get('fieldbackground') or '', foreground=ot.get('foreground') or '')
                        except Exception:
                            pass
                    op = po.get('orig_pane_lookup') or {}
                    if op:
                        try:
                            style.configure('Pane.Treeview', background=op.get('background') or '', fieldbackground=op.get('fieldbackground') or '', foreground=op.get('foreground') or '')
                        except Exception:
                            pass
                    # Restore combobox style if we saved it
                    try:
                        tms = po.get('tool_menu_style')
                        if tms and 'tool_menu' in globals():
                            try:
                                # Recreate under the saved style to ensure backend honors it
                                _recreate_tool_menu(use_pane_style=(tms == 'Pane.TCombobox'))
                            except Exception:
                                try:
                                    tool_menu.configure(style=tms)
                                except Exception:
                                    pass
                        else:
                            # ensure default (light) combobox style and recreate
                            try:
                                style.configure('TCombobox', fieldbackground='white', background='white', foreground='black')
                                try:
                                    _recreate_tool_menu(use_pane_style=False)
                                    try:
                                        # Move focus away from the combobox to avoid the
                                        # focused color state remaining visible on some backends.
                                        try:
                                            if 'tool_menu' in globals() and hasattr(tool_menu, 'set_colors'):
                                                try:
                                                    tool_menu.set_colors(dark=False)
                                                except Exception:
                                                    pass
                                            if 'run_btn' in globals() and run_btn:
                                                run_btn.focus_set()
                                            else:
                                                root.focus_force()
                                        except Exception:
                                            try:
                                                root.focus_force()
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                except Exception:
                                    try:
                                        tool_menu.configure(style='TCombobox')
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # Restore Listbox option defaults to light values so native
                    # popups created after this will be white on black text
                    try:
                        root.option_add('*Listbox.background', 'white')
                        root.option_add('*Listbox.foreground', 'black')
                        root.option_add('*Listbox.selectBackground', '#2a6bd6')
                    except Exception:
                        pass
                    # Restore menu bar to light appearance
                    try:
                        root.option_add('*Menu.background', '#d0d0d0')
                        root.option_add('*Menu.foreground', 'black')
                        root.option_add('*Menu.activeBackground', '#ffffff')
                        root.option_add('*Menu.activeForeground', 'black')
                        try:
                            menu_bar.config(background='#d0d0d0', foreground='black', activebackground='#ffffff', activeforeground='black')
                        except Exception:
                            pass
                        try:
                            view_menu.config(selectcolor='#000000')
                        except Exception:
                            pass
                    except Exception:
                        pass

                    # Restore custom in-window menu if present
                    try:
                        if 'custom_menu_frame' in globals() and getattr(custom_menu_frame, 'winfo_exists', lambda: False)():
                            try:
                                custom_menu_frame.config(bg=root.cget('bg'))
                            except Exception:
                                pass
                            try:
                                for t in ('custom_view', 'custom_help'):
                                    try:
                                        mb, m = globals().get(t, (None, None))
                                        if mb:
                                            try:
                                                mb.config(bg=root.cget('bg'), fg='black', activebackground='#ececec', activeforeground='black')
                                            except Exception:
                                                pass
                                        if m:
                                            try:
                                                m.config(bg='white', fg='black', selectcolor='#000000')
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # Restore heading lookups if available
                    try:
                        oh = po.get('orig_heading_lookup') or {}
                        if oh:
                            try:
                                style.configure('Treeview.Heading', background=oh.get('background') or '', foreground=oh.get('foreground') or '')
                            except Exception:
                                try:
                                    style.configure('Heading', background=oh.get('background') or '', foreground=oh.get('foreground') or '')
                                except Exception:
                                    pass
                    except Exception:
                        pass
                except Exception:
                    pass

        except Exception:
            pass

        # Recreate the treeviews without the Pane style so they return to
        # the light/default appearance on backends that only apply style
        # at creation time.
        try:
            try:
                user_tree = _recreate_tree(user_tree, use_pane_style=False)
            except Exception:
                pass
            try:
                dwh_tree = _recreate_tree(dwh_tree, use_pane_style=False)
            except Exception:
                pass
        except Exception:
            pass

        # restore master bg and any saved per-widget properties
        try:
            try:
                umbg = getattr(root, '_pane_orig', {}).get('user_master_bg', None)
                if umbg is not None:
                    user_tree.master.config(bg=umbg)
            except Exception:
                pass
            try:
                dmbg = getattr(root, '_pane_orig', {}).get('dwh_master_bg', None)
                if dmbg is not None:
                    dwh_tree.master.config(bg=dmbg)
            except Exception:
                pass
        except Exception:
            pass

        # Ensure every inserted item uses the standard 'row' tag and configure
        # that tag to match the restored Treeview lookups (some backends rely
        # on tag_configure for per-instance coloring).
        try:
            # determine appropriate colors from saved lookups or sensible defaults
            po = getattr(root, '_pane_orig', {}) or {}
            ot = po.get('orig_tree_lookup') or {}
            bg = ot.get('fieldbackground') or ot.get('background') or 'white'
            fg = ot.get('foreground') or 'black'
            try:
                user_tree.tag_configure('row', background=bg, foreground=fg)
            except Exception:
                pass
            try:
                for it in list(user_tree.get_children()):
                    try:
                        user_tree.item(it, tags=('row',))
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                dwh_tree.tag_configure('row', background=bg, foreground=fg)
            except Exception:
                pass
            try:
                for it in list(dwh_tree.get_children()):
                    try:
                        dwh_tree.item(it, tags=('row',))
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

        try:
            po = getattr(root, '_pane_orig', None)
            if po and po.get('log'):
                bg, fg, ins = po.get('log')
                try:
                    # restore to the saved original or fallback to default light colors
                    log_text.config(bg=bg or 'white', fg=fg or 'black', insertbackground=ins or 'black', selectbackground=None)
                except Exception:
                    try:
                        log_text.config(bg='white', fg='black', insertbackground='black', selectbackground=None)
                    except Exception:
                        pass
            else:
                # ensure log resets to white if we have no saved original
                try:
                    log_text.config(bg='white', fg='black', insertbackground='black', selectbackground=None)
                except Exception:
                    pass
        except Exception:
            pass

        # Debug: write status to debug log
        try:
            dbg = base_path / 'theme_debug.log'
            with open(dbg, 'a', encoding='utf-8') as df:
                df.write(f"SET LIGHT: user_tree.style={getattr(user_tree, 'cget', lambda k: None)('style')} bg={getattr(user_tree, 'cget', lambda k: None)('background')} fg={getattr(user_tree, 'cget', lambda k: None)('foreground')}\n")
                try:
                    its = list(user_tree.get_children())
                    df.write(f"SET LIGHT: user_tree items={len(its)} sample_tags={[user_tree.item(its[0]).get('tags') if its else None]}\n")
                except Exception:
                    pass
                df.write(f"SET LIGHT: dwh_tree.style={getattr(dwh_tree, 'cget', lambda k: None)('style')} bg={getattr(dwh_tree, 'cget', lambda k: None)('background')} fg={getattr(dwh_tree, 'cget', lambda k: None)('foreground')}\n")
        except Exception:
            pass

    # Dark mode toggle variable (pane-only). Default off.
    dark_mode_var = tk.BooleanVar(value=False)

    def _save_dark_mode_pref(is_dark):
        """Persist dark mode preference to libs/config.ini [preferences]."""
        try:
            from libs.paths import PROJECT_PATH as _BASE
            _cfg_path = _BASE / "libs" / "config.ini"
            _cfg = ConfigParser()
            try:
                _cfg.read(_cfg_path)
            except Exception:
                _cfg = ConfigParser()
            if not _cfg.has_section("preferences"):
                _cfg.add_section("preferences")
            _cfg.set("preferences", "dark_mode", str(is_dark).lower())
            _cfg_path.parent.mkdir(parents=True, exist_ok=True)
            with open(_cfg_path, "w", encoding="utf-8") as f:
                _cfg.write(f)
        except Exception:
            pass

    def _toggle_dark():
        try:
            if dark_mode_var.get():
                set_panes_dark()
            else:
                set_panes_light()
            # Notify registered callbacks about theme change
            try:
                for cb in getattr(root, '_theme_callbacks', [])[:]:
                    try:
                        cb(dark_mode_var.get())
                    except Exception:
                        pass
            except Exception:
                pass
            # Persist dark mode preference
            _save_dark_mode_pref(dark_mode_var.get())
        except Exception:
            pass

    # Expose a registration API on the root so child dialogs can register
    # callbacks to be notified when the pane-only dark mode changes.
    try:
        root._theme_callbacks = []

        def _register_theme_callback(cb):
            try:
                if callable(cb):
                    root._theme_callbacks.append(cb)
            except Exception:
                pass

        def _unregister_theme_callback(cb):
            try:
                if cb in getattr(root, '_theme_callbacks', []):
                    root._theme_callbacks.remove(cb)
            except Exception:
                pass

        root.register_theme_callback = _register_theme_callback
        root.unregister_theme_callback = _unregister_theme_callback
    except Exception:
        pass

    view_menu.add_checkbutton(label="Dark Mode", variable=dark_mode_var, command=_toggle_dark)
    menu_bar.add_cascade(label="View", menu=view_menu)
    # Debug helper to inspect treeview style/tags at runtime
    def _debug_panes():
        try:
            s = []
            try:
                s.append(f"user_tree {_tree_info(user_tree)}")
                items = list(user_tree.get_children())
                s.append(f"user_tree.items={len(items)}")
                if items:
                    s.append(f"sample_item_tags={user_tree.item(items[0]).get('tags')}")
            except Exception as e:
                s.append(f"user_tree error: {e}")
            try:
                s.append(f"dwh_tree {_tree_info(dwh_tree)}")
                items2 = list(dwh_tree.get_children())
                s.append(f"dwh_tree.items={len(items2)}")
                if items2:
                    s.append(f"sample_item_tags2={dwh_tree.item(items2[0]).get('tags')}")
            except Exception as e:
                s.append(f"dwh_tree error: {e}")
            try:
                style = ttk.Style()
                s.append(f"Pane.Treeview lookup background={style.lookup('Pane.Treeview','background')} fieldbackground={style.lookup('Pane.Treeview','fieldbackground')} foreground={style.lookup('Pane.Treeview','foreground')}")
                s.append(f"Treeview lookup background={style.lookup('Treeview','background')} fieldbackground={style.lookup('Treeview','fieldbackground')} foreground={style.lookup('Treeview','foreground')}")
            except Exception as e:
                s.append(f"style error: {e}")

            dbg = base_path / 'theme_debug.log'
            with open(dbg, 'a', encoding='utf-8') as df:
                df.write('\n'.join(s) + '\n---\n')
            from tkinter import messagebox
            messagebox.showinfo('Theme Debug', '\n'.join(s))
        except Exception as e:
            try:
                from tkinter import messagebox
                messagebox.showerror('Theme Debug Error', str(e))
            except Exception:
                pass

    # Debug Panes is intentionally hidden (keep handler for future use)
    
    # Replace native menu bar with a custom in-window menu bar composed of
    # Menubuttons inside a Frame so it can be reliably styled per-pane.
    # This is safer than relying on platform-drawn native menu bars which
    # frequently ignore Tk color configuration on Windows.
    def _create_custom_menu_bar(parent):
        # Container frame sits at the top of the window (below the verse row)
        f = tk.Frame(parent)

        # Helper to create a Menubutton + Menu pair
        def _show_menu(btn, menu):
            try:
                x = btn.winfo_rootx()
                y = btn.winfo_rooty() + btn.winfo_height()
                # For Tk >= 8.6 use tk_popup
                try:
                    menu.tk_popup(x, y)
                except Exception:
                    menu.post(x, y)
            except Exception:
                pass

        def _mb(label_text, menu_items):
            # Use a Button instead of Menubutton for more reliable styling
            mb = tk.Button(f, text=label_text, relief='flat', padx=6, pady=2)
            m = tk.Menu(f, tearoff=0)
            for item in menu_items:
                # item is a tuple: (type, label, command)
                itype, ilabel, icmd = item
                if itype == 'command':
                    m.add_command(label=ilabel, command=icmd)
                elif itype == 'check':
                    # icmd can be callable or tuple (command, variable)
                    var = None
                    cmd = icmd
                    if isinstance(icmd, tuple) and len(icmd) > 1:
                        cmd, var = icmd[0], icmd[1]
                    m.add_checkbutton(label=ilabel, command=(cmd if callable(cmd) else None), variable=var)
                elif itype == 'cascade':
                    m.add_cascade(label=ilabel, menu=icmd)
            # show popup on click
            mb.config(command=lambda b=mb, mm=m: _show_menu(b, mm))
            mb.pack(side='left', padx=(6, 2))
            return mb, m

        # Build View and Help menus using existing menu definitions
        # View: copy items from view_menu
        view_items = [
            ('check', 'Dark Mode', (_toggle_dark, dark_mode_var))
        ]
        # Help: use existing functions
        help_items = [
            ('command', 'About', show_about_popup),
            ('command', 'Check for Updates', lambda: webbrowser.open("https://github.com/hoonywise/HoonyTools/releases"))
        ]

        # Create menubuttons
        mb_view, m_view = _mb('View', view_items)
        mb_help, m_help = _mb('Help', help_items)

        return f, (mb_view, m_view), (mb_help, m_help)

    # Create the custom in-window menu bar and hide the native one
    try:
        # Create custom bar and then unset native menubar so it doesn't show
        custom_menu_frame, custom_view, custom_help = _create_custom_menu_bar(root)
        # Expose references globally so nested theme functions can style them
        try:
            globals()['custom_menu_frame'] = custom_menu_frame
            globals()['custom_view'] = custom_view
            globals()['custom_help'] = custom_help
        except Exception:
            pass
        # Pack the custom menu before the verse row so it appears at the top
        try:
            custom_menu_frame.pack(fill='x', side='top', before=verse_frame)
        except Exception:
            try:
                custom_menu_frame.pack(fill='x', side='top')
            except Exception:
                pass
        try:
            root.config(menu=None)
        except Exception:
            pass
    except Exception:
        # Fallback: keep the native menu if anything fails
        try:
            root.config(menu=menu_bar)
        except Exception:
            pass

    # Best-effort: style the combobox popup Listbox used by some backends
    def _style_combobox_popup(tv, dark):
        """Try to find the popup Listbox/Toplevel for a ttk.Combobox and
        configure its background/foreground. This is backend-dependent and
        best-effort — it attempts common window naming/conventions.
        """
        try:
            # The popup is often a Toplevel child of the root with a widget
            # name like 'tk_popup' or a Listbox child. We search recently
            # created toplevels and look for Listbox children.
            for w in root.winfo_children():
                try:
                    # Skip regular frames
                    if isinstance(w, tk.Toplevel):
                        for ch in w.winfo_children():
                            try:
                                # If there's a Listbox inside, style it
                                if isinstance(ch, tk.Listbox):
                                    if dark:
                                        ch.config(bg='#000000', fg='#ffffff', selectbackground='#444444')
                                    else:
                                        ch.config(bg='white', fg='black', selectbackground='#2a6bd6')
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

    # We replaced the native menu with a custom in-window menu. Keep the
    # menu_bar structure around for compatibility but do not reattach it as
    # the root menubar (native menubars ignore styling on some platforms).
    tk.Frame(root, height=1, bg=getattr(root, "_dark_theme", {}).get("border", "#b0b0b0")).pack(fill="x")

    # Restore dark mode preference from config.ini on startup
    try:
        from libs.paths import PROJECT_PATH as _BASE
        _cfg_path = _BASE / "libs" / "config.ini"
        _cfg = ConfigParser()
        _cfg.read(_cfg_path)
        if _cfg.getboolean("preferences", "dark_mode", fallback=False):
            dark_mode_var.set(True)
            _toggle_dark()
    except Exception:
        pass

    root.mainloop()

TOOLS = {
    "☑ SQL View Loader": run_sql_view_loader,
    "☑ SQL Materialized View Loader": run_sql_mv_loader,
    "☑ Materialized View Manager": None,  # placeholder, will be wired if available
    "☑ Designate PK": pk_designate_main,
    
    # Object Dropper removed - functionality now integrated into Drop buttons in left pane
}

# Wire the MV refresh tool if present (keep the tool list construction separate
# from runtime imports to avoid syntax issues inside the dict literal)
try:
    from tools.mv_refresh_gui import run_mv_refresh_gui
    TOOLS["☑ Materialized View Manager"] = run_mv_refresh_gui
except Exception:
    # leave the placeholder if import fails
    pass

if __name__ == "__main__":
    try:
        show_splash()
        launch_tool_gui()
    except KeyboardInterrupt:
        # Allow graceful exit when user force-quits (Ctrl+C or similar)
        try:
            sys.exit(0)
        except Exception:
            pass
