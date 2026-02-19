import tkinter as tk
from tkinter import messagebox
import logging
from libs.oracle_db_connector import get_db_connection
import ctypes
from libs.paths import ASSETS_PATH
import re

logger = logging.getLogger(__name__)


def run_mv_refresh_gui(on_finish=None):
    # Backwards-compatible parameter handling: the launcher may pass a parent
    # window (root) as the first argument. If a non-callable is passed, treat
    # it as parent and clear on_finish.
    parent = None
    if on_finish is not None and not callable(on_finish):
        parent = on_finish
        on_finish = None

    conn = get_db_connection()
    if not conn:
        return

    # use shared helper if available
    try:
        from libs.mv_log_utils import detect_tables_from_sql
    except Exception:
        def detect_tables_from_sql(sql_text):
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

    try:
        from libs.mv_log_utils import detect_existing_mlog, get_dependent_mviews
    except Exception:
        detect_existing_mlog = None
        get_dependent_mviews = None

    def create_materialized_view_logs(cursor, conn, tables, log_type, include_new_values=True):
        for t in tables:
            try:
                # If a helper is available, detect an existing log and surface via logs
                if detect_existing_mlog:
                    try:
                        meta = detect_existing_mlog(cursor, t)
                        if meta.get('exists'):
                            logger.info(f"Existing MV log detected for {t}: {meta.get('log_tables')}")
                    except Exception:
                        pass

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
            except Exception as e:
                logger.warning(f"Could not create MV log on {t}: {e}")

    root = tk.Toplevel(parent) if parent is not None else tk.Toplevel()
    root.title("Materialized View Manager")
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        root.iconbitmap(default=icon_path)
    except Exception:
        pass

    root.geometry("1200x650")

    left = tk.Frame(root)
    left.pack(side="left", fill="y", padx=8, pady=8)
    right = tk.Frame(root)
    right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

    tk.Label(left, text="Materialized Views:").pack(anchor="w")
    mview_listbox = tk.Listbox(left, width=40, height=30)
    mview_listbox.pack(fill="y")

    info_text = tk.Text(right, height=8)
    info_text.pack(fill="x")

    sql_text = tk.Text(right, height=16)
    sql_text.pack(fill="both", expand=True, pady=(6, 0))

    btn_frame = tk.Frame(right)
    btn_frame.pack(fill="x", pady=6)

    # Only COMPLETE refresh supported in this environment. FAST/ FORCED refresh
    # behavior was found unreliable and is intentionally not offered here.
    refresh_mode_var = tk.StringVar(value='C')
    tk.Radiobutton(btn_frame, text="COMPLETE", variable=refresh_mode_var, value='C').pack(side="left", padx=6)

    # Log creation options
    log_type_var = tk.StringVar(value='ROWID')
    tk.Label(btn_frame, text="  Log Type:").pack(side="left", padx=(12,0))
    tk.Radiobutton(btn_frame, text="WITH ROWID", variable=log_type_var, value='ROWID').pack(side="left", padx=4)
    tk.Radiobutton(btn_frame, text="WITH PRIMARY KEY", variable=log_type_var, value='PRIMARY KEY').pack(side="left", padx=4)
    include_new_var = tk.BooleanVar(value=True)
    tk.Checkbutton(btn_frame, text="INCLUDING NEW VALUES", variable=include_new_var).pack(side="left", padx=(8,0))

    def load_mviews(selected_name=None):
        try:
            cur = conn.cursor()
            # include REFRESH_MODE (ON DEMAND / ON COMMIT) when available
            try:
                cur.execute("SELECT mview_name, build_mode, refresh_method, refresh_mode, rewrite_enabled, last_refresh_date, QUERY FROM user_mviews ORDER BY mview_name")
            except Exception:
                # fallback for DBs that don't expose REFRESH_MODE column
                cur.execute("SELECT mview_name, build_mode, refresh_method, rewrite_enabled, last_refresh_date, QUERY FROM user_mviews ORDER BY mview_name")
            rows = cur.fetchall()
            mview_listbox.delete(0, tk.END)
            for r in rows:
                name = r[0]
                mview_listbox.insert(tk.END, name)
            # store metadata
            # attach as normal attribute for later lookup
            setattr(root, '_mview_rows', {r[0]: r for r in rows})
            cur.close()
            # restore selection if requested
            try:
                if selected_name:
                    # find index of the selected name
                    for i in range(mview_listbox.size()):
                        if mview_listbox.get(i) == selected_name:
                            mview_listbox.selection_clear(0, tk.END)
                            mview_listbox.selection_set(i)
                            mview_listbox.activate(i)
                            # update right pane to reflect restored selection
                            on_select()
                            break
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Failed to load materialized views: {e}")

    def on_select(event=None):
        sel = mview_listbox.curselection()
        if not sel:
            return
        name = mview_listbox.get(sel[0])
        row = getattr(root, '_mview_rows', {}).get(name)
        if not row:
            return
        # defensive extraction because REFRESH_MODE may not be available in older DBs
        build = row[1] if len(row) > 1 else ''
        refresh_method = row[2] if len(row) > 2 else ''
        refresh_mode = row[3] if len(row) > 3 else ''
        rewrite_enabled = row[4] if len(row) > 4 else (row[3] if len(row) > 3 else '')
        last_refresh = row[5] if len(row) > 5 else (row[4] if len(row) > 4 else '')
        query = row[6] if len(row) > 6 else (row[5] if len(row) > 5 else '')

        info_text.delete('1.0', tk.END)
        info_text.insert(tk.END, f"Name: {row[0]}\nBuild: {build}\nRefresh Method: {refresh_method}\nRefresh Type: {refresh_mode or 'ON DEMAND'}\nRewrite Enabled: {rewrite_enabled}\nLast Refresh: {last_refresh}\n")
        # Insert current log type information (bold, blue)
        try:
            info_text.tag_configure('logtype', foreground='blue', font=('Arial', 10, 'bold'))
        except Exception:
            pass
        log_info = ''
        try:
            mv_sql = query or ''
            if mv_sql and 'detect_tables_from_sql' in globals():
                bases = detect_tables_from_sql(mv_sql)
            else:
                bases = []
            # Fallback: if regex detection failed, try USER_DEPENDENCIES / ALL_DEPENDENCIES to find referenced tables
            if not bases:
                try:
                    cur = conn.cursor()
                    try:
                        cur.execute(
                            "SELECT REFERENCED_OWNER, REFERENCED_NAME FROM USER_DEPENDENCIES WHERE NAME = :mv AND REFERENCED_TYPE = 'TABLE'",
                            (row[0],)
                        )
                        dep_rows = cur.fetchall()
                        if dep_rows:
                            bases = [ (r[0] + '.' + r[1]) if r[0] else r[1] for r in dep_rows ]
                        else:
                            # try ALL_DEPENDENCIES with current user as owner
                            try:
                                cur.execute("SELECT USER FROM DUAL")
                                cur_user = cur.fetchone()[0]
                                cur.execute(
                                    "SELECT REFERENCED_OWNER, REFERENCED_NAME FROM ALL_DEPENDENCIES WHERE OWNER = :own AND NAME = :mv AND REFERENCED_TYPE = 'TABLE'",
                                    (cur_user, row[0])
                                )
                                dep_rows = cur.fetchall()
                                bases = [ f"{r[0]}.{r[1]}" for r in dep_rows ]
                            except Exception:
                                bases = []
                    finally:
                        try:
                            cur.close()
                        except Exception:
                            pass
                except Exception:
                    bases = []
            # Filter out the MV itself if it appears in the detected bases
            try:
                mv_basename = row[0].split('.')[-1].upper()
                filtered = []
                seen = set()
                for b in bases:
                    try:
                        bname = str(b).split('.')[-1].upper()
                    except Exception:
                        bname = str(b).upper()
                    if bname == mv_basename:
                        # skip self-reference
                        continue
                    if b not in seen:
                        seen.add(b)
                        filtered.append(b)
                bases = filtered
            except Exception:
                pass
            if not bases:
                log_info = 'Current Log Type: (no base tables detected)'
            else:
                parts = []
                try:
                    cur = conn.cursor()
                    for b in bases:
                        try:
                            if detect_existing_mlog:
                                meta = detect_existing_mlog(cur, b)
                                if meta and meta.get('exists'):
                                    parts.append(f"{b}: {meta.get('existing_type','UNKNOWN')}")
                                else:
                                    parts.append(f"{b}: No log")
                            else:
                                parts.append(f"{b}: (no detection)")
                        except Exception:
                            parts.append(f"{b}: (error)")
                    cur.close()
                except Exception:
                    parts = [f"{b}: (no access)" for b in bases]
                log_info = 'Current Log Type: ' + '; '.join(parts)
        except Exception:
            log_info = 'Current Log Type: (unknown)'
        # insert with tag
        try:
            info_text.insert(tk.END, log_info + '\n', 'logtype')
        except Exception:
            info_text.insert(tk.END, log_info + '\n')
        sql_text.delete('1.0', tk.END)
        try:
            sql_text.insert(tk.END, query or "")
        except Exception:
            sql_text.insert(tk.END, "")

    def do_refresh():
        sel = mview_listbox.curselection()
        if not sel:
            messagebox.showwarning("Select MV", "Please select a materialized view first.")
            return
        name = mview_listbox.get(sel[0])
        # Only COMPLETE mode is supported here; pass 'C' to DBMS_MVIEW.REFRESH
        mode = 'C'
        try:
            cur = conn.cursor()
            cur.execute(f"BEGIN DBMS_MVIEW.REFRESH('{name}','{mode}'); END;")
            conn.commit()
            messagebox.showinfo("Refresh", f"Refresh of {name} requested (COMPLETE).")
            cur.close()
            load_mviews(name)
        except Exception as e:
            logger.exception(f"Failed to refresh {name}: {e}")
            messagebox.showerror("Refresh Failed", str(e))

    def do_create_logs():
        sel = mview_listbox.curselection()
        if not sel:
            messagebox.showwarning("Select MV", "Please select a materialized view first.")
            return
        name = mview_listbox.get(sel[0])
        row = getattr(root, '_mview_rows', {}).get(name)
        mv_query = ''
        if row:
            mv_query = row[6] if len(row) > 6 else (row[5] if len(row) > 5 else '')
        tables = detect_tables_from_sql(mv_query)
        if not tables:
            messagebox.showinfo("No tables", "Could not detect base tables from the MV query.")
            return
        # Ask user to confirm table list and chosen options
        opt_label = f"Create materialized view logs on: {', '.join(tables)}\nType: {log_type_var.get()}\nINCLUDING NEW VALUES: {include_new_var.get()}"
        if not messagebox.askyesno("Create Logs", opt_label):
            return

        results = []
        try:
            cur = conn.cursor()
            for t in tables:
                try:
                    # If helper available, detect existing log and offer reuse/drop
                    choice = None
                    if 'detect_existing_mlog' in globals() and detect_existing_mlog:
                        try:
                            meta = detect_existing_mlog(cur, t)
                        except Exception:
                            meta = None
                        if meta and meta.get('exists'):
                            # Build desired SQL preview
                            try:
                                logger.debug("detect_existing_mlog meta for %s: %s", t, meta)
                            except Exception:
                                pass
                            desired_sql = f"DROP MATERIALIZED VIEW LOG ON {t};\nCREATE MATERIALIZED VIEW LOG ON {t} \n"
                            if log_type_var.get() == 'ROWID':
                                desired_sql += "  WITH ROWID\n"
                            else:
                                desired_sql += "  WITH PRIMARY KEY\n"
                            if include_new_var.get():
                                desired_sql += "  INCLUDING NEW VALUES"

                            def show_existing_log_options_compact(table_name, meta_info, desired_sql_text):
                                try:
                                    dlg = tk.Toplevel(root)
                                    dlg.title(f"Existing MV Log on {table_name}")
                                    dlg.grab_set()
                                except Exception:
                                    # fallback: simple yes/no for drop
                                    ans = messagebox.askyesno("Existing MV Log Detected", f"A materialized view log already exists on {table_name}.\nDrop and recreate?")
                                    return 'drop' if ans else None

                                tk.Label(dlg, text=f"A materialized view log already exists on {table_name}.").pack(padx=12, pady=(8,4), anchor='w')
                                deps = meta_info.get('deps') or []
                                tk.Label(dlg, text=f"{len(deps)} material view(s) that may be dependent:").pack(padx=12, anchor='w')
                                from tkinter import scrolledtext as _sc
                                deps_box = _sc.ScrolledText(dlg, width=60, height=6)
                                deps_box.pack(padx=12, pady=(0,6))
                                if deps:
                                    for m in deps:
                                        deps_box.insert('end', f"{m}\n")
                                else:
                                    deps_box.insert('1.0', '(none detected)')
                                deps_box.config(state='disabled')

                                tk.Label(dlg, text="Existing log columns:").pack(padx=12, anchor='w')
                                cols = meta_info.get('cols') or []
                                cols_frame = tk.Frame(dlg)
                                cols_frame.pack(padx=12, pady=(0,6), anchor='w')
                                if cols:
                                    for c in cols:
                                        tk.Label(cols_frame, text=f"- {c}").pack(anchor='w')
                                else:
                                    tk.Label(cols_frame, text="(could not read columns)").pack(anchor='w')

                                tk.Label(dlg, text="DDL Preview:").pack(padx=12, anchor='w')
                                ddl_box = _sc.ScrolledText(dlg, width=60, height=4)
                                ddl_box.pack(padx=12, pady=(4,6))
                                ddl_box.insert('1.0', desired_sql_text)
                                ddl_box.config(state='disabled')

                                def show_diag():
                                    try:
                                        meta_text = str(meta_info or {})
                                        try:
                                            cursor = conn.cursor()
                                            master_name = table_name.split('.')[-1].upper()
                                            diag_lines = []
                                            try:
                                                cursor.execute("SELECT COUNT(*) FROM USER_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                                                diag_lines.append(f"user_mview_logs_count: {cursor.fetchone()[0]}")
                                            except Exception:
                                                diag_lines.append("user_mview_logs_count: (no access)")
                                            try:
                                                cursor.execute("SELECT COUNT(*) FROM ALL_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                                                diag_lines.append(f"all_mview_logs_count: {cursor.fetchone()[0]}")
                                            except Exception:
                                                diag_lines.append("all_mview_logs_count: (no access)")
                                            try:
                                                mlog_name = f"MLOG$_{master_name}"
                                                cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                                                diag_lines.append(f"user_tables_mlog_count: {cursor.fetchone()[0]}")
                                            except Exception:
                                                diag_lines.append("user_tables_mlog_count: (no access)")
                                            try:
                                                cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                                                diag_lines.append(f"all_tables_mlog_count: {cursor.fetchone()[0]}")
                                            except Exception:
                                                diag_lines.append("all_tables_mlog_count: (no access)")
                                            cursor.close()
                                        except Exception:
                                            diag_lines = ["(could not collect diag counts)"]
                                        txt = f"detect_existing_mlog meta: {meta_text}\n" + '\n'.join(diag_lines)
                                        messagebox.showinfo('Debug Info', txt)
                                    except Exception as e:
                                        try:
                                            messagebox.showwarning('Debug Failed', f'Could not show debug info: {e}')
                                        except Exception:
                                            pass

                                tk.Button(dlg, text='Show debug info', command=show_diag).pack(padx=12, anchor='w', pady=(4,0))

                                ack = tk.BooleanVar(value=False)
                                ack_cb = tk.Checkbutton(dlg, text=f"I understand this will affect the {len(deps)} listed materialized view(s).", variable=ack)
                                ack_cb.pack(padx=12, pady=(4,4), anchor='w')

                                result = {'value': None}

                                def do_reuse():
                                    result['value'] = 'reuse'
                                    dlg.destroy()

                                def do_drop():
                                    if not ack.get():
                                        return
                                    result['value'] = 'drop'
                                    dlg.destroy()

                                def do_cancel():
                                    result['value'] = None
                                    dlg.destroy()

                                btnf = tk.Frame(dlg)
                                btnf.pack(pady=8)
                                tk.Button(btnf, text=f"Reuse Existing Log - {meta_info.get('existing_type','UNKNOWN')}", command=do_reuse, width=26).pack(side='left', padx=(0,6))
                                tk.Button(btnf, text="Cancel", command=do_cancel, width=10).pack(side='left', padx=6)
                                tk.Button(btnf, text="Drop & Recreate", command=do_drop, width=14).pack(side='left', padx=6)

                                dlg.update_idletasks()
                                dlg.geometry(f"{dlg.winfo_width()}x{dlg.winfo_height()}+{(dlg.winfo_screenwidth()//2)-(dlg.winfo_width()//2)}+{(dlg.winfo_screenheight()//2)-(dlg.winfo_height()//2)}")
                                try:
                                    dlg.wait_window(dlg)
                                except Exception:
                                    try:
                                        dlg.mainloop()
                                    except Exception:
                                        pass
                                return result.get('value')

                            choice = show_existing_log_options_compact(t, meta, desired_sql)
                            # If the user cancelled the existing-log dialog, treat as explicit cancel
                            # and do not attempt to create a log (avoids ORA-12000 when a log exists).
                            if choice is None:
                                results.append((t, False, 'user_cancel'))
                                continue

                    # Perform actions based on choice
                    if choice == 'reuse':
                        results.append((t, 'reused', None))
                        continue
                    elif choice == 'drop':
                        try:
                            cur.execute(f"DROP MATERIALIZED VIEW LOG ON {t}")
                            conn.commit()
                        except Exception as e:
                            results.append((t, False, f"drop_failed: {e}"))
                            continue

                    # Try to create the log
                    try:
                        sql = f"CREATE MATERIALIZED VIEW LOG ON {t} \n"
                        if log_type_var.get() == 'ROWID':
                            sql += "  WITH ROWID\n"
                        else:
                            sql += "  WITH PRIMARY KEY\n"
                        if include_new_var.get():
                            sql += "  INCLUDING NEW VALUES"
                        cur.execute(sql)
                        conn.commit()
                        results.append((t, True, None))
                    except Exception as e:
                        err = str(e)
                        # If DB reports the log already exists (ORA-12000), offer to drop & recreate
                        if 'ORA-12000' in err or 'materialized view log already exists' in err.lower():
                            try:
                                do_drop = messagebox.askyesno('Existing MV Log', f"The database reports a materialized view log already exists on {t}.\nDrop and recreate with the selected options?")
                            except Exception:
                                do_drop = False
                            if do_drop:
                                try:
                                    cur.execute(f"DROP MATERIALIZED VIEW LOG ON {t}")
                                    conn.commit()
                                    # try create again
                                    cur.execute(sql)
                                    conn.commit()
                                    results.append((t, True, None))
                                    continue
                                except Exception as e2:
                                    results.append((t, False, f"recreate_failed: {e2}"))
                                    continue
                        results.append((t, False, err))
                except Exception as e:
                    results.append((t, False, str(e)))
            cur.close()

            # Summarize
            created = [r[0] for r in results if r[1] is True]
            reused = [r[0] for r in results if r[1] == 'reused']
            failed = [(r[0], r[2]) for r in results if r[1] is False]
            msgs = []
            if created:
                msgs.append(f"Created logs on: {', '.join(created)}")
            if reused:
                msgs.append(f"Reused existing logs: {', '.join(reused)}")
            if msgs:
                messagebox.showinfo("MV Logs Created", "\n".join(msgs))
            if failed:
                msg_lines = [f"{t}: {err}" for (t, err) in failed]
                messagebox.showwarning("Some logs failed", "\n".join(msg_lines))
            # preserve selection so the user can perform another action on the same MV
            try:
                sel = mview_listbox.curselection()
                sel_name = mview_listbox.get(sel[0]) if sel else None
            except Exception:
                sel_name = None
            load_mviews(sel_name)
        except Exception as e:
            logger.exception(f"Failed to create logs: {e}")
            messagebox.showerror("Error", str(e))

    tk.Button(btn_frame, text="Refresh MV", command=do_refresh).pack(side="right", padx=6)
    tk.Button(btn_frame, text="Create Logs", command=do_create_logs).pack(side="right", padx=6)

    mview_listbox.bind('<<ListboxSelect>>', on_select)

    load_mviews()

    # Center window on screen (was opening slightly left on some displays)
    try:
        root.update_idletasks()
        w = root.winfo_width()
        h = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (w // 2)
        y = (root.winfo_screenheight() // 2) - (h // 2)
        root.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass

    def on_close():
        try:
            conn.close()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass
        # Call on_finish only if provided and callable
        if callable(on_finish):
            try:
                on_finish()
            except Exception:
                logger.exception("Error in on_finish callback for mv_refresh_gui")

    root.protocol("WM_DELETE_WINDOW", on_close)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        # If the process is force-terminated or interrupted while the GUI is open,
        # attempt a graceful shutdown to avoid printing a traceback to the user.
        try:
            logger.info("mv_refresh_gui interrupted by KeyboardInterrupt; closing window")
            on_close()
        except Exception:
            pass
    except Exception as e:
        # Catch-all to prevent exceptions inside the Tk event loop from bubbling
        # up into the caller unexpectedly. Log for diagnostics and try to close.
        logger.exception("Unexpected exception in mv_refresh_gui mainloop: %s", e)
        try:
            on_close()
        except Exception:
            pass
