import os
import pandas as pd
import oracledb
import logging
import re
import time
import threading
import queue as _queue
import tkinter as tk
from tkinter import Tk, filedialog, simpledialog, Toplevel, Label, Checkbutton, IntVar, Button, Entry
import sys
from pathlib import Path
from libs.table_utils import create_index_if_columns_exist
from typing import Any, Dict

# Add path to shared connector
from libs.paths import PROJECT_PATH as base_path

# Logging setup
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

from libs.oracle_db_connector import get_db_connection
from libs import abort_manager
from libs import session
from libs import gui_utils

def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    x = int((screen_width / 2) - (width / 2))
    y = int((screen_height / 2) - (height / 2))
    window.geometry(f"{width}x{height}+{x}+{y}")


def call_ui(ui_root, func, *args, **kwargs):
    """Run a UI callable on the Tk main thread and return its result.

    If already on the main thread the function is invoked directly. When called
    from a background thread this schedules the callable via parent.after(0, ...)
    and waits for the result using a Queue. The parent argument should be the
    launcher's root (or a valid Tk widget).
    """
    # Fast path when already on main thread
    try:
        if threading.current_thread() == threading.main_thread():
            return func(*args, **kwargs)
    except Exception:
        # If anything odd happens, fall back to scheduling
        pass

    q = _queue.Queue()
    # If called from a background thread, register a prompt Event so the
    # launcher abort handler can wake this worker if the user clicks Abort
    # while a main-thread prompt is being shown.
    ev = None

    def _run():
        try:
            res = func(*args, **kwargs)
            q.put((True, res))
        except Exception as e:
            q.put((False, e))

    try:
        # ui_root may be None if caller didn't provide a root; try to schedule
        # on the provided ui_root if possible, otherwise run directly.
        if ui_root is not None and hasattr(ui_root, 'after'):
            # register a prompt event so abort can cancel this wait
            try:
                ev = threading.Event()
                abort_manager.register_prompt_event(ev)
            except Exception:
                ev = None
            try:
                ui_root.after(0, _run)
            except Exception:
                # scheduling failed, run the function directly
                _run()
        else:
            # no valid ui_root to schedule on; run directly (best-effort)
            _run()
    except Exception:
        # scheduling failed, run the function directly
        _run()

    # Wait for result but poll so we can respond to abort requests.
    try:
        from queue import Empty
        while True:
            try:
                ok, payload = q.get(timeout=0.2)
                break
            except Empty:
                # If abort was requested, stop waiting and raise to caller
                try:
                    if getattr(abort_manager, 'should_abort', False):
                        raise RuntimeError("UI prompt cancelled due to abort")
                except Exception:
                    pass
                continue
        if ok:
            return payload
        raise payload
    finally:
        # Clear any registered prompt event
        try:
            abort_manager.register_prompt_event(None)
        except Exception:
            pass

def prompt_schema_choice(parent=None):
    result: Dict[str, Any] = {"choice": None}

    def select_user():
        result["choice"] = "user"
        win.destroy()

    def select_dwh():
        result["choice"] = "dwh"
        win.destroy()

    def cancel():
        result["choice"] = None
        win.destroy()

    # Parent the dialog when possible so it appears above the launcher
    try:
        win = Toplevel(parent) if parent is not None else Toplevel()
    except Exception:
        win = Toplevel()
    win.title("Select Schema Scope")
    
    # Apply theme immediately after creating dialog
    gui_utils.apply_theme_to_dialog(win)
    
    center_window(win, 300, 140)
    win.resizable(False, False)

    Label(win, text="Load to which schema?", font=("Arial", 11, "bold")).pack(pady=(15, 10))

    from tkinter import Frame  # Ensure Frame is imported

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

    b1.focus()
    b1.configure(takefocus=True)
    b2.configure(takefocus=True)
    b3.configure(takefocus=True)

    try:
        win.grab_set()
    except Exception as e:
        # On some platforms or when another app has an active grab, grab_set may fail.
        # Fall back to a non-modal dialog and log the situation.
        logger.warning(f"Could not grab focus for schema choice dialog: {e}")
    win.wait_window()

    return result["choice"]

# ==== CLEAN COLUMN NAMES TO BE ORACLE-COMPATIBLE ====
def clean_column_names(df):
    df.columns = [col.strip().replace(' ', '_').replace('-', '_').replace('.', '_').upper() for col in df.columns]
    return df

# ==== DROP TABLE IF EXISTS ====
def drop_table_if_exists(cursor, schema, table_name):
    try:
        cursor.execute("""
            SELECT table_name FROM all_tables 
            WHERE table_name = :1 AND owner = :2
        """, [table_name.upper(), schema])
        if cursor.fetchone():
            cursor.execute(f'DROP TABLE {schema}.{table_name.upper()} PURGE')
            logger.info(f"🗑️ Dropped existing table {schema}.{table_name}")
    except Exception as e:
        logger.warning(f"⚠️ Could not drop table {table_name}: {e}")

# ==== CREATE TABLE ====
def create_table(cursor, schema, table_name, df, col_sizes=None):
    """Create a new Oracle table from a DataFrame's column list.

    Parameters
    ----------
    col_sizes : dict or None
        Optional mapping of column_name -> VARCHAR2 size (int).
        When provided, each column uses the specified size instead of
        the default 4000.
    """
    def _col_def(col):
        if col_sizes and col.upper() in {k.upper() for k in col_sizes}:
            # Find the matching key (case-insensitive)
            for k, v in col_sizes.items():
                if k.upper() == col.upper():
                    return f'"{col}" VARCHAR2({v})'
        return f'"{col}" VARCHAR2(4000)'

    cols_sql = ', '.join([_col_def(col) for col in df.columns])
    cursor.execute(f'CREATE TABLE {schema}.{table_name.upper()} ({cols_sql})')
    cursor.execute(f'GRANT SELECT ON {schema}.{table_name.upper()} TO PUBLIC')
    # Register the fully-qualified table name so abort cleanup can drop it
    # even if the connection/cursor are gone.
    try:
        abort_manager.register_created_table(table_name, schema=schema)
    except Exception:
        # Best-effort registration; do not fail table creation if this errors.
        logger.debug("Failed to register created table with abort_manager")
    logger.info(f"✅ Created table and granted SELECT to PUBLIC: {schema}.{table_name}")

# ==== INSERT DATA ====
def insert_data(cursor, schema, table_name, df, conn):
    columns = ', '.join([f'"{col}"' for col in df.columns])
    values = ', '.join([f':{i+1}' for i in range(len(df.columns))])
    insert_sql = f'INSERT INTO {schema}.{table_name.upper()} ({columns}) VALUES ({values})'

    logger.info(f"📊 Preparing to insert {len(df)} rows into {schema}.{table_name}")

    success_count = 0
    fail_count = 0

    for i, row in df.iterrows():
        if abort_manager.should_abort:
            # Let the abort manager perform cleanup once. Do not attempt
            # to call cleanup_on_abort again from outer exception handlers.
            try:
                abort_manager.cleanup_on_abort(conn, cursor)
            except Exception:
                logger.exception("Error during cleanup_on_abort in insert_data")
            return False
        try:
            cursor.execute(insert_sql, tuple(row))
            success_count += 1
        except Exception as e:
            logger.warning(f"❌ Failed to insert row {i+1}: {e}")
            fail_count += 1

    logger.info(f"✅ Inserted {success_count} rows into {schema}.{table_name} ({fail_count} failed)")
    return True


# ==== NEW: helpers for append/replace/upsert flows ====
def get_table_columns(cursor, schema, table_name):
    cursor.execute("""
        SELECT column_name, data_type, nullable FROM all_tab_columns
        WHERE owner = :1 AND table_name = :2
        ORDER BY column_id
    """, [schema.upper(), table_name.upper()])
    return [row[0] for row in cursor.fetchall()]


def show_load_mode_dialog(parent, schema, table_name, df_columns):
    """Block-button dialog: Append | Replace | Upsert | Preview | Cancel
    Returns same dict structure as previous implementations, or None.
    """
    from tkinter import Toplevel, Frame, Button, Label
    from tkinter import messagebox, simpledialog

    logger.info(f"Opening button-based load mode dialog for {schema}.{table_name}")

    # Try to attach to parent if visible
    parent_win = None
    try:
        if parent is not None and getattr(parent, 'winfo_viewable', lambda: False)():
            parent_win = parent
    except Exception:
        parent_win = None

    win = Toplevel(parent_win) if parent_win is not None else Toplevel()
    try:
        win.transient(parent_win)
    except Exception:
        pass
    win.title(f"Load Mode: {schema}.{table_name}")
    
    # Apply theme immediately after creating dialog
    gui_utils.apply_theme_to_dialog(win)
    
    center_window(win, 420, 320)

    Label(win, text=f"Choose how to load into {schema}.{table_name}", font=("Arial", 10, "bold")).pack(pady=(8, 6))

    btn_frame = Frame(win)
    btn_frame.pack(fill="both", expand=True, padx=12, pady=6)

    result = {"mode": None, "preview_sql": False}
    from tkinter import IntVar
    preview_var = IntVar(value=0)  # default unchecked

    def do_close():
        try:
            win.destroy()
        except Exception:
            pass

    def on_append():
        result.update({"mode": "append", "preview_sql": bool(preview_var.get())})
        do_close()

    def on_replace():
        # For Replace we no longer collect per-column choices.
        # Replace behavior mirrors Append but is destructive (clears target first).
        result.update({"mode": "replace", "preview_sql": bool(preview_var.get())})
        do_close()

    def on_upsert():
        # Close the load-mode dialog and collect upsert options after it returns
        result.update({"mode": "upsert", "preview_sql": bool(preview_var.get())})
        do_close()

    def on_preview():
        # legacy: keep an explicit preview option but it will be translated by caller
        result.update({"mode": "preview", "preview_sql": True})
        do_close()

    # Buttons
    b_append = Button(btn_frame, text="Append", width=36, height=2, command=on_append)
    b_replace = Button(btn_frame, text="Replace", width=36, height=2, command=on_replace)
    b_upsert = Button(btn_frame, text="Upsert (MERGE)", width=36, height=2, command=on_upsert)
    b_preview = Button(btn_frame, text="Preview (dry-run)", width=36, height=2, command=on_preview)
    b_append.pack(pady=6)
    b_replace.pack(pady=6)
    b_upsert.pack(pady=6)
    b_preview.pack(pady=6)

    from tkinter import Frame as _Frame
    footer = _Frame(win)
    footer.pack(fill="x", padx=8, pady=(4,10))
    # Preview SQL checkbox (default checked)
    try:
        from tkinter import Checkbutton
        chk = Checkbutton(footer, text="Preview SQL (show formatted SQL; do not run automatically)", variable=preview_var)
        chk.pack(side="left", padx=6)
    except Exception:
        pass
    Button(footer, text="Cancel", width=12, command=do_close).pack(side="right")

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

    try:
        win.lift(); win.focus_force()
    except Exception:
        pass
    try:
        win.grab_set()
    except Exception:
        logger.info("Could not grab focus for load-mode dialog (non-fatal).")

    win.wait_window()
    return result if result.get("mode") else None


def show_replace_column_selector(parent, cols):
    # Deprecated: replace no longer uses per-column selectors.
    # Keep function for compatibility but do not open any Toplevel UI.
    logger.info("show_replace_column_selector called, but per-column replace is disabled. Returning None.")
    return None


def show_key_selector(parent, cols):
    # simple key selector used for upsert
    result = {"key_columns": []}

    def on_ok():
        result["key_columns"] = [c for i, c in enumerate(cols) if vars_[i].get()]
        if not result["key_columns"]:
            from tkinter import messagebox
            _safe_messagebox('showwarning', "Key Required", "Please select at least one key column for MERGE.")
            return
        win.destroy()

    def on_cancel():
        result.clear()
        win.destroy()

    from tkinter import Frame, simpledialog, messagebox
    logger.info(f"Opening key selector for {len(cols)} columns")
    parent_win = None
    try:
        if parent is not None and getattr(parent, 'winfo_viewable', lambda: False)():
            parent_win = parent
    except Exception:
        parent_win = None

    try:
        win = Toplevel(parent_win) if parent_win is not None else Toplevel()
        try:
            win.transient(parent_win)
        except Exception:
            pass
        
        # Apply theme immediately after creating dialog
        gui_utils.apply_theme_to_dialog(win)
        
        try:
            try:
                win.attributes('-topmost', True)
            except Exception:
                pass
            win.deiconify(); win.lift(); win.update(); win.wait_visibility(); win.focus_force()
            try:
                win.after(150, lambda: win.attributes('-topmost', False))
            except Exception:
                try:
                    win.attributes('-topmost', False)
                except Exception:
                    pass
        except Exception:
            pass
        win.title("Select key columns for MERGE")
        center_window(win, 420, 420)
    except Exception as e:
        logger.exception(f"Could not open key-selector Toplevel, falling back to simpledialog: {e}")
        keys = simpledialog.askstring("Key Columns", f"Enter key columns (comma-separated) from: {', '.join(cols)}")
        if keys is None:
            return None
        key_list = [c.strip().upper() for c in keys.split(',') if c.strip()]
        invalid = [c for c in key_list if c not in [x.upper() for x in cols]]
        if invalid:
            _safe_messagebox('showerror', "Invalid Columns", f"Invalid key columns: {invalid}")
            return None
        return {"key_columns": key_list}

    Label(win, text="Select key column(s):", font=("Arial", 10, "bold")).pack(pady=(8, 4))
    frame1 = Frame(win)
    frame1.pack(fill="both", expand=True, padx=10)

    vars_ = []
    for c in cols:
        var = IntVar(value=0)
        chk = Checkbutton(frame1, text=c, variable=var)
        chk.pack(anchor="w")
        vars_.append(var)

    btn_frame = Frame(win)
    btn_frame.pack(pady=8)
    Button(btn_frame, text="OK", width=10, command=on_ok).pack(side="left", padx=8)
    Button(btn_frame, text="Cancel", width=10, command=on_cancel).pack(side="left", padx=8)

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

    try:
        win.grab_set()
    except Exception as e:
        logger.warning(f"Could not grab focus for key selector: {e}")
    win.wait_window()
    return result if result.get("key_columns") else None


def show_upsert_selector(parent, cols):
    """Select key columns and which columns to update for Upsert.

    Returns dict {"key_columns": [...], "update_columns": [...]} or None if cancelled.
    """
    from tkinter import Frame, simpledialog, messagebox
    logger.info(f"Opening upsert selector for {len(cols)} columns")

    # Try a simple standalone Toplevel first
    try:
        win = Toplevel()
        
        # Apply theme immediately after creating dialog
        gui_utils.apply_theme_to_dialog(win)
        
        try:
            win.attributes('-topmost', True)
        except Exception:
            pass
        try:
            win.deiconify(); win.lift(); win.update()
        except Exception:
            pass
        win.title("Upsert: select key and update columns")
        center_window(win, 600, 480)

        # Create a scrollable area for the column checklists
        from tkinter import Canvas, Scrollbar, VERTICAL, RIGHT, LEFT, BOTH, Y
        container = Frame(win)
        container.pack(fill="both", expand=True)

        canvas = Canvas(container)
        scrollbar = Scrollbar(container, orient=VERTICAL, command=canvas.yview)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        scrollable_frame = Frame(canvas)
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_config(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        scrollable_frame.bind("<Configure>", _on_config)

        # Keys section
        Label(scrollable_frame, text="Select key column(s):", font=("Arial", 10, "bold")).pack(pady=(8, 4))
        frame_keys = Frame(scrollable_frame)
        frame_keys.pack(fill="both", padx=10)
        key_vars = []
        for i, c in enumerate(cols):
            var = IntVar(value=0)
            chk = Checkbutton(frame_keys, text=c, variable=var)
            chk.pack(anchor="w")
            key_vars.append(var)

        Label(scrollable_frame, text="Select columns to UPDATE from uploaded data:", font=("Arial", 9, "bold")).pack(pady=(8, 4))
        frame_updates = Frame(scrollable_frame)
        frame_updates.pack(fill="both", expand=True, padx=10)
        update_vars = []
        update_chks = []
        for i, c in enumerate(cols):
            var = IntVar(value=1)
            chk = Checkbutton(frame_updates, text=c, variable=var)
            chk.pack(anchor="w")
            update_vars.append(var)
            update_chks.append(chk)

        # If a column is selected as a key, it cannot be updated by MERGE (Oracle restriction).
        # Wire key checkbox changes to disable the corresponding update checkbox.
        def make_key_handler(idx):
            def _handler(*_args):
                try:
                    if key_vars[idx].get():
                        # uncheck and disable update
                        try:
                            update_vars[idx].set(0)
                        except Exception:
                            pass
                        try:
                            update_chks[idx].config(state='disabled')
                        except Exception:
                            pass
                    else:
                        # enable update checkbox and default to checked
                        try:
                            update_chks[idx].config(state='normal')
                        except Exception:
                            pass
                        try:
                            update_vars[idx].set(1)
                        except Exception:
                            pass
                except Exception:
                    pass
            return _handler

        for idx in range(len(cols)):
            try:
                key_vars[idx].trace_add('write', make_key_handler(idx))
            except Exception:
                try:
                    # older tkinter
                    key_vars[idx].trace('w', make_key_handler(idx))
                except Exception:
                    pass

        # Footer with buttons (kept visible)
        btn_frame = Frame(win)
        btn_frame.pack(fill="x", pady=6)

        nonlocal_result = {"key_columns": [], "update_columns": []}

        def on_ok():
            keys = [c for i, c in enumerate(cols) if key_vars[i].get()]
            ups = [c for i, c in enumerate(cols) if update_vars[i].get()]
            if not keys:
                _safe_messagebox('showwarning', "Key Required", "Please select at least one key column for MERGE.")
                return
            nonlocal_result["key_columns"] = keys
            nonlocal_result["update_columns"] = ups
            try:
                win.destroy()
            except Exception:
                pass

        def on_cancel():
            nonlocal_result.clear()
            try:
                win.destroy()
            except Exception:
                pass

        # Center the buttons and place Cancel to the left of OK (swapped order)
        btn_inner = Frame(btn_frame)
        btn_inner.pack()
        Button(btn_inner, text="OK", width=10, command=on_ok).pack(side="left", padx=8)
        Button(btn_inner, text="Cancel", width=10, command=on_cancel).pack(side="left")

        # Mouse wheel support
        try:
            canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        except Exception:
            pass

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

        try:
            win.grab_set()
        except Exception as e:
            logger.warning(f"Could not grab focus for upsert selector: {e}")
        win.wait_window()
        return nonlocal_result if nonlocal_result.get("key_columns") else None
    except Exception as e:
        logger.exception(f"Could not open upsert Toplevel, falling back to simpledialog: {e}")
        keys = simpledialog.askstring("Key Columns", f"Enter key columns (comma-separated) from: {', '.join(cols)}")
        if keys is None:
            return None
        key_list = [c.strip().upper() for c in keys.split(',') if c.strip()]
        updates = simpledialog.askstring("Update Columns", f"Enter columns to UPDATE (comma-separated) from: {', '.join(cols)}")
        if updates is None:
            return None
        upd_list = [c.strip().upper() for c in updates.split(',') if c.strip()]
        invalid_keys = [c for c in key_list if c not in [x.upper() for x in cols]]
        invalid_upd = [c for c in upd_list if c not in [x.upper() for x in cols]]
        if invalid_keys or invalid_upd:
            _safe_messagebox('showerror', "Invalid Columns", f"Invalid columns selected. Keys invalid: {invalid_keys}; Updates invalid: {invalid_upd}")
            return None
        return {"key_columns": key_list, "update_columns": upd_list}


def create_staging_table_from_df(cursor, schema, staging_table, df):
    cols_sql = ', '.join([f'"{col}" VARCHAR2(4000)' for col in df.columns])
    cursor.execute(f'CREATE TABLE {schema}.{staging_table} ({cols_sql})')
    # Register staging table with abort_manager so abort cleanup can drop it
    try:
        abort_manager.register_created_table(staging_table, schema=schema)
    except Exception:
        logger.debug("Failed to register staging table with abort_manager")


def bulk_insert_chunked(conn, cursor, schema, table_name, df, chunk_size=500, insert_columns=None):
    """Bulk insert dataframe into target table.
    If insert_columns is provided (list of column names), only those columns are inserted and
    their order is used for the VALUES binding.
    """
    if insert_columns is None:
        cols_list = list(df.columns)
    else:
        # preserve the provided order
        cols_list = list(insert_columns)

    cols = [f'"{c}"' for c in cols_list]
    columns_sql = ', '.join(cols)
    values_placeholders = ', '.join([f':{i+1}' for i in range(len(cols_list))])
    insert_sql = f'INSERT INTO {schema}.{table_name} ({columns_sql}) VALUES ({values_placeholders})'

    total = len(df)
    inserted = 0

    # prepare data rows in the right column order
    if insert_columns is None:
        data = [tuple(x) for x in df.values.tolist()]
    else:
        data = []
        for _, row in df.iterrows():
            data.append(tuple(row[col] for col in cols_list))

    for i in range(0, total, chunk_size):
        # Check for abort request between chunks so we can stop cooperatively
        if getattr(abort_manager, 'should_abort', False):
            logger.info("⛔ Abort detected during bulk insert. Running cleanup_on_abort and returning.")
            try:
                abort_manager.cleanup_on_abort(conn, cursor)
            except Exception:
                logger.exception("Error during cleanup_on_abort")
            return inserted

        chunk = data[i:i+chunk_size]
        try:
            cursor.executemany(insert_sql, chunk)
            try:
                conn.commit()
            except Exception:
                # Some drivers may not like commit in tight loop; ignore commit failures here and continue
                pass
            inserted += len(chunk)
        except Exception as e:
            logger.warning(f"Bulk insert failed at chunk starting {i}: {e}")
            for row in chunk:
                # Check abort between fallback row inserts so abort is responsive
                if getattr(abort_manager, 'should_abort', False):
                    try:
                        abort_manager.cleanup_on_abort(conn, cursor)
                    except Exception:
                        logger.exception("Error during cleanup_on_abort in fallback row loop")
                    return inserted
                try:
                    cursor.execute(insert_sql, row)
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    inserted += 1
                except Exception as e2:
                    logger.warning(f"Row insert failed during fallback: {e2}")
    return inserted


def merge_from_staging(cursor, schema, target_table, staging_table, key_cols, update_cols):
    # Deprecated simple merge. Use merge_with_checks instead.
    raise RuntimeError("merge_from_staging is deprecated; use merge_with_checks(conn, cursor, ...) instead")


def _quote_ident(name):
    return f'"{name.upper()}"'


def format_sql_for_display(sql: str) -> str:
    """Lightweight SQL formatter for MERGE preview.

    - Breaks SQL at major MERGE clauses for readability.
    - Splits long parenthesized column lists onto multiple indented lines.
    This is intentionally simple (no full SQL parser) but improves visibility
    in the preview window.
    """
    if not sql:
        return sql

    # Normalize whitespace
    s = re.sub(r"\s+", " ", sql).strip()

    # Insert line breaks before key MERGE clauses (case-insensitive)
    clauses = [
        r"MERGE INTO",
        r"USING",
        r"ON \(",
        r"WHEN MATCHED THEN UPDATE SET",
        r"WHEN MATCHED THEN UPDATE",
        r"WHEN MATCHED THEN",
        r"WHEN NOT MATCHED THEN INSERT",
        r"VALUES \(",
    ]
    for cl in clauses:
        s = re.sub(rf"(?i)\b{cl}\b", lambda m: "\n" + m.group(0).upper(), s)

    # Break comma-separated lists inside parentheses (useful for INSERT columns/values)
    def _break_list(match):
        inner = match.group(1)
        parts = [p.strip() for p in inner.split(',')]
        if len(parts) <= 1:
            return f"({inner})"
        joined = ",\n        ".join(parts)
        return f"(\n        {joined}\n    )"

    # Apply to INSERT (...) and VALUES (...)
    s = re.sub(r"\(\s*([^\)]+?)\s*\)", _break_list, s)

    # Tidy up spacing around parentheses and commas
    s = re.sub(r"\s+,\s+", ", ", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)

    return s.strip()


def show_sql_preview(parent, title, summary, sql):
    from tkinter import Toplevel, Text, Scrollbar, RIGHT, Y, BOTH, END, Label, Button, Frame, HORIZONTAL, X
    from tkinter import filedialog, messagebox

    pv = Toplevel(parent) if parent is not None else Toplevel()
    try:
        pv.transient(parent)
    except Exception:
        pass
    pv.title(title)
    
    # Apply theme immediately after creating dialog
    gui_utils.apply_theme_to_dialog(pv)
    
    # Withdraw briefly so window manager does not place it at a default offset
    try:
        pv.withdraw()
    except Exception:
        pass
    # Ensure geometry is calculated and then center on the screen
    try:
        pv.update_idletasks()
    except Exception:
        pass
    center_window(pv, 720, 520)
    try:
        pv.deiconify()
    except Exception:
        pass

    # Build widgets
    Label(pv, text=f"{summary}", font=("Arial", 10, "bold")).pack(pady=6)

    txt_frame = Frame(pv)
    txt_frame.pack(fill=BOTH, expand=True, padx=8, pady=6)
    vsb = Scrollbar(txt_frame, orient='vertical')
    vsb.pack(side=RIGHT, fill=Y)
    hsb = Scrollbar(txt_frame, orient=HORIZONTAL)
    hsb.pack(side='bottom', fill=X)
    txt = Text(txt_frame, wrap='none', yscrollcommand=vsb.set, xscrollcommand=hsb.set,
               font=("Courier New", 10))
    txt.pack(fill=BOTH, expand=True)
    vsb.config(command=txt.yview)
    hsb.config(command=txt.xview)
    formatted = format_sql_for_display(sql)
    txt.insert(END, formatted)
    txt.config(state='disabled')
    
    # Apply pane theme to the text widget explicitly
    gui_utils.apply_theme_to_pane(txt)

    btns = Frame(pv)
    btns.pack(pady=8)
    confirmed = {"val": False}

    def _do_copy():
        try:
            pv.clipboard_clear()
            pv.clipboard_append(formatted)
            # ensure clipboard content persists after window closes
            pv.update()
            try:
                _safe_messagebox('showinfo', "Copied", "SQL copied to clipboard.", dlg=pv)
            except Exception:
                logger.info("SQL copied to clipboard.")
        except Exception as e:
            logger.warning(f"Could not copy SQL to clipboard: {e}")

    def _do_save():
        try:
            fname = filedialog.asksaveasfilename(parent=pv, defaultextension='.sql', filetypes=[('SQL file', '*.sql'), ('Text file', '*.txt')], title='Save SQL to file')
            if not fname:
                return
            with open(fname, 'w', encoding='utf-8') as fh:
                fh.write(formatted)
            try:
                _safe_messagebox('showinfo', "Saved", f"SQL saved to: {fname}", dlg=pv)
            except Exception:
                logger.info(f"SQL saved to: {fname}")
        except Exception as e:
            logger.error(f"Failed to save SQL to file: {e}")

    def _do_exec():
        confirmed["val"] = True
        try:
            try:
                pv.grab_release()
            except Exception:
                pass
            pv.destroy()
        except Exception:
            pass

    def _do_cancel():
        confirmed["val"] = False
        try:
            try:
                pv.grab_release()
            except Exception:
                pass
            pv.destroy()
        except Exception:
            pass

    Button(btns, text="Execute", width=12, command=_do_exec).pack(side="left", padx=6)
    Button(btns, text="Copy SQL", width=12, command=_do_copy).pack(side="left", padx=6)
    Button(btns, text="Save to .sql", width=12, command=_do_save).pack(side="left", padx=6)
    Button(btns, text="Cancel", width=10, command=_do_cancel).pack(side="left", padx=6)

    # Live theme update callback
    def _on_theme_change(theme_key):
        try:
            gui_utils.apply_theme_to_existing_widgets(pv)
            # Re-apply pane theme to text widget explicitly
            try:
                txt.config(state='normal')
                gui_utils.apply_theme_to_pane(txt)
                txt.config(state='disabled')
            except Exception:
                pass
        except Exception:
            pass
    
    # Register theme callback and unregister on destroy
    try:
        gui_utils.register_theme_callback(_on_theme_change)
        def _on_destroy(event=None):
            if event and event.widget == pv:
                try:
                    gui_utils.unregister_theme_callback(_on_theme_change)
                except Exception:
                    pass
        pv.bind('<Destroy>', _on_destroy)
    except Exception:
        pass
    # Avoid using grab_set(); it often fails when other apps hold the input grab.
    # Instead make the window topmost briefly and focus it so the user sees it,
    # then wait for the window to be closed. This is more reliable across OSes.
    try:
        try:
            pv.attributes('-topmost', True)
        except Exception:
            pass
        pv.protocol("WM_DELETE_WINDOW", _do_cancel)
        pv.bind('<Return>', lambda e: _do_exec())
        pv.bind('<Escape>', lambda e: _do_cancel())
        # ensure the window is visible and on top, then focus
        try:
            pv.lift()
            pv.update()
            pv.focus_force()
        except Exception:
            pass
        exec_btn = btns.winfo_children()[0]
        try:
            exec_btn.focus_force()
        except Exception:
            pass
        # remove topmost after ensuring it is visible
        try:
            pv.after(150, lambda: pv.attributes('-topmost', False))
        except Exception:
            pass
    except Exception:
        logger.info("Could not focus SQL preview window (non-fatal).")

    logger.info(f"Opened SQL preview: {title}")
    pv.wait_window()
    return confirmed["val"]


def build_insert_preview_sql(schema, table_name, insert_cols, sample_row=None):
    cols_sql = ', '.join([_quote_ident(c) for c in insert_cols])
    if sample_row is None:
        vals = ', '.join([':{}'.format(i+1) for i in range(len(insert_cols))])
    else:
        def _esc(v):
            return str(v).replace("'", "''")
        vals = ', '.join([f"'{_esc(sample_row.get(c, ''))}'" for c in insert_cols])
    return f"INSERT INTO {schema}.{table_name} ({cols_sql}) VALUES ({vals})"




def merge_with_checks(conn, cursor, schema, target_table, staging_table, key_cols, update_cols=None, dry_run=True):
    """Perform validations and optionally execute a MERGE from staging into target.

    Returns a dict with keys: ok, total_staging, matched, to_insert, sql (string), message (optional)
    If dry_run is False, the MERGE is executed (commit on success) and returned dict includes 'executed': True/False
    """
    schema_u = schema.upper()
    tgt = target_table.upper()
    stg = staging_table.upper()

    # fetch target columns and nullable info
    cursor.execute("""
        SELECT column_name, nullable FROM all_tab_columns
        WHERE owner = :1 AND table_name = :2
        ORDER BY column_id
    """, [schema_u, tgt])
    tgt_cols_info = cursor.fetchall()
    if not tgt_cols_info:
        return {"ok": False, "message": f"Target table {schema_u}.{tgt} not found."}
    tgt_cols = [r[0] for r in tgt_cols_info]
    tgt_nullable = {r[0]: r[1] for r in tgt_cols_info}

    # fetch staging columns
    cursor.execute("""
        SELECT column_name FROM all_tab_columns
        WHERE owner = :1 AND table_name = :2
        ORDER BY column_id
    """, [schema_u, stg])
    stg_cols_info = cursor.fetchall()
    if not stg_cols_info:
        return {"ok": False, "message": f"Staging table {schema_u}.{stg} not found."}
    stg_cols = [r[0] for r in stg_cols_info]

    # normalize inputs
    key_cols_u = [c.upper() for c in key_cols]
    if update_cols is None:
        # default: all staging cols intersect target cols excluding keys
        update_cols_u = [c for c in stg_cols if c in tgt_cols and c not in key_cols_u]
    else:
        update_cols_u = [c.upper() for c in update_cols]

    # Ensure we do not try to update key columns (Oracle ORA-38104)
    keys_in_updates = [c for c in update_cols_u if c in key_cols_u]
    if keys_in_updates:
        # Oracle MERGE cannot update columns used in the ON clause (ORA-38104).
        # Automatically remove key columns from the update list and continue.
        update_cols_u = [c for c in update_cols_u if c not in key_cols_u]
        logger.info(f"Auto-excluded key columns from update set (Oracle restriction): {keys_in_updates}")

    # existence checks
    missing_keys = [k for k in key_cols_u if k not in tgt_cols or k not in stg_cols]
    if missing_keys:
        return {"ok": False, "message": f"Key columns missing in target or staging: {missing_keys}"}
    missing_updates = [c for c in update_cols_u if c not in tgt_cols or c not in stg_cols]
    if missing_updates:
        return {"ok": False, "message": f"Update columns missing in target or staging: {missing_updates}"}

    # check duplicates in staging for key combination
    on_cols = key_cols_u
    on_expr = ','.join(on_cols)
    group_by_clause = ', '.join([_quote_ident(c) for c in on_cols])
    dup_sql = f"SELECT {group_by_clause}, COUNT(*) FROM {schema_u}.{stg} GROUP BY {group_by_clause} HAVING COUNT(*) > 1"
    try:
        cursor.execute(dup_sql)
        dup_rows = cursor.fetchall()
    except Exception as e:
        return {"ok": False, "message": f"Error checking duplicates in staging: {e}"}
    if dup_rows:
        return {"ok": False, "message": f"Duplicate key values found in staging (first sample: {dup_rows[0]})"}

    # NOT NULL checks: any target NOT NULL column missing from staging -> will be NULL on insert -> abort
    notnull_missing = [c for c, n in tgt_nullable.items() if n == 'N' and c not in stg_cols]
    if notnull_missing:
        return {"ok": False, "message": f"Target NOT NULL columns not provided by staging: {notnull_missing}"}

    # For NOT NULL columns present in staging, ensure no NULLs
    for col in tgt_cols:
        if tgt_nullable.get(col) == 'N' and col in stg_cols:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {schema_u}.{stg} WHERE {_quote_ident(col)} IS NULL")
                cnt = cursor.fetchone()[0]
                if cnt and cnt > 0:
                    return {"ok": False, "message": f"Staging column {col} contains {cnt} NULL(s) but target requires NOT NULL."}
            except Exception as e:
                return {"ok": False, "message": f"Error checking NOT NULL values for {col}: {e}"}

    # dry-run counts
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {schema_u}.{stg}")
        total_stg = cursor.fetchone()[0]
    except Exception as e:
        return {"ok": False, "message": f"Could not count staging rows: {e}"}

    # build ON clause for join
    on_clause = ' AND '.join([f't.{_quote_ident(c)} = s.{_quote_ident(c)}' for c in on_cols])
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {schema_u}.{tgt} t JOIN {schema_u}.{stg} s ON ({on_clause})")
        matched = cursor.fetchone()[0]
    except Exception as e:
        return {"ok": False, "message": f"Could not compute matched count: {e}"}

    to_insert = total_stg - matched

    # Build MERGE SQL
    # UPDATE clause
    if update_cols_u:
        set_clause = ', '.join([f't.{_quote_ident(c)} = s.{_quote_ident(c)}' for c in update_cols_u])
        update_sql = f"WHEN MATCHED THEN UPDATE SET {set_clause}"
    else:
        update_sql = ''

    # INSERT columns: use intersection of target and staging (preserve target order)
    insert_cols = [c for c in tgt_cols if c in stg_cols]
    insert_cols_sql = ', '.join([_quote_ident(c) for c in insert_cols])
    insert_vals_sql = ', '.join([f's.{_quote_ident(c)}' for c in insert_cols])

    merge_sql = f"MERGE INTO {schema_u}.{tgt} t USING {schema_u}.{stg} s ON ({on_clause}) "
    if update_sql:
        merge_sql += update_sql + ' '
    merge_sql += f"WHEN NOT MATCHED THEN INSERT ({insert_cols_sql}) VALUES ({insert_vals_sql})"

    result = {
        "ok": True,
        "total_staging": total_stg,
        "matched": matched,
        "to_insert": to_insert,
        "sql": merge_sql,
        "update_cols": update_cols_u,
        "key_cols": key_cols_u,
    }

    if dry_run:
        return result

    # execute merge
    try:
        cursor.execute(merge_sql)
        conn.commit()
        result["executed"] = True
        return result
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"ok": False, "message": f"MERGE failed: {e}", "sql": merge_sql}


def replace_table_with_df(conn, cursor, root, schema, table_name, df):
    """Destructive Replace: clear target table then insert dataframe rows.

    Behavior:
    - If incoming columns == target columns: truncate/delete then insert all columns
    - If incoming columns subset of target: offer subset replace (other cols NULL)
    - If incoming has extras: offer to drop extras then insert matching columns
    - Final confirmation is requested before destructive action
    """
    from tkinter import messagebox

    existing_cols = [c.upper() for c in get_table_columns(cursor, schema, table_name)]
    incoming_cols = [c.upper() for c in df.columns]
    existing_set = set(existing_cols)
    incoming_set = set(incoming_cols)

    # final confirm before destructive replace
    proceed_confirm = call_ui(root, lambda: _safe_messagebox('askyesno', "Confirm Replace", f"This will REMOVE ALL ROWS from {schema}.{table_name} and replace with the uploaded file.\n\nProceed?", dlg=root))
    if not proceed_confirm:
        logger.info("User cancelled destructive Replace.")
        return

    # determine which columns to insert
    if existing_set == incoming_set:
        insert_df = df
    elif incoming_set.issubset(existing_set):
        ok = call_ui(root, lambda: _safe_messagebox('askyesno', "Subset Replace", f"Incoming columns are a subset of target table columns.\nInsert only the incoming columns into {schema}.{table_name}?\n(Other target columns will be set to NULL)", dlg=root))
        if not ok:
            logger.info("Replace cancelled by user (subset confirmation).")
            return
        insert_df = df[[c for c in df.columns if c.upper() in existing_set]]
    else:
        extras = list(incoming_set - existing_set)
        ok = call_ui(root, lambda: _safe_messagebox('askyesno', "Extra Columns", f"Incoming data contains columns not present in target table: {extras}\n\nIgnore extra columns and insert matching columns?", dlg=root))
        if not ok:
            call_ui(root, lambda: _safe_messagebox('showerror', "Schema Mismatch", f"Replace cancelled.\n\nTarget columns: {existing_cols}\nIncoming columns: {incoming_cols}", dlg=root))
            logger.warning(f"Replace aborted due to column mismatch for {schema}.{table_name}")
            return
        insert_df = df[[c for c in df.columns if c.upper() in existing_set]]

    # clear target table (prefer TRUNCATE then fallback to DELETE)
    try:
        cursor.execute(f"TRUNCATE TABLE {schema}.{table_name}")
        logger.info(f"Truncated table {schema}.{table_name}")
    except Exception as e:
        logger.info(f"TRUNCATE failed ({e}), attempting DELETE FROM {schema}.{table_name}")
        try:
            cursor.execute(f"DELETE FROM {schema}.{table_name}")
            logger.info(f"Deleted rows from {schema}.{table_name}")
        except Exception as e2:
            logger.error(f"Failed to clear target table {schema}.{table_name}: {e2}")
            raise
    try:
        conn.commit()
    except Exception:
        pass

    # bulk insert
    insert_cols = list(insert_df.columns)
    inserted = bulk_insert_chunked(conn, cursor, schema, table_name, insert_df, insert_columns=insert_cols)
    logger.info(f"✅ Replaced {inserted} rows in {schema}.{table_name}")
    try:
        conn.commit()
    except Exception:
        pass


# ==== SHEET SELECTOR DIALOG ====
def select_sheets_gui(file, sheets):
    from tkinter import Toplevel, Label, IntVar, Entry, Button, Checkbutton, Frame, Canvas, Scrollbar, VERTICAL, RIGHT, LEFT, BOTH, Y

    result = {}

    def on_submit():
        for i, sheet in enumerate(sheets):
            if vars_[i]["var"].get():
                entered = vars_[i]["entry"].get().strip()
                if entered:
                    result[sheet] = entered.upper()
        top.destroy()

    def on_cancel():
        result.clear()
        top.destroy()

    top = Toplevel()
    top.title(f"Select Sheets: {os.path.basename(file)}")
    
    # Apply theme immediately after creating dialog
    gui_utils.apply_theme_to_dialog(top)
    
    center_window(top, 500, 600)

    Label(
        top,
        text="Columns named PIDM, TERM, and STUDENT_ID will be indexed (if present)",
        font=("Arial", 9),
        fg="gray"
    ).pack(pady=(0, 10))

    # Top-aligned buttons
    btn_frame = Frame(top)
    btn_frame.pack(pady=(0, 10))
    Button(btn_frame, text="OK", width=10, command=on_submit).pack(side="left", padx=10)
    Button(btn_frame, text="Cancel", width=10, command=on_cancel).pack(side="left", padx=10)
    
    top.bind("<Return>", lambda event: on_submit())  # ✅ Pressing Enter submits

    # Scrollable canvas for sheet list
    canvas = Canvas(top)
    scrollbar = Scrollbar(top, orient=VERTICAL, command=canvas.yview)
    scrollable_frame = Frame(canvas)

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=LEFT, fill=BOTH, expand=True)
    scrollbar.pack(side=RIGHT, fill=Y)

    canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

    vars_ = []
    for sheet in sheets:
        frame = Frame(scrollable_frame)
        var = IntVar(value=1)
        chk = Checkbutton(frame, text=sheet, variable=var)
        chk.pack(side="left")
        entry = Entry(frame)
        default_table_name = f"{os.path.splitext(os.path.basename(file))[0]}_{sheet}".replace('-', '_').replace(' ', '_').upper()
        entry.insert(0, default_table_name)
        entry.pack(side="right", padx=10, fill="x", expand=True)        
        
        if len(vars_) == 0:
            entry.focus()
            entry.select_range(0, 'end')  # ✅ Highlight entire prefilled name    
        
        frame.pack(fill="x", padx=10, pady=2)
        vars_.append({"var": var, "entry": entry})

    # Live theme update callback
    def _on_theme_change(theme_key):
        try:
            gui_utils.apply_theme_to_existing_widgets(top)
        except Exception:
            pass
    
    # Register theme callback and unregister on destroy
    try:
        gui_utils.register_theme_callback(_on_theme_change)
        def _on_destroy(event=None):
            if event and event.widget == top:
                try:
                    gui_utils.unregister_theme_callback(_on_theme_change)
                except Exception:
                    pass
        top.bind('<Destroy>', _on_destroy)
    except Exception:
        pass

    try:
        top.grab_set()
    except Exception as e:
        logger.warning(f"Could not grab focus for sheet selector: {e}")
    top.wait_window()
    return result if result else None

# ==== MAIN FUNCTION ====
def load_multiple_files(launcher_root=None):
    """Load multiple Excel/CSV files.

    UI interactions run on the provided launcher_root when available; heavy DB work
    runs in a background thread so the main GUI remains responsive and the
    Abort button can take effect.
    """
    parent = launcher_root
    created_temp_root = False
    if parent is None:
        parent = Tk()
        parent.withdraw()
        created_temp_root = True

    try:
        logger.info(f"load_multiple_files invoked (thread={threading.current_thread().name} id={threading.get_ident()})")
    except Exception:
        logger.info("load_multiple_files invoked")

    # Ensure schema choice prompt runs on the main thread / parent
    try:
        schema_choice = call_ui(parent, prompt_schema_choice, parent)
    except Exception as e:
        logger.exception(f"Exception while showing schema choice dialog: {e}")
        if created_temp_root:
            try:
                parent.destroy()
            except Exception:
                pass
        return
    if schema_choice is None:
        if created_temp_root:
            try:
                parent.destroy()
            except Exception:
                pass
        return

    try:
        # askopenfilenames does not accept a positional 'parent' reliably across
        # Tk versions. Call it with a keyword via a lambda so call_ui schedules
        # the dialog correctly on the main thread.
        file_paths = call_ui(parent, lambda: filedialog.askopenfilenames(parent=parent))
    except Exception as e:
        logger.exception(f"Exception while showing file-open dialog: {e}")
        if created_temp_root:
            try:
                parent.destroy()
            except Exception:
                pass
        return
    # filedialog.askopenfilenames expects parent as first positional arg in some
    # environments; call_ui will schedule the dialog on the main thread.
    if not file_paths:
        logger.warning("❌ No files selected. Aborting.")
        if created_temp_root:
            try:
                parent.destroy()
            except Exception:
                pass
        return

    # Log scheduling details before starting background work
    try:
        logger.info(f"Scheduling loader background worker: files={len(file_paths)} schema_choice={schema_choice}")
    except Exception:
        logger.info("Scheduling loader background worker (could not determine file count)")

    def _background_work(file_paths, schema_choice, parent, created_temp_root):
        logger.info(f"Background worker starting (thread={threading.current_thread().name} id={threading.get_ident()})")

        # Establish connection (downgrade DPY-1001/abort errors)
        schema_key = 'schema2' if schema_choice == "dwh" else 'schema1'
        try:
            conn = get_db_connection(schema=schema_key, root=parent)
        except Exception as e:
            # Treat driver 'not connected' errors as expected when an abort
            # is in progress or when raised on a background thread.
            try:
                if abort_manager.is_expected_disconnect(e):
                    logger.warning(f"⏹️ Aborted during connection/setup: {e}")
                    return
            except Exception:
                pass
            logger.exception(f"❌ Failed to obtain DB connection: {e}")
            return

        # register this connection so external abort handlers can close it
        try:
            abort_manager.register_connection(conn)
        except Exception:
            pass

        if not conn:
            logger.error("❌ Failed to connect to Oracle. get_db_connection returned None or False")
            if created_temp_root:
                try:
                    parent.destroy()
                except Exception:
                    pass
            return

        cursor = None
        try:
            # Register connection with session for cleanup
            try:
                session.register_connection(parent, conn, schema_key)
            except Exception:
                logger.debug('Failed to register connection', exc_info=True)

            schema = conn.username.upper()
            logger.info(f"🔐 Connected to schema: {schema}")
            try:
                logger.info(f"Acquiring cursor from connection (username={getattr(conn, 'username', None)})")
            except Exception:
                logger.info("Acquiring cursor from connection")
            cursor = conn.cursor()
            abort_manager.reset()

            for file_path in file_paths:
                logger.info(f"Processing file: {file_path}")
                try:
                    file_name = os.path.splitext(os.path.basename(file_path))[0].replace('-', '_').replace(' ', '_').upper()

                    if file_path.lower().endswith('.csv'):
                        df = pd.read_csv(file_path)
                        df = clean_column_names(df)
                        file_prefix = file_name
                        df.columns = [col.replace(f"{file_prefix}_", "") for col in df.columns]
                        df = df.astype(str).fillna('')
                        table_name = file_name
                        from tkinter.simpledialog import askstring
                        # askstring may not accept a positional parent across Tk versions;
                        # schedule it with a lambda to pass parent as keyword.
                        override = call_ui(parent, lambda: askstring("Rename Table", f"Default table name is '{table_name}'. Enter a new name or leave blank:", parent=parent))
                        if override and override.strip():
                            table_name = override.strip().replace('-', '_').replace(' ', '_').upper()

                        cols_exist = get_table_columns(cursor, schema, table_name)
                        logger.info(f"Checking existing table for {schema}.{table_name}: found {len(cols_exist)} columns")
                        if cols_exist:
                            try:
                                opts = call_ui(parent, show_load_mode_dialog, parent, schema, table_name, df.columns)
                            except Exception as e:
                                logger.exception(f"❌ Exception while showing load mode dialog for {schema}.{table_name}: {e}")
                                opts = None
                            if not opts:
                                logger.info("❌ User cancelled load or dialog did not appear.")
                                continue
                            mode = opts.get("mode")
                            if mode == "preview":
                                logger.info(f"🔎 Preview requested for {schema}.{table_name}. No changes made.")
                            elif mode == "append":
                                logger.info(f"⏩ Appending data to {schema}.{table_name}")
                                preview = opts.get("preview_sql", True)
                                existing_cols = [c.upper() for c in get_table_columns(cursor, schema, table_name)]
                                incoming_cols = [c.upper() for c in df.columns]
                                existing_set = set(existing_cols)
                                incoming_set = set(incoming_cols)
                                from tkinter import messagebox
                                if existing_set == incoming_set:
                                    if preview:
                                        sample = df.iloc[0].to_dict() if len(df) > 0 else None
                                        ins_sql = build_insert_preview_sql(schema, table_name, list(df.columns), sample)
                                        summary = f"Rows in file: {len(df)}\nInsert columns: {list(df.columns)}"
                                        logger.debug(f"Opening INSERT preview for {schema}.{table_name} (len={len(ins_sql)})")
                                        do_exec = call_ui(parent, show_sql_preview, parent, f"INSERT Preview: {schema}.{table_name}", summary, ins_sql)
                                        if do_exec:
                                            inserted = bulk_insert_chunked(conn, cursor, schema, table_name, df)
                                            logger.info(f"✅ Appended {inserted} rows to {schema}.{table_name}")
                                    else:
                                        inserted = bulk_insert_chunked(conn, cursor, schema, table_name, df)
                                        logger.info(f"✅ Appended {inserted} rows to {schema}.{table_name}")
                                elif incoming_set.issubset(existing_set):
                                    ok = call_ui(parent, lambda: _safe_messagebox('askyesno', "Subset Append", f"Incoming columns are a subset of target table columns.\n\nInsert only the incoming columns into {schema}.{table_name}?\n(This will insert values only for these columns and leave other target columns NULL)", dlg=parent))
                                    if ok:
                                        insert_cols = list(df.columns)
                                        if preview:
                                            sample = df.iloc[0].to_dict() if len(df) > 0 else None
                                            ins_sql = build_insert_preview_sql(schema, table_name, insert_cols, sample)
                                            summary = f"Rows in file: {len(df)}\nInsert columns: {insert_cols}\n(Other target columns will be NULL)"
                                            logger.debug(f"Opening INSERT (subset) preview for {schema}.{table_name} (len={len(ins_sql)})")
                                            do_exec = call_ui(parent, show_sql_preview, parent, f"INSERT Preview (subset): {schema}.{table_name}", summary, ins_sql)
                                            if do_exec:
                                                inserted = bulk_insert_chunked(conn, cursor, schema, table_name, df, insert_columns=insert_cols)
                                                logger.info(f"✅ Appended {inserted} rows (subset) to {schema}.{table_name}")
                                        else:
                                            inserted = bulk_insert_chunked(conn, cursor, schema, table_name, df, insert_columns=insert_cols)
                                            logger.info(f"✅ Appended {inserted} rows (subset) to {schema}.{table_name}")
                                else:
                                    extras = list(incoming_set - existing_set)
                                    ok = call_ui(parent, lambda: _safe_messagebox('askyesno', "Extra Columns", f"Incoming data contains columns not present in target table: {extras}\n\nIgnore extra columns and insert matching columns?", dlg=parent))
                                    if ok:
                                        df = df[[c for c in df.columns if c.upper() in existing_set]]
                                        insert_cols = list(df.columns)
                                        if preview:
                                            sample = df.iloc[0].to_dict() if len(df) > 0 else None
                                            ins_sql = build_insert_preview_sql(schema, table_name, insert_cols, sample)
                                            summary = f"Rows in file: {len(df)}\nInsert columns: {insert_cols}\nDropped extras: {extras}"
                                            logger.debug(f"Opening INSERT (extras dropped) preview for {schema}.{table_name} (len={len(ins_sql)})")
                                            do_exec = call_ui(parent, show_sql_preview, parent, f"INSERT Preview (extras dropped): {schema}.{table_name}", summary, ins_sql)
                                            if do_exec:
                                                inserted = bulk_insert_chunked(conn, cursor, schema, table_name, df, insert_columns=insert_cols)
                                                logger.info(f"✅ Appended {inserted} rows (with extras dropped) to {schema}.{table_name}")
                                        else:
                                            inserted = bulk_insert_chunked(conn, cursor, schema, table_name, df, insert_columns=insert_cols)
                                            logger.info(f"✅ Appended {inserted} rows (with extras dropped) to {schema}.{table_name}")
                                    else:
                                        call_ui(parent, lambda: _safe_messagebox('showerror', "Schema Mismatch", f"Append cancelled.\n\nTarget columns: {existing_cols}\nIncoming columns: {incoming_cols}", dlg=parent))
                                        logger.warning(f"Append aborted due to column mismatch for {schema}.{table_name}")
                            elif mode == "replace":
                                logger.info(f"♻️ Replacing {schema}.{table_name} with file contents (destructive)")
                                preview = opts.get("preview_sql", True)
                                existing_cols = [c.upper() for c in get_table_columns(cursor, schema, table_name)]
                                incoming_cols = [c.upper() for c in df.columns]
                                existing_set = set(existing_cols)
                                incoming_set = set(incoming_cols)
                                if existing_set == incoming_set:
                                    insert_df = df
                                else:
                                    insert_df = df[[c for c in df.columns if c.upper() in existing_set]]
                                insert_cols = list(insert_df.columns)
                                sample = insert_df.iloc[0].to_dict() if len(insert_df) > 0 else None
                                truncate_sql = f"TRUNCATE TABLE {schema}.{table_name}"
                                ins_sql = build_insert_preview_sql(schema, table_name, insert_cols, sample)
                                if preview:
                                    summary = f"Rows in file: {len(insert_df)}\nThis operation will TRUNCATE the target table before inserting.\nInsert columns: {insert_cols}"
                                    combined_sql = truncate_sql + "\n" + ins_sql
                                    logger.debug(f"Opening REPLACE preview for {schema}.{table_name} (len={len(combined_sql)})")
                                    do_exec = call_ui(parent, show_sql_preview, parent, f"REPLACE Preview: {schema}.{table_name}", summary, combined_sql)
                                    if do_exec:
                                        try:
                                            replace_table_with_df(conn, cursor, parent, schema, table_name, df)
                                        except Exception as e:
                                            logger.error(f"❌ Replace failed for {schema}.{table_name}: {e}")
                                        else:
                                            logger.info(f"✅ Replace complete for {schema}.{table_name}")
                                else:
                                    try:
                                        replace_table_with_df(conn, cursor, parent, schema, table_name, df)
                                    except Exception as e:
                                        logger.error(f"❌ Replace failed for {schema}.{table_name}: {e}")
                                    else:
                                        logger.info(f"✅ Replace complete for {schema}.{table_name}")
                            elif mode == "upsert":
                                logger.info(f"🔀 Upsert (MERGE) into {schema}.{table_name}")
                                preview = opts.get("preview_sql", True)
                                ts = int(time.time())
                                stg = f"{table_name}__STG_{ts}"
                                create_staging_table_from_df(cursor, schema, stg, df)
                                inserted = bulk_insert_chunked(conn, cursor, schema, stg, df)
                                logger.info(f"✅ Loaded staging {schema}.{stg} ({inserted} rows)")
                                try:
                                    sel = call_ui(parent, show_upsert_selector, parent, list(df.columns))
                                except Exception as e:
                                    logger.exception(f"Exception while opening upsert selector: {e}")
                                    sel = None
                                if not sel:
                                    logger.info("User cancelled Upsert selection. Dropping staging.")
                                    try:
                                        cursor.execute(f"DROP TABLE {schema}.{stg} PURGE")
                                    except Exception:
                                        pass
                                    conn.commit()
                                else:
                                    key_cols = sel.get("key_columns", [])
                                    update_cols = sel.get("update_columns", list(df.columns))
                                    try:
                                        res = merge_with_checks(conn, cursor, schema, table_name, stg, key_cols, update_cols, dry_run=True)
                                    except Exception as e:
                                        logger.exception(f"Exception preparing merge: {e}")
                                        res = {"ok": False, "message": str(e)}
                                    if not res.get("ok"):
                                        logger.error(f"Pre-merge checks failed: {res.get('message')}")
                                        try:
                                            cursor.execute(f"DROP TABLE {schema}.{stg} PURGE")
                                        except Exception:
                                            logger.warning(f"Could not drop staging table {schema}.{stg}")
                                        conn.commit()
                                    else:
                                        summary = f"Staging rows: {res['total_staging']}\nMatched (will update): {res['matched']}\nWill insert: {res['to_insert']}"
                                        if preview:
                                            logger.debug(f"Opening MERGE preview for {schema}.{table_name} (len={len(res.get('sql',''))})")
                                            do_exec = call_ui(parent, show_sql_preview, parent, f"MERGE Preview: {schema}.{table_name}", summary, res.get('sql', ''))
                                            if do_exec:
                                                exec_res = merge_with_checks(conn, cursor, schema, table_name, stg, key_cols, update_cols, dry_run=False)
                                                if not exec_res.get("ok"):
                                                    logger.error(f"MERGE failed: {exec_res.get('message')}")
                                                else:
                                                    logger.info(f"✅ Upsert executed for {schema}.{table_name}")
                                        else:
                                            exec_res = merge_with_checks(conn, cursor, schema, table_name, stg, key_cols, update_cols, dry_run=False)
                                            if not exec_res.get("ok"):
                                                logger.error(f"MERGE failed: {exec_res.get('message')}")
                                            else:
                                                logger.info(f"✅ Upsert executed for {schema}.{table_name}")
                                        try:
                                            cursor.execute(f"DROP TABLE {schema}.{stg} PURGE")
                                        except Exception:
                                            logger.warning(f"Could not drop staging table {schema}.{stg}")
                                        conn.commit()
                                        logger.info(f"✅ Upsert complete for {schema}.{table_name}")
                        else:
                            # new table: create and insert
                            drop_table_if_exists(cursor, schema, table_name)
                            create_table(cursor, schema, table_name, df)
                            success = insert_data(cursor, schema, table_name, df, conn)
                            if not success:
                                continue
                            logger.info(f"🚀 Loaded CSV: {schema}.{table_name}")
                except Exception as e:
                    logger.error(f"❌ Failed to load file {file_path}: {e}")

            conn.commit()
            logger.info("✅ All files processed successfully.")

        except Exception as e:
            try:
                if abort_manager.is_expected_disconnect(e) or getattr(abort_manager, 'cleanup_done', False) or getattr(abort_manager, 'should_abort', False):
                    # This is an expected disconnect during abort/cleanup. Downgrade
                    # the noisy DPY-1001 stacktrace to DEBUG so normal abort flows
                    # don't spam ERROR-level logs.
                    logger.debug(f"⏹️ Aborted during background work (expected): {e}")
                    # Attempt best-effort cleanup if possible, but swallow errors.
                    try:
                        if 'conn' in locals() and conn:
                            try:
                                abort_manager.cleanup_on_abort(conn, cursor)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    return
            except Exception:
                # If abort_manager.is_expected_disconnect itself fails, fall through to full exception path
                pass

            logger.exception(f"❌ Unhandled exception in background worker: {e}")
            try:
                if 'conn' in locals() and conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
            except Exception:
                pass
            return

        finally:
            try:
                if 'cursor' in locals() and cursor:
                    try:
                        cursor.close()
                    except Exception as e:
                        try:
                            if not abort_manager.is_expected_disconnect(e):
                                logger.warning(f"⚠️ Failed to close cursor: {e}")
                        except Exception:
                            logger.warning(f"⚠️ Failed to close cursor: {e}")
            except Exception:
                pass

            try:
                if 'conn' in locals() and conn:
                    try:
                        conn.close()
                    except Exception as e:
                        try:
                            if not abort_manager.is_expected_disconnect(e):
                                logger.warning(f"⚠️ Failed to close connection: {e}")
                        except Exception:
                            logger.warning(f"⚠️ Failed to close connection: {e}")
            except Exception:
                pass

            try:
                try:
                    session.close_connections(parent)
                except Exception:
                    logger.debug('Session cleanup failed', exc_info=True)
                if created_temp_root:
                    try:
                        parent.destroy()
                    except Exception:
                        pass
            except Exception:
                pass
            # Clear abort state so launcher knows abort/cleanup completed and
            # can re-enable UI. reset() is idempotent and clears should_abort.
            try:
                abort_manager.reset()
            except Exception:
                pass

    t = threading.Thread(target=_background_work, args=(file_paths, schema_choice, parent, created_temp_root), daemon=True)
    t.start()
    logger.info(f"Background worker thread started: name={t.name} ident={t.ident}")
    # If we created a temporary hidden root (loader run standalone), the
    # background worker schedules UI work via `parent.after`. For those
    # callbacks to run we must run the Tk mainloop here until the worker
    # finishes and destroys the temporary root. The worker will call
    # `parent.destroy()` when finished if `created_temp_root` is True.
    if created_temp_root:
        try:
            parent.mainloop()
        except Exception:
            pass


# =============================================================================
# New structured Data Loader GUI  (launched from pane Load buttons)
# =============================================================================

def _compute_col_sizes(df, buffer=1.2, minimum=20):
    """Compute tight VARCHAR2 sizes from actual data in a DataFrame.

    Returns a dict mapping column_name -> int size.
    Each size is max(observed_byte_length) * buffer, rounded up,
    with a floor of *minimum*.
    """
    import math
    sizes = {}
    for col in df.columns:
        max_len = df[col].astype(str).str.encode('utf-8').apply(len).max()
        if pd.isna(max_len) or max_len == 0:
            max_len = 1
        computed = max(minimum, math.ceil(int(max_len) * buffer))
        sizes[col.upper()] = computed
    return sizes


def load_files_gui(parent=None, schema_choice='user', on_status_change=None, on_finish=None):
    """Open the structured Data Loader dialog.

    Parameters
    ----------
    parent : Tk widget or None
        The launcher root window.
    schema_choice : str
        'user' or 'dwh' — determines the target schema.
    on_status_change : callable or None
        Callback function(status) where status is 'busy', 'aborting', or 'idle'.
        Used to update the main GUI status indicator.
    on_finish : callable or None
        Callback function called when the dialog is closed (cancel, X, or after loading).
        Used to refresh object panes in the main GUI.
    """
    import math
    from tkinter import Toplevel, Frame, Label, Button, Entry, StringVar, IntVar
    from tkinter import Listbox, Scrollbar, filedialog
    from tkinter.constants import LEFT, RIGHT, BOTH, Y, END, EXTENDED
    try:
        import tkinter.ttk as ttk
    except Exception:
        ttk = None

    # =========================================================================
    # Get credentials FIRST, before showing the tool GUI
    # =========================================================================
    schema_key = 'schema2' if schema_choice == 'dwh' else 'schema1'
    conn = get_db_connection(schema=schema_key, root=parent)
    if not conn:
        # User cancelled or connection failed - don't show the GUI
        return
    
    # Register connection for cleanup
    try:
        session.register_connection(parent, conn, schema_key)
    except Exception:
        logger.debug('Failed to register connection', exc_info=True)

    # Store connection info for use in _execute_load
    _conn_info = {
        'conn': conn,
        'schema_key': schema_key,
        'schema': conn.username.upper()
    }

    # --- file entry storage ---
    # Each entry is a dict:
    #   { 'path': str, 'sheet': str or None, 'df': DataFrame,
    #     'table_name': str, 'rows': int, 'cols': int,
    #     'col_sizes': dict, 'columns': list }
    file_entries = []

    # --- Status callback helper for main GUI indicator ---
    def _set_main_status(status):
        """Update main GUI status indicator if callback provided."""
        if on_status_change:
            try:
                on_status_change(status)
                if parent:
                    parent.update_idletasks()
            except Exception:
                pass

    # --- Build dialog window ---
    if parent:
        win = Toplevel(parent)
        try:
            win.transient(parent)
        except Exception:
            pass
    else:
        win = tk.Tk()

    # Apply theme immediately after creating dialog
    gui_utils.apply_theme_to_dialog(win)

    schema_label = 'Schema 2' if schema_choice == 'dwh' else 'Schema 1'
    win.title(f'Data Loader - {schema_label}')

    # --- File list section ---
    file_frame = tk.LabelFrame(win, text='Files to Load', padx=6, pady=6)
    file_frame.pack(fill=BOTH, expand=True, padx=8, pady=(8, 4))

    file_btn_bar = Frame(file_frame)
    file_btn_bar.pack(fill='x', pady=(0, 4))

    add_btn = Button(file_btn_bar, text='Add Files...', width=12)
    add_btn.pack(side=LEFT, padx=(0, 6))
    remove_btn = Button(file_btn_bar, text='Remove Selected', width=14)
    remove_btn.pack(side=LEFT, padx=(0, 6))
    clear_btn = Button(file_btn_bar, text='Clear All', width=10)
    clear_btn.pack(side=LEFT)

    # File treeview
    file_tv_frame = Frame(file_frame)
    file_tv_frame.pack(fill=BOTH, expand=True)

    file_cols = ("filename", "sheet", "rows", "columns", "table_name")
    if ttk:
        file_tv = ttk.Treeview(file_tv_frame, columns=file_cols, show="headings", height=8)
    else:
        file_tv = ttk.Treeview(file_tv_frame, columns=file_cols, show="headings", height=8) if ttk else None

    if file_tv:
        file_tv.heading("filename", text="File")
        file_tv.heading("sheet", text="Sheet")
        file_tv.heading("rows", text="Rows")
        file_tv.heading("columns", text="Cols")
        file_tv.heading("table_name", text="Table Name")
        file_tv.column("filename", width=200, anchor="w")
        file_tv.column("sheet", width=80, anchor="center")
        file_tv.column("rows", width=60, anchor="center")
        file_tv.column("columns", width=50, anchor="center")
        file_tv.column("table_name", width=200, anchor="w")
        file_vs = Scrollbar(file_tv_frame, orient="vertical", command=file_tv.yview)
        file_tv.configure(yscrollcommand=file_vs.set)
        file_tv.pack(side=LEFT, fill=BOTH, expand=True)
        file_vs.pack(side=RIGHT, fill=Y)

    # --- Table name edit ---
    name_frame = Frame(file_frame)
    name_frame.pack(fill='x', pady=(4, 0))
    Label(name_frame, text='Table Name (selected):', font=("Arial", 9)).pack(side=LEFT, padx=(0, 6))
    table_name_var = StringVar()
    name_entry = Entry(name_frame, textvariable=table_name_var, width=40)
    name_entry.pack(side=LEFT, padx=(0, 6))
    rename_btn = Button(name_frame, text='Apply Rename', width=14)
    rename_btn.pack(side=LEFT)

    # --- Batch mode + sizing ---
    options_frame = tk.LabelFrame(win, text='Options', padx=6, pady=6)
    options_frame.pack(fill='x', padx=8, pady=4)

    # Batch mode
    batch_row = Frame(options_frame)
    batch_row.pack(fill='x', pady=(0, 4))
    Label(batch_row, text='Batch Mode:', font=("Arial", 9, 'bold')).pack(side=LEFT, padx=(0, 8))
    batch_mode_var = IntVar(value=0)  # 0 = separate, 1 = single
    tk.Radiobutton(batch_row, text='Separate tables (one per file)', variable=batch_mode_var, value=0).pack(side=LEFT, padx=(0, 12))
    tk.Radiobutton(batch_row, text='Single table (merge all files)', variable=batch_mode_var, value=1).pack(side=LEFT, padx=(0, 12))
    Label(batch_row, text='Name:', font=("Arial", 9)).pack(side=LEFT, padx=(0, 4))
    single_table_var = StringVar(value='BATCH_LOAD')
    single_entry = Entry(batch_row, textvariable=single_table_var, width=24)
    single_entry.pack(side=LEFT)

    # Sizing mode
    sizing_row = Frame(options_frame)
    sizing_row.pack(fill='x', pady=(0, 4))
    Label(sizing_row, text='VARCHAR2 Sizing:', font=("Arial", 9, 'bold')).pack(side=LEFT, padx=(0, 8))
    sizing_mode_var = IntVar(value=0)  # 0 = tight, 1 = fixed 4000
    tk.Radiobutton(sizing_row, text='Tight (max data length + 20%)', variable=sizing_mode_var, value=0).pack(side=LEFT, padx=(0, 12))
    tk.Radiobutton(sizing_row, text='Fixed VARCHAR2(4000)', variable=sizing_mode_var, value=1).pack(side=LEFT)

    # Load mode
    mode_row = Frame(options_frame)
    mode_row.pack(fill='x', pady=(0, 4))
    Label(mode_row, text='Load Mode:', font=("Arial", 9, 'bold')).pack(side=LEFT, padx=(0, 8))
    load_mode_var = IntVar(value=0)  # 0=create, 1=append, 2=replace, 3=upsert
    tk.Radiobutton(mode_row, text='Create New', variable=load_mode_var, value=0).pack(side=LEFT, padx=(0, 8))
    tk.Radiobutton(mode_row, text='Append', variable=load_mode_var, value=1).pack(side=LEFT, padx=(0, 8))
    tk.Radiobutton(mode_row, text='Replace', variable=load_mode_var, value=2).pack(side=LEFT, padx=(0, 8))
    tk.Radiobutton(mode_row, text='Upsert (MERGE)', variable=load_mode_var, value=3).pack(side=LEFT)

    # Preview SQL checkbox
    preview_row = Frame(options_frame)
    preview_row.pack(fill='x')
    preview_var = IntVar(value=0)  # default unchecked
    tk.Checkbutton(preview_row, text='Preview SQL before executing', variable=preview_var).pack(side=LEFT)

    # --- Column preview ---
    col_frame = tk.LabelFrame(win, text='Column Preview (selected file)', padx=6, pady=6)
    col_frame.pack(fill=BOTH, expand=True, padx=8, pady=4)

    col_tv_frame = Frame(col_frame)
    col_tv_frame.pack(fill=BOTH, expand=True)

    col_cols = ("col_name", "max_len", "oracle_size", "sample")
    if ttk:
        col_tv = ttk.Treeview(col_tv_frame, columns=col_cols, show="headings", height=6)
        col_tv.heading("col_name", text="Column")
        col_tv.heading("max_len", text="Max Length")
        col_tv.heading("oracle_size", text="VARCHAR2 Size")
        col_tv.heading("sample", text="Sample Values")
        col_tv.column("col_name", width=160, anchor="w")
        col_tv.column("max_len", width=80, anchor="center")
        col_tv.column("oracle_size", width=100, anchor="center")
        col_tv.column("sample", width=250, anchor="w")
        col_vs = Scrollbar(col_tv_frame, orient="vertical", command=col_tv.yview)
        col_tv.configure(yscrollcommand=col_vs.set)
        col_tv.pack(side=LEFT, fill=BOTH, expand=True)
        col_vs.pack(side=RIGHT, fill=Y)
    else:
        col_tv = None

    # --- Index column selection ---
    idx_frame = tk.LabelFrame(win, text='Index Columns (optional)', padx=6, pady=6)
    idx_frame.pack(fill=BOTH, expand=True, padx=8, pady=4)

    idx_inner = Frame(idx_frame)
    idx_inner.pack(fill=BOTH, expand=True)
    Label(idx_inner, text='Select columns to index after loading (each gets its own index):',
          font=("Arial", 9)).pack(anchor='w')
    idx_list_frame = Frame(idx_inner)
    idx_list_frame.pack(fill=BOTH, expand=True, pady=(4, 0))
    idx_list = Listbox(idx_list_frame, height=5, selectmode=EXTENDED, exportselection=False)
    idx_list_sb = Scrollbar(idx_list_frame, orient="vertical", command=idx_list.yview)
    idx_list.configure(yscrollcommand=idx_list_sb.set)
    idx_list.pack(side=LEFT, fill=BOTH, expand=True)
    idx_list_sb.pack(side=RIGHT, fill=Y)

    # --- Upsert key/update column selectors (shown only in upsert mode) ---
    upsert_frame = tk.LabelFrame(win, text='Upsert Configuration', padx=6, pady=6)
    # Don't pack yet — will be shown/hidden dynamically

    upsert_inner = Frame(upsert_frame)
    upsert_inner.pack(fill=BOTH, expand=True)

    key_frame = Frame(upsert_inner)
    key_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 6))
    Label(key_frame, text='Key Columns (select for MERGE ON)', font=("Arial", 9, 'bold')).pack(anchor='w')
    key_list_frame = Frame(key_frame)
    key_list_frame.pack(fill=BOTH, expand=True)
    key_list = Listbox(key_list_frame, height=6, selectmode=EXTENDED, exportselection=False)
    key_list_sb = Scrollbar(key_list_frame, orient="vertical", command=key_list.yview)
    key_list.configure(yscrollcommand=key_list_sb.set)
    key_list.pack(side=LEFT, fill=BOTH, expand=True)
    key_list_sb.pack(side=RIGHT, fill=Y)

    upd_frame = Frame(upsert_inner)
    upd_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(6, 0))
    Label(upd_frame, text='Update Columns (WHEN MATCHED)', font=("Arial", 9, 'bold')).pack(anchor='w')
    upd_list_frame = Frame(upd_frame)
    upd_list_frame.pack(fill=BOTH, expand=True)
    upd_list = Listbox(upd_list_frame, height=6, selectmode=EXTENDED, exportselection=False)
    upd_list_sb = Scrollbar(upd_list_frame, orient="vertical", command=upd_list.yview)
    upd_list.configure(yscrollcommand=upd_list_sb.set)
    upd_list.pack(side=LEFT, fill=BOTH, expand=True)
    upd_list_sb.pack(side=RIGHT, fill=Y)

    def _toggle_upsert_frame(*args):
        if load_mode_var.get() == 3:
            upsert_frame.pack(fill=BOTH, expand=True, padx=8, pady=4, before=btn_frame)
            # Expand window height to accommodate upsert pane
            try:
                win.geometry('960x1000')
            except Exception:
                pass
        else:
            upsert_frame.pack_forget()
            # Shrink window back
            try:
                win.geometry('960x860')
            except Exception:
                pass
    load_mode_var.trace_add('write', _toggle_upsert_frame)

    # --- Status / progress ---
    status_var = StringVar(value='Ready')
    status_label = Label(win, textvariable=status_var, font=("Arial", 9), fg='#444444', anchor='w')
    status_label.pack(fill='x', padx=8, pady=(4, 0))

    # --- Button bar ---
    btn_frame = Frame(win)
    btn_frame.pack(fill='x', padx=8, pady=(6, 8))

    load_btn = Button(btn_frame, text='Load', width=12)
    load_btn.pack(side=LEFT, padx=(0, 6))
    abort_btn = Button(btn_frame, text='Abort', width=10, state='disabled')
    abort_btn.pack(side=LEFT, padx=(0, 6))
    close_btn = Button(btn_frame, text='Close', width=10, command=win.destroy)
    close_btn.pack(side=RIGHT)

    # =========================================================================
    # Event handlers / logic
    # =========================================================================

    def _sanitize_table_name(name):
        return name.strip().replace('-', '_').replace(' ', '_').replace('.', '_').upper()

    def _abort_load():
        """Abort an in-progress load operation.

        Mirrors the abort logic from HoonyTools.pyw but scoped to this loader
        dialog.  Sets the abort_manager flag, closes registered connections,
        and spawns a monitor thread to re-enable the UI.
        """
        abort_manager.set_abort(True)
        logger.warning("Abort requested by user (loader).")
        status_var.set('Aborting...')
        _set_main_status('aborting')  # Turn main GUI indicator amber
        abort_btn.config(state='disabled')

        # Close schema2 connections in background if applicable
        try:
            if parent:
                import threading as _thr
                def _close_conns():
                    try:
                        session.close_connections(parent)
                    except Exception:
                        logger.debug('Failed to close connections during abort', exc_info=True)
                _thr.Thread(target=_close_conns, daemon=True).start()
        except Exception:
            pass

        # Cancel any pending prompt events (unblock workers waiting on prompts)
        try:
            abort_manager.cancel_prompt_event()
        except Exception:
            pass

        # Close the worker's registered connection to interrupt blocking DB calls
        try:
            abort_manager.close_registered_connection()
        except Exception:
            pass

        # Monitor thread: wait for abort to clear, then re-enable UI
        def _monitor():
            import time
            max_wait = 30.0
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
                    logger.warning("Abort monitor timed out; forcing reset")
                    try:
                        abort_manager.reset()
                    except Exception:
                        pass
                    break
                time.sleep(step)
                waited += step

            def _reenable():
                try:
                    load_btn.config(state='normal')
                except Exception:
                    pass
                try:
                    abort_btn.config(state='disabled')
                except Exception:
                    pass
                try:
                    status_var.set('Aborted.')
                except Exception:
                    pass
                _set_main_status('idle')  # Turn main GUI indicator green

            try:
                win.after(0, _reenable)
            except Exception:
                pass

        threading.Thread(target=_monitor, daemon=True).start()

    abort_btn.config(command=_abort_load)

    def _refresh_file_tv():
        """Rebuild the file treeview from file_entries."""
        if not file_tv:
            return
        file_tv.delete(*file_tv.get_children())
        for i, entry in enumerate(file_entries):
            sheet = entry.get('sheet') or '-'
            file_tv.insert("", "end", iid=str(i), values=(
                os.path.basename(entry['path']),
                sheet,
                entry['rows'],
                entry['cols'],
                entry['table_name'],
            ))

    # Track the currently-selected file entry index so we can persist
    # index selections when switching between files.
    _current_file_idx = [None]  # mutable container so nested functions can update

    def _save_selections():
        """Save the current idx_list, key_list, and upd_list selections to the active file entry."""
        cidx = _current_file_idx[0]
        if cidx is not None and cidx < len(file_entries):
            sel = idx_list.curselection()
            file_entries[cidx]['index_selections'] = [idx_list.get(i) for i in sel]
            # Save upsert selections
            key_sel = key_list.curselection()
            file_entries[cidx]['upsert_key_selections'] = [key_list.get(i) for i in key_sel]
            upd_sel = upd_list.curselection()
            file_entries[cidx]['upsert_upd_selections'] = [upd_list.get(i) for i in upd_sel]

    def _on_file_select(event=None):
        """When a file is selected in the file treeview, show its column preview."""
        sel = file_tv.selection() if file_tv else ()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(file_entries):
            return

        # Save selections from the previously-selected file
        _save_selections()

        entry = file_entries[idx]
        _current_file_idx[0] = idx
        table_name_var.set(entry['table_name'])

        # Populate column preview
        if col_tv:
            col_tv.delete(*col_tv.get_children())
        df = entry['df']
        col_sizes = entry.get('col_sizes', {})
        for col in df.columns:
            max_len = df[col].astype(str).str.len().max()
            if pd.isna(max_len):
                max_len = 0
            else:
                max_len = int(max_len)
            oracle_size = col_sizes.get(col.upper(), 4000) if sizing_mode_var.get() == 0 else 4000
            # Sample: first 3 non-empty unique values
            uniq = df[col].dropna().astype(str).unique()[:3]
            sample = ', '.join(uniq)
            if len(sample) > 60:
                sample = sample[:57] + '...'
            if col_tv:
                col_tv.insert("", "end", values=(col, max_len, oracle_size, sample))

        # Populate index column list — in batch mode, only repopulate if empty
        # (columns are identical across files) to preserve selections.
        is_batch = batch_mode_var.get() == 1
        if is_batch and idx_list.size() > 0:
            # Batch mode: keep existing list and selections as-is
            pass
        else:
            idx_list.delete(0, END)
            for col in df.columns:
                idx_list.insert(END, col)
            # Restore previously-saved index selections for this entry
            saved = entry.get('index_selections', [])
            if saved:
                all_items = [idx_list.get(i) for i in range(idx_list.size())]
                for i, item in enumerate(all_items):
                    if item in saved:
                        idx_list.selection_set(i)

        # Populate upsert column lists and restore saved selections
        key_list.delete(0, END)
        upd_list.delete(0, END)
        for col in df.columns:
            key_list.insert(END, col)
        for col in df.columns:
            upd_list.insert(END, col)

        # Restore saved upsert selections for this entry
        saved_keys = entry.get('upsert_key_selections', [])
        if saved_keys:
            all_keys = [key_list.get(i) for i in range(key_list.size())]
            for i, item in enumerate(all_keys):
                if item in saved_keys:
                    key_list.selection_set(i)
        saved_upd = entry.get('upsert_upd_selections', [])
        if saved_upd:
            all_upd = [upd_list.get(i) for i in range(upd_list.size())]
            for i, item in enumerate(all_upd):
                if item in saved_upd:
                    upd_list.selection_set(i)

    if file_tv:
        file_tv.bind('<<TreeviewSelect>>', _on_file_select)

    def _add_files():
        """Open file dialog and add selected files."""
        paths = filedialog.askopenfilenames(
            parent=win,
            title='Select files to load',
            filetypes=[
                ('Data Files', '*.csv *.xlsx *.xls'),
                ('CSV Files', '*.csv'),
                ('Excel Files', '*.xlsx *.xls'),
                ('All Files', '*.*'),
            ]
        )
        if not paths:
            return

        for path in paths:
            # Duplicate detection
            existing_paths = [(e['path'], e.get('sheet')) for e in file_entries]

            lower = path.lower()
            if lower.endswith('.csv'):
                if (path, None) in existing_paths:
                    continue
                try:
                    df = pd.read_csv(path)
                    df = clean_column_names(df)
                    file_name = os.path.splitext(os.path.basename(path))[0]
                    file_prefix = file_name.replace('-', '_').replace(' ', '_').upper()
                    df.columns = [col.replace(f"{file_prefix}_", "") for col in df.columns]
                    df = df.astype(str).fillna('')
                    tbl_name = _sanitize_table_name(file_name)
                    col_sizes = _compute_col_sizes(df)
                    file_entries.append({
                        'path': path, 'sheet': None, 'df': df,
                        'table_name': tbl_name,
                        'rows': len(df), 'cols': len(df.columns),
                        'col_sizes': col_sizes, 'columns': list(df.columns),
                        'index_selections': [],
                        'upsert_key_selections': [],
                        'upsert_upd_selections': [],
                    })
                except Exception as e:
                    logger.exception(f'Failed to read CSV {path}: {e}')
                    _safe_messagebox('showerror', 'Read Error', f'Failed to read {os.path.basename(path)}:\n{e}', dlg=win)

            elif lower.endswith(('.xlsx', '.xls')):
                try:
                    xls = pd.ExcelFile(path)
                    sheets = xls.sheet_names
                    if not sheets:
                        continue

                    # If multiple sheets, let user pick via a quick dialog
                    if len(sheets) > 1:
                        selected_sheets = _pick_sheets(path, sheets)
                        if not selected_sheets:
                            continue
                    else:
                        selected_sheets = sheets

                    file_name = os.path.splitext(os.path.basename(path))[0]
                    for sheet in selected_sheets:
                        if (path, sheet) in existing_paths:
                            continue
                        try:
                            df = pd.read_excel(xls, sheet_name=sheet)
                            df = clean_column_names(df)
                            df = df.astype(str).fillna('')
                            if len(sheets) > 1:
                                tbl_name = _sanitize_table_name(f'{file_name}_{sheet}')
                            else:
                                tbl_name = _sanitize_table_name(file_name)
                            col_sizes = _compute_col_sizes(df)
                            file_entries.append({
                                'path': path, 'sheet': sheet, 'df': df,
                                'table_name': tbl_name,
                                'rows': len(df), 'cols': len(df.columns),
                                'col_sizes': col_sizes, 'columns': list(df.columns),
                                'index_selections': [],
                                'upsert_key_selections': [],
                                'upsert_upd_selections': [],
                            })
                        except Exception as e:
                            logger.exception(f'Failed to read sheet {sheet} from {path}: {e}')
                except Exception as e:
                    logger.exception(f'Failed to read Excel {path}: {e}')
                    _safe_messagebox('showerror', 'Read Error', f'Failed to read {os.path.basename(path)}:\n{e}', dlg=win)

        _refresh_file_tv()
        # Auto-select first entry
        if file_tv and file_entries:
            file_tv.selection_set('0')
            _on_file_select()

    def _pick_sheets(path, sheets):
        """Show a small dialog to let the user select which sheets to load."""
        result = []
        dlg = Toplevel(win)
        dlg.title(f'Select Sheets: {os.path.basename(path)}')
        
        # Apply theme immediately after creating dialog
        gui_utils.apply_theme_to_dialog(dlg)
        
        dlg.transient(win)
        dlg.grab_set()

        Label(dlg, text='Select sheets to load:', font=("Arial", 10, 'bold')).pack(pady=(8, 4))

        vars_ = {}
        for sheet in sheets:
            var = IntVar(value=1)
            tk.Checkbutton(dlg, text=sheet, variable=var).pack(anchor='w', padx=16)
            vars_[sheet] = var

        def _ok():
            for sheet, var in vars_.items():
                if var.get():
                    result.append(sheet)
            dlg.destroy()

        def _cancel():
            dlg.destroy()

        bf = Frame(dlg)
        bf.pack(pady=8)
        Button(bf, text='OK', width=8, command=_ok).pack(side=LEFT, padx=4)
        Button(bf, text='Cancel', width=8, command=_cancel).pack(side=LEFT, padx=4)

        # Live theme update callback
        def _on_dlg_theme_change(theme_key):
            try:
                gui_utils.apply_theme_to_existing_widgets(dlg)
            except Exception:
                pass
        
        # Register theme callback and unregister on destroy
        try:
            gui_utils.register_theme_callback(_on_dlg_theme_change)
            def _on_dlg_destroy(event=None):
                if event and event.widget == dlg:
                    try:
                        gui_utils.unregister_theme_callback(_on_dlg_theme_change)
                    except Exception:
                        pass
            dlg.bind('<Destroy>', _on_dlg_destroy)
        except Exception:
            pass

        dlg.protocol('WM_DELETE_WINDOW', _cancel)
        dlg.wait_window()
        return result

    def _remove_selected():
        sel = file_tv.selection() if file_tv else ()
        if not sel:
            return
        indices = sorted([int(s) for s in sel], reverse=True)
        for idx in indices:
            if idx < len(file_entries):
                del file_entries[idx]
        _refresh_file_tv()
        if col_tv:
            col_tv.delete(*col_tv.get_children())

    def _clear_all():
        file_entries.clear()
        _refresh_file_tv()
        if col_tv:
            col_tv.delete(*col_tv.get_children())
        table_name_var.set('')

    def _apply_rename():
        sel = file_tv.selection() if file_tv else ()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(file_entries):
            return
        new_name = _sanitize_table_name(table_name_var.get())
        if new_name:
            file_entries[idx]['table_name'] = new_name
            _refresh_file_tv()
            try:
                file_tv.selection_set(str(idx))
            except Exception:
                pass

    add_btn.config(command=_add_files)
    remove_btn.config(command=_remove_selected)
    clear_btn.config(command=_clear_all)
    rename_btn.config(command=_apply_rename)

    # Auto-apply rename when user tabs out or clicks away from the name entry
    def _on_name_entry_focus_out(event=None):
        _apply_rename()
    name_entry.bind('<FocusOut>', _on_name_entry_focus_out)
    # Also apply on Enter key
    name_entry.bind('<Return>', _on_name_entry_focus_out)

    # =========================================================================
    # Load execution
    # =========================================================================
    def _execute_load():
        if not file_entries:
            _safe_messagebox('showwarning', 'No Files', 'Add at least one file to load.', dlg=win)
            return

        is_single = batch_mode_var.get() == 1
        use_tight = sizing_mode_var.get() == 0
        mode = load_mode_var.get()  # 0=create, 1=append, 2=replace, 3=upsert
        do_preview = preview_var.get() == 1

        # Validate batch single-table mode: all files must have same columns
        if is_single and len(file_entries) > 1:
            base_cols = set(c.upper() for c in file_entries[0]['columns'])
            for entry in file_entries[1:]:
                entry_cols = set(c.upper() for c in entry['columns'])
                if entry_cols != base_cols:
                    _safe_messagebox('showerror', 'Column Mismatch',
                        f'Cannot merge into single table: column mismatch.\n\n'
                        f'{os.path.basename(file_entries[0]["path"])}: {sorted(base_cols)}\n'
                        f'{os.path.basename(entry["path"])}: {sorted(entry_cols)}',
                        dlg=win)
                    return

        # Get upsert config if needed
        upsert_keys = []
        upsert_updates = []
        if mode == 3:
            key_sel = key_list.curselection()
            upd_sel = upd_list.curselection()
            if not key_sel:
                _safe_messagebox('showwarning', 'Upsert Keys', 'Select at least one key column for MERGE ON.', dlg=win)
                return
            upsert_keys = [key_list.get(i) for i in key_sel]
            upsert_updates = [upd_list.get(i) for i in upd_sel]
            if not upsert_updates:
                upsert_updates = [c for c in file_entries[0]['columns'] if c not in upsert_keys]

        # Save current selections to the active file entry before snapshotting
        _save_selections()

        # Capture index columns to create after loading.
        # In batch mode (single table), use the current listbox selection for all.
        # In separate mode, each file_entry carries its own 'index_selections'.
        idx_sel = idx_list.curselection()
        index_columns = [idx_list.get(i) for i in idx_sel] if idx_sel else []

        # Disable controls during load; enable Abort
        load_btn.config(state='disabled')
        abort_btn.config(state='normal')
        status_var.set('Loading...')
        _set_main_status('busy')  # Turn main GUI indicator red
        win.update_idletasks()

        # Use the connection established at GUI startup
        conn = _conn_info['conn']
        schema = _conn_info['schema']

        try:
            abort_manager.register_connection(conn)
        except Exception:
            pass

        # Snapshot entries for the worker (avoid reading UI from background)
        _entries_snapshot = list(file_entries)
        _single_tbl = _sanitize_table_name(single_table_var.get()) or 'BATCH_LOAD'

        def _worker():
            nonlocal is_single, use_tight, mode, do_preview, upsert_keys, upsert_updates, index_columns
            cursor = None
            try:
                cursor = conn.cursor()
                abort_manager.reset()

                if is_single:
                    # Merge all DataFrames into one
                    combined_df = pd.concat([e['df'] for e in _entries_snapshot], ignore_index=True)
                    combined_df = combined_df.astype(str).fillna('')
                    tbl_name = _single_tbl
                    col_sizes = _compute_col_sizes(combined_df) if use_tight else None

                    total_rows = len(combined_df)
                    try:
                        if win.winfo_exists():
                            win.after(0, lambda: status_var.set(f'Loading {total_rows} rows into {schema}.{tbl_name}...'))
                    except Exception:
                        pass

                    _load_one_table(conn, cursor, schema, tbl_name, combined_df,
                                    col_sizes, mode, do_preview, upsert_keys, upsert_updates,
                                    index_columns)
                else:
                    total = len(_entries_snapshot)
                    for i, entry in enumerate(_entries_snapshot):
                        if getattr(abort_manager, 'should_abort', False):
                            logger.info('Abort requested during batch load')
                            break
                        tbl_name = entry['table_name']
                        df = entry['df']
                        col_sizes = entry['col_sizes'] if use_tight else None
                        # In separate mode, use per-file index selections
                        entry_idx_cols = entry.get('index_selections', []) or index_columns

                        try:
                            if win.winfo_exists():
                                win.after(0, lambda tn=tbl_name, idx=i: status_var.set(
                                    f'Loading file {idx+1}/{total}: {schema}.{tn}...'))
                        except Exception:
                            pass

                        _load_one_table(conn, cursor, schema, tbl_name, df,
                                        col_sizes, mode, do_preview, upsert_keys, upsert_updates,
                                        entry_idx_cols)

                try:
                    conn.commit()
                except Exception:
                    pass

                logger.info('All files processed.')
                try:
                    if win.winfo_exists():
                        win.after(0, lambda: status_var.set('All files loaded successfully.'))
                except Exception:
                    pass

                # Clear the file list pane on success
                def _clear_after_load():
                    try:
                        file_entries.clear()
                        _current_file_idx[0] = None
                        _refresh_file_tv()
                        if col_tv:
                            col_tv.delete(*col_tv.get_children())
                        idx_list.delete(0, END)
                        key_list.delete(0, END)
                        upd_list.delete(0, END)
                        table_name_var.set('')
                    except tk.TclError:
                        pass
                try:
                    if win.winfo_exists():
                        win.after(0, _clear_after_load)
                except Exception:
                    pass

            except Exception as e:
                logger.exception(f'Load failed: {e}')
                try:
                    if win.winfo_exists():
                        win.after(0, lambda: status_var.set(f'Error: {e}'))
                except Exception:
                    pass
            finally:
                try:
                    if cursor:
                        cursor.close()
                except Exception:
                    pass
                # NOTE: Don't close conn here - keep it open for multiple loads
                # Connection will be closed when window is closed
                try:
                    abort_manager.reset()
                except Exception:
                    pass
                def _on_worker_done():
                    try:
                        # Check if widgets still exist before updating them
                        if win.winfo_exists():
                            try:
                                load_btn.config(state='normal')
                            except tk.TclError:
                                pass
                            try:
                                abort_btn.config(state='disabled')
                            except tk.TclError:
                                pass
                        _set_main_status('idle')  # Turn main GUI indicator green
                    except Exception:
                        pass
                try:
                    win.after(0, _on_worker_done)
                except Exception:
                    pass

        def _load_one_table(conn, cursor, schema, tbl_name, df, col_sizes, mode,
                            do_preview, upsert_keys, upsert_updates,
                            index_cols_to_create=None):
            """Process a single table load (create / append / replace / upsert).

            Parameters
            ----------
            index_cols_to_create : list or None
                Column names to create individual indexes on after loading.
            """
            cols_exist = get_table_columns(cursor, schema, tbl_name)

            if mode == 0:
                # Create New: drop + create + insert
                if do_preview:
                    # Build CREATE TABLE SQL for preview
                    def _build_col_def(col):
                        if col_sizes and col.upper() in {k.upper() for k in col_sizes}:
                            for k, v in col_sizes.items():
                                if k.upper() == col.upper():
                                    return f'"{col}" VARCHAR2({v})'
                        return f'"{col}" VARCHAR2(4000)'
                    cols_sql = ', '.join([_build_col_def(c) for c in df.columns])
                    create_sql = f'CREATE TABLE {schema}.{tbl_name} ({cols_sql})'
                    sample = df.iloc[0].to_dict() if len(df) > 0 else None
                    ins_sql = build_insert_preview_sql(schema, tbl_name, list(df.columns), sample)
                    combined_sql = create_sql + ";\n\n" + ins_sql
                    summary = f"Rows: {len(df)}\nColumns: {len(df.columns)}\nThis will DROP existing table (if any) and CREATE a new one."
                    # Preview must run on main thread
                    result = [None]
                    import threading
                    ev = threading.Event()
                    def _show():
                        result[0] = show_sql_preview(win, f"CREATE TABLE Preview: {schema}.{tbl_name}", summary, combined_sql)
                        ev.set()
                    win.after(0, _show)
                    ev.wait()
                    if not result[0]:
                        return

                drop_table_if_exists(cursor, schema, tbl_name)
                create_table(cursor, schema, tbl_name, df, col_sizes=col_sizes)
                success = insert_data(cursor, schema, tbl_name, df, conn)
                if success:
                    logger.info(f'Loaded {len(df)} rows into new table {schema}.{tbl_name}')
                else:
                    logger.warning(f'Insert aborted for {schema}.{tbl_name}')

            elif mode == 1:
                # Append
                if not cols_exist:
                    # Table doesn't exist: create it first
                    create_table(cursor, schema, tbl_name, df, col_sizes=col_sizes)
                    cols_exist = get_table_columns(cursor, schema, tbl_name)

                existing_set = set(c.upper() for c in cols_exist)
                incoming_set = set(c.upper() for c in df.columns)

                if existing_set == incoming_set:
                    insert_cols = list(df.columns)
                elif incoming_set.issubset(existing_set):
                    insert_cols = list(df.columns)
                else:
                    # Filter to matching columns only
                    insert_cols = [c for c in df.columns if c.upper() in existing_set]
                    if not insert_cols:
                        logger.error(f'No matching columns for append to {schema}.{tbl_name}')
                        return

                if do_preview:
                    sample = df.iloc[0].to_dict() if len(df) > 0 else None
                    ins_sql = build_insert_preview_sql(schema, tbl_name, insert_cols, sample)
                    summary = f"Rows: {len(df)}\nInsert columns: {insert_cols}"
                    # Preview must run on main thread
                    result = [None]
                    import threading
                    ev = threading.Event()
                    def _show():
                        result[0] = show_sql_preview(win, f"INSERT Preview: {schema}.{tbl_name}", summary, ins_sql)
                        ev.set()
                    win.after(0, _show)
                    ev.wait()
                    if not result[0]:
                        return

                inserted = bulk_insert_chunked(conn, cursor, schema, tbl_name, df,
                                               insert_columns=insert_cols)
                logger.info(f'Appended {inserted} rows to {schema}.{tbl_name}')

            elif mode == 2:
                # Replace
                if not cols_exist:
                    create_table(cursor, schema, tbl_name, df, col_sizes=col_sizes)

                if do_preview:
                    existing_cols_list = get_table_columns(cursor, schema, tbl_name)
                    existing_set = set(c.upper() for c in existing_cols_list)
                    insert_cols = [c for c in df.columns if c.upper() in existing_set] or list(df.columns)
                    sample = df.iloc[0].to_dict() if len(df) > 0 else None
                    trunc_sql = f"TRUNCATE TABLE {schema}.{tbl_name}"
                    ins_sql = build_insert_preview_sql(schema, tbl_name, insert_cols, sample)
                    combined = trunc_sql + "\n" + ins_sql
                    summary = f"Rows: {len(df)}\nTRUNCATE then INSERT."
                    result = [None]
                    import threading
                    ev = threading.Event()
                    def _show():
                        result[0] = show_sql_preview(win, f"REPLACE Preview: {schema}.{tbl_name}", summary, combined)
                        ev.set()
                    win.after(0, _show)
                    ev.wait()
                    if not result[0]:
                        return

                replace_table_with_df(conn, cursor, win, schema, tbl_name, df)
                logger.info(f'Replaced {schema}.{tbl_name}')

            elif mode == 3:
                # Upsert (MERGE)
                if not cols_exist:
                    create_table(cursor, schema, tbl_name, df, col_sizes=col_sizes)
                    # After creating, just do a plain insert since no existing data
                    inserted = bulk_insert_chunked(conn, cursor, schema, tbl_name, df)
                    logger.info(f'Created and inserted {inserted} rows into {schema}.{tbl_name} (upsert, new table)')
                    return

                import time as _time
                ts = int(_time.time())
                stg = f"{tbl_name}__STG_{ts}"
                create_staging_table_from_df(cursor, schema, stg, df)
                inserted = bulk_insert_chunked(conn, cursor, schema, stg, df)
                logger.info(f'Loaded staging {schema}.{stg} ({inserted} rows)')

                key_cols = [k.upper() for k in upsert_keys]
                upd_cols = [u.upper() for u in upsert_updates] if upsert_updates else None

                res = merge_with_checks(conn, cursor, schema, tbl_name, stg,
                                        key_cols, upd_cols, dry_run=True)
                if not res.get('ok'):
                    logger.error(f'Merge pre-check failed: {res.get("message")}')
                    try:
                        _safe_messagebox('showerror', 'Merge Failed',
                                         f'Pre-check failed:\n{res.get("message")}', dlg=win)
                    except Exception:
                        pass
                    try:
                        cursor.execute(f"DROP TABLE {schema}.{stg} PURGE")
                    except Exception:
                        pass
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    return

                if do_preview:
                    summary = (f"Staging rows: {res['total_staging']}\n"
                               f"Matched (update): {res['matched']}\n"
                               f"New (insert): {res['to_insert']}")
                    result = [None]
                    import threading
                    ev = threading.Event()
                    def _show():
                        result[0] = show_sql_preview(win, f"MERGE Preview: {schema}.{tbl_name}",
                                                     summary, res.get('sql', ''))
                        ev.set()
                    win.after(0, _show)
                    ev.wait()
                    if not result[0]:
                        try:
                            cursor.execute(f"DROP TABLE {schema}.{stg} PURGE")
                            conn.commit()
                        except Exception:
                            pass
                        return

                exec_res = merge_with_checks(conn, cursor, schema, tbl_name, stg,
                                             key_cols, upd_cols, dry_run=False)
                if not exec_res.get('ok'):
                    logger.error(f'MERGE failed: {exec_res.get("message")}')
                else:
                    logger.info(f'Upsert complete for {schema}.{tbl_name}')

                try:
                    cursor.execute(f"DROP TABLE {schema}.{stg} PURGE")
                    conn.commit()
                except Exception:
                    pass

            # --- Create individual indexes on user-selected columns ---
            if index_cols_to_create:
                for idx_col in index_cols_to_create:
                    # Check for abort before each index creation
                    if getattr(abort_manager, 'should_abort', False):
                        logger.info('Abort requested during index creation')
                        break
                    try:
                        create_index_if_columns_exist(cursor, schema, tbl_name, [idx_col])
                    except Exception as e:
                        # Downgrade DPY disconnect errors during abort to debug level
                        if abort_manager.is_expected_disconnect(e):
                            logger.debug(f'Index creation interrupted (abort): {idx_col}')
                        else:
                            logger.warning(f'Failed to create index on {idx_col} for {schema}.{tbl_name}: {e}')
                try:
                    conn.commit()
                except Exception:
                    pass

        # Spawn the worker thread to perform DB operations in the background
        threading.Thread(target=_worker, daemon=True).start()

    # Wire the Load button — _execute_load reads UI state on the main thread
    # then spawns _worker in a background thread for DB operations.
    load_btn.config(command=_execute_load)

    # --- Center and show ---
    # Import center_window from index_gui which has the DPI-aware version
    try:
        from tools.index_gui import center_window as _center
    except Exception:
        def _center(w, width, height):
            w.update_idletasks()
            sw = w.winfo_screenwidth()
            sh = w.winfo_screenheight()
            x = int((sw - width) / 2)
            y = int((sh - height) / 2)
            w.geometry(f"{width}x{height}+{x}+{y}")

    _center(win, 960, 860)
    try:
        win.deiconify()
        win.lift()
        win.focus_force()
        try:
            win.attributes('-topmost', True)
            win.after(200, lambda: win.attributes('-topmost', False))
        except Exception:
            pass
        win.grab_set()
    except Exception:
        pass

    # --- Theme support ---
    def _theme_cb(enable_dark):
        try:
            bg = '#0b0b0b' if enable_dark else 'white'
            fg = '#e6e6e6' if enable_dark else 'black'
            name_entry.config(bg=bg, fg=fg, insertbackground=fg)
            single_entry.config(bg=bg, fg=fg, insertbackground=fg)
        except Exception:
            pass

    try:
        if parent and hasattr(parent, 'register_theme_callback'):
            parent.register_theme_callback(_theme_cb)
            def _on_destroy(event=None):
                try:
                    parent.unregister_theme_callback(_theme_cb)
                except Exception:
                    pass
            win.bind('<Destroy>', _on_destroy)
    except Exception:
        pass

    # --- Window close handler ---
    def _on_window_close():
        # Close the database connection when window is closed
        try:
            if _conn_info.get('conn'):
                _conn_info['conn'].close()
                _conn_info['conn'] = None
        except Exception:
            logger.debug('Failed to close connection on window close', exc_info=True)
        try:
            session.close_connections(parent)
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass

    win.protocol('WM_DELETE_WINDOW', _on_window_close)

    # Live theme update callback
    def _on_theme_change(theme_key):
        try:
            gui_utils.apply_theme_to_existing_widgets(win)
        except Exception:
            pass
    
    # Register theme callback and unregister on destroy
    try:
        gui_utils.register_theme_callback(_on_theme_change)
        def _on_theme_destroy(event=None):
            if event and event.widget == win:
                try:
                    gui_utils.unregister_theme_callback(_on_theme_change)
                except Exception:
                    pass
        win.bind('<Destroy>', _on_theme_destroy)
    except Exception:
        pass

    # --- Wait ---
    try:
        if parent:
            try:
                win.wait_window()
            except tk.TclError:
                pass
        else:
            try:
                win.mainloop()
            except tk.TclError:
                pass
    finally:
        # Call on_finish callback when dialog is closed
        if on_finish:
            try:
                on_finish()
            except Exception:
                pass


if __name__ == '__main__':
    load_files_gui()

