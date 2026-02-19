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

APP_VERSION = "1.3.0"

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
from loaders.excel_csv_loader import load_multiple_files
from loaders.sql_view_loader import run_sql_view_loader
from loaders.sql_mv_loader import run_sql_mv_loader
from tools.object_cleanup_gui import drop_user_tables, delete_dwh_rows
from tools.pk_designate_gui import main as pk_designate_main
from libs.bible_books import book_lookup

should_abort = False
auto_scroll_enabled = True
is_gui_running = True

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
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width / 2) - (width / 2))
    y = int((screen_height / 2) - (height / 2))
    window.geometry(f"{width}x{height}+{x}+{y}")

def abort_process():
    abort_manager.set_abort(True)
    logger.warning("⛔ Abort requested by user.")

def run_selected():
    global should_abort
    should_abort = False
    tool_name = selected_tool.get()
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

    if tool_name == "✅ Excel/CSV Loader":
        def threaded_excel():
            try:
                TOOLS[tool_name]()
            except Exception as e:
                logger.exception(f"❌ Error running {tool_name}: {e}")
            finally:
                status_light.config(text="🟢")

        threading.Thread(target=threaded_excel, daemon=True).start()
        return

    

    # For everything else
    def run_and_update():
        try:
            # Tools that accept an on_finish callback should be called with it so the launcher
            # can update its status light. Treat SQL View and SQL Materialized View loaders
            # the same way.
            if tool_name in ("☑ SQL View Loader", "☑ SQL Materialized View Loader"):
                TOOLS[tool_name](on_finish=lambda: status_light.config(text="🟢"))
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
        except Exception as e:
            logger.exception(f"❌ Error running {tool_name}: {e}")
            status_light.config(text="🟢")

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


    
    global root, selected_tool, log_text, log_stream, status_light

    hidden_root = tk.Tk()
    hidden_root.withdraw()  # Hide it immediately
    
    # 👇 Taskbar ownership
    root = tk.Toplevel(hidden_root)
    root.protocol("WM_DELETE_WINDOW", hidden_root.quit)

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
    if not session.stored_credentials:
        root.destroy()
        hidden_root.destroy()
        return
    
    # ✅ After login success: show and center the main window
    root.deiconify()
    center_window(root, 1280, 960)  # Resize to full GUI and center on screen
    root.title("HoonyTools Launcher")

    # === Main content: two-column layout (left object lists, right main UI) ===
    content_frame = tk.Frame(root)
    content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # Left pane for object lists (fixed width)
    left_pane = tk.Frame(content_frame, width=360)
    left_pane.pack(side="left", fill="y", padx=(0, 10))

    # Right pane for existing UI (tools, log, status)
    right_pane = tk.Frame(content_frame)
    right_pane.pack(side="left", fill="both", expand=True)

    # === Bible Verse Row ===
    verse_frame = tk.Frame(right_pane)
    verse_frame.pack(fill="x", padx=10, pady=(0, 0))

    verse_label = tk.Label(
        verse_frame,
        text=get_random_verse(),
        font=("Arial", 9, "italic"),
        fg="#444444",
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
    tk.Frame(root, height=1, bg="#ccc").pack(fill="x", padx=10, pady=(5, 10))    

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
    
    # --- Helper: create object list frame in left pane
    def _make_objects_frame(parent, title):
        frame = tk.LabelFrame(parent, text=title, padx=6, pady=6)
        frame.pack(fill="both", pady=(0, 8))
        tv = ttk.Treeview(frame, columns=("name", "type"), show="headings", height=10)
        tv.heading("name", text="Name")
        tv.heading("type", text="Type")
        tv.column("name", width=180, anchor="w")
        tv.column("type", width=120, anchor="center")
        vs = tk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        tv.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        btn_frame_local = tk.Frame(frame)
        btn_frame_local.pack(fill="x", pady=(6, 0))
        refresh_btn = tk.Button(btn_frame_local, text="Refresh", width=10)
        refresh_btn.pack(side="left")
        status_lbl = tk.Label(btn_frame_local, text="", font=("Arial", 8), fg="#444444")
        status_lbl.pack(side="left", padx=(6, 0))
        return tv, refresh_btn, status_lbl

    # Create the two object panes in the left_pane
    user_tree, user_refresh_btn, user_status = _make_objects_frame(left_pane, "User Objects")
    dwh_tree, dwh_refresh_btn, dwh_status = _make_objects_frame(left_pane, "DWH Objects (login required)")

    # Utility to populate a treeview from rows [(name, type), ...]
    def _populate_treeview(tv, rows):
        try:
            tv.delete(*tv.get_children())
        except Exception:
            pass
        for name, obj_type in rows:
            tv.insert("", "end", values=(name, obj_type))

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
                cur.execute("""
                    SELECT object_name, object_type FROM all_objects
                    WHERE owner = :owner
                    AND object_type IN ('TABLE','VIEW','MATERIALIZED VIEW')
                    ORDER BY object_name
                """, [conn.username.upper()])
                rows = cur.fetchall()
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

            root.after(0, lambda: (_populate_treeview(user_tree, rows), user_status.config(text=f"{len(rows)} objects")))
        threading.Thread(target=worker, daemon=True).start()

    def refresh_dwh_objects():
        dwh_status.config(text="Loading...")
        def worker():
            from libs.oracle_db_connector import get_db_connection
            conn = get_db_connection(force_shared=True, root=root)
            if not conn:
                root.after(0, lambda: dwh_status.config(text="Not logged in"))
                return
            try:
                cur = conn.cursor()
                cur.execute("""
                    SELECT object_name, object_type FROM all_objects
                    WHERE owner = :owner
                    AND object_type IN ('TABLE','VIEW','MATERIALIZED VIEW')
                    ORDER BY object_name
                """, ["DWH"])
                rows = cur.fetchall()
            except Exception as e:
                rows = []
                logger.exception(f"Failed to list DWH objects: {e}")
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

            root.after(0, lambda: (_populate_treeview(dwh_tree, rows), dwh_status.config(text=f"{len(rows)} objects")))
        threading.Thread(target=worker, daemon=True).start()

    # Wire buttons
    user_refresh_btn.config(command=refresh_user_objects)
    dwh_refresh_btn.config(command=refresh_dwh_objects)

    tool_select_frame = tk.Frame(right_pane)
    tool_select_frame.pack(pady=(10, 10))

    tk.Label(
        tool_select_frame, 
        text="Select Tool:",
        font=("Arial", 12, "bold")
    ).pack(side="left", padx=(0, 10))
    
    legend_frame = tk.Frame(right_pane)
    legend_frame.pack(fill="x", padx=10)

    tk.Label(
        legend_frame,
        text="☑ = User/DWH   |   🔒 = DWH only   |   📁 = Local only",
        font=("Arial", 10),
        anchor="w",  # align left
        justify="left"
    ).pack() 
    
    # Divider between legend and button row
    tk.Frame(right_pane, height=1, bg="#ccc").pack(fill="x", padx=10, pady=(10, 15))

    selected_tool = tk.StringVar()
    tool_menu = ttk.Combobox(tool_select_frame, textvariable=selected_tool, values=list(TOOLS.keys()), font=("Arial", 11), state="readonly", width=22)
    tool_menu.pack(side="left")

    # Optional: pre-select the first item
    tool_menu.current(0)

    btn_frame = tk.Frame(tool_select_frame)
    btn_frame.pack()

    tk.Button(btn_frame, text="Run", width=10, command=lambda: run_selected()).pack(side="left", padx=7)
    tk.Button(btn_frame, text="Abort", width=10, command=abort_process).pack(side="left", padx=7)

    def safe_exit():
        global is_gui_running
        is_gui_running = False
        try:
            root.destroy()
        except Exception:
            pass
        # ❌ DO NOT destroy hidden_root — let the process exit handle it
        sys.exit()

    tk.Button(btn_frame, text="Exit", width=10, command=safe_exit).pack(side="left", padx=7)

    # Place the log area in the right pane (narrower because left pane uses space)
    log_text = scrolledtext.ScrolledText(right_pane, width=80, height=25)
    log_text.pack(padx=10, pady=(10, 5), fill="both", expand=True)
    
    # === Status Bar (under verse) ===
    tk.Frame(root, height=1, bg="#ccc").pack(fill="x", padx=10)
    status_bar = tk.Frame(root)
    status_bar.pack(side="bottom", fill="x", padx=10, pady=(0, 5))

    tk.Label(
        status_bar,
        text=f"Logged in as: {session.stored_credentials['username']} @ {session.stored_credentials['dsn']}",
        font=("Arial", 8),
        anchor="w",
        justify="left"
    ).pack(side="left")

    status_light = tk.Label(
        status_bar,
        text="🟢",
        font=("Arial", 12)
    )
    status_light.pack(side="right", padx=10)

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

    # Add menu bar with "Help > About"
    menu_bar = tk.Menu(
        root,
        bg="#d0d0d0",                # darker gray for menu bar
        fg="black",
        activebackground="#ffffff",  # white hover for dropdown
        activeforeground="black"
    )
    
    help_menu = tk.Menu(
        menu_bar,
        tearoff=0,
        bg="#ffffff",                # white dropdown
        fg="black",
        activebackground="#d0d0d0",  # light gray hover
        activeforeground="black"
    )
    
    help_menu.add_command(label="About", command=show_about_popup)
    help_menu.add_command(
        label="Check for Updates",
        command=lambda: webbrowser.open("https://github.com/hoonywise/HoonyTools/releases")
    )
    menu_bar.add_cascade(label="Help", menu=help_menu, underline=0)
    root.config(menu=menu_bar)    
    tk.Frame(root, height=1, bg="#b0b0b0").pack(fill="x")
        
    root.mainloop()

TOOLS = {    
    "☑ Excel/CSV Loader": load_multiple_files,
    "☑ Object Dropper": drop_user_tables,
    "☑ SQL View Loader": run_sql_view_loader,
    "☑ SQL Materialized View Loader": run_sql_mv_loader,
    "☑ Materialized View Manager": None,  # placeholder, will be wired if available
    "☑ Designate PK": pk_designate_main,
    
    # the repository for later separation.
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
    show_splash()
    launch_tool_gui()
