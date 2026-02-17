import oracledb
import logging
import tkinter as tk
from tkinter import Tk, simpledialog, messagebox
import threading
from libs import session
import queue
from configparser import ConfigParser
from libs.paths import PROJECT_PATH as BASE_PATH

config = ConfigParser()
config.read(BASE_PATH / "libs" / "config.ini")

logger = logging.getLogger(__name__)

_credentials = {}
_error_queue = queue.Queue()

def process_queued_errors(root=None):
    try:
        while not _error_queue.empty():
            title, message = _error_queue.get_nowait()
            if root:
                root.update()
            messagebox.showerror(title, message)
    except Exception as e:
        print(f"Error displaying queued error: {e}")

def show_error_safe(title, message):
    if threading.current_thread() is threading.main_thread():
        messagebox.showerror(title, message)
    else:
        _error_queue.put((title, message))

def _show_login_dialog(hardcoded_user=None, hardcoded_dsn="DWHDB_DB"):
    import ctypes
    from libs.paths import ASSETS_PATH
    import tkinter as tk
    from tkinter import messagebox, Toplevel
    
    config_path = BASE_PATH / "libs" / "config.ini"
    config = ConfigParser()
    config.read(config_path)    

    # ❌ DO NOT create hidden_root — let launcher_gui own the icon
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

    login_window.grab_set()
    login_window.focus_force()

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
        else:
            messagebox.showerror("Error", "Username, password, and DSN are all required.")

    def cancel():
        login_window.destroy()

    btn_frame = tk.Frame(frame, pady=10)
    btn_frame.grid(row=4, columnspan=2)
    tk.Button(btn_frame, text="Login", command=submit, width=10).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Cancel", command=cancel, width=10).pack(side="left", padx=5)

    login_window.wait_window()
    return result if result else None

def prompt_credentials(hardcoded_user=None, hardcoded_dsn="DWHDB_DB"):
    
    if threading.current_thread() is threading.main_thread():
        return _show_login_dialog(hardcoded_user, hardcoded_dsn)

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
                or not session.dwh_credentials.get("save", False)
            ):
                if root:
                    result_holder = {}
                    def ask_login():
                        result_holder["creds"] = prompt_credentials(hardcoded_user="dwh", hardcoded_dsn="DWHDB_DB")
                    root.after(0, ask_login)
                    login_window = tk.Toplevel(root)
                    login_window.withdraw()  # we just need to wait on something
                    login_window.after(100, login_window.destroy)
                    login_window.wait_window()
                    creds_temp = result_holder.get("creds")
                else:
                    creds_temp = prompt_credentials(hardcoded_user="dwh", hardcoded_dsn="DWHDB_DB")

                if creds_temp:
                    session.dwh_credentials = creds_temp
                    session.stored_credentials = creds_temp

                    if creds_temp.get("save", False):
                        config["dwh"] = {
                            "username": "dwh",
                            "password": creds_temp["password"],
                            "dsn": creds_temp["dsn"]
                        }

                        config_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(config_path, "w") as f:
                            config.write(f)

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

