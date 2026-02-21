import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
import logging
import re
from libs.oracle_db_connector import get_db_connection
from libs import session
from libs.gui_utils import is_dark_mode_active, DARK_BG, DARK_FG, DARK_BTN_BG, DARK_BTN_ACTIVE_BG, DARK_SELECT_BG, DARK_INSERT_BG
import ctypes
from libs.paths import ASSETS_PATH
from pathlib import Path

logger = logging.getLogger(__name__)

# reference to Tk's default root if present (use getattr to avoid static-analysis issues)
_tk_default_root = getattr(tk, '_default_root', None)

_MV_HELPERS = {}
try:
    from libs.mv_log_utils import detect_tables_from_sql as _ht, get_dependent_mviews as _gd, detect_existing_mlog as _dm
    _MV_HELPERS['detect_tables_from_sql'] = _ht
    _MV_HELPERS['get_dependent_mviews'] = _gd
    _MV_HELPERS['detect_existing_mlog'] = _dm
except Exception:
    # helpers may not exist in older tree states; fall back to inline implementations below
    pass


def run_sql_mv_loader(parent=None, on_finish=None, use_dwh=False):
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
        # Don't call on_finish here - it would trigger a refresh which prompts again
        return
    
    # Register connection for cleanup
    try:
        session.register_connection(parent if parent else _tk_default_root, conn, schema_key)
    except Exception:
        logger.debug('Failed to register connection', exc_info=True)
    
    def detect_tables_from_sql(sql_text):
        """A conservative table detector: finds tokens after FROM and JOIN. Returns list of unique table identifiers."""
        # prefer shared helper when available
        try:
            helper = _MV_HELPERS.get('detect_tables_from_sql')
            if helper:
                return helper(sql_text)
        except Exception:
            pass
        # fallback to inline implementation
        text = re.sub(r"\s+", " ", sql_text.replace('\n', ' ')).upper()
        candidates = []
        for m in re.finditer(r"(?:FROM|JOIN)\s+([A-Z0-9_\.]+)", text):
            tbl = m.group(1).strip().rstrip(',')
            candidates.append(tbl)
        seen = set(); out = []
        for t in candidates:
            if t not in seen:
                seen.add(t); out.append(t)
        return out

    # Centralized messagebox helper: prefer dlg (when provided), then builder_window,
    # then parent, then unparented. Returns the messagebox result or sensible default.
    # Prefer shared safe_messagebox from loaders package so other loaders can reuse it
    try:
        from loaders import safe_messagebox as _safe_messagebox
    except Exception:
        # Fallback to local shim if import fails
        def _safe_messagebox(fn_name: str, *args, dlg=None):
            try:
                parent_to_use = None
                if dlg is not None:
                    parent_to_use = dlg
                else:
                    try:
                        parent_to_use = builder_window  # may raise NameError if not yet created
                    except Exception:
                        parent_to_use = parent if parent is not None else None
                if parent_to_use is not None:
                    return getattr(messagebox, fn_name)(*args, parent=parent_to_use)
                return getattr(messagebox, fn_name)(*args)
            except Exception:
                try:
                    return getattr(messagebox, fn_name)(*args)
                except Exception:
                    if fn_name.startswith('ask'):
                        return False
                    return None

    def show_create_logs_dialog(tables):
        """Show a modal dialog asking which tables to create logs on.
        Returns (create_flag, selected_tables, log_type, include_new_values) or None if cancelled."""
        try:
            try:
                dlg = tk.Toplevel(builder_window)
            except NameError:
                dlg = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
            dlg.title("Create Materialized View Logs")
            try:
                dlg.transient(builder_window)
            except Exception:
                pass
            dlg.grab_set()
        except Exception as e:
            # If creating the Toplevel fails (threading/root issues), fallback to a simple confirmation
            logger.exception("Failed to open Create Logs dialog: %s", e)
            try:
                try:
                    pb = builder_window
                except NameError:
                    pb = parent
                if pb is not None:
                    create_choice = _safe_messagebox('askyesno', "Create MV Logs?", f"Detected tables: {', '.join(tables)}\nCreate materialized view logs with WITH ROWID and INCLUDING NEW VALUES?", dlg=pb)
                else:
                    create_choice = _safe_messagebox('askyesno', "Create MV Logs?", f"Detected tables: {', '.join(tables)}\nCreate materialized view logs with WITH ROWID and INCLUDING NEW VALUES?", dlg=None)
            except Exception:
                create_choice = False
            if not create_choice:
                return (False, [], None, None)
            return (True, tables, 'ROWID', True)
        tk.Label(dlg, text="The selected MV options require materialized view logs for fast refresh/ON COMMIT.\nSelect tables to create logs on:", justify="left").pack(padx=12, pady=(8, 6))
        checks = []
        frame = tk.Frame(dlg)
        frame.pack(padx=12, pady=6)
        for t in tables:
            var = tk.BooleanVar(value=True)
            cb = tk.Checkbutton(frame, text=t, variable=var)
            cb.pack(anchor="w")
            checks.append((t, var))

        type_var = tk.StringVar(value="ROWID")
        tk.Label(dlg, text="Log Type:").pack(anchor="w", padx=12)
        type_frame = tk.Frame(dlg)
        type_frame.pack(padx=12, pady=(0, 6), anchor="w")
        tk.Radiobutton(type_frame, text="WITH ROWID", variable=type_var, value="ROWID").pack(side="left", padx=(0, 12))
        tk.Radiobutton(type_frame, text="WITH PRIMARY KEY", variable=type_var, value="PRIMARY KEY").pack(side="left")

        new_vals_var = tk.BooleanVar(value=True)
        tk.Checkbutton(dlg, text="INCLUDING NEW VALUES", variable=new_vals_var).pack(anchor="w", padx=12)

        result = {}

        def on_ok():
            selected = [t for (t, v) in checks if v.get()]
            result['value'] = (True, selected, type_var.get(), new_vals_var.get())
            dlg.destroy()

        def on_skip():
            result['value'] = (False, [], None, None)
            dlg.destroy()

        def on_cancel():
            result['value'] = None
            dlg.destroy()

        btnf = tk.Frame(dlg)
        btnf.pack(pady=8)
        # Create buttons with dark mode styling if needed
        _dlg_btns = []
        btn1 = tk.Button(btnf, text="Create Logs & Continue", command=on_ok, width=18)
        btn2 = tk.Button(btnf, text="Skip Logs & Continue", command=on_skip, width=18)
        btn3 = tk.Button(btnf, text="Cancel", command=on_cancel, width=10)
        btn1.pack(side="left", padx=6)
        btn2.pack(side="left", padx=6)
        btn3.pack(side="left", padx=6)
        _dlg_btns.extend([btn1, btn2, btn3])
        # Detect dark mode and style buttons
        try:
            import tkinter.ttk as _ttk_dlg
            st = _ttk_dlg.Style()
            bg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
            if isinstance(bg, str) and bg.strip().lower() in ('#000000', '#000', 'black'):
                for btn in _dlg_btns:
                    btn.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')
        except Exception:
            pass

        dlg.update_idletasks()
        # center dialog
        w = dlg.winfo_width(); h = dlg.winfo_height()
        x = (dlg.winfo_screenwidth() // 2) - (w // 2)
        y = (dlg.winfo_screenheight() // 2) - (h // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        # Use wait_window to avoid nested mainloops
        try:
            dlg.wait_window(dlg)
        except Exception:
            try:
                dlg.mainloop()
            except Exception:
                pass
        return result.get('value')

    def get_dependent_mviews(cursor, table):
        """Return a list of dependent materialized view names for the given table.
        Strategy:
          1) Try ALL_DEPENDENCIES (cross-schema) if permitted
          2) Fallback to USER_DEPENDENCIES
          3) Fallback to a text search of USER_MVIEWS (heuristic)
        Returns list of strings like 'OWNER.MVIEW' or 'MVIEW'.
        """
        # prefer shared helper when available
        try:
            helper = _MV_HELPERS.get('get_dependent_mviews')
            if helper:
                return helper(cursor, table)
        except Exception:
            pass
        parts = table.split('.')
        if len(parts) == 2:
            owner = parts[0].upper()
            base = parts[1].upper()
        else:
            owner = None
            base = parts[-1].upper()

        deps = []
        # Try ALL_DEPENDENCIES first
        try:
            if owner:
                cursor.execute(
                    "SELECT OWNER, NAME FROM ALL_DEPENDENCIES "
                    "WHERE REFERENCED_OWNER = :own AND REFERENCED_NAME = :tbl "
                    "AND REFERENCED_TYPE = 'TABLE' AND TYPE = 'MATERIALIZED VIEW' ORDER BY OWNER, NAME",
                    (owner, base)
                )
            else:
                cursor.execute("SELECT USER FROM DUAL")
                current_user = cursor.fetchone()[0]
                cursor.execute(
                    "SELECT OWNER, NAME FROM ALL_DEPENDENCIES "
                    "WHERE REFERENCED_OWNER = :own AND REFERENCED_NAME = :tbl "
                    "AND REFERENCED_TYPE = 'TABLE' AND TYPE = 'MATERIALIZED VIEW' ORDER BY OWNER, NAME",
                    (current_user, base)
                )
            rows = cursor.fetchall()
            if rows:
                deps = [f"{r[0]}.{r[1]}" for r in rows]
                return deps
        except Exception:
            deps = []

        # Fallback to USER_DEPENDENCIES
        try:
            cursor.execute(
                "SELECT NAME FROM USER_DEPENDENCIES "
                "WHERE REFERENCED_NAME = :tbl AND REFERENCED_TYPE = 'TABLE' AND TYPE = 'MATERIALIZED VIEW'",
                (base,)
            )
            rows = cursor.fetchall()
            if rows:
                deps = [r[0] for r in rows]
                return deps
        except Exception:
            deps = []

        # Last-resort heuristic: text-search USER_MVIEWS
        try:
            cursor.execute(
                "SELECT MVIEW_NAME FROM USER_MVIEWS WHERE UPPER(query) LIKE '%' || :tbl || '%'",
                (base,)
            )
            rows = cursor.fetchall()
            deps = [r[0] for r in rows]
        except Exception:
            deps = []

        return deps

    def show_existing_log_options(table, cursor, desired_sql, mv_ddl=None):
        """Ask the user what to do when an existing MLOG$_<table> is present.
        Returns one of: 'reuse', 'drop', or None (cancel)."""
        meta = None
        try:
            try:
                dlg = tk.Toplevel(builder_window)
            except NameError:
                dlg = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
            dlg.title(f"Existing MV Log on {table}")
            try:
                dlg.transient(builder_window)
            except Exception:
                pass
            dlg.grab_set()
        except Exception as e:
            logger.exception("Failed to open Existing Log dialog: %s", e)
            try:
                deps = get_dependent_mviews(cursor, table)
            except Exception:
                deps = []
            msg = (f"A materialized view log already exists on {table}.\n"
                   f"Dependent materialized views: {', '.join(deps) if deps else 'None'}\n\n"
                   "Do you want to drop and recreate the log with the selected options?\n"
                   "This will affect any dependent materialized views.")
            try:
                try:
                    pb = builder_window
                except NameError:
                    pb = parent
                if pb is not None:
                    ans = _safe_messagebox('askyesno', "Drop & Recreate MV Log?", msg, dlg=pb)
                else:
                    ans = _safe_messagebox('askyesno', "Drop & Recreate MV Log?", msg, dlg=None)
            except Exception:
                ans = False
            return 'drop' if ans else None

        # Prefer centralized detection helper when available
        cols = []
        deps = []
        existing_type = 'UNKNOWN'
        pk_cols = []
        seq_present = False
        includes_new = False
        try:
            helper = _MV_HELPERS.get('detect_existing_mlog') if _MV_HELPERS else None
            if helper:
                meta = helper(cursor, table)
                try:
                    logger.debug(f"detect_existing_mlog meta for {table}: {meta}")
                except Exception:
                    pass
                cols = meta.get('cols') or []
                deps = meta.get('deps') or []
                existing_type = meta.get('existing_type', 'UNKNOWN')
                pk_cols = meta.get('pk_cols') or []
                seq_present = bool(meta.get('seq_present'))
                includes_new = bool(meta.get('includes_new'))
                # Extra conservative check: if helper reports a log but we cannot read
                # any columns and there are no dependent MVs, verify the physical
                # MLOG$_<master> presence directly. If not visible, treat as no log.
                try:
                    if meta.get('exists') and not cols and not deps:
                        master_name = table.split('.')[-1].upper()
                        mlog_name = f"MLOG$_{master_name}"
                        phys = False
                        try:
                            if '.' in table:
                                owner_part = table.split('.')[0].upper()
                                cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :own AND TABLE_NAME = :tn", (owner_part, mlog_name))
                                phys = cursor.fetchone()[0] > 0
                            else:
                                cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                                cnt = cursor.fetchone()[0]
                                if cnt == 0:
                                    cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                                    cnt = cursor.fetchone()[0]
                                phys = cnt > 0
                        except Exception:
                            phys = False
                        if not phys:
                            # no physical log visible; ignore the helper's exists indication
                            meta['exists'] = False
                            cols = []
                            deps = []
                            existing_type = 'UNKNOWN'
                            pk_cols = []
                            seq_present = False
                            includes_new = False
                except Exception:
                    pass
            else:
                # fallback to best-effort local detection
                mlog_name = f"MLOG$_{table.split('.')[-1].upper()}"
                try:
                    cursor.execute("SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :tn ORDER BY COLUMN_ID", (mlog_name,))
                    cols = [r[0] for r in cursor.fetchall()]
                except Exception:
                    cols = []
                try:
                    deps = get_dependent_mviews(cursor, table)
                except Exception:
                    deps = []
                try:
                    cursor.execute("SELECT ucc.column_name FROM user_constraints uc JOIN user_cons_columns ucc ON uc.constraint_name = ucc.constraint_name WHERE uc.table_name = :tn AND uc.constraint_type = 'P'", (table.split('.')[-1].upper(),))
                    pk_cols = [r[0] for r in cursor.fetchall()]
                except Exception:
                    pk_cols = []
                if any(c.upper() in [pc.upper() for pc in pk_cols] for c in cols):
                    existing_type = 'PRIMARY KEY'
                elif any('ROW' in c.upper() or 'M_ROW' in c.upper() or 'ROWID' in c.upper() for c in cols):
                    existing_type = 'ROWID'
                seq_present = any('SEQ' in c.upper() or 'SNAPTIME' in c.upper() for c in cols)
                includes_new = any('OLD_NEW' in c.upper() or 'NEW' in c.upper() for c in cols)
        except Exception:
            # keep defaults if helper fails
            pass

        # Detect dark mode once for pane-only styling (ScrolledText widgets)
        _is_dark = is_dark_mode_active()

        lbl_title = tk.Label(dlg, text=f"A materialized view log already exists on {table}.", font=("Arial", 10, "bold"))
        lbl_title.pack(padx=12, pady=(8, 4), anchor='w')
        
        lbl_cols = tk.Label(dlg, text="Existing log columns:")
        lbl_cols.pack(padx=12, anchor='w')
        
        cols_frame = tk.Frame(dlg)
        cols_frame.pack(padx=12, pady=(0,6), anchor='w')
        
        if cols:
            for c in cols:
                tk.Label(cols_frame, text=f"- {c}").pack(anchor='w')
        else:
            tk.Label(cols_frame, text="(could not read columns)").pack(anchor='w')

        tk.Label(dlg, text="Material Views that May Be Dependent:").pack(padx=12, anchor='w')
        
        # show count and a scrollable list so long lists are usable
        try:
            logger.info(f"Dependent materialized views for {table}: {deps}")
        except Exception:
            pass
        
        tk.Label(dlg, text=f"{len(deps)} material view(s) that may be dependent:").pack(padx=12, anchor='w')

        deps_box = scrolledtext.ScrolledText(dlg, width=80, height=8)
        deps_box.pack(padx=12, pady=(0,6))
        if deps:
            for m in deps:
                deps_box.insert('end', f"{m}\n")
        else:
            deps_box.insert('1.0', '(none detected)')
        deps_box.config(state='disabled')
        
        # Apply dark mode to deps_box
        if _is_dark:
            deps_box.config(bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_INSERT_BG)

        def copy_deps():
            try:
                builder_window.clipboard_clear()
                builder_window.clipboard_append('\n'.join(deps))
                _safe_messagebox('showinfo', 'Copied', 'Dependent MV list copied to clipboard.', dlg=dlg)
            except Exception:
                _safe_messagebox('showwarning', 'Copy Failed', 'Could not copy to clipboard.', dlg=dlg)

        def save_deps():
            try:
                path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text','*.txt')])
                if path:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(deps))
                    _safe_messagebox('showinfo', 'Saved', f'List saved to {path}', dlg=dlg)
            except Exception as e:
                _safe_messagebox('showwarning', 'Save Failed', f'Could not save list: {e}', dlg=dlg)

        btns_deps = tk.Frame(dlg)
        btns_deps.pack(padx=12, anchor='w')
        
        btn_copy = tk.Button(btns_deps, text='Copy list', command=copy_deps, width=10)
        btn_save = tk.Button(btns_deps, text='Save list', command=save_deps, width=10)
        btn_copy.pack(side='left', padx=(0,6))
        btn_save.pack(side='left')

        # Gather low-level diagnostic counts to help debug false positives
        diag = {}
        mlog_name = None
        try:
            master_name = table.split('.')[-1].upper()
            try:
                cursor.execute("SELECT COUNT(*) FROM USER_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                diag['user_mview_logs_count'] = cursor.fetchone()[0]
            except Exception:
                diag['user_mview_logs_count'] = None
            try:
                cursor.execute("SELECT COUNT(*) FROM ALL_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                diag['all_mview_logs_count'] = cursor.fetchone()[0]
            except Exception:
                diag['all_mview_logs_count'] = None
            try:
                mlog_name = f"MLOG$_{master_name}"
                cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                diag['user_tables_mlog_count'] = cursor.fetchone()[0]
            except Exception:
                diag['user_tables_mlog_count'] = None
            try:
                cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                diag['all_tables_mlog_count'] = cursor.fetchone()[0]
            except Exception:
                diag['all_tables_mlog_count'] = None
        except Exception:
            diag = {}

        # Debug info button (helps surface permission/stale-dictionary cases)
        def show_diag():
            try:
                meta_text = ''
                try:
                    meta_text = str(meta)
                except Exception:
                    meta_text = '(no meta)'
                lines = [f"detect_existing_mlog meta: {meta_text}"]
                for k in ('user_mview_logs_count','all_mview_logs_count','user_tables_mlog_count','all_tables_mlog_count'):
                    lines.append(f"{k}: {diag.get(k)!r}")
                try:
                    _safe_messagebox('showinfo', 'Debug Info', '\n'.join(lines), dlg=dlg)
                except Exception:
                    _safe_messagebox('showwarning', 'Debug Failed', f'Could not show debug info: (failed to display debug info)', dlg=dlg)
            except Exception:
                # swallow any unexpected errors while preparing debug text
                try:
                    _safe_messagebox('showwarning', 'Debug Failed', 'Could not produce debug info.', dlg=dlg)
                except Exception:
                    pass
        btn_debug = tk.Button(btns_deps, text='Show debug info', command=show_diag, width=14)
        btn_debug.pack(side='left', padx=(6,0))

        # acknowledgement checkbox variable (checkbox will be placed next to the confirmation entry)
        ack_var = tk.BooleanVar(value=False)

        tk.Label(dlg, text="Compatibility summary (quick checks):", font=("Arial", 10, "bold")).pack(padx=12, pady=(6,4), anchor='w')
        # Compatibility checks will be computed from DB metadata
        try:
            mlog_name = f"MLOG$_{table.split('.')[-1].upper()}"
            cursor.execute("SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :tn ORDER BY COLUMN_ID", (mlog_name,))
            cols = [r[0] for r in cursor.fetchall()]
        except Exception:
            cols = []


        # determine requested type from desired_sql
        try:
            req_type = 'ROWID' if 'WITH ROWID' in desired_sql.upper() else ('PRIMARY KEY' if 'PRIMARY KEY' in desired_sql.upper() else 'UNKNOWN')
        except Exception:
            req_type = 'UNKNOWN'

        # render checklist
        chkf = tk.Frame(dlg)
        chkf.pack(padx=12, anchor='w')
        
        def label_status(text, ok):
            color = 'green' if ok else 'red'
            tk.Label(chkf, text=text, fg=color).pack(anchor='w')

        label_status(f"Requested log type: {req_type}", True)
        label_status(f"Existing log type (heuristic): {existing_type}", existing_type == req_type)
        label_status(f"Primary key on master: {', '.join(pk_cols) if pk_cols else 'No'}", bool(pk_cols) or req_type != 'PRIMARY KEY')
        label_status(f"Sequence-like column present: {'Yes' if seq_present else 'No'}", seq_present)
        label_status(f"INCLUDING NEW VALUES present: {'Yes' if includes_new else 'No'}", includes_new)

        tk.Label(dlg, text="The tool will run the following DDL if you choose Drop & Recreate:").pack(padx=12, anchor='w')
        
        ddl_box = scrolledtext.ScrolledText(dlg, width=80, height=6)
        ddl_box.pack(padx=12, pady=(4,6))
        ddl_box.insert("1.0", desired_sql)
        ddl_box.config(state='disabled')
        
        # Apply dark mode to ddl_box
        if _is_dark:
            ddl_box.config(bg=DARK_BG, fg=DARK_FG, insertbackground=DARK_INSERT_BG)

        # Note: Run Explain / MV_CAPABILITIES_TABLE support removed to keep the dialog simple.
        # Advanced EXPLAIN functionality was intentionally removed per UX decision.

        # expected base table name (unqualified)
        expected_name = table.split('.')[-1].upper()
        # We'll position the confirmation controls and buttons in a bottom bar.

        result = {'value': None}  # type: dict[str, None | str]

        def do_reuse():
            result['value'] = 'reuse'
            dlg.destroy()

        def do_drop():
            result['value'] = 'drop'
            dlg.destroy()

        def do_cancel():
            result['value'] = None
            dlg.destroy()

        # Bottom bar: center column will contain a vertical stack of
        # Reuse, Cancel, and Confirm entry. Below them we'll place the
        # acknowledgement checkbox and Drop button on the same line.
        bottom_bar = tk.Frame(dlg)
        bottom_bar.pack(pady=8, fill='x', padx=12)

        bottom_bar.grid_columnconfigure(0, weight=1)
        bottom_bar.grid_columnconfigure(1, weight=0)
        bottom_bar.grid_columnconfigure(2, weight=1)

        center_stack = tk.Frame(bottom_bar)
        center_stack.grid(row=0, column=1)

        reuse_label = f"Reuse Existing Log - {existing_type}" if existing_type and existing_type != 'UNKNOWN' else "Reuse Existing Log"
        btn_row = tk.Frame(center_stack)
        btn_row.pack(side='top', pady=(0,6))
        
        btn_reuse = tk.Button(btn_row, text=reuse_label, command=do_reuse, width=26)
        btn_cancel_dlg = tk.Button(btn_row, text="Cancel", command=do_cancel, width=10)
        btn_reuse.pack(side='left', padx=(0,6))
        btn_cancel_dlg.pack(side='left')

        # (Confirmation entry removed — checkbox alone is required to enable Drop)

        # Controls row: ack checkbox and drop button on the same line
        controls_row = tk.Frame(center_stack)
        controls_row.pack(side='top', pady=(6,0))
        
        ack_cb = tk.Checkbutton(controls_row, text=f"I understand this will affect the {len(deps)} listed materialized view(s).", variable=ack_var)
        ack_cb.pack(side='left')
        
        drop_btn = tk.Button(controls_row, text="Drop & Recreate", command=do_drop, width=18)
        drop_btn.pack(side='left', padx=(12,0))
        drop_btn.config(state='disabled')

        def can_enable_drop():
            try:
                return bool(ack_var.get())
            except Exception:
                return False

        def update_buttons(*_):
            if can_enable_drop():
                drop_btn.config(state='normal')
            else:
                drop_btn.config(state='disabled')

        # Bind watchers
        try:
            ack_var.trace_add('write', lambda *_: update_buttons())
        except Exception:
            ack_var.trace('w', lambda *_: update_buttons())

        dlg.update_idletasks()
        w = dlg.winfo_width(); h = dlg.winfo_height()
        x = (dlg.winfo_screenwidth() // 2) - (w // 2)
        y = (dlg.winfo_screenheight() // 2) - (h // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        try:
            dlg.wait_window(dlg)
        except Exception:
            try:
                dlg.mainloop()
            except Exception:
                pass
        return result.get('value')

    def create_materialized_view_logs(cursor, conn, tables, log_type, include_new_values=True):
        """Attempt to create materialized view logs for the given tables.
        tables: list of strings like SCHEMA.TABLE or TABLE
        log_type: 'ROWID' or 'PRIMARY KEY'
        include_new_values: bool
        """
        results = []
        for t in tables:
            try:
                if '.' in t:
                    schema, table = t.split('.', 1)
                else:
                    schema = None
                    table = t
                sql = f"CREATE MATERIALIZED VIEW LOG ON {t} \n"
                if log_type == 'ROWID':
                    sql += "  WITH ROWID\n"
                else:
                    sql += "  WITH PRIMARY KEY\n"
                if include_new_values:
                    sql += "  INCLUDING NEW VALUES"
                try:
                    cursor.execute(sql)
                    conn.commit()
                    logger.info(f"✅ Created materialized view log on {t}")
                    results.append((t, True, None))
                except Exception as e:
                    err = str(e)
                    logger.warning(f"Could not create MV log on {t}: {err}")
                    # Possibly an existing incompatible log exists. Ask user whether to drop and recreate.
                    try:
                        prompt = (f"Could not create materialized view log on {t}:\n{err}\n\n"
                                  "Do you want to DROP any existing materialized view log on this table and recreate it with the selected options?\n"
                                  "This may affect other materialized views that depend on the existing log.")
                        try:
                            try:
                                pb = builder_window
                            except NameError:
                                pb = parent
                            if pb is not None:
                                drop_confirm = _safe_messagebox('askyesno', "Existing MV Log Detected", prompt, dlg=pb)
                            else:
                                drop_confirm = _safe_messagebox('askyesno', "Existing MV Log Detected", prompt, dlg=None)
                        except Exception:
                            drop_confirm = False
                    except Exception:
                        drop_confirm = False

                    if drop_confirm:
                        try:
                            cursor.execute(f"DROP MATERIALIZED VIEW LOG ON {t}")
                            conn.commit()
                            logger.info(f"Dropped existing materialized view log on {t}")
                            # try create again
                            cursor.execute(sql)
                            conn.commit()
                            logger.info(f"✅ Recreated materialized view log on {t}")
                            results.append((t, True, None))
                        except Exception as e2:
                            err2 = str(e2)
                            logger.warning(f"Failed to drop/recreate MV log on {t}: {err2}")
                            results.append((t, False, err2))
                    else:
                        results.append((t, False, err))
            except Exception as e:
                logger.exception("Unexpected error creating MV log on %s: %s", t, e)
                results.append((t, False, str(e)))
        return results
    def on_submit():
        mv_name = mv_name_entry.get().strip()
        sql_query = sql_text.get("1.0", tk.END).strip()
        build_mode = build_var.get()
        refresh_method = refresh_method_var.get()
        refresh_trigger = refresh_trigger_var.get()
        query_rewrite = rewrite_var.get()
        # use_dwh is now a parameter passed to run_sql_mv_loader

        if not mv_name:
            try:
                _safe_messagebox('showerror', "Missing MV Name", "\u274c Please enter a materialized view name.", dlg=builder_window)
            except Exception:
                try:
                    _safe_messagebox('showerror', "Missing MV Name", "\u274c Please enter a materialized view name.", dlg=builder_window)
                except Exception:
                    pass
            return

        if not sql_query:
            try:
                _safe_messagebox('showerror', "Missing SQL", "\u274c Please paste a SQL query.", dlg=builder_window)
            except Exception:
                try:
                    _safe_messagebox('showerror', "Missing SQL", "\u274c Please paste a SQL query.", dlg=builder_window)
                except Exception:
                    pass
            return

        # Remove trailing semicolon if present
        if sql_query.endswith(";"):
            sql_query = sql_query.rstrip("; \n")

        # Use the connection established at GUI startup
        cursor = None

        # Ensure the DB connection is always closed even on early returns
        try:
            # If ON COMMIT requested, detect base tables and offer to create logs
            need_logs = (refresh_trigger == "ON COMMIT")
            if need_logs:
                tables = detect_tables_from_sql(sql_query)
                # Only proceed to show dialog if any tables detected
                if tables:
                    dlg_result = show_create_logs_dialog(tables)
                    if dlg_result is None:
                        # user cancelled
                        return
                    create_logs_flag, selected_tables, log_type, include_new_values = dlg_result
                    if create_logs_flag and selected_tables:
                        # attempt to create logs before creating MV
                        try:
                            cursor = conn.cursor()
                            # ensure include_new_values is a bool (default True)
                            if include_new_values is None:
                                include_new_values = True

                            # Check for existing logs and ask user for safer handling
                            final_results = []
                            # get current user for ownership checks
                            try:
                                cursor.execute("SELECT USER FROM DUAL")
                                current_user = cursor.fetchone()[0]
                            except Exception:
                                current_user = None

                            # Use shared detection helper when available for a simpler flow
                            final_results = []
                            helper = _MV_HELPERS.get('detect_existing_mlog') if _MV_HELPERS else None
                            for t in selected_tables:
                                try:
                                    exists = False
                                    # Prefer helper-based detection
                                    if helper:
                                        try:
                                            meta = helper(cursor, t)
                                            exists = bool(meta.get('exists'))
                                            # If helper reports exists but has no readable columns or deps,
                                            # verify the physical MLOG$_<master> presence; if not visible,
                                            # treat as not existing to avoid false positives.
                                            try:
                                                if exists and not (meta.get('cols') or meta.get('deps')):
                                                    master_name = t.split('.')[-1].upper()
                                                    mlog_name = f"MLOG$_{master_name}"
                                                    phys = False
                                                    try:
                                                        if '.' in t:
                                                            owner_part = t.split('.')[0].upper()
                                                            cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :own AND TABLE_NAME = :tn", (owner_part, mlog_name))
                                                            phys = cursor.fetchone()[0] > 0
                                                        else:
                                                            # For unqualified master names, only consider USER_TABLES to avoid
                                                            # treating a log owned by another schema as 'existing' for the current user.
                                                            cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                                                            cnt = cursor.fetchone()[0]
                                                            phys = cnt > 0
                                                    except Exception:
                                                        phys = False
                                                    if not phys:
                                                        exists = False
                                                        try:
                                                            # also update meta to reflect conservative view
                                                            meta['exists'] = False
                                                        except Exception:
                                                            pass
                                            except Exception:
                                                pass
                                        except Exception:
                                            exists = False
                                    else:
                                        # Minimal fallback: check USER_MVIEW_LOGS presence
                                        try:
                                            master_name = t.split('.')[-1].upper()
                                            try:
                                                cursor.execute("SELECT COUNT(*) FROM USER_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                                                exists = cursor.fetchone()[0] > 0
                                            except Exception:
                                                exists = False
                                        except Exception:
                                            exists = False

                                    if exists:
                                        desired_sql = f"DROP MATERIALIZED VIEW LOG ON {t};\nCREATE MATERIALIZED VIEW LOG ON {t} \n"
                                        if log_type == 'ROWID':
                                            desired_sql += "  WITH ROWID\n"
                                        else:
                                            desired_sql += "  WITH PRIMARY KEY\n"
                                        if include_new_values:
                                            desired_sql += "  INCLUDING NEW VALUES"

                                        choice = show_existing_log_options(t, cursor, desired_sql)
                                        if choice == 'reuse':
                                            final_results.append((t, 'reused', None))
                                            continue
                                        elif choice == 'drop':
                                            try:
                                                cursor.execute(f"DROP MATERIALIZED VIEW LOG ON {t}")
                                                conn.commit()
                                            except Exception as e:
                                                final_results.append((t, False, str(e)))
                                                continue
                                        else:
                                            final_results.append((t, False, 'user_cancel'))
                                            continue

                                    # Verify target object exists and is a table
                                    try:
                                        if '.' in t:
                                            owner_part, table_part = t.split('.', 1)
                                            owner_check = owner_part.strip().upper()
                                            table_check = table_part.strip().upper()
                                        else:
                                            owner_check = current_user
                                            table_check = t.strip().upper()
                                        try:
                                            cursor.execute(
                                                "SELECT OWNER, OBJECT_TYPE FROM ALL_OBJECTS WHERE OWNER = :own AND OBJECT_NAME = :tbl",
                                                (owner_check, table_check)
                                            )
                                            obj = cursor.fetchone()
                                        except Exception:
                                            obj = None
                                        if not obj:
                                            err_msg = f"target object {t} not found or not accessible"
                                            final_results.append((t, False, err_msg))
                                            continue
                                        owner_found, obj_type = obj[0], obj[1]
                                        if obj_type.upper() != 'TABLE':
                                            err_msg = f"target object {t} is not a TABLE (found type: {obj_type})"
                                            final_results.append((t, False, err_msg))
                                            continue
                                    except Exception as e:
                                        final_results.append((t, False, str(e)))
                                        continue

                                    # Attempt to create the log
                                    try:
                                        sql = f"CREATE MATERIALIZED VIEW LOG ON {t} \n"
                                        if log_type == 'ROWID':
                                            sql += "  WITH ROWID\n"
                                        else:
                                            sql += "  WITH PRIMARY KEY\n"
                                        if include_new_values:
                                            sql += "  INCLUDING NEW VALUES"
                                        cursor.execute(sql)
                                        conn.commit()
                                        final_results.append((t, True, None))
                                    except Exception as e:
                                        final_results.append((t, False, str(e)))
                                except Exception as e:
                                    final_results.append((t, False, str(e)))

                            results = final_results
                            # summarize results and ask user whether to continue on failures
                            created = [r[0] for r in results if r[1] is True]
                            reused = [r[0] for r in results if r[1] == 'reused']
                            failed = [(r[0], r[2]) for r in results if r[1] is False or (isinstance(r[1], str) and r[1] not in ("reused",))]
                            msgs = []
                            if created:
                                msgs.append(f"Created logs on: {', '.join(created)}")
                            if reused:
                                msgs.append(f"Reused existing logs: {', '.join(reused)}")
                            if msgs:
                                try:
                                    _safe_messagebox('showinfo', "MV Logs Created", "\n".join(msgs), dlg=builder_window)
                                    ensure_builder_on_top()
                                except Exception:
                                    pass
                            if failed:
                                msg_lines = [f"{t}: {err}" for (t, err) in failed]
                                msg = "Some MV logs could not be created:\n\n" + "\n".join(msg_lines) + "\n\nDo you want to continue creating the materialized view anyway?"
                                try:
                                    cont = _safe_messagebox('askyesno', "MV Log Creation Failed", msg, dlg=builder_window)
                                    ensure_builder_on_top()
                                except Exception:
                                    cont = False
                                if not cont:
                                    try:
                                        cursor.close()
                                    except Exception:
                                        pass
                                    return
                        except Exception as e:
                            logger.warning(f"Failed to create MV logs: {e}")
                        finally:
                            try:
                                if cursor:
                                    cursor.close()
                            except Exception:
                                pass

            try:
                cursor = conn.cursor()

                # Build DDL pieces
                build_clause = f"BUILD {build_mode}"
                refresh_clause = f"REFRESH {refresh_method} {refresh_trigger}"
                rewrite_clause = "ENABLE QUERY REWRITE" if query_rewrite else ""

                ddl = f"CREATE MATERIALIZED VIEW {mv_name} \n  {build_clause}\n  {refresh_clause}"
                if rewrite_clause:
                    ddl += f"\n  {rewrite_clause}"
                ddl += f"\nAS {sql_query}"

                cursor.execute(ddl)

                # Grant select to PUBLIC (same behavior as view loader)
                grant_stmt = f'GRANT SELECT ON {mv_name} TO PUBLIC'
                cursor.execute(grant_stmt)

                conn.commit()
                logger.info(f"✅ Materialized View '{mv_name}' created and granted SELECT to PUBLIC.")

                try:
                    _safe_messagebox('showinfo', "Success", f"\u2705 Materialized View '{mv_name}' created successfully.", dlg=builder_window)
                    ensure_builder_on_top()
                except Exception:
                    try:
                        _safe_messagebox('showinfo', "Success", f"\u2705 Materialized View '{mv_name}' created successfully.", dlg=builder_window)
                    except Exception:
                        pass
                # Window stays open - user closes manually; on_finish called when window closes
            except Exception as e:
                # Log full traceback to help debugging
                logger.exception("❌ Error creating materialized view: %s", e)
                # Provide helpful hint for common MV issues
                hint = "\n\nTip: REFRESH FAST/ON COMMIT may require materialized view logs or PKs on source tables."
                # Show dialog with concise message but include trace in log file
                try:
                    _safe_messagebox('showerror', "Error", f"\u274c Failed to create materialized view:\n{e}{hint}", dlg=builder_window)
                    ensure_builder_on_top()
                except Exception:
                    try:
                        _safe_messagebox('showerror', "Error", f"\u274c Failed to create materialized view:\n{e}{hint}", dlg=builder_window)
                        ensure_builder_on_top()
                    except Exception:
                        try:
                            _safe_messagebox('showerror', "Error", f"\u274c Failed to create materialized view:\n{e}{hint}", dlg=None)
                        except Exception:
                            pass
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.warning(f"⚠️ Failed to close cursor: {e}")
            # Connection stays open for consecutive MV creations
            # It will be closed when the window is destroyed via session cleanup

    def on_cancel():
        builder_window.destroy()
        # on_finish is called in the finally block after window closes

    # Create Toplevel with optional parent so the window can be modal
    builder_window = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
    builder_window.title("SQL Materialized View Loader")
    # widen builder window so bottom option row isn't squished on smaller displays
    builder_window.geometry("1300x740")

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

    # Pane-only dark mode support (polling fallback)
    try:
        import tkinter.ttk as _ttk
    except Exception:
        _ttk = None
    _last_dark = None
    _poll_id = None
    _all_buttons = []  # Will be populated when buttons are created

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
        # Only apply dark colors to the SQL text pane and the MV name entry.
        # Do not darken frames, labelframes, or control panels — keep chrome
        # light so only the content panes change.
        try:
            if dark:
                sql_text.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff', selectbackground='#2a6bd6')
                try:
                    mv_name_entry.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff')
                except Exception:
                    pass
            else:
                sql_text.config(bg='white', fg='black', insertbackground='black', selectbackground='#2a6bd6')
                try:
                    mv_name_entry.config(bg='white', fg='black', insertbackground='black')
                except Exception:
                    pass
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

    # Determine initial dark state before creating content widgets to avoid
    # visible white -> black flip when dark mode is already enabled.
    try:
        _initial_dark = _detect_dark_from_style()
    except Exception:
        _initial_dark = False

    try:
        # apply current style immediately to ensure internal state is consistent
        _apply_theme(_initial_dark)
    except Exception:
        pass

    # Register theme callback with parent when available; otherwise start polling
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
                # apply current style immediately via callback
                try:
                    _theme_cb(_detect_dark_from_style())
                except Exception:
                    pass
            except Exception:
                pass
        else:
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

    # Helper to briefly bring the builder window to the front after modal messageboxes
    def ensure_builder_on_top(delay=50):
        try:
            builder_window.lift()
            builder_window.attributes('-topmost', True)
            builder_window.after(delay, lambda: builder_window.attributes('-topmost', False))
        except Exception:
            pass

    def load_sql_from_file():
        """Open file dialog, load SQL content, and auto-fill MV name from filename."""
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

                # Auto-fill MV name from filename with MV_ prefix
                filename = os.path.basename(filepath)
                name_without_ext = os.path.splitext(filename)[0]
                mv_name = f"MV_{name_without_ext}".upper()
                mv_name_entry.delete(0, tk.END)
                mv_name_entry.insert(0, mv_name)
            except Exception as e:
                _safe_messagebox('showerror', "Error", f"Failed to read file:\n{e}", dlg=builder_window)
                try:
                    builder_window.bell()  # System chime
                except Exception:
                    pass

    # Preserve taskbar icon and branding
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        builder_window.iconbitmap(default=icon_path)
    except Exception as e:
        logger.warning(f"⚠️ Failed to set taskbar icon: {e}")

    tk.Label(builder_window, text="Enter SQL to turn into a MATERIALIZED VIEW:", font=("Arial", 11, "bold")).pack(pady=(10, 5))

    # Create SQL text with initial theme to avoid visible white -> black flip
    try:
        if _initial_dark:
            sql_text = scrolledtext.ScrolledText(builder_window, width=120, height=25, font=("Courier New", 10), bg='#000000', fg='#ffffff', insertbackground='#ffffff', selectbackground='#2a6bd6')
        else:
            sql_text = scrolledtext.ScrolledText(builder_window, width=120, height=25, font=("Courier New", 10), bg='white', fg='black', insertbackground='black', selectbackground='#2a6bd6')
    except Exception:
        sql_text = scrolledtext.ScrolledText(builder_window, width=120, height=25, font=("Courier New", 10))
    sql_text.pack(padx=10, pady=(0, 10), fill="both", expand=False)

    # Shared container for name row and buttons to ensure alignment
    control_container = tk.Frame(builder_window)
    control_container.pack(pady=8)

    # Name row - label outside, entry inside
    name_row = tk.Frame(control_container)
    name_row.pack(pady=(0, 10))

    tk.Label(name_row, text="Materialized View Name:").pack(side="left", padx=(0, 5))
    # Create MV name entry with initial theme to avoid flash
    try:
        if _initial_dark:
            mv_name_entry = tk.Entry(name_row, width=33, bg='#000000', fg='#ffffff', insertbackground='#ffffff')
        else:
            mv_name_entry = tk.Entry(name_row, width=33)
    except Exception:
        mv_name_entry = tk.Entry(name_row, width=33)
    mv_name_entry.pack(side="left")

    # Import SQL button
    btn_import_sql = tk.Button(name_row, text="Import SQL", command=load_sql_from_file, width=10)
    btn_import_sql.pack(side="left", padx=(10, 0))
    _all_buttons.append(btn_import_sql)

    # Row 1: Parameter frames (centered)
    param_frame = tk.Frame(control_container)
    param_frame.pack(pady=(0, 10))

    # Build mode
    build_frame = tk.LabelFrame(param_frame, text="Build", padx=8, pady=6)
    build_frame.pack(side="left", padx=8)
    build_var = tk.StringVar(value="IMMEDIATE")
    tk.Radiobutton(build_frame, text="IMMEDIATE", variable=build_var, value="IMMEDIATE").pack(anchor="w")
    tk.Radiobutton(build_frame, text="DEFERRED", variable=build_var, value="DEFERRED").pack(anchor="w")

    # Refresh method
    refresh_frame = tk.LabelFrame(param_frame, text="Refresh Method", padx=8, pady=6)
    refresh_frame.pack(side="left", padx=8)
    refresh_method_var = tk.StringVar(value="COMPLETE")
    tk.Radiobutton(refresh_frame, text="COMPLETE", variable=refresh_method_var, value="COMPLETE").pack(anchor="w")
    # FAST refresh removed from UI because it's environment/version dependent and
    # often requires destructive log changes. Use ON COMMIT trigger to request
    # log creation instead.
    # FORCE option removed because FAST refresh is unsupported in this environment.
    # The refresh method is therefore limited to COMPLETE (and UI should not offer FORCE).

    # Refresh trigger
    trigger_frame = tk.LabelFrame(param_frame, text="Refresh Trigger", padx=8, pady=6)
    trigger_frame.pack(side="left", padx=8)
    refresh_trigger_var = tk.StringVar(value="ON DEMAND")
    tk.Radiobutton(trigger_frame, text="ON DEMAND", variable=refresh_trigger_var, value="ON DEMAND").pack(anchor="w")
    tk.Radiobutton(trigger_frame, text="ON COMMIT", variable=refresh_trigger_var, value="ON COMMIT").pack(anchor="w")

    # Row 2: Query Rewrite checkbox (centered)
    rewrite_frame = tk.Frame(control_container)
    rewrite_frame.pack(pady=(0, 15))
    rewrite_var = tk.BooleanVar(value=False)
    rewrite_chk = tk.Checkbutton(rewrite_frame, text="Enable Query Rewrite", variable=rewrite_var)
    rewrite_chk.pack()

    # Button row - inside same container for alignment
    btn_frame = tk.Frame(control_container)
    btn_frame.pack()

    # Create buttons with references for dark mode styling
    btn_create_mv = tk.Button(btn_frame, text="Create", command=on_submit, width=10)
    btn_cancel_mv = tk.Button(btn_frame, text="Close", command=on_cancel, width=10)
    btn_create_mv.pack(side="left", padx=10)
    btn_cancel_mv.pack(side="left", padx=10)
    _all_buttons.extend([btn_create_mv, btn_cancel_mv])
    
    # Apply initial button theme if dark mode is active
    if _initial_dark:
        for btn in _all_buttons:
            try:
                btn.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')
            except Exception:
                pass

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
