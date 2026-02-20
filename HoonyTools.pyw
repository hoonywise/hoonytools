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

APP_VERSION = "1.3.7"

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

    # Run the Excel/CSV loader in a background thread so the main GUI remains responsive.
    if tool_name == "☑ Excel/CSV Loader":
        def threaded_excel():
            logger.info("Starting Excel/CSV loader thread")
            try:
                logger.info(f"threaded_excel: about to invoke loader callable for {tool_name}")
                try:
                    TOOLS[tool_name](root)
                except TypeError:
                    TOOLS[tool_name]()
                logger.info("threaded_excel: loader callable returned")
            except Exception as e:
                logger.exception(f"❌ Error running {tool_name}: {e}")
            finally:
                try:
                    status_light.config(text="🟢")
                except Exception:
                    pass

        threading.Thread(target=threaded_excel, daemon=True).start()
        return

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


    
    global root, selected_tool, log_text, log_stream, status_light, run_btn, tool_menu, abort_btn

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
        root.destroy()
        hidden_root.destroy()
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
        status_lbl = tk.Label(top_bar, text="", font=("Arial", 8), fg="#444444")
        status_lbl.pack(side="left")

        # Content area (treeview + scrollbar) sits below the top bar and expands
        content_area = tk.Frame(frame)
        content_area.pack(fill="both", expand=True)

        # Lock treeview width to avoid auto-resize when labels change
        # Add a third column `pk` to show primary key info (comma-separated columns or empty)
        tv = ttk.Treeview(content_area, columns=("name", "type", "pk"), show="headings")
        tv.heading("name", text="Name")
        tv.heading("type", text="Type")
        tv.heading("pk", text="PK")
        tv.column("name", width=160, anchor="w", stretch=False)
        tv.column("type", width=120, anchor="center", stretch=False)
        tv.column("pk", width=160, anchor="center", stretch=False)
        vs = tk.Scrollbar(content_area, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vs.set)
        tv.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")

        return frame, tv, refresh_btn, status_lbl

    # Create the two object panes in the left_pane (stacked, share vertical space)
    user_frame, user_tree, user_refresh_btn, user_status = _make_objects_frame(left_pane, "User Objects")
    dwh_frame, dwh_tree, dwh_refresh_btn, dwh_status = _make_objects_frame(left_pane, "DWH Objects")

    # Prevent the left pane from auto-resizing when internal labels change
    left_pane.pack_propagate(False)

    # Create external count labels aligned to the right of each object frame
    # Use grid placement so they don't affect the inner frame widths
    user_count_label = tk.Label(left_pane, text="", font=("Arial", 8), fg="#444444")
    dwh_count_label = tk.Label(left_pane, text="", font=("Arial", 8), fg="#444444")
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
            tv.insert("", "end", values=(name, obj_type, pk or ""))

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
                        WHERE owner = :owner
                        AND object_type IN ('TABLE','VIEW','MATERIALIZED VIEW')
                        ORDER BY object_name
                    """, ["DWH"])
                    rows = cur.fetchall()
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

    tk.Label(
        toolbar_inner,
        text="Select Tool:",
        font=("Arial", 12, "bold")
    ).pack(side="left", padx=(0, 10))

    # Tool selector and buttons
    selected_tool = tk.StringVar()
    tool_menu = ttk.Combobox(toolbar_inner, textvariable=selected_tool, values=list(TOOLS.keys()), font=("Arial", 11), state="readonly", width=22)
    tool_menu.pack(side="left")
    tool_menu.current(0)

    btn_frame = tk.Frame(toolbar_inner)
    btn_frame.pack(side="left", padx=12)

    # Keep references to these controls so abort handler can disable/enable them
    run_btn = tk.Button(btn_frame, text="Run", width=10, command=lambda: run_selected())
    run_btn.pack(side="left", padx=7)
    abort_btn = tk.Button(btn_frame, text="Abort", width=10, command=abort_process)
    abort_btn.pack(side="left", padx=7)

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
    tk.Frame(right_pane, height=1, bg="#ccc").pack(fill="x", padx=10, pady=(8, 12))

    # Place the log area in the right pane (narrower because left pane uses space)
    log_text = scrolledtext.ScrolledText(right_pane, width=80, height=25)
    log_text.pack(padx=10, pady=(0, 5), fill="both", expand=True)
    
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
    try:
        show_splash()
        launch_tool_gui()
    except KeyboardInterrupt:
        # Allow graceful exit when user force-quits (Ctrl+C or similar)
        try:
            sys.exit(0)
        except Exception:
            pass
