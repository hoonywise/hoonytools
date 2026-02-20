import tkinter as tk
from tkinter import messagebox, scrolledtext
import logging
from libs.oracle_db_connector import get_db_connection
from libs import session
from libs import dwh_session
import ctypes
from libs.paths import ASSETS_PATH

logger = logging.getLogger(__name__)

# reference to Tk's default root if present (use getattr to avoid static-analysis issues)
_tk_default_root = getattr(tk, '_default_root', None)

def run_sql_view_loader(parent=None, on_finish=None):
    # Backwards-compatible parameter handling: the launcher may pass a parent
    # window (root) as the first argument. If a non-callable is passed, treat
    # it as parent and clear on_finish.
    if on_finish is not None and not callable(on_finish):
        parent = on_finish
        on_finish = None
    # Theme support for pane-only dark mode (polling fallback)
    try:
        import tkinter.ttk as _ttk
    except Exception:
        _ttk = None
    _last_dark = None
    _poll_id = None

    def _detect_dark_from_style():
        try:
            if _ttk:
                st = _ttk.Style()
                bg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
                if isinstance(bg, str) and bg.strip():
                    b = bg.strip().lower()
                    if b in ('#000000', '#000') or 'black' in b:
                        return True
        except Exception:
            pass
        return False

    def _apply_theme(dark: bool):
        # Only apply dark colors to the main SQL pane. Do not recolor frames
        # or other chrome — the launcher wants pane-only dark mode.
        try:
            if dark:
                sql_text.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff', selectbackground='#444444')
            else:
                sql_text.config(bg='white', fg='black', insertbackground='black', selectbackground='#2a6bd6')
        except Exception:
            pass

    def _poll_theme():
        nonlocal _last_dark, _poll_id
        try:
            dark = _detect_dark_from_style()
            if dark is not _last_dark:
                _last_dark = dark
                _apply_theme(dark)
        except Exception:
            pass
        try:
            _poll_id = builder_window.after(600, _poll_theme)
        except Exception:
            _poll_id = None

    def _stop_polling(event=None):
        nonlocal _poll_id
        try:
            if _poll_id:
                builder_window.after_cancel(_poll_id)
                _poll_id = None
        except Exception:
            pass

    # Use shared safe messagebox helper when available for consistent parenting
    try:
        from loaders import safe_messagebox as _safe_messagebox
    except Exception:
        def _safe_messagebox(fn_name: str, *args, dlg=None):
            try:
                if dlg is not None:
                    return getattr(messagebox, fn_name)(*args, parent=dlg)
                return getattr(messagebox, fn_name)(*args)
            except Exception:
                try:
                    return getattr(messagebox, fn_name)(*args)
                except Exception:
                    if fn_name.startswith('ask'):
                        return False
                    return None

    def on_submit():
        view_name = view_name_entry.get().strip()
        sql_query = sql_text.get("1.0", tk.END).strip()
        use_dwh = dwh_var.get()

        if not view_name:
            _safe_messagebox('showerror', "Missing View Name", "❌ Please enter a view name.", dlg=builder_window)
            try:
                ensure_builder_on_top()
            except Exception:
                pass
            return

        if not sql_query:
            _safe_messagebox('showerror', "Missing SQL", "❌ Please paste a SQL query.", dlg=builder_window)
            try:
                ensure_builder_on_top()
            except Exception:
                pass
            return

        # Choose credentials source
        conn = get_db_connection(force_shared=True) if use_dwh else get_db_connection()
        if not conn:
            return
        if use_dwh:
            # register against the global default root so cleanup can clear in-memory creds
            try:
                dwh_session.register_connection(_tk_default_root, conn)
            except Exception:
                # best-effort; don't block view creation on registration failure
                logger.debug('Failed to register dwh connection', exc_info=True)

        cursor = None
        try:
            cursor = conn.cursor()
            ddl = f"CREATE OR REPLACE VIEW {view_name} AS {sql_query}"
            cursor.execute(ddl)

            # ✅ Grant select to PUBLIC
            grant_stmt = f'GRANT SELECT ON {view_name} TO PUBLIC'
            cursor.execute(grant_stmt)

            conn.commit()
            logger.info(f"✅ View '{view_name}' created and granted SELECT to PUBLIC.")

            _safe_messagebox('showinfo', "Success", f"✅ View '{view_name}' created successfully.", dlg=builder_window)
            builder_window.destroy()
            if on_finish:
                on_finish()            
        except Exception as e:
            logger.error(f"❌ Error creating view: {e}")
            try:
                _safe_messagebox('showerror', "Error", f"❌ Failed to create view:\n{e}", dlg=builder_window)
            except Exception:
                # fallback if parenting fails
                try:
                    _safe_messagebox('showerror', "Error", f"❌ Failed to create view:\n{e}")
                except Exception:
                    pass
            try:
                ensure_builder_on_top()
            except Exception:
                pass
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.warning(f"⚠️ Failed to close cursor: {e}")

            try:
                if conn:
                    conn.close()
                    try:
                        dwh_session.cleanup(_tk_default_root)
                    except Exception:
                        logger.debug('DWH cleanup failed', exc_info=True)
            except Exception as e:
                logger.warning(f"⚠️ Failed to close connection: {e}")

    def on_cancel():
        builder_window.destroy()
        if on_finish:
            on_finish()

    # Detect initial dark mode BEFORE creating widgets to avoid a white flash
    try:
        _initial_dark = _detect_dark_from_style()
    except Exception:
        _initial_dark = False

    # Create Toplevel with optional parent so the window can be modal
    builder_window = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
    builder_window.title("SQL View Loader")
    builder_window.geometry("800x600")

    # If launched from the main launcher, make the window transient and modal
    grabbed = False
    try:
        if parent is not None:
            try:
                builder_window.transient(parent)
                builder_window.update_idletasks()
                builder_window.deiconify()
                builder_window.lift()
            except Exception:
                pass
            try:
                builder_window.grab_set()
                grabbed = True
            except Exception:
                grabbed = False
    except Exception:
        pass

    # ✅ Ensure taskbar icon and branding is preserved
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        builder_window.iconbitmap(default=icon_path)
    except Exception as e:
        logger.warning(f"⚠️ Failed to set taskbar icon: {e}")

    def ensure_builder_on_top():
        try:
            builder_window.lift()
            builder_window.attributes('-topmost', True)
            # clear topmost shortly after to avoid stealing focus permanently
            builder_window.after(120, lambda: builder_window.attributes('-topmost', False))
        except Exception:
            pass

    tk.Label(builder_window, text="Enter SQL to turn into a view:", font=("Arial", 11, "bold")).pack(pady=(10, 5))

    # Create SQL text with initial theme to avoid visible white -> black flip
    try:
        if _initial_dark:
            sql_text = scrolledtext.ScrolledText(builder_window, width=95, height=20, font=("Courier New", 10), bg='#000000', fg='#ffffff', insertbackground='#ffffff', selectbackground='#444444')
        else:
            sql_text = scrolledtext.ScrolledText(builder_window, width=95, height=20, font=("Courier New", 10), bg='white', fg='black', insertbackground='black', selectbackground='#2a6bd6')
    except Exception:
        sql_text = scrolledtext.ScrolledText(builder_window, width=95, height=20, font=("Courier New", 10))
    sql_text.pack(padx=10, pady=(0, 10))

    control_frame = tk.Frame(builder_window)
    control_frame.pack(pady=5)

    tk.Label(control_frame, text="View Name:").grid(row=0, column=0, padx=(0, 5))
    # Create the view name entry with initial theme to avoid flash
    try:
        if _initial_dark:
            view_name_entry = tk.Entry(control_frame, width=40, bg='#000000', fg='#ffffff', insertbackground='#ffffff')
        else:
            view_name_entry = tk.Entry(control_frame, width=40)
    except Exception:
        view_name_entry = tk.Entry(control_frame, width=40)
    view_name_entry.grid(row=0, column=1, padx=(0, 20))

    dwh_var = tk.BooleanVar()
    # Keep checkbox/frames in default (light) chrome; avoid changing their bg so chrome stays consistent
    dwh_checkbox = tk.Checkbutton(control_frame, text="Load to DWH schema (shared login)", variable=dwh_var)
    dwh_checkbox.grid(row=0, column=2)

    btn_frame = tk.Frame(builder_window)
    btn_frame.pack(pady=15)

    tk.Button(btn_frame, text="Create View", command=on_submit, width=15).pack(side="left", padx=10)
    tk.Button(btn_frame, text="Cancel", command=on_cancel, width=10).pack(side="left", padx=10)

    # Center on screen
    builder_window.update_idletasks()
    width = builder_window.winfo_width()
    height = builder_window.winfo_height()
    x = (builder_window.winfo_screenwidth() // 2) - (width // 2)
    y = (builder_window.winfo_screenheight() // 2) - (height // 2)
    builder_window.geometry(f"{width}x{height}+{x}+{y}")

    # Register theme callback with parent when available; otherwise fall back to polling
    def _theme_cb(enable_dark: bool):
        try:
            _apply_theme(bool(enable_dark))
        except Exception:
            pass

    try:
        if parent is not None and hasattr(parent, 'register_theme_callback'):
            try:
                parent.register_theme_callback(_theme_cb)
                # ensure we unregister when this window is destroyed
                def _on_destroy(event=None):
                    try:
                        if parent and hasattr(parent, 'unregister_theme_callback'):
                            parent.unregister_theme_callback(_theme_cb)
                    except Exception:
                        pass
                try:
                    builder_window.bind('<Destroy>', _on_destroy)
                except Exception:
                    pass
                # Apply current style immediately
                try:
                    _apply_theme(_detect_dark_from_style())
                except Exception:
                    pass
            except Exception:
                pass
        else:
            # Polling fallback: start polling to pick up subsequent theme changes
            try:
                builder_window.after(600, _poll_theme)
            except Exception:
                pass
            try:
                builder_window.bind('<Destroy>', _stop_polling)
            except Exception:
                pass
    except Exception:
        pass

    # Run modal or standalone mainloop depending on whether a parent was provided
    try:
        if parent is not None:
            try:
                builder_window.wait_window()
            except Exception:
                pass
        else:
            try:
                builder_window.mainloop()
            except KeyboardInterrupt:
                try:
                    if grabbed:
                        try:
                            builder_window.grab_release()
                        except Exception:
                            pass
                    builder_window.destroy()
                except Exception:
                    pass
    finally:
        # Ensure we release modal grab if we set it
        try:
            if grabbed:
                try:
                    builder_window.grab_release()
                except Exception:
                    pass
        except Exception:
            pass
