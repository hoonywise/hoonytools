import sys
from pathlib import Path
from libs.paths import PROJECT_PATH as BASE_PATH
import oracledb
import logging
from tkinter import Toplevel, Label, Checkbutton, IntVar, Button, simpledialog, Frame, Canvas, Scrollbar, VERTICAL, RIGHT, LEFT, Y, BOTH
from tkinter import _default_root
from libs.oracle_db_connector import get_db_connection
from libs import dwh_session

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
    center_window(win, 300, 140)
    win.resizable(False, False)

    Label(win, text="Drop from which schema?", font=("Arial", 11, "bold")).pack(pady=(15, 10))

    btn_frame = Frame(win)
    btn_frame.pack(pady=5)

    b1 = Button(btn_frame, text="User Schema", width=12, command=select_user)
    b2 = Button(btn_frame, text="DWH Schema", width=12, command=select_dwh)
    b3 = Button(btn_frame, text="Cancel", width=12, command=cancel)

    b1.pack(side="left", padx=5)
    b2.pack(side="left", padx=5)
    b3.pack(side="left", padx=5)

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
    center_window(window, 500, 600)

    Label(window, text=title).pack(pady=5)

    # Top-aligned buttons
    btn_frame = Frame(window)
    btn_frame.pack(pady=(0, 10))
    Button(btn_frame, text="OK", width=10, command=on_submit).pack(side="left", padx=20)
    Button(btn_frame, text="Cancel", width=10, command=on_cancel).pack(side="left", padx=20)

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

    # 🖱️ Enable mouse scrolling inside the canvas only while cursor is over it.
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

    window.grab_set()
    window.wait_window()
    return selected

def drop_user_tables():
    schema_choice = prompt_schema_choice()
    if schema_choice is None:
        return

    from tkinter import _default_root
    conn = get_db_connection(force_shared=(schema_choice == "dwh"), root=_default_root)

    # Register the connection with the central DWH session manager so it can
    # be cleaned up if the app/window requests it later.
    try:
        if schema_choice == 'dwh' and conn:
            dwh_session.register_connection(_default_root, conn)
    except Exception:
        logger.debug('Failed to register dwh connection', exc_info=True)

    if not conn:
        logger.error("❌ Failed to connect.")
        return

    schema = "DWH" if schema_choice == "dwh" else conn.username.upper()
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
        # Ensure in-memory DWH credentials are cleared when appropriate
        dwh_session.cleanup(_default_root)
    except Exception:
        logger.debug('DWH cleanup failed', exc_info=True)
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
    conn = get_db_connection(force_shared=True, root=_default_root)
    try:
        if conn:
            dwh_session.register_connection(_default_root, conn)
    except Exception:
        logger.debug('Failed to register dwh connection', exc_info=True)
    if not conn:
        logger.error("❌ Failed to connect to DWH.")
        return

    schema = "DWH"
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
            center_window(win, 350, 120)
            win.resizable(False, False)

            tk.Label(win, text=prompt).pack(pady=(15, 5))
            entry = tk.Entry(win, width=30)
            entry.pack(pady=5)
            entry.focus()  # ✅ Autofocus

            btn_frame = tk.Frame(win)
            btn_frame.pack(pady=5)
            tk.Button(btn_frame, text="OK", width=10, command=submit).pack(side="left", padx=5)
            tk.Button(btn_frame, text="Cancel", width=10, command=cancel).pack(side="left", padx=5)

            win.bind("<Return>", lambda event: submit())  # ✅ Enter to submit
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
            cursor.execute(f'DELETE FROM DWH."{table}" WHERE {column} = :1', [value])
            logger.info(f"🧹 Deleted from {table} where {column} = {value}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to delete from {table}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    try:
        dwh_session.cleanup(_default_root)
    except Exception:
        logger.debug('DWH cleanup failed', exc_info=True)
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
