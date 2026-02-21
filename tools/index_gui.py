import re
import logging
import tkinter as tk
try:
    import tkinter.ttk as ttk
except Exception:
    ttk = None
from tkinter import Toplevel, Listbox, Scrollbar, Button, Label, Entry, StringVar, IntVar
from tkinter.constants import MULTIPLE, END, LEFT, RIGHT, Y, BOTH, EXTENDED

from libs.oracle_db_connector import get_db_connection
from libs import session

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
    """Center *window* on the monitor that contains it (or the cursor)."""
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

    # Try DPI-aware, multi-monitor centering on Windows
    try:
        import sys
        if sys.platform.startswith("win"):
            import ctypes

            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            class RECT(ctypes.Structure):
                _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                            ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                            ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

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
                        window.geometry(f"{w}x{h}+{x}+{y}")
                        return
    except Exception:
        pass

    # Fallback: center on primary screen
    sw = window.winfo_screenwidth()
    sh = window.winfo_screenheight()
    x = int((sw - w) / 2)
    y = int((sh - h) / 2)
    window.geometry(f"{w}x{h}+{x}+{y}")


def _quote_ident(name):
    """Quote an Oracle identifier."""
    return f'"{name}"'


def _sanitize_index_name(name: str, max_len: int = 128) -> str:
    """Sanitize and truncate an index name to Oracle's identifier limit.

    Oracle 12.2+ supports up to 128-character identifiers.
    Older versions use a 30-character limit.  Default to 128; callers
    targeting older databases can pass max_len=30.
    """
    cand = re.sub(r'[^A-Za-z0-9]', '_', name).upper()
    return cand[:max_len]


def _ensure_dialog_parent(parent):
    """Return a Toplevel attached to parent, or a new Tk root when None.

    The window is created but NOT yet centered — the caller should call
    ``center_window`` after building the dialog contents so the geometry
    request reflects the final size.
    """
    if parent:
        win = Toplevel(parent)
        try:
            win.transient(parent)
        except Exception:
            pass
        return win
    else:
        root = tk.Tk()
        return root


def main(parent=None, schema=None, object_name=None, object_type=None, on_finish=None):
    """Entry point for the Index Manager tool.

    Parameters
    ----------
    parent : tk widget or None
        The launcher root window (for parenting the dialog).
    schema : str
        The Oracle schema/owner (e.g. 'DWH' or the user's username).
    object_name : str
        The table or materialized view name.
    object_type : str
        'TABLE' or 'MATERIALIZED VIEW'.
    on_finish : callable or None
        Optional callback invoked when the dialog is closed.
    """
    if not schema or not object_name:
        _safe_messagebox('showwarning', 'Missing Info', 'Schema and object name are required.', dlg=parent)
        return

    # Determine connection type based on schema
    is_dwh = schema.upper() == 'DWH'
    schema_key = 'schema2' if is_dwh else 'schema1'
    conn = get_db_connection(schema=schema_key, root=parent)
    if not conn:
        logger.error('Failed to get DB connection for index tool')
        return

    # Register connection for cleanup
    try:
        if parent:
            session.register_connection(parent, conn, schema_key)
    except Exception:
        logger.debug('Failed to register connection', exc_info=True)

    owner = schema.upper()

    # --- Build the dialog ---
    win = _ensure_dialog_parent(parent)
    win.title(f'Index Manager - {owner}.{object_name}')

    # List to track all buttons for dark mode styling
    _all_buttons = []

    # === Main layout: left (columns) + right (existing indexes) ===
    main_frame = tk.Frame(win)
    main_frame.pack(fill=BOTH, expand=True, padx=8, pady=8)

    left_frame = tk.Frame(main_frame)
    left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 6))

    right_frame = tk.Frame(main_frame)
    right_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(6, 0))

    # --- Left: Column list (multi-select) ---
    Label(left_frame, text='Columns (select one or more)', font=("Arial", 10, 'bold')).pack(anchor='w')

    col_list_frame = tk.Frame(left_frame)
    col_list_frame.pack(fill=BOTH, expand=True, pady=(4, 0))

    col_list = Listbox(col_list_frame, width=40, height=20, selectmode=EXTENDED, exportselection=False)
    col_scroll = Scrollbar(col_list_frame, command=col_list.yview)
    col_list.config(yscrollcommand=col_scroll.set)
    col_list.pack(side=LEFT, fill=BOTH, expand=True)
    col_scroll.pack(side=RIGHT, fill=Y)

    # --- Right: Existing indexes ---
    Label(right_frame, text='Existing Indexes', font=("Arial", 10, 'bold')).pack(anchor='w')

    idx_list_frame = tk.Frame(right_frame)
    idx_list_frame.pack(fill=BOTH, expand=True, pady=(4, 0))

    idx_tree = None
    if ttk:
        idx_tree = ttk.Treeview(idx_list_frame, columns=("index_name", "columns", "uniqueness"), show="headings", height=16)
        idx_tree.heading("index_name", text="Index Name")
        idx_tree.heading("columns", text="Columns")
        idx_tree.heading("uniqueness", text="Type")
        idx_tree.column("index_name", width=160, anchor="w")
        idx_tree.column("columns", width=180, anchor="w")
        idx_tree.column("uniqueness", width=80, anchor="center")
        idx_scroll = Scrollbar(idx_list_frame, orient="vertical", command=idx_tree.yview)
        idx_tree.configure(yscrollcommand=idx_scroll.set)
        idx_tree.pack(side=LEFT, fill=BOTH, expand=True)
        idx_scroll.pack(side=RIGHT, fill=Y)
    else:
        # Fallback: plain Listbox
        idx_listbox = Listbox(idx_list_frame, width=50, height=16, exportselection=False)
        idx_lb_scroll = Scrollbar(idx_list_frame, command=idx_listbox.yview)
        idx_listbox.config(yscrollcommand=idx_lb_scroll.set)
        idx_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        idx_lb_scroll.pack(side=RIGHT, fill=Y)

    # --- Controls area (below main_frame) ---
    ctrl_frame = tk.Frame(win)
    ctrl_frame.pack(fill='x', padx=8, pady=(4, 0))

    # Index creation mode: Individual vs Composite
    mode_var = IntVar(value=0)  # 0 = Individual, 1 = Composite

    mode_frame = tk.Frame(ctrl_frame)
    mode_frame.pack(fill='x', pady=(0, 6))

    Label(mode_frame, text='Index Mode:', font=("Arial", 9, 'bold')).pack(side=LEFT, padx=(0, 8))
    tk.Radiobutton(mode_frame, text='Individual (one index per column)', variable=mode_var, value=0, command=lambda: _update_index_name()).pack(side=LEFT, padx=(0, 12))
    tk.Radiobutton(mode_frame, text='Composite (one index on all selected columns)', variable=mode_var, value=1, command=lambda: _update_index_name()).pack(side=LEFT)

    # Index name (editable, mainly for composite mode)
    name_frame = tk.Frame(ctrl_frame)
    name_frame.pack(fill='x', pady=(0, 6))

    Label(name_frame, text='Index Name (composite):', font=("Arial", 9)).pack(side=LEFT, padx=(0, 8))
    index_name_var = StringVar()
    name_entry = Entry(name_frame, textvariable=index_name_var, width=40)
    name_entry.pack(side=LEFT)

    # Info label — shows mode hint or key size estimate
    info_label = Label(name_frame, text='(auto-generated per column in Individual mode)', font=("Arial", 8), fg='#666666')
    info_label.pack(side=LEFT, padx=(8, 0))

    # Key size label — shows estimated total bytes for composite index
    key_size_label = Label(ctrl_frame, text='', font=("Arial", 8), fg='#666666')
    key_size_label.pack(fill='x', pady=(0, 4))

    # --- Theme support ---
    def _apply_entry_theme(dark=None):
        """Apply dark/light theme to entry widgets."""
        if dark is None:
            # Auto-detect from ttk style
            try:
                if ttk:
                    st = ttk.Style()
                    sbg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
                    if isinstance(sbg, str) and sbg.strip().lower() in ('#000000', '#000', 'black'):
                        dark = True
                    else:
                        dark = False
            except Exception:
                dark = False

        if dark:
            try:
                name_entry.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff')
            except Exception:
                pass
            try:
                col_list.config(bg='#0b0b0b', fg='#e6e6e6', selectbackground='#2a6bd6')
            except Exception:
                pass
        else:
            try:
                name_entry.config(bg='white', fg='black', insertbackground='black')
            except Exception:
                pass
            try:
                col_list.config(bg='white', fg='black', selectbackground='#2a6bd6')
            except Exception:
                pass
        # Apply button styling for dark/light mode
        try:
            for btn in _all_buttons:
                try:
                    if dark:
                        btn.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')
                    else:
                        btn.config(bg='SystemButtonFace', fg='SystemButtonText', activebackground='SystemButtonFace', activeforeground='SystemButtonText')
                except Exception:
                    pass
        except Exception:
            pass

    _apply_entry_theme()

    def _theme_cb(enable_dark: bool):
        _apply_entry_theme(dark=enable_dark)

    # Register theme callback if parent supports it
    try:
        if parent and hasattr(parent, 'register_theme_callback'):
            parent.register_theme_callback(_theme_cb)

            def _on_destroy(event=None):
                try:
                    if parent and hasattr(parent, 'unregister_theme_callback'):
                        parent.unregister_theme_callback(_theme_cb)
                except Exception:
                    pass
            win.bind('<Destroy>', _on_destroy)
    except Exception:
        pass

    # --- Column metadata cache (name -> data_length in bytes) ---
    col_data_lengths = {}  # populated by load_columns()

    # Query the database block size once to determine the max key length
    db_max_key_bytes = 6398  # conservative default for 8 KB block size
    try:
        _param_cur = conn.cursor()
        _param_cur.execute("SELECT value FROM v$parameter WHERE name = 'db_block_size'")
        _row = _param_cur.fetchone()
        if _row:
            _block_size = int(_row[0])
            # Oracle reserves some overhead per block; max key ~ 75% of block size
            db_max_key_bytes = int(_block_size * 0.75) - 6
        _param_cur.close()
    except Exception:
        # v$parameter may not be accessible; keep the default
        pass

    # --- Data loading functions ---
    def load_columns():
        """Load columns for the selected object into the column list."""
        col_list.delete(0, END)
        col_data_lengths.clear()
        cur = conn.cursor()
        try:
            cur.execute('''
                SELECT column_name, data_type, data_length, nullable
                FROM all_tab_columns
                WHERE owner = :own AND table_name = :tbl
                ORDER BY column_id
            ''', [owner, object_name])
            rows = cur.fetchall()
            for col_name, data_type, data_length, nullable in rows:
                col_data_lengths[col_name] = int(data_length) if data_length else 0
                nullable_str = ' (NULLABLE)' if nullable == 'Y' else ''
                display = f"{col_name}  [{data_type}({data_length})]{nullable_str}"
                col_list.insert(END, display)
        except Exception as e:
            logger.exception('Failed to list columns: %s', e)
            _safe_messagebox('showerror', 'Error', f'Failed to list columns: {e}', dlg=win)
        finally:
            cur.close()

    def load_existing_indexes():
        """Load existing indexes for the selected object."""
        if idx_tree:
            try:
                idx_tree.delete(*idx_tree.get_children())
            except Exception:
                pass
        else:
            try:
                idx_listbox.delete(0, END)
            except Exception:
                pass

        cur = conn.cursor()
        try:
            # Get all indexes and their columns for this table
            cur.execute('''
                SELECT ai.index_name,
                       ai.uniqueness,
                       LISTAGG(aic.column_name, ', ') WITHIN GROUP (ORDER BY aic.column_position) AS cols
                FROM all_indexes ai
                JOIN all_ind_columns aic
                  ON ai.owner = aic.index_owner AND ai.index_name = aic.index_name
                WHERE ai.table_owner = :own AND ai.table_name = :tbl
                GROUP BY ai.index_name, ai.uniqueness
                ORDER BY ai.index_name
            ''', [owner, object_name])
            rows = cur.fetchall()
            for idx_name, uniqueness, cols in rows:
                type_str = uniqueness if uniqueness else 'NONUNIQUE'
                if idx_tree:
                    idx_tree.insert("", "end", values=(idx_name, cols, type_str))
                else:
                    idx_listbox.insert(END, f"{idx_name} ({cols}) [{type_str}]")
        except Exception as e:
            logger.exception('Failed to list existing indexes: %s', e)
            _safe_messagebox('showerror', 'Error', f'Failed to list existing indexes: {e}', dlg=win)
        finally:
            cur.close()

    def _get_selected_columns():
        """Return list of column names from current selection."""
        sel_indices = col_list.curselection()
        if not sel_indices:
            return []
        cols = []
        for i in sel_indices:
            raw = col_list.get(i)
            # Parse column name from display format: "COL_NAME  [DATA_TYPE](NULLABLE)"
            col_name = raw.split('  [')[0].strip() if '  [' in raw else raw.strip()
            cols.append(col_name)
        return cols

    def _update_index_name(event=None):
        """Auto-generate index name based on selection and mode."""
        cols = _get_selected_columns()
        if not cols:
            index_name_var.set('')
            key_size_label.config(text='')
            return

        # Calculate total key size for the selection
        total_bytes = sum(col_data_lengths.get(c, 0) for c in cols)

        if mode_var.get() == 0:
            # Individual mode: show hint
            index_name_var.set(f'(auto: {object_name}_<COL>_IDX)')
            key_size_label.config(text=f'{len(cols)} column(s) selected')
        else:
            # Composite mode: generate name and show key size
            col_part = '_'.join(cols)
            name = _sanitize_index_name(f'{object_name}_{col_part}_IDX')
            index_name_var.set(name)
            if total_bytes > db_max_key_bytes:
                key_size_label.config(
                    text=f'Estimated key size: {total_bytes:,} bytes  --  EXCEEDS max ({db_max_key_bytes:,} bytes)',
                    fg='red')
            else:
                key_size_label.config(
                    text=f'Estimated key size: {total_bytes:,} / {db_max_key_bytes:,} bytes',
                    fg='#666666')

    # Bind selection change to update index name
    col_list.bind('<<ListboxSelect>>', _update_index_name)

    def create_indexes():
        """Create indexes based on current selection and mode."""
        cols = _get_selected_columns()
        if not cols:
            _safe_messagebox('showwarning', 'No Columns', 'Please select one or more columns to index.', dlg=win)
            return

        is_individual = (mode_var.get() == 0)
        cur = conn.cursor()

        try:
            if is_individual:
                # Create one index per selected column
                stmts = []
                for col in cols:
                    idx_name = _sanitize_index_name(f'{object_name}_{col}_IDX')
                    sql = f'CREATE INDEX {_quote_ident(idx_name)} ON {_quote_ident(owner)}.{_quote_ident(object_name)} ({_quote_ident(col)})'
                    stmts.append((idx_name, sql))

                # Confirm
                summary = '\n'.join([f'  {name}  ({col})' for (name, _), col in zip(stmts, cols)])
                if not _safe_messagebox('askyesno', 'Confirm Index Creation',
                                        f'Create {len(stmts)} individual index(es) on {owner}.{object_name}?\n\n{summary}',
                                        dlg=win):
                    return

                success_count = 0
                skip_count = 0
                fail_count = 0
                for idx_name, sql in stmts:
                    try:
                        cur.execute(sql)
                        logger.info(f'Created index {idx_name} on {owner}.{object_name}')
                        success_count += 1
                    except Exception as e:
                        err_str = str(e)
                        logger.warning(f'Index creation failed. SQL: {sql}\nError: {err_str}')
                        if 'ORA-01408' in err_str:
                            logger.info(f'Index on same column(s) already exists for {idx_name}. Skipping.')
                            skip_count += 1
                        elif 'ORA-00955' in err_str:
                            logger.info(f'Index name {idx_name} already exists. Skipping.')
                            skip_count += 1
                        elif 'ORA-01450' in err_str:
                            logger.warning(f'Cannot create index {idx_name} - max key length exceeded: {err_str}')
                            fail_count += 1
                        elif 'ORA-00972' in err_str:
                            logger.warning(f'Index name {idx_name} too long for this database: {err_str}')
                            fail_count += 1
                        else:
                            logger.warning(f'Failed to create index {idx_name}: {err_str}')
                            fail_count += 1

                msg_parts = []
                if success_count:
                    msg_parts.append(f'{success_count} created')
                if skip_count:
                    msg_parts.append(f'{skip_count} skipped (already exist)')
                if fail_count:
                    msg_parts.append(f'{fail_count} failed')
                _safe_messagebox('showinfo', 'Index Creation Result', ', '.join(msg_parts) + '.', dlg=win)

            else:
                # Composite mode: one index on all selected columns

                # Pre-validate: estimate total key size in bytes
                total_key_bytes = sum(col_data_lengths.get(c, 0) for c in cols)
                if total_key_bytes > db_max_key_bytes:
                    detail_lines = [f'  {c}: {col_data_lengths.get(c, "?")} bytes' for c in cols]
                    detail = '\n'.join(detail_lines)
                    _safe_messagebox(
                        'showerror', 'Key Too Large',
                        f'The combined column size ({total_key_bytes:,} bytes) exceeds the '
                        f'Oracle max index key length (~{db_max_key_bytes:,} bytes).\n\n'
                        f'Column sizes:\n{detail}\n\n'
                        f'Select fewer or narrower columns for the composite index.',
                        dlg=win)
                    return

                custom_name = index_name_var.get().strip()
                if not custom_name or custom_name.startswith('(auto:'):
                    col_part = '_'.join(cols)
                    custom_name = _sanitize_index_name(f'{object_name}_{col_part}_IDX')

                custom_name = _sanitize_index_name(custom_name)
                col_list_sql = ', '.join([_quote_ident(c) for c in cols])
                sql = f'CREATE INDEX {_quote_ident(custom_name)} ON {_quote_ident(owner)}.{_quote_ident(object_name)} ({col_list_sql})'

                # Show total key size in confirmation
                size_info = f'Estimated key size: {total_key_bytes:,} / {db_max_key_bytes:,} bytes'
                if not _safe_messagebox('askyesno', 'Confirm Index Creation',
                                        f'Create composite index on {owner}.{object_name}?\n\n'
                                        f'Index: {custom_name}\n'
                                        f'Columns: {", ".join(cols)}\n'
                                        f'{size_info}\n\n'
                                        f'SQL:\n{sql}',
                                        dlg=win):
                    return

                try:
                    cur.execute(sql)
                    logger.info(f'Created composite index {custom_name} on {owner}.{object_name}')
                    _safe_messagebox('showinfo', 'Success', f'Composite index {custom_name} created.', dlg=win)
                except Exception as e:
                    err_str = str(e)
                    logger.warning(f'Composite index creation failed. SQL: {sql}\nError: {err_str}')
                    if 'ORA-01408' in err_str:
                        _safe_messagebox('showinfo', 'Already Exists', f'An index on the same column(s) already exists.', dlg=win)
                    elif 'ORA-00955' in err_str:
                        _safe_messagebox('showinfo', 'Already Exists', f'Index name {custom_name} already exists.', dlg=win)
                    elif 'ORA-01450' in err_str:
                        _safe_messagebox('showerror', 'Key Too Large', f'ORA-01450: Max key length exceeded.\n\n{err_str}', dlg=win)
                    elif 'ORA-00972' in err_str:
                        _safe_messagebox('showerror', 'Name Too Long', f'Index name is too long for this database.\n\nTry a shorter custom name.\n\n{err_str}', dlg=win)
                    else:
                        logger.exception(f'Failed to create composite index: {e}')
                        _safe_messagebox('showerror', 'Error', f'Failed to create index:\n\n{err_str}', dlg=win)

            # Refresh the existing indexes list after creation
            load_existing_indexes()

        finally:
            cur.close()

    def drop_selected_index():
        """Drop the currently selected index from the existing indexes tree."""
        if not idx_tree:
            return
        sel = idx_tree.selection()
        if not sel:
            _safe_messagebox('showwarning', 'No Selection', 'Select an index to drop.', dlg=win)
            return

        item = idx_tree.item(sel[0])
        idx_name = item['values'][0] if item.get('values') else None
        if not idx_name:
            return

        if not _safe_messagebox('askyesno', 'Confirm Drop',
                                f'Drop index {idx_name} from {owner}.{object_name}?',
                                dlg=win):
            return

        cur = conn.cursor()
        try:
            cur.execute(f'DROP INDEX {_quote_ident(owner)}.{_quote_ident(idx_name)}')
            logger.info(f'Dropped index {idx_name} from {owner}')
            _safe_messagebox('showinfo', 'Success', f'Index {idx_name} dropped.', dlg=win)
            load_existing_indexes()
        except Exception as e:
            logger.exception(f'Failed to drop index: {e}')
            _safe_messagebox('showerror', 'Error', f'Failed to drop index: {e}', dlg=win)
        finally:
            cur.close()

    # --- Button bar ---
    btn_frame = tk.Frame(win)
    btn_frame.pack(fill='x', padx=8, pady=(6, 8))

    btn_create = Button(btn_frame, text='Create Index', command=create_indexes, width=14)
    btn_drop = Button(btn_frame, text='Drop Selected Index', command=drop_selected_index, width=18)
    btn_refresh = Button(btn_frame, text='Refresh', command=lambda: (load_columns(), load_existing_indexes()), width=10)
    btn_close = Button(btn_frame, text='Close', command=win.destroy, width=10)
    btn_create.pack(side=LEFT, padx=(0, 6))
    btn_drop.pack(side=LEFT, padx=(0, 6))
    btn_refresh.pack(side=LEFT, padx=(0, 6))
    btn_close.pack(side=RIGHT)
    _all_buttons.extend([btn_create, btn_drop, btn_refresh, btn_close])

    # Apply initial dark mode styling to buttons
    try:
        if ttk:
            st = ttk.Style()
            sbg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
            if isinstance(sbg, str) and sbg.strip().lower() in ('#000000', '#000', 'black'):
                for btn in _all_buttons:
                    try:
                        btn.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')
                    except Exception:
                        pass
    except Exception:
        pass

    # --- Center and show the dialog after all widgets are built ---
    center_window(win, 900, 560)
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
        logger.exception('Failed to show/grab index main window')

    # --- Initial data load ---
    load_columns()
    load_existing_indexes()

    # --- Wait for dialog ---
    if parent:
        try:
            win.wait_window()
        except tk.TclError:
            logger.info('Index manager window closed before wait_window completed')
    else:
        try:
            win.mainloop()
        except tk.TclError:
            logger.info('Index manager mainloop terminated unexpectedly')

    # Cleanup session connections
    try:
        target = parent if parent else win
        session.close_connections(target)
    except Exception:
        logger.debug('Session cleanup failed', exc_info=True)

    # Call on_finish callback when window is closed
    if on_finish:
        try:
            on_finish()
        except Exception:
            pass


if __name__ == '__main__':
    main()
