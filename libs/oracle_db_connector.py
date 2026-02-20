import oracledb
import logging
import tkinter as tk
from tkinter import Tk, simpledialog, messagebox
import threading
from libs import session
import queue
from libs import abort_manager
from configparser import ConfigParser
from libs.paths import PROJECT_PATH as BASE_PATH

config = ConfigParser()
config.read(BASE_PATH / "libs" / "config.ini")

logger = logging.getLogger(__name__)

# Local safe messagebox helper to avoid parent-less dialogs when possible
def _safe_messagebox(fn_name: str, *args, parent=None):
    try:
        if parent is not None:
            return getattr(messagebox, fn_name)(*args, parent=parent)
        return getattr(messagebox, fn_name)(*args)
    except Exception:
        try:
            return getattr(messagebox, fn_name)(*args)
        except Exception:
            if fn_name.startswith('ask'):
                return False
            return None

_credentials = {}
_error_queue = queue.Queue()

def process_queued_errors(root=None):
    try:
        while not _error_queue.empty():
            title, message = _error_queue.get_nowait()
            if root:
                root.update()
            _safe_messagebox('showerror', title, message, parent=root)
    except Exception as e:
        print(f"Error displaying queued error: {e}")

def show_error_safe(title, message):
    if threading.current_thread() is threading.main_thread():
        _safe_messagebox('showerror', title, message)
    else:
        _error_queue.put((title, message))

def _show_login_dialog(hardcoded_user=None, hardcoded_dsn="DWHDB_DB", parent=None):
    import ctypes
    from libs.paths import ASSETS_PATH
    import tkinter as tk
    from tkinter import messagebox, Toplevel
    
    config_path = BASE_PATH / "libs" / "config.ini"
    config = ConfigParser()
    config.read(config_path)    

    # ❌ DO NOT create hidden_root — let launcher_gui own the icon
    # Parent the dialog when possible so it appears above the launcher/root
    try:
        login_window = Toplevel(parent) if parent is not None else Toplevel()
    except Exception:
        login_window = Toplevel()
    login_window.title("Oracle Login")
    login_window.resizable(False, False)

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
    except Exception:
        pass

    try:
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        login_window.iconbitmap(default=icon_path)
    except Exception:
        pass

    screen_width = login_window.winfo_screenwidth()
    screen_height = login_window.winfo_screenheight()
    x = int((screen_width / 2) - (300 / 2))
    y = int((screen_height / 2) - (150 / 2))
    login_window.geometry(f"+{x}+{y}")

    # Register active prompt on parent so abort handlers can close it if needed
    try:
        if parent is not None:
            try:
                setattr(parent, '_active_prompt_window', login_window)
                logger.debug(f"Registered active prompt window on parent={parent}")
            except Exception:
                pass
    except Exception:
        pass
    # Avoid using grab_set() for the login dialog. Grabs can prevent the
    # launcher main window from responding to Abort clicks on some platforms.
    # Instead, make the dialog transient, bring it to the front, and focus it.
    try:
        if parent is not None:
            try:
                login_window.transient(parent)
            except Exception:
                pass
        try:
            login_window.attributes('-topmost', True)
        except Exception:
            pass
        try:
            login_window.deiconify(); login_window.lift(); login_window.update(); login_window.focus_force()
        except Exception:
            pass
        try:
            # remove topmost after ensuring it's visible
            login_window.after(150, lambda: login_window.attributes('-topmost', False))
        except Exception:
            pass
    except Exception:
        pass

    frame = tk.Frame(login_window, padx=20, pady=10)
    frame.pack()

    tk.Label(frame, text="Username:").grid(row=0, column=0, sticky="e")
    username_entry = tk.Entry(frame, width=25)
    username_entry.grid(row=0, column=1)
    username_entry.insert(0, hardcoded_user if hardcoded_user else "")

    tk.Label(frame, text="Password:").grid(row=1, column=0, sticky="e")
    password_entry = tk.Entry(frame, show="*", width=25)
    password_entry.grid(row=1, column=1)
    
    tk.Label(frame, text="DSN:").grid(row=2, column=0, sticky="e")
    dsn_entry = tk.Entry(frame, width=25)
    dsn_entry.grid(row=2, column=1)
    dsn_entry.insert(0, hardcoded_dsn)    
    
    # Use last saved user if no hardcoded_user is provided
    if hardcoded_user:
        user_key = hardcoded_user.strip().lower()
    else:
        # Try to find a non-DWH section with a saved login
        non_dwh_sections = [s for s in config.sections() if s != "dwh"]
        user_key = non_dwh_sections[0] if non_dwh_sections else ""

    saved_username = user_key
    saved_pwd = ""
    saved_dsn = hardcoded_dsn

    if user_key and config.has_section(user_key):
        saved_username = config[user_key].get("username", user_key)
        saved_pwd = config[user_key].get("password", "")
        saved_dsn = config[user_key].get("dsn", hardcoded_dsn)

    username_entry.delete(0, tk.END)
    username_entry.insert(0, saved_username)
    password_entry.delete(0, tk.END)
    password_entry.insert(0, saved_pwd)
    dsn_entry.delete(0, tk.END)
    dsn_entry.insert(0, saved_dsn)

    # ✅ Save password checkbox (checked if password exists)
    save_pw_var = tk.BooleanVar(value=bool(saved_pwd))
    save_pw_check = tk.Checkbutton(frame, text="Save password", variable=save_pw_var)
    save_pw_check.grid(row=3, columnspan=2, pady=(5, 5), sticky="w")
    
    if username_entry.get().strip().lower() == "dwh":
        password_entry.focus()  # ✅ Focus password if user is DWH
    else:
        username_entry.focus()  # ✅ Focus username for manual login
    
    login_window.bind("<Return>", lambda event: submit())  # ✅ Press Enter to submit    

    result = {}

    def submit():
        user = username_entry.get().strip()
        pwd = password_entry.get().strip()
        dsn = dsn_entry.get().strip()
        if user and pwd and dsn:
            result.update({
                "username": user,
                "password": pwd,
                "dsn": dsn,
                "save": save_pw_var.get()  # ⬅️ this is the key
            })

            # Save config.ini if checkbox is checked
            section_name = user.lower()

            if save_pw_var.get():
                config[section_name] = {
                    "username": user,
                    "password": pwd,
                    "dsn": dsn
                }
                logger.info(f"💾 Saved credentials for {user} to config.ini")
            else:
                if config.has_section(section_name):
                    config.remove_section(section_name)
                    logger.info(f"🧹 Removed saved credentials for {user} from config.ini")

            # Always write updated config
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w") as f:
                config.write(f)

            login_window.destroy()
            try:
                if parent is not None and hasattr(parent, '_active_prompt_window'):
                    try:
                        delattr(parent, '_active_prompt_window')
                        logger.debug(f"Cleared active prompt window attribute on parent={parent}")
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            _safe_messagebox('showerror', "Error", "Username, password, and DSN are all required.", parent=login_window)

    def cancel():
        try:
            login_window.destroy()
        finally:
            try:
                if parent is not None and hasattr(parent, '_active_prompt_window'):
                    try:
                        delattr(parent, '_active_prompt_window')
                        logger.debug(f"Cleared active prompt window attribute on parent={parent}")
                    except Exception:
                        pass
            except Exception:
                pass

    btn_frame = tk.Frame(frame, pady=10)
    btn_frame.grid(row=4, columnspan=2)
    tk.Button(btn_frame, text="Login", command=submit, width=10).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side="left", padx=5)

    login_window.wait_window()
    return result if result else None

def prompt_credentials(hardcoded_user=None, hardcoded_dsn="DWHDB_DB", parent=None):
    
    if threading.current_thread() is threading.main_thread():
        return _show_login_dialog(hardcoded_user, hardcoded_dsn, parent=parent)

    show_error_safe("Thread Error", "❌ Login prompt must be called from the main thread.")
    return None

def get_db_connection(force_shared=False, root=None):
    try:
        oracledb.init_oracle_client()
        logger.info("✅ Oracle client initialized (Thick mode if available)")
    except Exception:
        logger.info("ℹ️ Proceeding with Thin mode")    
    config_path = BASE_PATH / "libs" / "config.ini"
    try:
        creds = None

        if force_shared:

            if (
                not session.dwh_credentials
                or session.dwh_credentials.get("username", "").lower() != "dwh"
            ):
                # If a root is provided and we're on a background thread, schedule
                # the prompt on the main thread and wait for the result using an Event.
                if root and threading.current_thread() is not threading.main_thread():
                    result_holder = {}
                    ev = threading.Event()

                    def ask_login():
                        try:
                            # Parent the prompt to the launcher's root so abort handler
                            # can find and close it if needed.
                            result_holder["creds"] = prompt_credentials(hardcoded_user="dwh", hardcoded_dsn="DWHDB_DB", parent=root)
                        finally:
                            try:
                                ev.set()
                            finally:
                                try:
                                    abort_manager.register_prompt_event(None)
                                except Exception:
                                    pass

                    try:
                        logger.info("Scheduling DWH login prompt on main thread via root.after")
                        # Register the Event so abort handlers can wake the worker
                        try:
                            abort_manager.register_prompt_event(ev)
                        except Exception:
                            pass
                        root.after(0, ask_login)
                        # Wait for the main thread to complete prompting, but don't block
                        # forever: poll the Event with a short timeout so Abort can
                        # interrupt the wait.
                        import time as _time
                        waited = 0.0
                        timeout = 30.0
                        interval = 0.2
                        from libs import abort_manager as _am
                        while not ev.wait(interval):
                            if getattr(_am, 'should_abort', False):
                                logger.info("Abort requested while waiting for DWH login prompt; cancelling prompt wait")
                                # ensure any main-thread prompt is cancelled by clearing registration
                                try:
                                    _am.cancel_prompt_event()
                                except Exception:
                                    pass
                                break
                            waited += interval
                            if waited >= timeout:
                                logger.warning("Timed out waiting for DWH login prompt; cancelling")
                                break
                        logger.info("DWH login prompt completed or cancelled; checking credentials result")
                        try:
                            abort_manager.register_prompt_event(None)
                        except Exception:
                            pass
                    except Exception:
                        # Fallback to direct call if scheduling failed
                        logger.warning("Scheduling DWH login prompt failed; falling back to direct prompt")
                        result_holder["creds"] = prompt_credentials(hardcoded_user="dwh", hardcoded_dsn="DWHDB_DB")

                    creds_temp = result_holder.get("creds")
                else:
                    creds_temp = prompt_credentials(hardcoded_user="dwh", hardcoded_dsn="DWHDB_DB")

                if creds_temp:
                    session.dwh_credentials = creds_temp
                    session.stored_credentials = creds_temp

                    if creds_temp.get("save", False):
                        # Re-read the on-disk config immediately before writing to avoid
                        # overwriting sections added by other parts of the app (e.g. GUI)
                        from configparser import ConfigParser
                        local_cfg = ConfigParser()
                        try:
                            local_cfg.read(config_path)
                        except Exception:
                            # If read fails for any reason, start with an empty config
                            local_cfg = ConfigParser()

                        local_cfg["dwh"] = {
                            "username": "dwh",
                            "password": creds_temp["password"],
                            "dsn": creds_temp["dsn"]
                        }

                        config_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(config_path, "w", encoding="utf-8") as f:
                            local_cfg.write(f)

                        logger.info("💾 Saved DWH credentials to config.ini")
                    else:
                        logger.info("🔓 DWH login used but not saved (checkbox unchecked)")
                else:
                    return None

            # 🧠 Use in-memory session creds if they exist
            if session.dwh_credentials:
                section = session.dwh_credentials
            elif config.has_section("dwh"):
                section = config["dwh"]
            else:
                show_error_safe("Config Error", "❌ Missing [dwh] section in config.ini. Please log in again and check 'Save password'.")
                return None

            if not section.get("username") or not section.get("password") or not section.get("dsn"):
                show_error_safe("Config Error", "❌ Incomplete DWH credentials in config.ini. Please ensure username, password, and DSN are saved.")
                return None

            creds = {
                "username": section.get("username"),
                "password": section.get("password"),
                "dsn": section.get("dsn")
            }

        else:
            if not session.user_credentials:
                # If a root is provided and we're in a background thread, schedule
                # the prompt on the main thread and wait for the result.
                if root and threading.current_thread() is not threading.main_thread():
                    result_holder = {}
                    ev = threading.Event()

                    def ask_user_login():
                        try:
                            result_holder["creds"] = prompt_credentials()
                        finally:
                            try:
                                ev.set()
                            finally:
                                try:
                                    abort_manager.register_prompt_event(None)
                                except Exception:
                                    pass

                    try:
                        logger.info("Scheduling user login prompt on main thread via root.after")
                        try:
                            abort_manager.register_prompt_event(ev)
                        except Exception:
                            pass
                        root.after(0, ask_user_login)
                        # Poll the Event like above so Abort can interrupt waiting.
                        import time as _time
                        waited = 0.0
                        timeout = 30.0
                        interval = 0.2
                        from libs import abort_manager as _am
                        while not ev.wait(interval):
                            if getattr(_am, 'should_abort', False):
                                logger.info("Abort requested while waiting for user login prompt; cancelling prompt wait")
                                try:
                                    _am.cancel_prompt_event()
                                except Exception:
                                    pass
                                break
                            waited += interval
                            if waited >= timeout:
                                logger.warning("Timed out waiting for user login prompt; cancelling")
                                break
                        logger.info("User login prompt completed or cancelled; checking credentials result")
                        try:
                            abort_manager.register_prompt_event(None)
                        except Exception:
                            pass
                    except Exception:
                        logger.warning("Scheduling user login prompt failed; falling back to direct prompt")
                        # Fallback: try to prompt on main thread directly, parent when possible
                        try:
                            result_holder["creds"] = prompt_credentials(parent=root)
                        except Exception:
                            result_holder["creds"] = prompt_credentials()

                    session.user_credentials = result_holder.get("creds")
                    session.stored_credentials = session.user_credentials
                else:
                    if threading.current_thread() is not threading.main_thread():
                        show_error_safe("Thread Error", "❌ Cannot prompt for login from a background thread.")
                        return None
                    session.user_credentials = prompt_credentials()
                    session.stored_credentials = session.user_credentials

            if not session.user_credentials:
                logger.warning("❌ Oracle login was not completed.")
                return None

            creds = session.user_credentials

        if not creds:
            logger.warning("❌ Oracle login cancelled or config is missing.")
            show_error_safe("Login Failed", "❌ Could not load shared credentials. Please check your config.ini.")
            return None

        conn = oracledb.connect(
            user=creds["username"],
            password=creds["password"],
            dsn=creds["dsn"],
            mode=oracledb.DEFAULT_AUTH
        )
        logger.info(f"✅ Connected to {creds['dsn']} as {creds['username']}")
        # Auto-register shared DWH connections so callers don't need to.
        # Import lazily to avoid circular imports with libs.dwh_session.
        try:
            if force_shared and root is not None:
                try:
                    from libs import dwh_session
                    dwh_session.register_connection(root, conn)
                except Exception:
                    logger.debug("Failed to auto-register DWH connection", exc_info=True)
        except Exception:
            # defensive: any failure here must not prevent returning the connection
            logger.debug("Unexpected error during DWH auto-registration", exc_info=True)

        return conn

    except Exception as e:
        if "ORA-01017" in str(e):
            logger.warning("❌ Oracle login failed: Invalid username or password.")
            try:
                show_error_safe("Invalid Credentials", "❌ Username or password is incorrect. Please try again.")
            except:
                pass
        elif "ORA-12170" in str(e):
            msg = "❌ Could not connect to Oracle: Timeout.\n\nMake sure you are connected to VPN if working remotely."
            logger.warning(msg)
            try:
                show_error_safe("VPN Required", msg)
            except:
                pass
        else:
            logger.exception(f"❌ Oracle connection failed: {e}")
            try:
                show_error_safe("Connection Error", f"Failed to connect to Oracle:\n{e}")
            except:
                pass

