import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
import logging
import re
from libs.oracle_db_connector import get_db_connection
from libs import session
import ctypes
from libs.paths import ASSETS_PATH
from pathlib import Path

logger = logging.getLogger(__name__)


def run_sql_mv_loader(on_finish=None):
    def detect_tables_from_sql(sql_text):
        """A conservative table detector: finds tokens after FROM and JOIN. Returns list of unique table identifiers."""
        # Normalize spacing and remove subquery parentheses content crudely
        text = re.sub(r"\s+", " ", sql_text.replace('\n', ' ')).upper()
        # Find FROM/JOIN occurrences
        candidates = []
        for m in re.finditer(r"(?:FROM|JOIN)\s+([A-Z0-9_\.]+)", text):
            tbl = m.group(1).strip()
            # strip trailing commas
            tbl = tbl.rstrip(',')
            candidates.append(tbl)
        # Deduplicate while preserving order
        seen = set()
        out = []
        for t in candidates:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def show_create_logs_dialog(tables):
        """Show a modal dialog asking which tables to create logs on.
        Returns (create_flag, selected_tables, log_type, include_new_values) or None if cancelled."""
        try:
            dlg = tk.Toplevel()
            dlg.title("Create Materialized View Logs")
            dlg.grab_set()
        except Exception as e:
            # If creating the Toplevel fails (threading/root issues), fallback to a simple confirmation
            logger.exception("Failed to open Create Logs dialog: %s", e)
            try:
                trace_file = Path.cwd() / "mv_debug_trace.txt"
                with trace_file.open("a", encoding="utf-8") as f:
                    f.write(f"DIALOG_OPEN_FAILED: {e}\n")
            except Exception:
                pass
            try:
                create_choice = messagebox.askyesno("Create MV Logs?", f"Detected tables: {', '.join(tables)}\nCreate materialized view logs with WITH ROWID and INCLUDING NEW VALUES?")
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
        tk.Button(btnf, text="Create Logs & Continue", command=on_ok, width=18).pack(side="left", padx=6)
        tk.Button(btnf, text="Skip Logs & Continue", command=on_skip, width=18).pack(side="left", padx=6)
        tk.Button(btnf, text="Cancel", command=on_cancel, width=10).pack(side="left", padx=6)

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
        try:
            dlg = tk.Toplevel()
            dlg.title(f"Existing MV Log on {table}")
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
                ans = messagebox.askyesno("Drop & Recreate MV Log?", msg)
            except Exception:
                ans = False
            return 'drop' if ans else None

        # get existing log columns
        try:
            mlog_name = f"MLOG$_{table.split('.')[-1].upper()}"
            cursor.execute("SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :tn ORDER BY COLUMN_ID", (mlog_name,))
            cols = [r[0] for r in cursor.fetchall()]
        except Exception:
            cols = []

        # get dependent mviews (use dependency-based lookup with fallback)
        try:
            deps = get_dependent_mviews(cursor, table)
        except Exception:
            deps = []

        tk.Label(dlg, text=f"A materialized view log already exists on {table}.", font=("Arial", 10, "bold")).pack(padx=12, pady=(8, 4), anchor='w')
        tk.Label(dlg, text="Existing log columns:").pack(padx=12, anchor='w')
        cols_frame = tk.Frame(dlg)
        cols_frame.pack(padx=12, pady=(0,6), anchor='w')
        if cols:
            for c in cols:
                tk.Label(cols_frame, text=f"- {c}").pack(anchor='w')
        else:
            tk.Label(cols_frame, text="(could not read columns)").pack(anchor='w')

        tk.Label(dlg, text="Dependent materialized views:").pack(padx=12, anchor='w')
        # show count and a scrollable list so long lists are usable
        try:
            logger.info(f"Dependent materialized views for {table}: {deps}")
        except Exception:
            pass
        tk.Label(dlg, text=f"{len(deps)} dependent materialized view(s) found:").pack(padx=12, anchor='w')

        deps_box = scrolledtext.ScrolledText(dlg, width=80, height=8)
        deps_box.pack(padx=12, pady=(0,6))
        if deps:
            deps_box.insert('1.0', '\n'.join(deps))
        else:
            deps_box.insert('1.0', '(none detected)')
        deps_box.config(state='disabled')

        def copy_deps():
            try:
                builder_window.clipboard_clear()
                builder_window.clipboard_append('\n'.join(deps))
                messagebox.showinfo('Copied', 'Dependent MV list copied to clipboard.')
            except Exception:
                try:
                    messagebox.showwarning('Copy Failed', 'Could not copy to clipboard.')
                except Exception:
                    pass

        def save_deps():
            try:
                path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text','*.txt')])
                if path:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(deps))
                    messagebox.showinfo('Saved', f'List saved to {path}')
            except Exception as e:
                try:
                    messagebox.showwarning('Save Failed', f'Could not save list: {e}')
                except Exception:
                    pass

        btns_deps = tk.Frame(dlg)
        btns_deps.pack(padx=12, anchor='w')
        tk.Button(btns_deps, text='Copy list', command=copy_deps, width=10).pack(side='left', padx=(0,6))
        tk.Button(btns_deps, text='Save list', command=save_deps, width=10).pack(side='left')

        # acknowledgement checkbox to reduce accidental destructive actions
        ack_var = tk.BooleanVar(value=False)
        ack_cb = tk.Checkbutton(dlg, text=f"I understand this will affect the {len(deps)} listed materialized view(s).", variable=ack_var)
        ack_cb.pack(padx=12, pady=(8,4), anchor='w')

        tk.Label(dlg, text="Compatibility summary (quick checks):", font=("Arial", 10, "bold")).pack(padx=12, pady=(6,4), anchor='w')
        # Compatibility checks will be computed from DB metadata
        try:
            mlog_name = f"MLOG$_{table.split('.')[-1].upper()}"
            cursor.execute("SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :tn ORDER BY COLUMN_ID", (mlog_name,))
            cols = [r[0] for r in cursor.fetchall()]
        except Exception:
            cols = []

        # determine requested type from desired_sql
        req_type = 'ROWID' if 'WITH ROWID' in desired_sql.upper() else ('PRIMARY KEY' if 'PRIMARY KEY' in desired_sql.upper() else 'UNKNOWN')

        # detect existing type heuristically
        existing_type = 'UNKNOWN'
        pk_cols = []
        try:
            cursor.execute("SELECT ucc.column_name FROM user_constraints uc JOIN user_cons_columns ucc ON uc.constraint_name = ucc.constraint_name WHERE uc.table_name = :tn AND uc.constraint_type = 'P'", (table.split('.')[-1].upper(),))
            pk_cols = [r[0] for r in cursor.fetchall()]
        except Exception:
            pk_cols = []
        if any(c.upper() in [pc.upper() for pc in pk_cols] for c in cols):
            existing_type = 'PRIMARY KEY'
        elif any('ROW' in c.upper() or 'M_ROW' in c.upper() or 'ROWID' in c.upper() for c in cols):
            existing_type = 'ROWID'

        # sequence presence
        seq_present = any('SEQ' in c.upper() or 'SNAPTIME' in c.upper() for c in cols)
        # includes new values heuristic
        includes_new = any('OLD_NEW' in c.upper() or 'NEW' in c.upper() for c in cols)

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

        # Note: Run Explain / MV_CAPABILITIES_TABLE support removed to keep the dialog simple.
        # Advanced EXPLAIN functionality was intentionally removed per UX decision.

        # expected base table name (unqualified)
        expected_name = table.split('.')[-1].upper()
        tk.Label(dlg, text=f"Type the table name to confirm DROP & RECREATE: (expected: {expected_name})").pack(padx=12, anchor='w')
        confirm_var = tk.StringVar()
        confirm_entry = tk.Entry(dlg, textvariable=confirm_var)
        confirm_entry.pack(padx=12, pady=(0,6), anchor='w')

        result = {'value': None}  # type: dict[str, None | str]

        def do_reuse():
            result['value'] = 'reuse'
            dlg.destroy()

        def normalize_name(s: str) -> str:
            # accept either 'SALES' or 'SCHEMA.SALES' from user input
            if not s:
                return ''
            s = s.strip()
            if '.' in s:
                return s.split('.')[-1].strip().upper()
            return s.upper()

        def do_drop():
            if normalize_name(confirm_var.get()) != expected_name:
                messagebox.showerror("Confirmation mismatch", f"Table name does not match. Type the exact table name to confirm (expected: {expected_name}).")
                return
            result['value'] = 'drop'
            dlg.destroy()

        def do_cancel():
            result['value'] = None
            dlg.destroy()

        btnf = tk.Frame(dlg)
        btnf.pack(pady=8)
        tk.Button(btnf, text="Reuse Existing Log", command=do_reuse, width=18).pack(side='left', padx=6)
        # Drop button is gated: requires ack checkbox + exact typed table name (accepts schema-qualified input)
        drop_btn = tk.Button(btnf, text="Drop & Recreate (type name to confirm)", command=do_drop, width=28)
        drop_btn.pack(side='left', padx=6)
        drop_btn.config(state='disabled')
        tk.Button(btnf, text="Cancel", command=do_cancel, width=10).pack(side='left', padx=6)

        def can_enable_drop():
            try:
                ack_ok = ack_var.get()
            except Exception:
                ack_ok = False
            name_ok = normalize_name(confirm_var.get()) == expected_name
            return ack_ok and name_ok

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
        try:
            confirm_var.trace_add('write', lambda *_: update_buttons())
        except Exception:
            confirm_var.trace('w', lambda *_: update_buttons())

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
                        drop_confirm = messagebox.askyesno("Existing MV Log Detected", prompt)
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
        use_dwh = dwh_var.get()

        if not mv_name:
            messagebox.showerror("Missing MV Name", "❌ Please enter a materialized view name.")
            return

        if not sql_query:
            messagebox.showerror("Missing SQL", "❌ Please paste a SQL query.")
            return

        # Remove trailing semicolon if present
        if sql_query.endswith(";"):
            sql_query = sql_query.rstrip("; \n")

        # Choose credentials source
        conn = get_db_connection(force_shared=True) if use_dwh else get_db_connection()
        if not conn:
            return
        cursor = None
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

                        for t in selected_tables:
                            # If a log exists, show choices to reuse or drop & recreate
                            try:
                                master_name = t.split('.')[-1].upper()
                                # Prefer USER_MVIEW_LOGS (current schema) to avoid false positives
                                try:
                                    cursor.execute(
                                        "SELECT COUNT(*) FROM USER_MVIEW_LOGS WHERE MASTER = :m",
                                        (master_name,)
                                    )
                                    exists = cursor.fetchone()[0] > 0
                                except Exception:
                                    # fallback to ALL_MVIEW_LOGS if user view not available
                                    try:
                                        # if t qualified with owner, filter by owner too to reduce false matches
                                        if '.' in t:
                                            owner_part = t.split('.')[0].upper()
                                            cursor.execute(
                                                "SELECT COUNT(*) FROM ALL_MVIEW_LOGS WHERE MASTER = :m AND OWNER = :own",
                                                (master_name, owner_part)
                                            )
                                        else:
                                            cursor.execute(
                                                "SELECT COUNT(*) FROM ALL_MVIEW_LOGS WHERE MASTER = :m",
                                                (master_name,)
                                            )
                                        exists = cursor.fetchone()[0] > 0
                                    except Exception:
                                        exists = False

                                # Defensive: try to resolve the actual log table name(s) from the mview logs view
                                # Some dictionary views may contain stale or inaccessible entries; prefer explicit LOG_TABLE lookup.
                                # log diagnostic info about detected existence for troubleshooting
                                try:
                                    logger.debug(f"MV log detection for {t}: master_name={master_name}, preliminary_exists={exists}")
                                except Exception:
                                    pass

                                if exists:
                                    try:
                                        log_tables = []
                                        try:
                                            cursor.execute("SELECT LOG_TABLE FROM USER_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                                            rows = cursor.fetchall()
                                            log_tables = [r[0] for r in rows if r and r[0]]
                                        except Exception:
                                            log_tables = []

                                        if not log_tables:
                                            try:
                                                if '.' in t:
                                                    owner_part = t.split('.')[0].upper()
                                                    cursor.execute("SELECT LOG_TABLE FROM ALL_MVIEW_LOGS WHERE MASTER = :m AND OWNER = :own", (master_name, owner_part))
                                                else:
                                                    cursor.execute("SELECT LOG_TABLE FROM ALL_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                                                rows = cursor.fetchall()
                                                log_tables = [r[0] for r in rows if r and r[0]]
                                            except Exception:
                                                log_tables = []

                                        # If we couldn't determine any LOG_TABLEs, fall back to checking for MLOG$_<master> physical table
                                        if not log_tables:
                                            mlog_name = f"MLOG$_{master_name}"
                                            # check USER_TABLES first
                                            cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                                            mcount = cursor.fetchone()[0]
                                            if mcount == 0:
                                                if '.' in t:
                                                    owner_part = t.split('.')[0].upper()
                                                    cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :own AND TABLE_NAME = :tn", (owner_part, mlog_name))
                                                else:
                                                    cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                                                mcount = cursor.fetchone()[0]
                                            if mcount == 0:
                                                exists = False
                                        else:
                                            # Only consider reported LOG_TABLEs that match expected naming (MLOG$_<master>)
                                            filtered = []
                                            for lt in log_tables:
                                                if not lt:
                                                    continue
                                                lt_str = str(lt).upper()
                                                if lt_str.endswith(f"MLOG$_{master_name}") or lt_str == f"MLOG$_{master_name}":
                                                    filtered.append(lt_str)
                                            if not filtered:
                                                # none of the reported log table names look like a real MLOG$_ table for this master
                                                exists = False
                                            else:
                                                # verify at least one of the filtered log tables exists as a table accessible to the user
                                                found = False
                                                for lt in filtered:
                                                    if '.' in lt:
                                                        owner_lt, name_lt = lt.split('.', 1)
                                                        try:
                                                            cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :own AND TABLE_NAME = :tn", (owner_lt.upper(), name_lt.upper()))
                                                            cnt = cursor.fetchone()[0]
                                                        except Exception:
                                                            cnt = 0
                                                    else:
                                                        try:
                                                            cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :tn", (lt.upper(),))
                                                            cnt = cursor.fetchone()[0]
                                                            if cnt == 0:
                                                                cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE TABLE_NAME = :tn", (lt.upper(),))
                                                                cnt = cursor.fetchone()[0]
                                                        except Exception:
                                                            cnt = 0
                                                    if cnt > 0:
                                                        found = True
                                                        break
                                                if not found:
                                                    exists = False
                                    except Exception as e:
                                        # If we cannot verify the physical log presence due to permission errors
                                        # or other DB access issues, conservatively treat the log as not present
                                        logger.warning(f"Could not verify physical MLOG presence for {master_name}: {e}")
                                        exists = False

                                # Extra safeguard: if the dictionary reports a log but we cannot read
                                # any columns and there are no dependent MVs, treat as not existing.
                                if exists:
                                    try:
                                        deps_preview = []
                                        try:
                                            deps_preview = get_dependent_mviews(cursor, t)
                                        except Exception:
                                            deps_preview = []

                                        # check columns on MLOG$_<master>
                                        colcount = 0
                                        try:
                                            cursor.execute("SELECT COUNT(*) FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :tn", (f"MLOG$_{master_name}",))
                                            colcount = cursor.fetchone()[0]
                                            if colcount == 0 and '.' in t:
                                                owner_part = t.split('.')[0].upper()
                                                cursor.execute("SELECT COUNT(*) FROM ALL_TAB_COLUMNS WHERE OWNER = :own AND TABLE_NAME = :tn", (owner_part, f"MLOG$_{master_name}"))
                                                colcount = cursor.fetchone()[0]
                                        except Exception:
                                            colcount = 0

                                        if (not deps_preview) and colcount == 0:
                                            # nothing we can read; treat as no log
                                            logger.info(f"Dictionary indicates MV log for {t} but no physical log or dependents found; ignoring.")
                                            exists = False
                                    except Exception:
                                        pass
                            except Exception:
                                exists = False

                            if exists:
                                # prepare desired create SQL for preview
                                desired_sql = f"DROP MATERIALIZED VIEW LOG ON {t};\nCREATE MATERIALIZED VIEW LOG ON {t} \n"
                                if log_type == 'ROWID':
                                    desired_sql += "  WITH ROWID\n"
                                else:
                                    desired_sql += "  WITH PRIMARY KEY\n"
                                if include_new_values:
                                    desired_sql += "  INCLUDING NEW VALUES"

                                choice = show_existing_log_options(t, cursor, desired_sql)
                                if choice == 'reuse':
                                    # attempt to reuse: skip drop/create for this table
                                    logger.info(f"User chose to reuse existing MV log on {t}")
                                    final_results.append((t, True, None))
                                    continue
                                elif choice == 'drop':
                                    try:
                                        cursor.execute(f"DROP MATERIALIZED VIEW LOG ON {t}")
                                        conn.commit()
                                        logger.info(f"Dropped existing materialized view log on {t}")
                                    except Exception as e:
                                        logger.warning(f"Failed to drop existing materialized view log on {t}: {e}")
                                        final_results.append((t, False, str(e)))
                                        continue
                                else:
                                    # user cancelled
                                    final_results.append((t, False, 'user_cancel'))
                                    continue

                            # Before attempting to create, verify the target object exists and is a table
                            try:
                                # resolve owner and table
                                if '.' in t:
                                    owner_part, table_part = t.split('.', 1)
                                    owner_check = owner_part.strip().upper()
                                    table_check = table_part.strip().upper()
                                else:
                                    owner_check = current_user
                                    table_check = t.strip().upper()
                                # check ALL_OBJECTS for table presence and type
                                try:
                                    cursor.execute(
                                        "SELECT OWNER, OBJECT_TYPE FROM ALL_OBJECTS WHERE OWNER = :own AND OBJECT_NAME = :tbl",
                                        (owner_check, table_check)
                                    )
                                    obj = cursor.fetchone()
                                except Exception:
                                    obj = None
                                if not obj:
                                    # object not found or inaccessible
                                    err_msg = f"target object {t} not found or not accessible"
                                    logger.warning(f"Could not create MV log on {t}: {err_msg}")
                                    final_results.append((t, False, err_msg))
                                    continue
                                owner_found, obj_type = obj[0], obj[1]
                                if obj_type.upper() != 'TABLE':
                                    err_msg = f"target object {t} is not a TABLE (found type: {obj_type})"
                                    logger.warning(f"Could not create MV log on {t}: {err_msg}")
                                    final_results.append((t, False, err_msg))
                                    continue

                            except Exception as e:
                                logger.exception("Error checking object existence for %s: %s", t, e)
                                final_results.append((t, False, str(e)))
                                continue

                            # If no existing log or user chose drop, proceed to create
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
                                cursor.execute(sql)
                                conn.commit()
                                logger.info(f"✅ Created materialized view log on {t}")
                                final_results.append((t, True, None))
                            except Exception as e:
                                logger.warning(f"Could not create MV log on {t}: {e}")
                                final_results.append((t, False, str(e)))

                        results = final_results
                        # summarize results and ask user whether to continue on failures
                        succeeded = [r[0] for r in results if r[1]]
                        failed = [(r[0], r[2]) for r in results if not r[1]]
                        if succeeded:
                            try:
                                messagebox.showinfo("MV Logs Created", f"Created logs on: {', '.join(succeeded)}")
                            except Exception:
                                pass
                        if failed:
                            msg_lines = [f"{t}: {err}" for (t, err) in failed]
                            msg = "Some MV logs could not be created:\n\n" + "\n".join(msg_lines) + "\n\nDo you want to continue creating the materialized view anyway?"
                            try:
                                cont = messagebox.askyesno("MV Log Creation Failed", msg)
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

            messagebox.showinfo("Success", f"✅ Materialized View '{mv_name}' created successfully.")
            builder_window.destroy()
            if on_finish:
                on_finish()
        except Exception as e:
            # Log full traceback to help debugging
            import traceback
            tb = traceback.format_exc()
            logger.exception("❌ Error creating materialized view: %s", e)
            # write trace file for easier capture
            try:
                trace_file = Path.cwd() / "mv_debug_trace.txt"
                with trace_file.open("a", encoding="utf-8") as f:
                    f.write("EXCEPTION_DDL:\n")
                    f.write(tb + "\n")
            except Exception:
                pass
            # Provide helpful hint for common MV issues
            hint = "\n\nTip: REFRESH FAST/ON COMMIT may require materialized view logs or PKs on source tables."
            # Show dialog with concise message but include trace in log file
            messagebox.showerror("Error", f"❌ Failed to create materialized view:\n{e}{hint}")
        finally:
            try:
                if cursor:
                    cursor.close()
            except Exception as e:
                logger.warning(f"⚠️ Failed to close cursor: {e}")

            try:
                if conn:
                    conn.close()
            except Exception as e:
                logger.warning(f"⚠️ Failed to close connection: {e}")

    def on_cancel():
        builder_window.destroy()
        if on_finish:
            on_finish()

    builder_window = tk.Toplevel()
    builder_window.title("SQL Materialized View Loader")
    builder_window.geometry("1100x700")
    builder_window.grab_set()

    # Preserve taskbar icon and branding
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        builder_window.iconbitmap(default=icon_path)
    except Exception as e:
        logger.warning(f"⚠️ Failed to set taskbar icon: {e}")

    tk.Label(builder_window, text="Enter SQL to turn into a MATERIALIZED VIEW:", font=("Arial", 11, "bold")).pack(pady=(10, 5))

    sql_text = scrolledtext.ScrolledText(builder_window, width=120, height=25, font=("Courier New", 10))
    sql_text.pack(padx=10, pady=(0, 10), fill="both", expand=False)

    # Use a grid-based control area so widgets can expand proportionally
    control_frame = tk.Frame(builder_window)
    control_frame.pack(pady=8, fill="x", padx=12)

    # Row 0: MV name + DWH checkbox
    tk.Label(control_frame, text="Materialized View Name:").grid(row=0, column=0, sticky="w")
    mv_name_entry = tk.Entry(control_frame)
    mv_name_entry.grid(row=0, column=1, sticky="we", padx=(6, 12))
    dwh_var = tk.BooleanVar()
    dwh_checkbox = tk.Checkbutton(control_frame, text="Load to DWH schema (shared login)", variable=dwh_var)
    dwh_checkbox.grid(row=0, column=2, sticky="w")

    # Configure grid weights so the entry expands
    control_frame.grid_columnconfigure(1, weight=1)

    # Row 1: Parameter frames
    param_frame = tk.Frame(control_frame)
    param_frame.grid(row=1, column=0, columnspan=3, pady=(10, 0), sticky="we")

    # Build mode
    build_frame = tk.LabelFrame(param_frame, text="Build", padx=8, pady=6)
    build_frame.pack(side="left", padx=(0, 12))
    build_var = tk.StringVar(value="IMMEDIATE")
    tk.Radiobutton(build_frame, text="IMMEDIATE", variable=build_var, value="IMMEDIATE").pack(anchor="w")
    tk.Radiobutton(build_frame, text="DEFERRED", variable=build_var, value="DEFERRED").pack(anchor="w")

    # Refresh method
    refresh_frame = tk.LabelFrame(param_frame, text="Refresh Method", padx=8, pady=6)
    refresh_frame.pack(side="left", padx=(0, 12))
    refresh_method_var = tk.StringVar(value="COMPLETE")
    tk.Radiobutton(refresh_frame, text="COMPLETE", variable=refresh_method_var, value="COMPLETE").pack(anchor="w")
    # FAST refresh removed from UI because it's environment/version dependent and
    # often requires destructive log changes. Use ON COMMIT trigger to request
    # log creation instead.
    tk.Radiobutton(refresh_frame, text="FORCE", variable=refresh_method_var, value="FORCE").pack(anchor="w")

    # Refresh trigger
    trigger_frame = tk.LabelFrame(param_frame, text="Refresh Trigger", padx=8, pady=6)
    trigger_frame.pack(side="left", padx=(0, 12))
    refresh_trigger_var = tk.StringVar(value="ON DEMAND")
    tk.Radiobutton(trigger_frame, text="ON DEMAND", variable=refresh_trigger_var, value="ON DEMAND").pack(anchor="w")
    tk.Radiobutton(trigger_frame, text="ON COMMIT", variable=refresh_trigger_var, value="ON COMMIT").pack(anchor="w")

    # Query rewrite
    right_col = tk.Frame(param_frame)
    right_col.pack(side="left", padx=(0, 12))
    rewrite_var = tk.BooleanVar(value=False)
    rewrite_chk = tk.Checkbutton(right_col, text="Enable Query Rewrite", variable=rewrite_var)
    rewrite_chk.pack(anchor="n", pady=(6, 0))

    btn_frame = tk.Frame(builder_window)
    btn_frame.pack(pady=15)

    tk.Button(btn_frame, text="Create Materialized View", command=on_submit, width=22).pack(side="left", padx=10)
    tk.Button(btn_frame, text="Cancel", command=on_cancel, width=10).pack(side="left", padx=10)

    # Center on screen
    builder_window.update_idletasks()
    width = builder_window.winfo_width()
    height = builder_window.winfo_height()
    x = (builder_window.winfo_screenwidth() // 2) - (width // 2)
    y = (builder_window.winfo_screenheight() // 2) - (height // 2)
    builder_window.geometry(f"{width}x{height}+{x}+{y}")
    builder_window.mainloop()
