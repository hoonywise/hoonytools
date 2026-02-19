import tkinter as tk
from tkinter import messagebox, scrolledtext
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

    def create_materialized_view_logs(cursor, conn, tables, log_type, include_new_values=True):
        """Attempt to create materialized view logs for the given tables.
        tables: list of strings like SCHEMA.TABLE or TABLE
        log_type: 'ROWID' or 'PRIMARY KEY'
        include_new_values: bool
        """
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
                cursor.execute(sql)
                conn.commit()
                logger.info(f"✅ Created materialized view log on {t}")
            except Exception as e:
                # Log and continue — the MV creation step will surface errors if necessary
                logger.warning(f"Could not create MV log on {t}: {e}")
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
        # If FAST refresh or ON COMMIT requested, detect base tables and offer to create logs
        need_logs = (refresh_method in ("FAST",) or refresh_trigger in ("ON COMMIT",))
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
                        create_materialized_view_logs(cursor, conn, selected_tables, log_type, include_new_values)
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
    tk.Radiobutton(refresh_frame, text="FAST", variable=refresh_method_var, value="FAST").pack(anchor="w")
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
