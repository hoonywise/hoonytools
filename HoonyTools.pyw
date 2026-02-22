import tkinter as tk
from tkinter import scrolledtext, ttk

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
from libs import gui_utils

APP_VERSION = "2.2.0"


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

    # Configure ttk styles for dark theme
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
# SQL View Loader, SQL MV Loader, and PK Designate are imported lazily by pane button handlers
# drop_user_tables moved to integrated Drop buttons - import drop_objects on-demand in handlers
from libs.bible_books import book_lookup

should_abort = False
auto_scroll_enabled = True
is_gui_running = True
# Guard to prevent scheduling multiple schema2 login prompts concurrently
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
    return random.choice(BIBLE_VERSES) if BIBLE_VERSES else "ðŸ“– Verse not available"

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
    logger.warning("â›” Abort requested by user.")
    # Best-effort UI updates and attempt to interrupt blocking DB calls.
    try:
        # Update status light if present
        if 'status_light' in globals() and getattr(status_light, 'winfo_exists', lambda: False)():
            try:
                status_light.config(text="â¹ï¸ Aborting...")
            except Exception:
                pass

        # Attempt to close any registered connections on this root to help
        # unblock DB calls. Close them in a background thread so the main GUI
        # does not freeze if the close operation blocks or is slow.
        try:
            from libs import session as _sess
            import threading as _thr
            def _close_connections():
                try:
                    if 'root' in globals():
                        _sess.close_connections(root)
                except Exception:
                    logger.debug('Failed to close connections in background', exc_info=True)
            _thr.Thread(target=_close_connections, daemon=True).start()
        except Exception:
            pass

        # Attempt to close any active login/prompt windows that were parented
        # to the launcher root (for example schema2 login Toplevel). Destroying
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
                        status_light.config(text="ðŸŸ¢")
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
    # Load saved theme before showing splash
    from libs import gui_utils
    from configparser import ConfigParser
    from pathlib import Path
    gui_utils.load_theme_from_config()
    
    # Get splash-specific theme colors
    splash_bg = gui_utils.get_color('splash_bg')
    splash_fg = gui_utils.get_color('splash_fg')
    splash_muted_fg = gui_utils.get_color('splash_muted_fg')
    
    # Load splash opacity from config (default 1.0)
    target_opacity = 1.0
    try:
        config_path = base_path / "libs" / "config.ini"
        cfg = ConfigParser()
        cfg.read(config_path)
        target_opacity = cfg.getfloat('Appearance', 'splash_opacity')
        # Clamp to valid range
        target_opacity = max(0.0, min(1.0, target_opacity))
    except Exception:
        target_opacity = 1.0
    
    splash = tk.Tk()
    splash.overrideredirect(True)
    splash.config(bg=splash_bg)
    center_window(splash, 420, 260)
    splash.attributes('-alpha', 0.0)

    # === HoonyTools Logo + Title ===
    try:
        hoony_logo_path = ASSETS_PATH / "assets" / "hoonywise_300.png"
        hoony_img = Image.open(hoony_logo_path).resize((36, 36))
        hoony_logo = ImageTk.PhotoImage(hoony_img)

        logo_title_frame = tk.Frame(splash, bg=splash_bg)
        logo_title_frame.pack(pady=(40, 10))

        tk.Label(logo_title_frame, image=hoony_logo, bg=splash_bg).pack(side="left", padx=(0, 10))
        tk.Label(logo_title_frame, text="HoonyTools Launcher", font=("Arial", 16, "bold"),
                 bg=splash_bg, fg=splash_fg).pack(side="left")

        splash.hoony_logo = hoony_logo  # Prevent garbage collection
    except Exception:
        tk.Label(splash, text="HoonyTools Launcher", font=("Arial", 18, "bold"),
                 bg=splash_bg, fg=splash_fg).pack(pady=(40, 10))

    # === Created by hoonywise ===
    footer_top = tk.Label(
        splash,
        text="Created by hoonywise · hoonywise@proton.me",
        font=("Arial", 9, "italic"),
        bg=splash_bg,
        fg=splash_muted_fg
    )
    footer_top.pack(side="bottom", pady=(0, 2))

    footer_version = tk.Label(
        splash,
        text=f"v{APP_VERSION}",
        font=("Arial", 9, "bold"),
        bg=splash_bg,
        fg=splash_muted_fg
    )
    footer_version.pack(side="bottom", pady=(0, 12))

    def fade_in(alpha=0.0):
        if alpha < target_opacity:
            splash.attributes('-alpha', alpha)
            splash.after(30, lambda: fade_in(min(alpha + 0.05, target_opacity)))
        else:
            # Ensure we reach exactly target_opacity
            splash.attributes('-alpha', target_opacity)
            splash.after(3000, fade_out)  # hold full splash (logo + labels) for 3s

    def fade_out(alpha=None):
        if alpha is None:
            alpha = target_opacity
        if alpha > 0.0:
            splash.attributes('-alpha', alpha)
            splash.after(14, lambda: fade_out(alpha - 0.07))
        else:
            splash.destroy()
            
    fade_in()
    splash.mainloop()

def launch_tool_gui():
    from libs import session
    
    global root, log_text, log_stream, status_light

    # Create the main Tk root
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
            print(f"âš ï¸ Failed to set taskbar icon: {e}")

    # Load any saved credentials from config.ini (no mandatory login)
    # Users will be prompted on-demand when they use tools or refresh
    try:
        session.load_saved_credentials()
    except Exception:
        pass
    
    # Show the main window
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

    # === Word of God - Bible Verse Row ===
    verse_outer_frame = tk.Frame(root)
    verse_outer_frame.pack(fill="x", padx=8, pady=(12, 12))
    # Store reference for menu bar pack ordering
    globals()['verse_outer_frame'] = verse_outer_frame

    verse_labelframe = tk.LabelFrame(verse_outer_frame, text="Word of God", padx=7, pady=7)
    # Match horizontal alignment: align with left edge of object list pane and right edge of log pane
    # content_frame padx=10, left_pane padx=(6,10) -> left edge at 16px from window
    # We need padx=(6, 0) but verse_outer already has padx=10, so total left = 16px
    # Right side: log_text has padx=10 inside right_pane, so we need no extra right padding
    verse_labelframe.pack(fill="x", padx=(21.5, 12))

    # Top bar with Previous/Next buttons (like object pane)
    verse_btn_bar = tk.Frame(verse_labelframe)
    verse_btn_bar.pack(fill="x", anchor="n", padx=8, pady=(0, 8))
    
    verse_prev_btn = tk.Button(verse_btn_bar, text="Previous", width=10)
    verse_prev_btn.pack(side="left", padx=(0, 8))
    verse_next_btn = tk.Button(verse_btn_bar, text="Next", width=10)
    verse_next_btn.pack(side="left", padx=(0, 8))

    # Verse history for Previous/Next navigation
    verse_history = []  # List of shown verses
    verse_history_index = [-1]  # Current position in history (use list for mutability in closures)

    def _display_verse(verse_text_content):
        """Display a verse in the text widget."""
        try:
            verse_text.config(state="normal")
            verse_text.delete("1.0", tk.END)
            verse_text.insert("1.0", verse_text_content)
            verse_text.config(state="disabled")
        except Exception:
            pass

    def _show_next_verse():
        """Show next verse - either from history or get a new random one."""
        if verse_history_index[0] < len(verse_history) - 1:
            # Move forward in history
            verse_history_index[0] += 1
            _display_verse(verse_history[verse_history_index[0]])
        else:
            # Get a new random verse and add to history
            new_verse = get_random_verse()
            verse_history.append(new_verse)
            verse_history_index[0] = len(verse_history) - 1
            _display_verse(new_verse)

    def _show_prev_verse():
        """Show previous verse from history."""
        if verse_history_index[0] > 0:
            verse_history_index[0] -= 1
            _display_verse(verse_history[verse_history_index[0]])

    verse_prev_btn.config(command=_show_prev_verse)
    verse_next_btn.config(command=_show_next_verse)

    # Create a frame to hold the Text widget and scrollbar
    # Set minimum height to accommodate scrollbar (about 50px)
    verse_inner = tk.Frame(verse_labelframe, bg="white", height=50)
    verse_inner.pack(fill="x", expand=True)
    verse_inner.pack_propagate(False)  # Prevent shrinking below minimum height

    # Scrollbar (initially hidden, shown on hover)
    verse_scrollbar = tk.Scrollbar(verse_inner, orient="vertical")

    # Fixed-height Text widget - black text for readability
    # White background like the treeview areas in object list panes
    verse_text = tk.Text(
        verse_inner,
        font=("Arial", 9, "italic"),
        fg="black",
        bg="white",
        height=3,
        wrap="word",
        relief="flat",
        state="disabled",
        cursor="arrow",
        highlightthickness=0,
        borderwidth=0,
        yscrollcommand=verse_scrollbar.set
    )
    verse_text.pack(side="left", fill="both", expand=True)
    verse_scrollbar.config(command=verse_text.yview)

    # Show/hide scrollbar on hover
    def _show_verse_scrollbar(e=None):
        try:
            verse_scrollbar.pack(side="right", fill="y")
        except Exception:
            pass

    def _hide_verse_scrollbar(e=None):
        try:
            verse_scrollbar.pack_forget()
        except Exception:
            pass

    verse_inner.bind('<Enter>', _show_verse_scrollbar)
    verse_inner.bind('<Leave>', _hide_verse_scrollbar)
    verse_text.bind('<Enter>', _show_verse_scrollbar)
    verse_text.bind('<Leave>', _hide_verse_scrollbar)

    # Register widgets for theme styling
    globals()['verse_labelframe'] = verse_labelframe
    globals()['verse_text'] = verse_text
    globals()['verse_scrollbar'] = verse_scrollbar
    globals()['verse_inner'] = verse_inner
    globals()['verse_btn_bar'] = verse_btn_bar

    # Auto-rotate verse every ~78 seconds (adds to history like clicking Next)
    def rotate_verse():
        _show_next_verse()
        root.after(77777, rotate_verse)

    # Show first verse immediately and start auto-rotation timer
    _show_next_verse()
    root.after(77777, rotate_verse)

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

    # Register content frames for theme styling
    globals()['content_frame'] = content_frame
    globals()['left_pane'] = left_pane
    globals()['right_pane'] = right_pane

    # âœ… Set GUI icon (.ico for taskbar)
    icon_ico_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
    root.iconbitmap(default=icon_ico_path)

    # âœ… Set window icon (.png for title bar)
    icon_path = ASSETS_PATH / "assets" / "hoonywise_300.png"
    icon_img = tk.PhotoImage(file=icon_path)
    root.iconphoto(False, icon_img)
    root.icon_img = icon_img  # Prevents garbage collection

    # === Load Logo Assets ===
    assets_path = base_path / "assets"
    # Initialize Oracle client early (credentials loaded via session.load_saved_credentials())
    try:
        import oracledb as _orac
        try:
            _orac.init_oracle_client()
            logger.info("Oracle client initialized (Thick mode if available)")
        except Exception:
            logger.info("Oracle client init skipped or unavailable; proceeding with Thin mode")
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
                    arrow = ' \u25bc' if reverse else ' \u25b2'  # â–¼ or â–²
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
    def _make_objects_frame(parent, schema_key):
        """Create an object pane frame for a schema.
        
        Args:
            parent: Parent widget
            schema_key: 'schema1' or 'schema2' for session integration
        
        Returns:
            Tuple of (frame, treeview, buttons..., schema_label_widget)
        """
        from libs import session as _sess
        
        frame = tk.LabelFrame(parent, padx=6, pady=6)
        # allow frames to share available vertical space equally
        frame.pack(fill="both", pady=(0, 8), expand=True)
        
        # Create custom label with bold schema name (count shown separately at right edge)
        label_frame = tk.Frame(frame)
        schema_label = tk.Label(label_frame, text=_sess.get_label(schema_key), font=("Arial", 9, "bold"))
        schema_label.pack(side="left")
        frame.configure(labelwidget=label_frame)
        
        # Register the label widget with session for dynamic updates
        _sess.register_label_widget(schema_key, schema_label)

        # Top bar: Refresh, Load, Drop buttons
        top_bar = tk.Frame(frame)
        top_bar.pack(fill="x", anchor="n", padx=8, pady=(0, 8))
        refresh_btn = tk.Button(top_bar, text="Refresh", width=10)
        refresh_btn.pack(side="left", padx=(0, 8))
        load_btn = tk.Button(top_bar, text="Load", width=10)
        load_btn.pack(side="left", padx=(0, 8))
        drop_btn = tk.Button(top_bar, text="Drop", width=10)
        drop_btn.pack(side="left", padx=(0, 8))
        status_lbl = tk.Label(top_bar, text="", font=("Arial", 8), fg=getattr(parent.master, "_dark_theme", {}).get("muted", "#444444"))
        status_lbl.pack(side="left")

        # Second button row: View, M.View, P.Key, Index
        btn_row2 = tk.Frame(frame)
        btn_row2.pack(fill="x", anchor="n", padx=8, pady=(0, 8))
        view_btn = tk.Button(btn_row2, text="View", width=10)
        view_btn.pack(side="left", padx=(0, 8))
        mv_btn = tk.Button(btn_row2, text="M.View", width=10)
        mv_btn.pack(side="left", padx=(0, 8))
        pk_btn = tk.Button(btn_row2, text="P.Key", width=10)
        pk_btn.pack(side="left", padx=(0, 8))
        index_btn = tk.Button(btn_row2, text="Index", width=10)
        index_btn.pack(side="left", padx=(0, 8))

        # Content area (treeview + scrollbar)
        content_area = tk.Frame(frame)
        content_area.pack(fill="both", expand=True)

        # Treeview with name, type, info columns
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

        return frame, tv, refresh_btn, load_btn, drop_btn, status_lbl, view_btn, mv_btn, pk_btn, index_btn

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
    # schema1 = primary schema, schema2 = secondary schema
    schema1_frame, schema1_tree, schema1_refresh_btn, schema1_load_btn, schema1_drop_btn, schema1_status, schema1_view_btn, schema1_mv_btn, schema1_pk_btn, schema1_index_btn = _make_objects_frame(left_pane, 'schema1')
    schema2_frame, schema2_tree, schema2_refresh_btn, schema2_load_btn, schema2_drop_btn, schema2_status, schema2_view_btn, schema2_mv_btn, schema2_pk_btn, schema2_index_btn = _make_objects_frame(left_pane, 'schema2')
    
    # Enable sortable column headers for both treeviews
    _make_sortable_tree(schema1_tree)
    _make_sortable_tree(schema2_tree)
    
    # Enable Ctrl+A to select all for both treeviews
    _bind_select_all(schema1_tree)
    _bind_select_all(schema2_tree)

    # Keep cached row data so we can recreate trees when toggling theme
    schema1_rows = []
    schema2_rows = []

    # Prevent the left pane from auto-resizing when internal labels change
    left_pane.pack_propagate(False)

    # Create external count labels aligned to the right of each object frame
    # Match font size with schema label (Arial 9) but not bold, use muted color
    schema1_count_label = tk.Label(left_pane, text="", font=("Arial", 9), fg=getattr(left_pane, "_dark_theme", {}).get("muted", "#444444"))
    schema2_count_label = tk.Label(left_pane, text="", font=("Arial", 9), fg=getattr(left_pane, "_dark_theme", {}).get("muted", "#444444"))
    # start with a placeholder placement; we'll position these next to the LabelFrame titles
    schema1_count_label.place(x=0, y=0)
    schema2_count_label.place(x=0, y=0)

    # Register schema frames and count labels for theme styling
    globals()['schema1_frame'] = schema1_frame
    globals()['schema2_frame'] = schema2_frame
    globals()['schema1_count_label'] = schema1_count_label
    globals()['schema2_count_label'] = schema2_count_label

    # hide the internal status labels created inside each frame to avoid them resizing the frame
    try:
        schema1_status.pack_forget()
    except Exception:
        pass
    try:
        schema2_status.pack_forget()
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
    schema1_frame.pack_forget()
    schema2_frame.pack_forget()
    # add left padding so the object frames sit a few pixels in from the left border
    schema1_frame.grid(row=0, column=0, sticky="nsew", pady=(0,8), padx=(14,0))
    schema2_frame.grid(row=1, column=0, sticky="nsew", padx=(14,0))

    # Position the object-count labels at the right edge of each LabelFrame title area
    def position_count_labels(event=None):
        try:
            left_pane.update_idletasks()
            
            # Use frame width and position, with adequate right padding
            right_padding = 59  # Padding from right edge of frame

            # Schema1 frame - position count label at right side of title border
            uy = schema1_frame.winfo_y()
            frame_x = schema1_frame.winfo_x()
            frame_w = schema1_frame.winfo_width()
            label_w = schema1_count_label.winfo_reqwidth()
            schema1_count_label.place(x=frame_x + frame_w - label_w - right_padding, y=uy - 0)

            # Schema2 frame - position count label at right side of title border
            dy = schema2_frame.winfo_y()
            frame2_x = schema2_frame.winfo_x()
            frame2_w = schema2_frame.winfo_width()
            label2_w = schema2_count_label.winfo_reqwidth()
            schema2_count_label.place(x=frame2_x + frame2_w - label2_w - right_padding, y=dy - 0)
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
            if tv is schema1_tree:
                nonlocal schema1_rows
                schema1_rows = list(rows)
            elif tv is schema2_tree:
                nonlocal schema2_rows
                schema2_rows = list(rows)
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
            rows = schema1_rows if old_tv is schema1_tree else schema2_rows if old_tv is schema2_tree else []
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
    def refresh_schema1_objects():
        schema1_status.config(text="Loading...")
        def worker():
            from libs.oracle_db_connector import get_db_connection
            conn = get_db_connection(schema='schema1', root=root)
            if not conn:
                root.after(0, lambda: schema1_status.config(text="No connection"))
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
                if is_gui_running:
                    try:
                        root.after(0, lambda: (_populate_treeview(schema1_tree, rows), schema1_count_label.config(text="No Objects")))
                    except Exception:
                        pass
            else:
                if is_gui_running:
                    try:
                        root.after(0, lambda: (_populate_treeview(schema1_tree, rows), schema1_count_label.config(text=f"{len(rows)} Objects")))
                    except Exception:
                        pass
        threading.Thread(target=worker, daemon=True).start()

    def refresh_schema2_objects():
        schema2_status.config(text="Loading...")

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
                    conn = oracledb.connect(user=creds["user"], password=creds["password"], dsn=creds["dsn"])
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
                    err_text = str(e)
                    # Treat certain errors as expected environment/tns issues and avoid noisy stacktraces.
                    if ("DPY-4026" in err_text) or ("tnsnames" in err_text.lower()) or isinstance(e, FileNotFoundError):
                        # Informational: tnsnames/tns error detected; prompt the user to repair schema2 login.
                        logger.info(f"schema2 connect encountered tns/tnsnames issue; will prompt user: {err_text}")
                        # Update status label and schedule a single main-thread prompt to repair schema2 creds/config if not already prompting
                        try:
                            try:
                                root.after(0, lambda: schema2_status.config(text="Prompting for login..."))
                            except Exception:
                                pass
                            from libs import session as _session
                            global dwh_prompting
                            if not dwh_prompting:
                                dwh_prompting = True
                                def prompt_and_retry():
                                    try:
                                        from libs.oracle_db_connector import get_db_connection
                                        from libs import session as _s
                                        conn2 = get_db_connection(schema='schema2', root=root)
                                        if conn2:
                                            try:
                                                conn2.close()
                                            except Exception:
                                                pass
                                            new_creds = _s.get_credentials('schema2')
                                            if new_creds:
                                                # retry using new creds
                                                _start_worker_with_creds(new_creds)
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
                            logger.warning("Failed to schedule schema2 login prompt after tns error.")
                    else:
                        # Unexpected errors: log stacktrace so we can diagnose
                        logger.exception(f"Failed to list schema2 objects: {e}")
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
                    if is_gui_running:
                        try:
                            root.after(0, lambda: (_populate_treeview(schema2_tree, rows), schema2_count_label.config(text="No Objects"), schema2_status.config(text="")))
                        except Exception:
                            pass
                else:
                    if is_gui_running:
                        try:
                            root.after(0, lambda: (_populate_treeview(schema2_tree, rows), schema2_count_label.config(text=f"{len(rows)} Objects"), schema2_status.config(text="")))
                        except Exception:
                            pass

            threading.Thread(target=worker, daemon=True).start()

        # Decide whether we can use saved creds (no UI) or need to prompt on the main thread
        from libs import session

        creds = session.get_credentials('schema2')

        if creds:
            # Use the saved credentials in a background thread
            _start_worker_with_creds(creds)
            return

        # No saved creds: prompt on the main thread (get_db_connection will handle prompting)
        from libs.oracle_db_connector import get_db_connection
        conn = get_db_connection(schema='schema2', root=root)
        if not conn:
            if is_gui_running:
                try:
                    root.after(0, lambda: schema2_status.config(text="Not logged in"))
                except Exception:
                    pass
            return

        # If get_db_connection returned a connection, close it and use the stored session credentials
        try:
            conn.close()
        except Exception:
            pass

        # Credentials should have been set by get_db_connection when prompting
        creds = session.get_credentials('schema2')
        if not creds:
            root.after(0, lambda: schema2_status.config(text="No credentials"))
            return

        _start_worker_with_creds(creds)

    # Wire buttons
    schema1_refresh_btn.config(command=refresh_schema1_objects)
    schema2_refresh_btn.config(command=refresh_schema2_objects)

    # Expose refresh callbacks on root for Settings to call after saving credentials
    root._refresh_schema1 = refresh_schema1_objects
    root._refresh_schema2 = refresh_schema2_objects

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

    def launch_index_schema1():
        name, obj_type = _get_selected_object(schema1_tree)
        if not name:
            from tkinter import messagebox
            messagebox.showwarning('No Selection', 'Please select an object in the Schema 1 Objects pane first.', parent=root)
            return
        if obj_type and obj_type.upper() == 'VIEW':
            from tkinter import messagebox
            messagebox.showwarning('Not Supported', 'Indexes cannot be created on views. Please select a table or materialized view.', parent=root)
            return
        # Determine user schema from session credentials
        from libs import session as _sess
        owner = None
        creds = _sess.get_credentials('schema1')
        if creds:
            owner = creds.get('user', '').upper()
        if not owner:
            try:
                from libs.oracle_db_connector import get_db_connection
                conn = get_db_connection(schema='schema1', root=root)
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
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            # Only refresh if user successfully logged in (has credentials)
            if session.get_credentials('schema1'):
                refresh_schema1_objects()
        index_main(parent=root, schema_key='schema1', object_name=name, object_type=obj_type, on_finish=on_close)

    def launch_index_schema2():
        name, obj_type = _get_selected_object(schema2_tree)
        if not name:
            from tkinter import messagebox
            messagebox.showwarning('No Selection', 'Please select an object in the Schema 2 Objects pane first.', parent=root)
            return
        if obj_type and obj_type.upper() == 'VIEW':
            from tkinter import messagebox
            messagebox.showwarning('Not Supported', 'Indexes cannot be created on views. Please select a table or materialized view.', parent=root)
            return
        from tools.index_gui import main as index_main
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            # Only refresh if user successfully logged in (has credentials)
            if session.get_credentials('schema2'):
                refresh_schema2_objects()
        index_main(parent=root, schema_key='schema2', object_name=name, object_type=obj_type, on_finish=on_close)

    schema1_index_btn.config(command=launch_index_schema1)
    schema2_index_btn.config(command=launch_index_schema2)

    # --- Load button handlers ---
    def launch_load_schema1():
        from loaders.excel_csv_loader import load_files_gui
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            if session.get_credentials('schema1'):
                refresh_schema1_objects()
        load_files_gui(parent=root, schema_choice='user', on_status_change=_update_status_light, on_finish=on_close)

    def launch_load_schema2():
        from loaders.excel_csv_loader import load_files_gui
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            if session.get_credentials('schema2'):
                refresh_schema2_objects()
        load_files_gui(parent=root, schema_choice='dwh', on_status_change=_update_status_light, on_finish=on_close)

    schema1_load_btn.config(command=launch_load_schema1)
    schema2_load_btn.config(command=launch_load_schema2)

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
        """Update the status light indicator. Called during drop/load operations."""
        try:
            global status_light
            if status == 'busy':
                status_light.config(text="ðŸ”´")
            elif status == 'aborting':
                status_light.config(text="â³")  # amber/yellow
            else:  # idle
                status_light.config(text="ðŸŸ¢")
            # Force UI update during synchronous operations
            root.update_idletasks()
            root.update()
        except Exception:
            pass

    def launch_drop_schema1():
        """Handle Drop button click for User schema."""
        objects = _get_selected_objects(schema1_tree)
        if not objects:
            from tkinter import messagebox
            messagebox.showwarning('No Selection', 'Please select one or more objects to drop.', parent=root)
            return
        
        # Get schema name from session credentials
        from libs import session as _sess
        owner = None
        creds = _sess.get_credentials('schema1')
        if creds:
            owner = creds.get('user', '').upper()
        if not owner:
            try:
                from libs.oracle_db_connector import get_db_connection
                conn = get_db_connection(schema='schema1', root=root)
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
            on_complete=lambda: refresh_schema1_objects(),
            on_status_change=_update_status_light
        )

    def launch_drop_schema2():
        """Handle Drop button click for schema2."""
        objects = _get_selected_objects(schema2_tree)
        if not objects:
            from tkinter import messagebox
            messagebox.showwarning('No Selection', 'Please select one or more objects to drop.', parent=root)
            return
        
        # Get schema name from session credentials
        from libs import session as _sess
        owner = None
        creds = _sess.get_credentials('schema2')
        if creds:
            owner = creds.get('user', '').upper()
        if not owner:
            try:
                from libs.oracle_db_connector import get_db_connection
                conn = get_db_connection(schema='schema2', root=root)
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
            messagebox.showerror('Error', 'Could not determine schema2 owner.', parent=root)
            return
        
        # Call the drop function with status callback
        from tools.object_cleanup_gui import drop_objects
        drop_objects(
            schema_choice='dwh',
            schema_name=owner,
            objects=objects,
            parent_window=root,
            on_complete=lambda: refresh_schema2_objects(),
            on_status_change=_update_status_light
        )

    schema1_drop_btn.config(command=launch_drop_schema1)
    schema2_drop_btn.config(command=launch_drop_schema2)

    # --- View button handlers ---
    def launch_view_schema1():
        from loaders.sql_view_loader import run_sql_view_loader
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            # Only refresh if user successfully logged in (has credentials)
            if session.get_credentials('schema1'):
                refresh_schema1_objects()
        run_sql_view_loader(parent=root, on_finish=on_close, use_dwh=False)

    def launch_view_schema2():
        from loaders.sql_view_loader import run_sql_view_loader
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            # Only refresh if user successfully logged in (has credentials)
            if session.get_credentials('schema2'):
                refresh_schema2_objects()
        run_sql_view_loader(parent=root, on_finish=on_close, use_dwh=True)

    schema1_view_btn.config(command=launch_view_schema1)
    schema2_view_btn.config(command=launch_view_schema2)

    # --- MV button handlers ---
    def launch_mv_schema1():
        from loaders.sql_mv_loader import run_sql_mv_loader
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            # Only refresh if user successfully logged in (has credentials)
            if session.get_credentials('schema1'):
                refresh_schema1_objects()
        run_sql_mv_loader(parent=root, on_finish=on_close, use_dwh=False)

    def launch_mv_schema2():
        from loaders.sql_mv_loader import run_sql_mv_loader
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            # Only refresh if user successfully logged in (has credentials)
            if session.get_credentials('schema2'):
                refresh_schema2_objects()
        run_sql_mv_loader(parent=root, on_finish=on_close, use_dwh=True)

    schema1_mv_btn.config(command=launch_mv_schema1)
    schema2_mv_btn.config(command=launch_mv_schema2)

    # --- PK button handlers ---
    def launch_pk_schema1():
        from tools.pk_designate_gui import main as pk_main
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            if session.get_credentials('schema1'):
                refresh_schema1_objects()
        pk_main(parent=root, schema_choice='user', on_finish=on_close)

    def launch_pk_schema2():
        from tools.pk_designate_gui import main as pk_main
        _update_status_light('busy')
        def on_close():
            _update_status_light('idle')
            if session.get_credentials('schema2'):
                refresh_schema2_objects()
        pk_main(parent=root, schema_choice='dwh', on_finish=on_close)

    schema1_pk_btn.config(command=launch_pk_schema1)
    schema2_pk_btn.config(command=launch_pk_schema2)

    # Window close handler
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
        # âŒ DO NOT rely on hidden_root being present in other modules â€” prefer
        # explicit lifecycle management. Exit the process now.
        sys.exit()

    # Ensure the window manager close button performs cleanup
    try:
        root.protocol("WM_DELETE_WINDOW", safe_exit)
    except Exception:
        pass

    # Divider above log area
    log_separator = tk.Frame(right_pane, height=1, bg=getattr(root, "_dark_theme", {}).get("border", "#ccc"))
    log_separator.pack(fill="x", padx=10, pady=(8, 12))
    globals()['log_separator'] = log_separator

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
    
    # === Status Bar (status light only - login status removed) ===
    status_separator = tk.Frame(root, height=1, bg=getattr(root, "_dark_theme", {}).get("border", "#ccc"))
    status_separator.pack(fill="x", padx=10)
    status_bar = tk.Frame(root)
    status_bar.pack(side="bottom", fill="x", padx=10, pady=(0, 5))
    
    # Register status bar for theme styling
    globals()['status_bar'] = status_bar
    globals()['status_separator'] = status_separator

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
            if text == "ðŸ”´":
                self.canvas.itemconfig(self.circle_id, fill="#ef4444", outline="#dc2626")
            elif text == "ðŸŸ¢":
                self.canvas.itemconfig(self.circle_id, fill="#22c55e", outline="#16a34a")
            elif text == "â³":
                self.canvas.itemconfig(self.circle_id, fill="#f59e0b", outline="#d97706")  # amber/yellow
            elif text == "â¹ï¸ Aborting...":
                self.canvas.itemconfig(self.circle_id, fill="#f59e0b", outline="#d97706")
        def winfo_exists(self):
            try:
                return self.canvas.winfo_exists()
            except Exception:
                return False
    
    status_light = StatusLight(status_canvas, status_circle)

    def on_scroll(*args):
        global auto_scroll_enabled
        if float(log_text.yview()[1]) >= 0.999:
            auto_scroll_enabled = True
        else:
            auto_scroll_enabled = False

    log_text.config(yscrollcommand=lambda *args: [on_scroll(*args), log_text.vbar.set(*args)])
    
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
    
    # âœ… Validate after GUI + log area are ready
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

    # ðŸ§  Start it in the background so GUI stays responsive
    threading.Thread(target=setup_tray_icon, daemon=True).start()    
    
    import traceback
    def excepthook(type, value, tb):
        print("ðŸ’¥ Uncaught Exception:")
        traceback.print_exception(type, value, tb)

    sys.excepthook = excepthook    
    
    def show_about_popup():
        from tkinter import messagebox
        messagebox.showinfo(
            "About HoonyTools",
            f"HoonyTools v{APP_VERSION}\n\nCreated by hoonywise\n\nFor enterprise use, contact hoonywise@proton.me"
        )

    # Add menu bar (theme selection moved to Settings > Appearance)
    menu_bar = tk.Menu(root)

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

    def apply_full_theme():
        """
        Apply the current theme from gui_utils to the entire main window.
        
        This unified function handles all theme presets (dark and light)
        by reading colors from gui_utils.get_color().
        """
        nonlocal schema1_tree, schema2_tree
        
        # Configure ttk styles using gui_utils
        try:
            gui_utils.configure_ttk_styles(style)
        except Exception:
            pass
        
        # Configure root option database
        try:
            gui_utils.configure_root_options(root)
        except Exception:
            pass
        
        # Apply theme to root window background
        try:
            root.config(bg=gui_utils.get_color('window_bg'))
        except Exception:
            pass
        
        # Apply theme to menu bar
        try:
            gui_utils.apply_theme_to_menu(menu_bar)
        except Exception:
            pass
        
        # Apply theme to custom in-window menu if present
        try:
            if 'custom_menu_frame' in globals() and getattr(custom_menu_frame, 'winfo_exists', lambda: False)():
                try:
                    custom_menu_frame.config(bg=gui_utils.get_color('window_bg'))
                except Exception:
                    pass
                # Style menu buttons (custom_file, custom_help)
                for t in ('custom_file', 'custom_help'):
                    try:
                        mb, m = globals().get(t, (None, None))
                        if mb:
                            try:
                                mb.config(
                                    bg=gui_utils.get_color('menu_bg'),
                                    fg=gui_utils.get_color('menu_fg'),
                                    activebackground=gui_utils.get_color('menu_active_bg'),
                                    activeforeground=gui_utils.get_color('menu_active_fg')
                                )
                            except Exception:
                                pass
                        if m:
                            try:
                                gui_utils.apply_theme_to_menu(m)
                            except Exception:
                                pass
                    except Exception:
                        pass
        except Exception:
            pass
        
        # Style verse pane
        try:
            if 'verse_text' in globals():
                gui_utils.apply_theme_to_pane(globals()['verse_text'])
            if 'verse_inner' in globals():
                gui_utils.apply_theme_to_window(globals()['verse_inner'])
            if 'verse_scrollbar' in globals():
                gui_utils.apply_theme_to_scrollbar(globals()['verse_scrollbar'])
        except Exception:
            pass
        
        # Apply button theme using locals/nonlocals directly
        try:
            gui_utils.apply_theme_to_button(verse_prev_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(verse_next_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema1_refresh_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema1_load_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema1_drop_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema1_view_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema1_mv_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema1_pk_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema1_index_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema2_refresh_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema2_load_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema2_drop_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema2_view_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema2_mv_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema2_pk_btn)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(schema2_index_btn)
        except Exception:
            pass
        
        # Apply theme to schema trees and their containers
        is_dark = gui_utils.is_dark_theme()
        try:
            # Recreate trees to apply new style
            schema1_tree = _recreate_tree(schema1_tree, use_pane_style=is_dark)
        except Exception:
            pass
        try:
            schema2_tree = _recreate_tree(schema2_tree, use_pane_style=is_dark)
        except Exception:
            pass
        
        # Style tree master frames
        try:
            schema1_tree.master.config(bg=gui_utils.get_color('pane_bg'))
        except Exception:
            pass
        try:
            schema2_tree.master.config(bg=gui_utils.get_color('pane_bg'))
        except Exception:
            pass
        
        # Configure tree row tag colors
        try:
            pane_bg = gui_utils.get_color('pane_bg')
            pane_fg = gui_utils.get_color('pane_fg')
            schema1_tree.tag_configure('row', background=pane_bg, foreground=pane_fg)
            for it in list(schema1_tree.get_children()):
                try:
                    schema1_tree.item(it, tags=('row',))
                except Exception:
                    pass
        except Exception:
            pass
        try:
            schema2_tree.tag_configure('row', background=pane_bg, foreground=pane_fg)
            for it in list(schema2_tree.get_children()):
                try:
                    schema2_tree.item(it, tags=('row',))
                except Exception:
                    pass
        except Exception:
            pass
        
        # Style log pane
        try:
            if 'log_text' in globals():
                gui_utils.apply_theme_to_pane(log_text)
        except Exception:
            pass
        
        # Style verse section frames
        try:
            if 'verse_outer_frame' in globals():
                gui_utils.apply_theme_to_window(globals()['verse_outer_frame'])
        except Exception:
            pass
        try:
            if 'verse_labelframe' in globals():
                gui_utils.apply_theme_to_labelframe(globals()['verse_labelframe'])
        except Exception:
            pass
        try:
            if 'verse_btn_bar' in globals():
                gui_utils.apply_theme_to_window(globals()['verse_btn_bar'])
        except Exception:
            pass
        
        # Style main content frames
        try:
            if 'content_frame' in globals():
                gui_utils.apply_theme_to_window(globals()['content_frame'])
        except Exception:
            pass
        try:
            if 'left_pane' in globals():
                gui_utils.apply_theme_to_window(globals()['left_pane'])
        except Exception:
            pass
        try:
            if 'right_pane' in globals():
                gui_utils.apply_theme_to_window(globals()['right_pane'])
        except Exception:
            pass
        
        # Style schema LabelFrames and their child widgets
        for schema_frame_name in ['schema1_frame', 'schema2_frame']:
            try:
                if schema_frame_name in globals():
                    sf = globals()[schema_frame_name]
                    gui_utils.apply_theme_to_labelframe(sf)
                    # Theme all child widgets inside the LabelFrame
                    for child in sf.winfo_children():
                        try:
                            child_class = child.winfo_class()
                            if child_class == 'Frame':
                                gui_utils.apply_theme_to_window(child)
                                # Also theme grandchildren (buttons, labels in the frame)
                                for grandchild in child.winfo_children():
                                    try:
                                        gc_class = grandchild.winfo_class()
                                        if gc_class == 'Button':
                                            gui_utils.apply_theme_to_button(grandchild)
                                        elif gc_class == 'Label':
                                            gui_utils.apply_theme_to_label(grandchild)
                                    except Exception:
                                        pass
                            elif child_class == 'Label':
                                gui_utils.apply_theme_to_label(child)
                        except Exception:
                            pass
            except Exception:
                pass
        
        # Style count labels
        try:
            if 'schema1_count_label' in globals():
                gui_utils.apply_theme_to_label(globals()['schema1_count_label'])
        except Exception:
            pass
        try:
            if 'schema2_count_label' in globals():
                gui_utils.apply_theme_to_label(globals()['schema2_count_label'])
        except Exception:
            pass
        
        # Style status bar
        try:
            if 'status_bar' in globals():
                gui_utils.apply_theme_to_window(globals()['status_bar'])
        except Exception:
            pass
        
        # Style separator lines with border color
        border_color = gui_utils.get_color('border_bg')
        for sep_name in ['log_separator', 'status_separator', 'menu_separator']:
            try:
                if sep_name in globals():
                    globals()[sep_name].config(bg=border_color)
            except Exception:
                pass
        
        # Store reference for potential use by child dialogs
        try:
            root._pane_orig = pane_orig
        except Exception:
            pass
    
    # Alias for backward compatibility
    def apply_current_theme():
        """Alias for apply_full_theme() for backward compatibility."""
        apply_full_theme()

    # Legacy wrapper functions for backward compatibility
    def set_panes_dark():
        """Legacy function: Set panes to dark mode (pure_black theme)."""
        gui_utils.set_theme('pure_black', save=False)
        apply_current_theme()

    def set_panes_light():
        """Legacy function: Set panes to light mode (system_light theme)."""
        gui_utils.set_theme('system_light', save=False)
        apply_current_theme()

    # Theme change handler - called when theme changes from Settings
    def _on_theme_change(theme_key):
        """Handle theme change from gui_utils callback."""
        try:
            apply_current_theme()
        except Exception:
            pass

    # Register the callback with gui_utils
    try:
        gui_utils.register_theme_callback(_on_theme_change)
    except Exception:
        pass

    # Expose apply_current_theme on root so Settings dialog can trigger refresh
    try:
        root._apply_theme = apply_current_theme
    except Exception:
        pass

    # Expose a registration API on the root so child dialogs can register
    # callbacks to be notified when the theme changes.
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

    # Note: View menu removed - theme selection is now in Settings > Appearance

    # Settings launcher (defined here so it can be bound to keyboard shortcut)
    def _launch_settings():
        try:
            from libs.settings import show_settings
            show_settings(root)
        except Exception as e:
            try:
                from tkinter import messagebox
                messagebox.showerror("Error", f"Failed to launch Settings: {e}")
            except Exception:
                pass

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
                elif itype == 'separator':
                    m.add_separator()
            # show popup on click
            mb.config(command=lambda b=mb, mm=m: _show_menu(b, mm))
            mb.pack(side='left', padx=(6, 2))
            return mb, m

        # Build File, View and Help menus
        # File: M.View Manager
        def _launch_mv_manager():
            try:
                from tools.mv_refresh_gui import run_mv_refresh_gui
                def on_close():
                    # Refresh both panes since MV manager can affect both schemas
                    if session.get_credentials('schema1'):
                        refresh_schema1_objects()
                    if session.get_credentials('schema2'):
                        refresh_schema2_objects()
                run_mv_refresh_gui(on_finish=on_close)
            except Exception as e:
                try:
                    from tkinter import messagebox
                    messagebox.showerror("Error", f"Failed to launch M.View Manager: {e}")
                except Exception:
                    pass

        def _exit_app():
            """Exit the application."""
            try:
                root.destroy()
            except Exception:
                pass

        file_items = [
            ('command', 'M.View Manager', _launch_mv_manager),
            ('command', 'Settings', _launch_settings),
            ('separator', None, None),
            ('command', 'Exit', _exit_app)
        ]
        
        # Help: About and Updates
        help_items = [
            ('command', 'About', show_about_popup),
            ('command', 'Check for Updates', lambda: webbrowser.open("https://github.com/hoonywise/HoonyTools/releases"))
        ]

        # Create menubuttons (File and Help only - View menu removed, theme in Settings)
        mb_file, m_file = _mb('File', file_items)
        mb_help, m_help = _mb('Help', help_items)

        return f, (mb_file, m_file), (mb_help, m_help)

    # Create the custom in-window menu bar and hide the native one
    try:
        # Create custom bar and then unset native menubar so it doesn't show
        custom_menu_frame, custom_file, custom_help = _create_custom_menu_bar(root)
        # Expose references globally so nested theme functions can style them
        try:
            globals()['custom_menu_frame'] = custom_menu_frame
            globals()['custom_file'] = custom_file
            globals()['custom_help'] = custom_help
        except Exception:
            pass
        # Pack the custom menu before the verse row so it appears at the top
        try:
            custom_menu_frame.pack(fill='x', side='top', before=globals().get('verse_outer_frame'))
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

    # We replaced the native menu with a custom in-window menu. Keep the
    # menu_bar structure around for compatibility but do not reattach it as
    # the root menubar (native menubars ignore styling on some platforms).
    menu_separator = tk.Frame(root, height=1, bg=getattr(root, "_dark_theme", {}).get("border", "#b0b0b0"))
    menu_separator.pack(fill="x")
    globals()['menu_separator'] = menu_separator

    # Bind Ctrl+Alt+S to open Settings
    try:
        root.bind('<Control-Alt-s>', lambda e: _launch_settings())
        root.bind('<Control-Alt-S>', lambda e: _launch_settings())
    except Exception:
        pass

    # Load theme from config.ini on startup and apply it
    try:
        gui_utils.load_theme_from_config()
        apply_current_theme()
    except Exception:
        pass

    # Auto-refresh object panes on startup if saved credentials exist
    def _auto_refresh_on_startup():
        """Auto-refresh object panes if saved credentials exist (not a brand new launch)."""
        if session.get_credentials('schema1'):
            refresh_schema1_objects()
        if session.get_credentials('schema2'):
            refresh_schema2_objects()

    root.after(100, _auto_refresh_on_startup)

    root.mainloop()

if __name__ == "__main__":
    try:
        # Check if splash screen is enabled
        splash_enabled = True
        try:
            from configparser import ConfigParser
            from libs.paths import PROJECT_PATH
            config_path = PROJECT_PATH / "libs" / "config.ini"
            cfg = ConfigParser()
            cfg.read(config_path)
            splash_enabled = cfg.getboolean('Appearance', 'splash_enabled')
        except Exception:
            splash_enabled = True  # Default enabled if config not found
        
        # Show splash only if enabled
        if splash_enabled:
            show_splash()
        
        # Launch GUI immediately (no delay if splash disabled)
        launch_tool_gui()
    except KeyboardInterrupt:
        # Allow graceful exit when user force-quits (Ctrl+C or similar)
        try:
            sys.exit(0)
        except Exception:
            pass
