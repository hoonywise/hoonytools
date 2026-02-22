import logging
from tkinter import Toplevel, Label, Checkbutton, IntVar, Button, Frame, Canvas, Scrollbar, VERTICAL, RIGHT, LEFT, Y, BOTH
from tkinter import _default_root
try:
    import tkinter.ttk as ttk
except Exception:
    ttk = None
from libs.oracle_db_connector import get_db_connection
from libs import session
from libs import gui_utils

logger = logging.getLogger(__name__)

# Use shared safe messagebox helper when available for consistent parenting
try:
    from loaders import safe_messagebox as _safe_messagebox
except Exception:
    def _safe_messagebox(fn_name: str, *args, dlg=None):
        try:
            from tkinter import messagebox as _messagebox
        except Exception:
            _messagebox = None
        try:
            if _messagebox is None:
                return None
            if dlg is not None:
                return getattr(_messagebox, fn_name)(*args, parent=dlg)
            return getattr(_messagebox, fn_name)(*args)
        except Exception:
            try:
                return getattr(_messagebox, fn_name)(*args)
            except Exception:
                if fn_name.startswith('ask'):
                    return False
                return None

def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width / 2) - (width / 2))
    y = int((screen_height / 2) - (height / 2))
    window.geometry(f"{width}x{height}+{x}+{y}")

# Helper to briefly make the main/root window topmost so dialogs don't get hidden
def ensure_root_on_top(root=_default_root):
    try:
        if not root:
            return
        root.lift()
        root.attributes('-topmost', True)
        root.after(120, lambda: root.attributes('-topmost', False))
    except Exception:
        pass

def prompt_schema_choice():
    result = {"choice": None}

    def select_user():
        result["choice"] = "user"
        win.destroy()

    def select_dwh():
        result["choice"] = "dwh"
        win.destroy()

    def cancel():
        result["choice"] = None
        win.destroy()

    win = Toplevel()
    win.title("Select Schema Scope")
    
    # Apply theme immediately after creating dialog
    gui_utils.apply_theme_to_dialog(win)
    
    center_window(win, 300, 140)
    win.resizable(False, False)

    Label(win, text="Drop from which schema?", font=("Arial", 11, "bold")).pack(pady=(15, 10))

    btn_frame = Frame(win)
    btn_frame.pack(pady=5)

    b1 = Button(btn_frame, text="Schema 1", width=12, command=select_user)
    b2 = Button(btn_frame, text="Schema 2", width=12, command=select_dwh)
    b3 = Button(btn_frame, text="Cancel", width=12, command=cancel)

    b1.pack(side="left", padx=5)
    b2.pack(side="left", padx=5)
    b3.pack(side="left", padx=5)

    # Live theme update callback
    def _on_theme_change(theme_key):
        try:
            gui_utils.apply_theme_to_existing_widgets(win)
        except Exception:
            pass
    
    # Register theme callback and unregister on destroy
    try:
        gui_utils.register_theme_callback(_on_theme_change)
        def _on_destroy(event=None):
            if event and event.widget == win:
                try:
                    gui_utils.unregister_theme_callback(_on_theme_change)
                except Exception:
                    pass
        win.bind('<Destroy>', _on_destroy)
    except Exception:
        pass

    # Enable keyboard focus
    b1.focus()
    b1.configure(takefocus=True)
    b2.configure(takefocus=True)
    b3.configure(takefocus=True)
    win.grab_set()
    win.wait_window()

    return result["choice"]

def select_tables_gui(tables, title="Select tables to delete from your schema:"):
    selected = []

    def on_submit():
        for table, var in vars_.items():
            if var.get():
                selected.append(table)
        window.destroy()

    def on_cancel():
        window.destroy()

    window = Toplevel()
    window.title(title)
    
    # Apply theme immediately after creating dialog
    gui_utils.apply_theme_to_dialog(window)
    
    center_window(window, 500, 600)

    Label(window, text=title).pack(pady=5)

    # Top-aligned buttons
    btn_frame = Frame(window)
    btn_frame.pack(pady=(0, 10))
    btn_ok = Button(btn_frame, text="OK", width=10, command=on_submit)
    btn_cancel = Button(btn_frame, text="Cancel", width=10, command=on_cancel)
    btn_ok.pack(side="left", padx=20)
    btn_cancel.pack(side="left", padx=20)

    # Scrollable canvas for table list
    canvas = Canvas(window)
    scrollbar = Scrollbar(window, orient=VERTICAL, command=canvas.yview)
    scrollable_frame = Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side=LEFT, fill=BOTH, expand=True)
    scrollbar.pack(side=RIGHT, fill=Y)

    # Enable mouse scrolling inside the canvas only while cursor is over it.
    # Use enter/leave to bind/unbind the global mousewheel so the callback
    # does not fire after the window is destroyed (prevents TclError).
    def _on_mousewheel(ev):
        try:
            canvas.yview_scroll(int(-1*(ev.delta/120)), "units")
        except Exception:
            # ignore if canvas is no longer available
            pass

    canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
    canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

    vars_ = {}
    for table in tables:
        var = IntVar()
        chk = Checkbutton(scrollable_frame, text=table, variable=var)
        chk.pack(anchor="w")
        vars_[table] = var

    # Live theme update callback
    def _on_theme_change(theme_key):
        try:
            gui_utils.apply_theme_to_existing_widgets(window)
        except Exception:
            pass
    
    # Register theme callback and unregister on destroy
    try:
        gui_utils.register_theme_callback(_on_theme_change)
        def _on_destroy(event=None):
            if event and event.widget == window:
                try:
                    gui_utils.unregister_theme_callback(_on_theme_change)
                except Exception:
                    pass
        window.bind('<Destroy>', _on_destroy)
    except Exception:
        pass

    window.grab_set()
    window.wait_window()
    return selected

def drop_user_tables():
    schema_choice = prompt_schema_choice()
    if schema_choice is None:
        return

    from tkinter import _default_root
    schema_key = 'schema2' if schema_choice == "dwh" else 'schema1'
    conn = get_db_connection(schema=schema_key, root=_default_root)

    # Register the connection with the session manager so it can
    # be cleaned up if the app/window requests it later.
    try:
        if conn:
            session.register_connection(_default_root, conn, schema_key)
    except Exception:
        logger.debug('Failed to register connection', exc_info=True)

    if not conn:
        logger.error("❌ Failed to connect.")
        return

    schema = conn.username.upper()
    cursor = conn.cursor()

    # Retrieve object names and types, include materialized views
    cursor.execute("""
        SELECT object_name, object_type FROM all_objects
        WHERE owner = :owner
        AND object_type IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
        ORDER BY object_name
    """, [schema])
    rows = cursor.fetchall()

    if not rows:
        try:
            _safe_messagebox('showinfo', "No Objects", f"No tables, views or materialized views found in schema {schema}", dlg=_default_root)
        except Exception:
            try:
                _safe_messagebox('showinfo', "No Objects", f"No tables, views or materialized views found in schema {schema}")
            except Exception:
                pass
        try:
            ensure_root_on_top()
        except Exception:
            pass
        return

    # Prepare display strings for the GUI and a mapping back to name/type
    # If a MATERIALIZED VIEW and a TABLE share the same name, prefer the MATERIALIZED VIEW
    mv_names = {name.upper() for name, obj_type in rows if obj_type == 'MATERIALIZED VIEW'}

    display_map = {}
    display_list = []
    for name, obj_type in rows:
        upper_name = name.upper()
        # Materialized view log objects appear as TABLEs named like MLOG$... or MLOG$_...
        if obj_type == 'TABLE' and upper_name.startswith('MLOG$'):
            # extract the base table name from the log object name
            base = name.split('$', 1)[1].lstrip('_')
            disp = f"{name} (MATERIALIZED VIEW LOG on {base})"
            if disp in display_map:
                continue
            # map as MVIEW_LOG with original mlog name and base table
            display_map[disp] = ('MVIEW_LOG', name, base)
            display_list.append(disp)
            continue

        # Skip table entry when a materialized view of the same name exists
        if obj_type == 'TABLE' and upper_name in mv_names:
            continue
        disp = f"{name} ({obj_type})"
        # avoid duplicates if any
        if disp in display_map:
            continue
        # Mark map entries for object drops as ('OBJECT', name, obj_type)
        display_map[disp] = ('OBJECT', name, obj_type)
        display_list.append(disp)

    # Additionally include primary key constraints so user can drop PKs when needed
    try:
        cursor.execute("""
            SELECT constraint_name, table_name FROM all_constraints
            WHERE owner = :owner AND constraint_type = 'P'
            ORDER BY table_name, constraint_name
        """, [schema])
        pk_rows = cursor.fetchall()
        for constraint_name, table_name in pk_rows:
            disp = f"{constraint_name} (PRIMARY KEY on {table_name})"
            if disp in display_map:
                continue
            display_map[disp] = ('CONSTRAINT', constraint_name, table_name)
            display_list.append(disp)
    except Exception:
        # If constraints query fails for any reason, continue without PK entries
        logger.debug("Could not retrieve primary key constraints; skipping PK display")

    # deterministic order
    display_list.sort()

    selected = select_tables_gui(display_list, f"Select objects to drop from schema: {schema}")
    if not selected:
        try:
            _safe_messagebox('showinfo', "Cancelled", "No objects selected.", dlg=_default_root)
        except Exception:
            try:
                _safe_messagebox('showinfo', "Cancelled", "No objects selected.")
            except Exception:
                pass
        try:
            ensure_root_on_top()
        except Exception:
            pass
        return

    try:
        confirmed = _safe_messagebox('askyesno', "Confirm", f"Drop {len(selected)} object(s) from schema {schema}?", dlg=_default_root)
    except Exception:
        confirmed = _safe_messagebox('askyesno', "Confirm", f"Drop {len(selected)} object(s) from schema {schema}?")
    if not confirmed:
        return

    for disp in selected:
        entry = display_map.get(disp)
        if not entry:
            logger.warning(f"⚠️ Unknown selection: {disp}")
            continue
        try:
            if entry[0] == 'OBJECT':
                _, name, obj_type = entry
                if obj_type == 'TABLE':
                    cursor.execute(f'DROP TABLE "{schema}"."{name}" PURGE')
                    logger.info(f"🗑️ Dropped table: {schema}.{name}")
                elif obj_type == 'VIEW':
                    cursor.execute(f'DROP VIEW "{schema}"."{name}"')
                    logger.info(f"🗑️ Dropped view: {schema}.{name}")
                elif obj_type == 'MATERIALIZED VIEW':
                    cursor.execute(f'DROP MATERIALIZED VIEW "{schema}"."{name}"')
                    logger.info(f"🗑️ Dropped materialized view: {schema}.{name}")
                else:
                    # Fallback: try drop table then view
                    try:
                        cursor.execute(f'DROP TABLE "{schema}"."{name}" PURGE')
                        logger.info(f"🗑️ Dropped (fallback table): {schema}.{name}")
                    except Exception:
                        try:
                            cursor.execute(f'DROP VIEW "{schema}"."{name}"')
                            logger.info(f"🗑️ Dropped (fallback view): {schema}.{name}")
                        except Exception as e2:
                            logger.warning(f"⚠️ Could not drop {name}: {e2}")
            elif entry[0] == 'CONSTRAINT':
                _, constraint_name, table_name = entry
                # Drop constraint by name on the owning table
                try:
                    cursor.execute(f'ALTER TABLE "{schema}"."{table_name}" DROP CONSTRAINT "{constraint_name}"')
                    logger.info(f"🗑️ Dropped primary key constraint: {schema}.{constraint_name} on {table_name}")
                except Exception as e2:
                    logger.warning(f"⚠️ Could not drop constraint {constraint_name} on {table_name}: {e2}")
            elif entry[0] == 'MVIEW_LOG':
                # Drop materialized view log
                _, mlog_name, base_table = entry
                try:
                    cursor.execute(f'DROP MATERIALIZED VIEW LOG ON "{schema}"."{base_table}"')
                    logger.info(f"🗑️ Dropped materialized view log for {schema}.{base_table} (log object: {mlog_name})")
                except Exception as e2:
                    # Some Oracle versions require dropping the log object directly or quoted names; try direct DROP TABLE as fallback
                    try:
                        cursor.execute(f'DROP MATERIALIZED VIEW LOG ON {schema}."{base_table}"')
                        logger.info(f"🗑️ Dropped materialized view log (fallback) for {schema}.{base_table}")
                    except Exception as e3:
                        logger.warning(f"⚠️ Could not drop materialized view log {mlog_name} on {base_table}: {e2} / {e3}")
            else:
                logger.warning(f"⚠️ Unhandled entry type for {disp}: {entry[0]}")
        except Exception as e:
            logger.warning(f"⚠️ Could not process {disp}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    try:
        # Ensure session connections are cleaned up appropriately
        session.close_connections(_default_root)
    except Exception:
        logger.debug('Session cleanup failed', exc_info=True)
    try:
        _safe_messagebox('showinfo', "Done", "✅ Cleanup complete.", dlg=_default_root)
    except Exception:
        try:
            _safe_messagebox('showinfo', "Done", "✅ Cleanup complete.")
        except Exception:
            pass
    try:
        ensure_root_on_top()
    except Exception:
        pass
    logger.info("✅ Cleanup complete.")

def delete_dwh_rows(table_filter, label, prompt_label, parent_window=None):
    conn = get_db_connection(schema='schema2', root=_default_root)
    try:
        if conn:
            session.register_connection(_default_root, conn, 'schema2')
    except Exception:
        logger.debug('Failed to register connection', exc_info=True)
    if not conn:
        logger.error("❌ Failed to connect to schema2.")
        return

    schema = conn.username.upper()
    cursor = conn.cursor()
    cursor.execute("SELECT table_name FROM all_tables WHERE owner = :owner AND table_name LIKE :filter ORDER BY table_name", [schema, table_filter])
    tables = [row[0] for row in cursor.fetchall()]

    if not tables:
        try:
            _safe_messagebox('showinfo', "No Tables", f"No matching tables found in schema {schema}", dlg=(parent_window if parent_window is not None else _default_root))
        except Exception:
            try:
                _safe_messagebox('showinfo', "No Tables", f"No matching tables found in schema {schema}")
            except Exception:
                pass
        try:
            ensure_root_on_top(parent_window if parent_window is not None else _default_root)
        except Exception:
            pass
        return

    selected = select_tables_gui(tables, f"Select {schema} tables to delete rows from:")
    if not selected:
        try:
            _safe_messagebox('showinfo', "Cancelled", "No tables selected.", dlg=(parent_window if parent_window is not None else _default_root))
        except Exception:
            try:
                _safe_messagebox('showinfo', "Cancelled", "No tables selected.")
            except Exception:
                pass
        try:
            ensure_root_on_top(parent_window if parent_window is not None else _default_root)
        except Exception:
            pass
        return

    # Thread-safe input dialog with optional parent window
    def ask_string_threadsafe(title, prompt, parent=None):
        import threading, queue, tkinter as tk
        q = queue.Queue()

        def ask():
            def submit():
                val = entry.get().strip()
                q.put(val)
                win.destroy()

            def cancel():
                q.put(None)
                win.destroy()

            win = tk.Toplevel(parent)
            win.title(title)
            
            # Apply theme immediately after creating dialog
            gui_utils.apply_theme_to_dialog(win)
            
            center_window(win, 350, 120)
            win.resizable(False, False)

            tk.Label(win, text=prompt).pack(pady=(15, 5))
            entry = tk.Entry(win, width=30)
            entry.pack(pady=5)
            entry.focus()  # Autofocus

            btn_frame = tk.Frame(win)
            btn_frame.pack(pady=5)
            btn_ok_dlg = tk.Button(btn_frame, text="OK", width=10, command=submit)
            btn_cancel_dlg = tk.Button(btn_frame, text="Cancel", width=10, command=cancel)
            btn_ok_dlg.pack(side="left", padx=5)
            btn_cancel_dlg.pack(side="left", padx=5)

            # Live theme update callback
            def _on_theme_change(theme_key):
                try:
                    gui_utils.apply_theme_to_existing_widgets(win)
                except Exception:
                    pass
            
            # Register theme callback and unregister on destroy
            try:
                gui_utils.register_theme_callback(_on_theme_change)
                def _on_destroy(event=None):
                    if event and event.widget == win:
                        try:
                            gui_utils.unregister_theme_callback(_on_theme_change)
                        except Exception:
                            pass
                win.bind('<Destroy>', _on_destroy)
            except Exception:
                pass

            win.bind("<Return>", lambda event: submit())  # Enter to submit
            win.grab_set()
            win.wait_window()

        if threading.current_thread() is threading.main_thread():
            ask()
        else:
            temp_root = tk.Tk()
            temp_root.withdraw()
            temp_root.after(0, ask)
            while q.empty():
                temp_root.update()
            temp_root.destroy()

        return q.get()

    value = ask_string_threadsafe(f"Enter {label}", prompt_label, parent=parent_window)

    if not value:
        try:
            parent = parent_window if parent_window is not None else _default_root
            _safe_messagebox('showwarning', "Missing Input", f"{label} is required.", dlg=parent)
        except Exception:
            try:
                _safe_messagebox('showwarning', "Missing Input", f"{label} is required.")
            except Exception:
                pass
        try:
            ensure_root_on_top(parent if parent is not None else _default_root)
        except Exception:
            pass
        return

    try:
        confirmed = _safe_messagebox('askyesno', "Confirm", f"Delete rows from {len(selected)} tables where {label} = '{value}'?", dlg=(parent_window if parent_window is not None else _default_root))
    except Exception:
        confirmed = _safe_messagebox('askyesno', "Confirm", f"Delete rows from {len(selected)} tables where {label} = '{value}'?")
    if not confirmed:
        return

    for table in selected:
        try:
            column = "ACYR" if table.startswith("SCFF_") else "GI03_TERM_ID"
            cursor.execute(f'DELETE FROM "{schema}"."{table}" WHERE "{column}" = :1', [value])
            logger.info(f"🧹 Deleted from {schema}.{table} where {column} = {value}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to delete from {table}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    try:
        session.close_connections(_default_root)
    except Exception:
        logger.debug('Session cleanup failed', exc_info=True)
    try:
        _safe_messagebox('showinfo', "Done", f"✅ Deleted rows where {label} = {value}", dlg=(parent_window if parent_window is not None else _default_root))
    except Exception:
        try:
            _safe_messagebox('showinfo', "Done", f"✅ Deleted rows where {label} = {value}")
        except Exception:
            pass
    try:
        ensure_root_on_top(parent_window if parent_window is not None else _default_root)
    except Exception:
        pass
    logger.info("✅ Row deletion complete.")


# --- New integrated drop functions for main GUI Drop buttons ---

def _drop_table_indexes(cursor, schema, table_name):
    """
    Drop all user-created indexes on a table (silently, no confirmation).
    Called automatically before dropping a table.
    """
    try:
        cursor.execute("""
            SELECT ai.index_name 
            FROM all_indexes ai
            WHERE ai.owner = :owner 
              AND ai.table_name = :table_name
              AND ai.index_name NOT LIKE 'SYS_%'
              AND ai.index_name NOT LIKE 'BIN$%'
              AND NOT EXISTS (
                SELECT 1 FROM all_constraints ac
                WHERE ac.owner = ai.owner
                  AND ac.constraint_type IN ('P', 'U')
                  AND ac.index_name = ai.index_name
              )
        """, {'owner': schema, 'table_name': table_name})
        indexes = cursor.fetchall()
        for (idx_name,) in indexes:
            try:
                cursor.execute(f'DROP INDEX "{schema}"."{idx_name}"')
                logger.info(f"Auto-dropped index: {schema}.{idx_name}")
            except Exception as e:
                logger.debug(f"Could not drop index {idx_name}: {e}")
    except Exception as e:
        logger.debug(f"Could not query indexes for {table_name}: {e}")


def _show_error_dialog(parent, obj_name, obj_type, error_msg, remaining=0):
    """
    Show error dialog with options: Stop, Skip, Force (for tables only).
    Returns: 'stop', 'skip', or 'force'
    """
    import tkinter as tk
    
    result = {'choice': 'skip'}
    
    dlg = tk.Toplevel(parent)
    dlg.title("Drop Error")
    
    # Apply theme immediately after creating dialog
    gui_utils.apply_theme_to_dialog(dlg)
    
    dlg.transient(parent)
    dlg.grab_set()
    center_window(dlg, 500, 220)
    dlg.resizable(False, False)
    
    tk.Label(dlg, text=f"Failed to drop {obj_type}: {obj_name}", font=("Arial", 11, "bold")).pack(pady=(15, 5))
    
    # Truncate long error messages
    display_error = error_msg if len(error_msg) <= 200 else error_msg[:200] + "..."
    # Use semantic red foreground for error message - will be preserved by apply_theme_to_existing_widgets
    tk.Label(dlg, text=display_error, wraplength=450, fg="red").pack(pady=5)
    
    if remaining > 0:
        # Use semantic gray foreground - will be preserved by apply_theme_to_existing_widgets
        tk.Label(dlg, text=f"{remaining} object(s) remaining", fg="gray").pack()
    
    btn_frame = tk.Frame(dlg)
    btn_frame.pack(pady=15)
    
    def stop():
        result['choice'] = 'stop'
        dlg.destroy()
    
    def skip():
        result['choice'] = 'skip'
        dlg.destroy()
    
    def force():
        result['choice'] = 'force'
        dlg.destroy()
    
    btn_stop = tk.Button(btn_frame, text="Stop", width=10, command=stop)
    btn_skip = tk.Button(btn_frame, text="Skip", width=10, command=skip)
    btn_stop.pack(side="left", padx=5)
    btn_skip.pack(side="left", padx=5)
    
    # Only show Force option for TABLEs (CASCADE CONSTRAINTS)
    if obj_type.upper() == 'TABLE':
        force_btn = tk.Button(btn_frame, text="Force Drop", width=12, command=force)
        force_btn.pack(side="left", padx=5)
        # Add tooltip explaining what Force does - use semantic gray foreground
        tk.Label(dlg, text="Force Drop: Drops table with CASCADE CONSTRAINTS", font=("Arial", 8), fg="gray").pack()

    # Live theme update callback
    def _on_theme_change(theme_key):
        try:
            gui_utils.apply_theme_to_existing_widgets(dlg)
        except Exception:
            pass
    
    # Register theme callback and unregister on destroy
    try:
        gui_utils.register_theme_callback(_on_theme_change)
        def _on_destroy(event=None):
            if event and event.widget == dlg:
                try:
                    gui_utils.unregister_theme_callback(_on_theme_change)
                except Exception:
                    pass
        dlg.bind('<Destroy>', _on_destroy)
    except Exception:
        pass
    
    dlg.wait_window()
    return result['choice']


def _sort_objects_for_drop(objects):
    """
    Sort objects so that TABLEs are dropped first (which auto-drops associated MLOGs, indexes, etc.),
    followed by other object types. This prevents errors when dependent objects are selected
    alongside their parent tables.
    
    Drop order priority:
    1. TABLEs (highest priority - drops first, auto-drops MLOGs and indexes)
    2. MATERIALIZED VIEWs
    3. VIEWs
    4. MVIEW LOGs (materialized view logs)
    5. INDEXes
    6. PRIMARY KEYs
    """
    type_order = {
        'TABLE': 0,
        'MATERIALIZED VIEW': 1,
        'VIEW': 2,
        'MVIEW LOG': 3,
        'INDEX': 4,
        'PRIMARY KEY': 5,
    }
    
    def sort_key(obj):
        obj_type = obj['type'].upper()
        return (type_order.get(obj_type, 99), obj['name'].lower())
    
    return sorted(objects, key=sort_key)


def _get_table_for_object(obj):
    """
    Extract the parent table name from an object's info field.
    Returns the table name or None if not applicable.
    """
    info = obj.get('info', '')
    if info.startswith('Table: '):
        return info[7:]  # Remove 'Table: ' prefix
    return None


def drop_objects(schema_choice, schema_name, objects, parent_window=None, on_complete=None, on_status_change=None):
    """
    Drop specified database objects. Called from main GUI Drop buttons.
    
    Args:
        schema_choice: 'user' or 'dwh' - determines connection type (schema1 or schema2)
        schema_name: The actual schema name (e.g., the connected user's username)
        objects: List of dicts with keys: 'name', 'type', 'info' (optional)
        parent_window: Parent Tk window for dialogs
        on_complete: Callback function to run after completion (e.g., refresh)
        on_status_change: Callback function(status) where status is 'busy' or 'idle'
    
    Returns:
        True if any objects were dropped, False otherwise
    """
    from tkinter import messagebox
    
    # Helper to safely call status callback
    def set_status(status):
        if on_status_change:
            try:
                on_status_change(status)
                # Force UI refresh
                if parent_window:
                    parent_window.update_idletasks()
                    parent_window.update()
            except Exception:
                pass
    
    if not objects:
        return False
    
    # Sort objects so TABLEs are dropped first (to auto-drop dependent objects)
    sorted_objects = _sort_objects_for_drop(objects)
    
    # Build a set of table names being dropped (to skip dependent objects later)
    tables_being_dropped = {
        obj['name'].upper() for obj in sorted_objects 
        if obj['type'].upper() == 'TABLE'
    }
    
    # Build confirmation message
    obj_names = [f"{o['name']} ({o['type']})" for o in sorted_objects]
    if len(obj_names) > 10:
        display_list = '\n'.join(obj_names[:10]) + f'\n... and {len(obj_names) - 10} more'
    else:
        display_list = '\n'.join(obj_names)
    
    # Confirmation dialog
    confirmed = messagebox.askyesno(
        "Confirm Drop",
        f"Are you sure you want to drop the following {len(sorted_objects)} object(s)?\n\n{display_list}",
        parent=parent_window
    )
    if not confirmed:
        return False
    
    # Get database connection
    schema_key = 'schema2' if schema_choice == 'dwh' else 'schema1'
    conn = get_db_connection(schema=schema_key, root=parent_window)
    if not conn:
        messagebox.showerror("Connection Error", "Failed to connect to database.", parent=parent_window)
        return False
    
    # Register connection for cleanup
    try:
        if conn:
            session.register_connection(parent_window, conn, schema_key)
    except Exception:
        logger.debug('Failed to register connection', exc_info=True)
    
    schema = schema_name
    cursor = conn.cursor()
    
    # Set status to busy (red indicator)
    set_status('busy')
    
    dropped_count = 0
    skipped_count = 0
    auto_skipped_count = 0  # Objects skipped because parent table was dropped
    
    for i, obj in enumerate(sorted_objects):
        obj_name = obj['name']
        obj_type = obj['type'].upper()
        remaining = len(sorted_objects) - i - 1
        
        # Check if this object's parent table is being dropped - if so, skip silently
        # (the object will be auto-dropped with the table)
        parent_table = _get_table_for_object(obj)
        if parent_table and parent_table.upper() in tables_being_dropped and obj_type != 'TABLE':
            logger.info(f"Skipping {obj_type} {obj_name} - parent table {parent_table} is being dropped")
            auto_skipped_count += 1
            continue
        
        try:
            # For TABLEs, first drop associated indexes automatically (no confirmation)
            if obj_type == 'TABLE':
                _drop_table_indexes(cursor, schema, obj_name)
            
            # Execute the drop based on object type
            if obj_type == 'TABLE':
                cursor.execute(f'DROP TABLE "{schema}"."{obj_name}" PURGE')
                logger.info(f"Dropped TABLE: {schema}.{obj_name}")
            elif obj_type == 'VIEW':
                cursor.execute(f'DROP VIEW "{schema}"."{obj_name}"')
                logger.info(f"Dropped VIEW: {schema}.{obj_name}")
            elif obj_type == 'MATERIALIZED VIEW':
                cursor.execute(f'DROP MATERIALIZED VIEW "{schema}"."{obj_name}"')
                logger.info(f"Dropped MATERIALIZED VIEW: {schema}.{obj_name}")
            elif obj_type == 'MVIEW LOG':
                # Materialized view log - need to drop on the base table
                base_table = _get_table_for_object(obj)
                if base_table:
                    cursor.execute(f'DROP MATERIALIZED VIEW LOG ON "{schema}"."{base_table}"')
                    logger.info(f"Dropped MVIEW LOG: {schema}.{obj_name} on table {base_table}")
                else:
                    logger.warning(f"Cannot drop MVIEW LOG {obj_name} - base table not found in info")
                    skipped_count += 1
                    continue
            elif obj_type == 'INDEX':
                cursor.execute(f'DROP INDEX "{schema}"."{obj_name}"')
                logger.info(f"Dropped INDEX: {schema}.{obj_name}")
            elif obj_type == 'PRIMARY KEY':
                # Get the table name from the info field
                table_name = _get_table_for_object(obj)
                if table_name:
                    cursor.execute(f'ALTER TABLE "{schema}"."{table_name}" DROP CONSTRAINT "{obj_name}"')
                    logger.info(f"Dropped PRIMARY KEY: {schema}.{obj_name} on table {table_name}")
                else:
                    logger.warning(f"Cannot drop PRIMARY KEY {obj_name} - table name not found in info")
                    skipped_count += 1
                    continue
            else:
                logger.warning(f"Unknown object type: {obj_type} for {obj_name}")
                skipped_count += 1
                continue
            
            dropped_count += 1
            
        except Exception as e:
            error_msg = str(e)
            
            # Check if error indicates object doesn't exist (already dropped with parent table)
            if 'ORA-00942' in error_msg or 'ORA-01418' in error_msg or 'does not exist' in error_msg.lower():
                logger.info(f"Object {obj_name} already dropped (likely with parent table)")
                auto_skipped_count += 1
                continue
            
            logger.warning(f"Failed to drop {obj_type} {obj_name}: {error_msg}")
            
            # Show error dialog with Stop/Skip/Force options
            response = _show_error_dialog(
                parent_window,
                obj_name,
                obj_type,
                error_msg,
                remaining=remaining
            )
            
            if response == 'stop':
                logger.info("Drop operation stopped by user")
                break
            elif response == 'force' and obj_type == 'TABLE':
                # Try CASCADE CONSTRAINTS for tables with FK references
                try:
                    cursor.execute(f'DROP TABLE "{schema}"."{obj_name}" CASCADE CONSTRAINTS PURGE')
                    dropped_count += 1
                    logger.info(f"Force dropped TABLE (CASCADE CONSTRAINTS): {schema}.{obj_name}")
                except Exception as e2:
                    skipped_count += 1
                    logger.warning(f"Force drop also failed for {obj_name}: {e2}")
            else:  # skip
                skipped_count += 1
                logger.info(f"Skipped {obj_type}: {obj_name}")
    
    # Commit changes
    try:
        conn.commit()
    except Exception as e:
        logger.warning(f"Failed to commit: {e}")
    
    # Close connection
    try:
        cursor.close()
    except Exception:
        pass
    try:
        conn.close()
    except Exception:
        pass
    
    # Cleanup session connections
    try:
        session.close_connections(parent_window, schema=schema_key)
    except Exception:
        logger.debug('Session cleanup failed', exc_info=True)
    
    # Set status back to idle (green indicator)
    set_status('idle')
    
    # Show summary
    if dropped_count > 0 or skipped_count > 0 or auto_skipped_count > 0:
        summary_msg = f"Dropped: {dropped_count}"
        if auto_skipped_count > 0:
            summary_msg += f"\nAuto-dropped with parent: {auto_skipped_count}"
        if skipped_count > 0:
            summary_msg += f"\nSkipped (errors): {skipped_count}"
        messagebox.showinfo("Drop Complete", summary_msg, parent=parent_window)
    
    # Bring main window to front
    try:
        ensure_root_on_top(parent_window)
    except Exception:
        pass
    
    # Call completion callback (e.g., refresh object list)
    if on_complete and (dropped_count > 0 or auto_skipped_count > 0):
        try:
            on_complete()
        except Exception as e:
            logger.warning(f"on_complete callback failed: {e}")
    
    logger.info(f"Drop operation complete. Dropped: {dropped_count}, Auto-skipped: {auto_skipped_count}, Skipped: {skipped_count}")
    return dropped_count > 0 or auto_skipped_count > 0
