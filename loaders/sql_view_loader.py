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

def run_sql_view_loader(on_finish=None):
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

    def on_submit():
        view_name = view_name_entry.get().strip()
        sql_query = sql_text.get("1.0", tk.END).strip()
        use_dwh = dwh_var.get()

        if not view_name:
            messagebox.showerror("Missing View Name", "❌ Please enter a view name.", parent=builder_window)
            try:
                ensure_builder_on_top()
            except Exception:
                pass
            return

        if not sql_query:
            messagebox.showerror("Missing SQL", "❌ Please paste a SQL query.", parent=builder_window)
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

            messagebox.showinfo("Success", f"✅ View '{view_name}' created successfully.", parent=builder_window)
            builder_window.destroy()
            if on_finish:
                on_finish()            
        except Exception as e:
            logger.error(f"❌ Error creating view: {e}")
            try:
                messagebox.showerror("Error", f"❌ Failed to create view:\n{e}", parent=builder_window)
            except Exception:
                # fallback if parenting fails
                try:
                    messagebox.showerror("Error", f"❌ Failed to create view:\n{e}")
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

    builder_window = tk.Toplevel()
    builder_window.title("SQL View Loader")
    builder_window.geometry("800x600")
    builder_window.grab_set()

    # Start theme polling so panes follow launcher's pane-only dark mode
    try:
        # apply initial
        try:
            if _detect_dark_from_style():
                _apply_theme(True)
            else:
                _apply_theme(False)
        except Exception:
            pass
        try:
            builder_window.after(600, _poll_theme)
        except Exception:
            pass
        # stop polling when window closed
        builder_window.bind('<Destroy>', _stop_polling)
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

    sql_text = scrolledtext.ScrolledText(builder_window, width=95, height=20, font=("Courier New", 10))
    sql_text.pack(padx=10, pady=(0, 10))

    control_frame = tk.Frame(builder_window)
    control_frame.pack(pady=5)

    tk.Label(control_frame, text="View Name:").grid(row=0, column=0, padx=(0, 5))
    view_name_entry = tk.Entry(control_frame, width=40)
    view_name_entry.grid(row=0, column=1, padx=(0, 20))

    dwh_var = tk.BooleanVar()
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
    builder_window.mainloop()
