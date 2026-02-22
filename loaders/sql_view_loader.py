import tkinter as tk
from tkinter import messagebox, scrolledtext
import logging
from libs.oracle_db_connector import get_db_connection
from libs import session
from libs import gui_utils
import ctypes
from libs.paths import ASSETS_PATH

logger = logging.getLogger(__name__)

# reference to Tk's default root if present (use getattr to avoid static-analysis issues)
_tk_default_root = getattr(tk, '_default_root', None)

def run_sql_view_loader(parent=None, on_finish=None, use_dwh=False):
    # Backwards-compatible parameter handling: the launcher may pass a parent
    # window (root) as the first argument. If a non-callable is passed, treat
    # it as parent and clear on_finish.
    if on_finish is not None and not callable(on_finish):
        parent = on_finish
        on_finish = None
    # use_dwh parameter determines whether to use schema2 (secondary) credentials
    
    # =========================================================================
    # Get credentials FIRST, before showing the tool GUI
    # =========================================================================
    schema_key = 'schema2' if use_dwh else 'schema1'
    conn = get_db_connection(schema=schema_key, root=parent)
    if not conn:
        # User cancelled or connection failed - don't show the GUI
        # Still call on_finish so the launcher can reset the status light
        if on_finish:
            try:
                on_finish()
            except Exception:
                pass
        return
    
    # Register connection for cleanup
    try:
        session.register_connection(parent if parent else _tk_default_root, conn, schema_key)
    except Exception:
        logger.debug('Failed to register connection', exc_info=True)

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

        # Remove trailing semicolon if present (common when copying from SQL editors)
        if sql_query.endswith(";"):
            sql_query = sql_query.rstrip("; \n")

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

        # Use the connection established at startup
        cursor = None
        try:
            cursor = conn.cursor()
            # Build DDL with optional clauses
            ddl = f"CREATE OR REPLACE VIEW {view_name} AS {sql_query}"
            # Add optional clauses (WITH READ ONLY and WITH CHECK OPTION are mutually exclusive in practice,
            # but Oracle will raise an error if both are specified, so we let Oracle handle validation)
            if read_only_var.get():
                ddl += " WITH READ ONLY"
            elif check_option_var.get():
                ddl += " WITH CHECK OPTION"
            cursor.execute(ddl)

            # ✅ Grant select to PUBLIC
            grant_stmt = f'GRANT SELECT ON {view_name} TO PUBLIC'
            cursor.execute(grant_stmt)

            conn.commit()
            logger.info(f"✅ View '{view_name}' created and granted SELECT to PUBLIC.")

            _safe_messagebox('showinfo', "Success", f"✅ View '{view_name}' created successfully.", dlg=builder_window)
            # Window stays open - user closes manually; on_finish called when window closes
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

    def on_cancel():
        builder_window.destroy()
        # on_finish is called in the finally block after window closes

    # Create Toplevel with optional parent so the window can be modal
    builder_window = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
    builder_window.title("SQL View Loader")
    builder_window.geometry("1300x740")
    
    # Apply theme immediately after creating dialog, before adding widgets
    gui_utils.apply_theme_to_dialog(builder_window)

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
    
    # Live theme update callback
    def _on_theme_change(theme_key):
        """Theme change callback - applies theme to all existing widgets."""
        try:
            gui_utils.apply_theme_to_existing_widgets(builder_window)
            # Re-apply pane theming for ScrolledText
            try:
                gui_utils.apply_theme_to_pane(sql_text)
            except Exception:
                pass
        except Exception:
            pass

    # Register theme callback and unregister on destroy
    try:
        gui_utils.register_theme_callback(_on_theme_change)
        
        def _on_destroy(event=None):
            if event and event.widget == builder_window:
                try:
                    gui_utils.unregister_theme_callback(_on_theme_change)
                except Exception:
                    pass
        builder_window.bind('<Destroy>', _on_destroy)
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

    def load_sql_from_file():
        """Open file dialog, load SQL content, and auto-fill view name from filename."""
        from tkinter import filedialog
        import os

        filepath = filedialog.askopenfilename(
            title="Select SQL File",
            filetypes=[("SQL Files", "*.sql"), ("All Files", "*.*")],
            parent=builder_window
        )
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                # Clear and insert content
                sql_text.delete('1.0', tk.END)
                sql_text.insert('1.0', content)

                # Auto-fill view name from filename with V_ prefix
                filename = os.path.basename(filepath)
                name_without_ext = os.path.splitext(filename)[0]
                view_name = f"V_{name_without_ext}".upper()
                view_name_entry.delete(0, tk.END)
                view_name_entry.insert(0, view_name)
            except Exception as e:
                _safe_messagebox('showerror', "Error", f"Failed to read file:\n{e}", dlg=builder_window)
                try:
                    builder_window.bell()  # System chime
                except Exception:
                    pass

    tk.Label(builder_window, text="Enter SQL to turn into a VIEW:", font=("Arial", 11, "bold")).pack(pady=(10, 5))

    # Create SQL text - theme colors are inherited from option database
    sql_text = scrolledtext.ScrolledText(builder_window, width=120, height=25, font=("Courier New", 10))
    sql_text.pack(padx=10, pady=(0, 10), fill="both", expand=False)
    # Apply pane theming explicitly for best results
    gui_utils.apply_theme_to_pane(sql_text)

    # Shared container for name row and buttons to ensure alignment
    control_container = tk.Frame(builder_window)
    control_container.pack(pady=8)

    # Name row - label outside, entry inside a fixed-width inner frame
    name_row = tk.Frame(control_container)
    name_row.pack(pady=(0, 10))

    tk.Label(name_row, text="View Name:").pack(side="left", padx=(0, 5))
    # Create the view name entry - theme colors are inherited from option database
    view_name_entry = tk.Entry(name_row, width=33)
    view_name_entry.pack(side="left")

    # Import SQL button - theme colors are inherited from option database
    btn_import_sql = tk.Button(name_row, text="Import SQL", command=load_sql_from_file, width=10)
    btn_import_sql.pack(side="left", padx=(10, 0))

    # Options row - checkboxes for view options (centered)
    options_row = tk.Frame(control_container)
    options_row.pack(pady=(0, 15))

    read_only_var = tk.BooleanVar(value=False)
    check_option_var = tk.BooleanVar(value=False)
    chk_read_only = tk.Checkbutton(options_row, text="WITH READ ONLY", variable=read_only_var)
    chk_check_option = tk.Checkbutton(options_row, text="WITH CHECK OPTION", variable=check_option_var)
    chk_read_only.pack(side="left", padx=10)
    chk_check_option.pack(side="left", padx=10)

    # Button row - inside same container for alignment
    btn_frame = tk.Frame(control_container)
    btn_frame.pack()

    # Create buttons - theme colors are inherited from option database
    btn_create = tk.Button(btn_frame, text="Create", command=on_submit, width=10)
    btn_cancel = tk.Button(btn_frame, text="Close", command=on_cancel, width=10)
    btn_create.pack(side="left", padx=10)
    btn_cancel.pack(side="left", padx=10)

    # Center on screen
    builder_window.update_idletasks()
    width = builder_window.winfo_width()
    height = builder_window.winfo_height()
    x = (builder_window.winfo_screenwidth() // 2) - (width // 2)
    y = (builder_window.winfo_screenheight() // 2) - (height // 2)
    builder_window.geometry(f"{width}x{height}+{x}+{y}")

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
        # Call on_finish callback when window is closed
        if on_finish:
            try:
                on_finish()
            except Exception:
                pass
