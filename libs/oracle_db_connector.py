"""
Oracle database connection management for HoonyTools.

Provides credential prompting and connection management for dual schema support.
"""
import oracledb
import logging
import tkinter as tk
from tkinter import messagebox
import threading
from libs import session
import queue
from libs import abort_manager
from configparser import ConfigParser
from libs.paths import PROJECT_PATH as BASE_PATH

logger = logging.getLogger(__name__)


# =============================================================================
# Error Handling Utilities
# =============================================================================

_error_queue = queue.Queue()


def _safe_messagebox(fn_name: str, *args, parent=None):
    """Safe messagebox helper to avoid parent-less dialogs when possible."""
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


def process_queued_errors(root=None):
    """Process any queued error messages from background threads."""
    try:
        while not _error_queue.empty():
            title, message = _error_queue.get_nowait()
            if root:
                root.update()
            _safe_messagebox('showerror', title, message, parent=root)
    except Exception as e:
        print(f"Error displaying queued error: {e}")


def show_error_safe(title, message):
    """Show error message, queuing it if called from background thread."""
    if threading.current_thread() is threading.main_thread():
        _safe_messagebox('showerror', title, message)
    else:
        _error_queue.put((title, message))


# =============================================================================
# Login Dialog
# =============================================================================

def _show_login_dialog(schema='schema1', parent=None):
    """Show login dialog for the specified schema.
    
    Args:
        schema: 'schema1' or 'schema2'
        parent: Optional parent window for dialog
    
    Returns:
        Credentials dict or None if cancelled
    """
    import ctypes
    from libs.paths import ASSETS_PATH
    import tkinter as tk
    from tkinter import messagebox, Toplevel
    
    config_path = BASE_PATH / "libs" / "config.ini"
    cfg = ConfigParser()
    cfg.read(config_path)

    # Create dialog window
    try:
        login_window = Toplevel(parent) if parent is not None else Toplevel()
    except Exception:
        login_window = Toplevel()
    
    schema_display = "Schema 1" if schema == 'schema1' else "Schema 2"
    login_window.title(f"Oracle Login - {schema_display}")
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

    # Center on screen
    screen_width = login_window.winfo_screenwidth()
    screen_height = login_window.winfo_screenheight()
    x = int((screen_width / 2) - (300 / 2))
    y = int((screen_height / 2) - (150 / 2))
    login_window.geometry(f"+{x}+{y}")

    # Register active prompt on parent for abort handling
    try:
        if parent is not None:
            setattr(parent, '_active_prompt_window', login_window)
            logger.debug(f"Registered active prompt window on parent={parent}")
    except Exception:
        pass

    # Make dialog transient and modal
    try:
        if parent is not None:
            login_window.transient(parent)
        login_window.update_idletasks()
        login_window.deiconify()
        login_window.lift()
        login_window.focus_force()
        # Set grab to make dialog modal (blocks interaction with parent)
        try:
            login_window.grab_set()
        except Exception:
            pass
        # Temporarily topmost to ensure visibility
        login_window.attributes('-topmost', True)
        login_window.after(150, lambda: login_window.attributes('-topmost', False))
    except Exception:
        pass

    frame = tk.Frame(login_window, padx=20, pady=10)
    frame.pack()

    tk.Label(frame, text="Username:").grid(row=0, column=0, sticky="e")
    username_entry = tk.Entry(frame, width=25)
    username_entry.grid(row=0, column=1)

    tk.Label(frame, text="Password:").grid(row=1, column=0, sticky="e")
    password_entry = tk.Entry(frame, show="*", width=25)
    password_entry.grid(row=1, column=1)
    
    tk.Label(frame, text="DSN:").grid(row=2, column=0, sticky="e")
    dsn_entry = tk.Entry(frame, width=25)
    dsn_entry.grid(row=2, column=1)

    # Load saved credentials for this schema if they exist
    saved_user = ""
    saved_pwd = ""
    saved_dsn = ""

    if cfg.has_section(schema):
        saved_user = cfg.get(schema, 'user', fallback='')
        saved_pwd = cfg.get(schema, 'password', fallback='')
        saved_dsn = cfg.get(schema, 'dsn', fallback='')

    username_entry.insert(0, saved_user)
    password_entry.insert(0, saved_pwd)
    dsn_entry.insert(0, saved_dsn)

    # Save password checkbox
    save_pw_var = tk.BooleanVar(value=bool(saved_pwd))
    save_pw_check = tk.Checkbutton(frame, text="Save password", variable=save_pw_var)
    save_pw_check.grid(row=3, columnspan=2, pady=(5, 5), sticky="w")
    
    # Focus password if username exists, otherwise focus username
    if saved_user:
        password_entry.focus()
    else:
        username_entry.focus()
    
    result = {}

    def submit():
        user = username_entry.get().strip()
        pwd = password_entry.get().strip()
        dsn = dsn_entry.get().strip()
        
        if user and pwd and dsn:
            result.update({
                "user": user,
                "password": pwd,
                "dsn": dsn,
                "save": save_pw_var.get()
            })

            # Save to config.ini if checkbox is checked
            if save_pw_var.get():
                # Re-read config to avoid overwriting other sections
                local_cfg = ConfigParser()
                try:
                    local_cfg.read(config_path)
                except Exception:
                    pass
                
                if not local_cfg.has_section(schema):
                    local_cfg.add_section(schema)
                
                local_cfg.set(schema, 'user', user)
                local_cfg.set(schema, 'password', pwd)
                local_cfg.set(schema, 'dsn', dsn)
                
                config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(config_path, "w", encoding="utf-8") as f:
                    local_cfg.write(f)
                
                logger.info(f"Saved credentials for {schema} to config.ini")
            else:
                # Remove section if save is unchecked
                local_cfg = ConfigParser()
                try:
                    local_cfg.read(config_path)
                except Exception:
                    pass
                
                if local_cfg.has_section(schema):
                    local_cfg.remove_section(schema)
                    with open(config_path, "w", encoding="utf-8") as f:
                        local_cfg.write(f)
                    logger.info(f"Removed saved credentials for {schema} from config.ini")

            login_window.destroy()
            _clear_active_prompt(parent)
        else:
            _safe_messagebox('showerror', "Error", "Username, password, and DSN are all required.", parent=login_window)

    def cancel():
        try:
            login_window.destroy()
        finally:
            _clear_active_prompt(parent)

    def _clear_active_prompt(parent):
        try:
            if parent is not None and hasattr(parent, '_active_prompt_window'):
                delattr(parent, '_active_prompt_window')
        except Exception:
            pass

    # Bind Enter key to submit
    login_window.bind("<Return>", lambda event: submit())

    btn_frame = tk.Frame(frame, pady=10)
    btn_frame.grid(row=4, columnspan=2)
    btn_login = tk.Button(btn_frame, text="Login", command=submit, width=10)
    btn_login.pack(side="left", padx=5)
    btn_cancel = tk.Button(btn_frame, text="Cancel", command=cancel, width=10)
    btn_cancel.pack(side="left", padx=5)

    # Apply dark mode styling to buttons if active
    def _detect_dark_mode():
        try:
            from tkinter import ttk
            bg = ttk.Style().lookup('Pane.Treeview', 'background')
            return str(bg).lower() in ('#000000', 'black')
        except Exception:
            return False

    if _detect_dark_mode():
        for btn in (btn_login, btn_cancel):
            btn.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')

    login_window.wait_window()
    return result if result else None


def prompt_credentials(schema='schema1', parent=None):
    """Prompt for credentials for the specified schema.
    
    Args:
        schema: 'schema1' or 'schema2'
        parent: Optional parent window
    
    Returns:
        Credentials dict or None if cancelled
    """
    if threading.current_thread() is threading.main_thread():
        return _show_login_dialog(schema=schema, parent=parent)

    show_error_safe("Thread Error", "Login prompt must be called from the main thread.")
    return None


# =============================================================================
# Database Connection
# =============================================================================

def get_db_connection(schema='schema1', root=None):
    """Get a database connection for the specified schema.
    
    Args:
        schema: 'schema1' or 'schema2'
        root: Optional Tkinter root window for parenting dialogs and connection tracking
    
    Returns:
        oracledb connection object or None if connection failed
    """
    try:
        oracledb.init_oracle_client()
        logger.info("Oracle client initialized (Thick mode if available)")
    except Exception:
        logger.info("Proceeding with Thin mode")
    
    try:
        creds = session.get_credentials(schema)
        
        # If no credentials in memory, prompt for login
        if not creds:
            creds = _prompt_for_credentials(schema, root)
            
            if creds:
                # Store credentials in session
                session.set_credentials(schema, creds)
                
                # Save to config if requested
                if creds.get("save", False):
                    session.save_credentials(schema)
            else:
                return None
        
        if not creds:
            logger.warning(f"No credentials available for {schema}")
            return None
        
        # Validate credentials
        user = creds.get("user", "")
        password = creds.get("password", "")
        dsn = creds.get("dsn", "")
        
        if not user or not password or not dsn:
            show_error_safe("Config Error", f"Incomplete credentials for {schema}. Please log in again.")
            # Clear invalid credentials
            session.clear_credentials(schema)
            return None
        
        # Connect to database
        conn = oracledb.connect(
            user=user,
            password=password,
            dsn=dsn,
            mode=oracledb.DEFAULT_AUTH
        )
        logger.info(f"Connected to {dsn} as {user} ({schema})")
        
        # Register connection for cleanup tracking
        if root is not None:
            session.register_connection(root, conn, schema)
        
        # Update pane label widget if registered
        session.update_label_widget(schema)
        
        return conn

    except Exception as e:
        _handle_connection_error(e)
        return None


def _prompt_for_credentials(schema, root):
    """Prompt for credentials, handling background thread scheduling.
    
    Args:
        schema: 'schema1' or 'schema2'
        root: Tkinter root window
    
    Returns:
        Credentials dict or None
    """
    # If on main thread, prompt directly
    if threading.current_thread() is threading.main_thread():
        return prompt_credentials(schema=schema, parent=root)
    
    # If on background thread with root, schedule on main thread
    if root:
        result_holder = {}
        ev = threading.Event()

        def ask_login():
            try:
                result_holder["creds"] = prompt_credentials(schema=schema, parent=root)
            finally:
                try:
                    ev.set()
                finally:
                    try:
                        abort_manager.register_prompt_event(None)
                    except Exception:
                        pass

        try:
            logger.info(f"Scheduling {schema} login prompt on main thread")
            abort_manager.register_prompt_event(ev)
            root.after(0, ask_login)
            
            # Poll with timeout so Abort can interrupt
            waited = 0.0
            timeout = 30.0
            interval = 0.2
            
            while not ev.wait(interval):
                if getattr(abort_manager, 'should_abort', False):
                    logger.info(f"Abort requested while waiting for {schema} login prompt")
                    try:
                        abort_manager.cancel_prompt_event()
                    except Exception:
                        pass
                    break
                waited += interval
                if waited >= timeout:
                    logger.warning(f"Timed out waiting for {schema} login prompt")
                    break
            
            abort_manager.register_prompt_event(None)
            return result_holder.get("creds")
            
        except Exception:
            logger.warning(f"Scheduling {schema} login prompt failed; falling back to direct prompt")
            return prompt_credentials(schema=schema, parent=root)
    
    # No root and on background thread - cannot prompt
    show_error_safe("Thread Error", "Cannot prompt for login from a background thread.")
    return None


def _handle_connection_error(e):
    """Handle database connection errors with user-friendly messages.
    
    Logs a clean single-line message for the GUI log pane and shows
    a dialog with actionable guidance. Full tracebacks are logged at
    DEBUG level only, keeping the log pane readable for end users.
    """
    error_str = str(e)
    
    # --- Authentication errors ---
    if "ORA-01017" in error_str:
        logger.error("Connection failed: Invalid username or password.")
        show_error_safe("Invalid Credentials", "Username or password is incorrect.\nPlease try again.")
    
    # --- Network / connectivity errors ---
    elif "ORA-12543" in error_str:
        logger.error("Connection failed: Database host is unreachable.")
        show_error_safe("Connection Error",
                        "Database host is unreachable.\n\n"
                        "Check your network connection or verify the database server is running.")
    elif "ORA-12170" in error_str:
        logger.error("Connection failed: Connection timed out.")
        show_error_safe("Connection Timeout",
                        "Could not connect to Oracle: Timeout.\n\n"
                        "Make sure you are connected to VPN if working remotely.")
    elif "ORA-12541" in error_str:
        logger.error("Connection failed: No listener on the database host.")
        show_error_safe("Connection Error",
                        "Database listener is not running.\n\n"
                        "The database server may be down. Contact your DBA.")
    elif "ORA-12528" in error_str:
        logger.error("Connection failed: Database is blocking new connections.")
        show_error_safe("Connection Error",
                        "Database is blocking new connections.\n\n"
                        "It may be starting up or shutting down. Try again shortly.")
    
    # --- Service / TNS resolution errors ---
    elif "ORA-12514" in error_str:
        logger.error("Connection failed: Database service not found.")
        show_error_safe("Connection Error",
                        "Database service not found.\n\n"
                        "Check the DSN (service name) in Settings.")
    elif "ORA-12154" in error_str:
        logger.error("Connection failed: Could not resolve connect identifier.")
        show_error_safe("Connection Error",
                        "Could not resolve database connect string.\n\n"
                        "Check the DSN in Settings or verify tnsnames.ora configuration.")
    
    # --- Database availability errors ---
    elif "ORA-01034" in error_str:
        logger.error("Connection failed: Oracle database is not available.")
        show_error_safe("Connection Error",
                        "Oracle database is not available.\n\n"
                        "The database may be shut down. Contact your DBA.")
    elif "ORA-12537" in error_str or "ORA-12547" in error_str:
        logger.error("Connection failed: Network connection lost.")
        show_error_safe("Connection Error",
                        "Network connection to database was lost.\n\n"
                        "Check your network connection and try again.")
    
    # --- Oracle client / driver errors ---
    elif "DPY-4026" in error_str:
        logger.error("Connection failed: Could not find tnsnames.ora.")
        show_error_safe("Configuration Error",
                        "Could not find tnsnames.ora.\n\n"
                        "Check Oracle client configuration or use a direct DSN\n"
                        "(e.g., host:port/service_name) in Settings.")
    elif "DPY-4011" in error_str:
        logger.error("Connection failed: Connection closed by database or network.")
        show_error_safe("Connection Error",
                        "Connection was closed by the database or network.\n\n"
                        "The database may have restarted. Try again.")
    elif "DPY-6005" in error_str:
        logger.error("Connection failed: Cannot connect to database.")
        show_error_safe("Connection Error",
                        "Cannot connect to database.\n\n"
                        "Verify the host, port, and service name in Settings.")
    
    # --- Generic fallback ---
    else:
        # Clean single-line error for the log pane
        logger.error(f"Connection failed: {e}")
        # Full traceback at DEBUG level for troubleshooting
        logger.debug("Connection error details:", exc_info=True)
        show_error_safe("Connection Error", f"Failed to connect to Oracle:\n{e}")
