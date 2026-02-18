import tkinter as tk
from tkinter import messagebox
import logging
from libs.oracle_db_connector import get_db_connection
import ctypes
from libs.paths import ASSETS_PATH
import re

logger = logging.getLogger(__name__)


def run_mv_refresh_gui(on_finish=None):
    conn = get_db_connection()
    if not conn:
        return

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

    def create_materialized_view_logs(cursor, conn, tables, log_type, include_new_values=True):
        for t in tables:
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
                logger.info(f"✅ Created materialized view log on {t}")
            except Exception as e:
                logger.warning(f"Could not create MV log on {t}: {e}")

    root = tk.Toplevel()
    root.title("Materialized View Manager")
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        root.iconbitmap(default=icon_path)
    except Exception:
        pass

    root.geometry("900x600")

    left = tk.Frame(root)
    left.pack(side="left", fill="y", padx=8, pady=8)
    right = tk.Frame(root)
    right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

    tk.Label(left, text="Materialized Views:").pack(anchor="w")
    mview_listbox = tk.Listbox(left, width=30, height=30)
    mview_listbox.pack(fill="y")

    info_text = tk.Text(right, height=8)
    info_text.pack(fill="x")

    sql_text = tk.Text(right, height=16)
    sql_text.pack(fill="both", expand=True, pady=(6, 0))

    btn_frame = tk.Frame(right)
    btn_frame.pack(fill="x", pady=6)

    refresh_mode_var = tk.StringVar(value='C')
    tk.Radiobutton(btn_frame, text="COMPLETE", variable=refresh_mode_var, value='C').pack(side="left", padx=6)
    tk.Radiobutton(btn_frame, text="FAST", variable=refresh_mode_var, value='F').pack(side="left", padx=6)
    tk.Radiobutton(btn_frame, text="FORCE", variable=refresh_mode_var, value='?').pack(side="left", padx=6)

    def load_mviews():
        try:
            cur = conn.cursor()
            cur.execute("SELECT mview_name, build_mode, refresh_method, rewrite_enabled, last_refresh_date, QUERY FROM user_mviews ORDER BY mview_name")
            rows = cur.fetchall()
            mview_listbox.delete(0, tk.END)
            for r in rows:
                name = r[0]
                mview_listbox.insert(tk.END, name)
            # store metadata
            root._mview_rows = {r[0]: r for r in rows}
            cur.close()
        except Exception as e:
            logger.exception(f"Failed to load materialized views: {e}")

    def on_select(event=None):
        sel = mview_listbox.curselection()
        if not sel:
            return
        name = mview_listbox.get(sel[0])
        row = root._mview_rows.get(name)
        info_text.delete('1.0', tk.END)
        info_text.insert(tk.END, f"Name: {row[0]}\nBuild: {row[1]}\nRefresh Method: {row[2]}\nRewrite Enabled: {row[3]}\nLast Refresh: {row[4]}\n")
        sql_text.delete('1.0', tk.END)
        try:
            sql_text.insert(tk.END, row[5] or "")
        except Exception:
            sql_text.insert(tk.END, "")

    def do_refresh():
        sel = mview_listbox.curselection()
        if not sel:
            messagebox.showwarning("Select MV", "Please select a materialized view first.")
            return
        name = mview_listbox.get(sel[0])
        mode = refresh_mode_var.get()
        try:
            cur = conn.cursor()
            # map '?' to FORCE
            mode_code = mode if mode in ('C', 'F') else ' ? '
            cur.execute(f"BEGIN DBMS_MVIEW.REFRESH('{name}','{mode}'); END;")
            conn.commit()
            messagebox.showinfo("Refresh", f"Refresh of {name} requested ({mode}).")
            cur.close()
            load_mviews()
        except Exception as e:
            logger.exception(f"Failed to refresh {name}: {e}")
            messagebox.showerror("Refresh Failed", str(e))

    def do_create_logs():
        sel = mview_listbox.curselection()
        if not sel:
            messagebox.showwarning("Select MV", "Please select a materialized view first.")
            return
        name = mview_listbox.get(sel[0])
        row = root._mview_rows.get(name)
        mv_query = row[5] or ''
        tables = detect_tables_from_sql(mv_query)
        if not tables:
            messagebox.showinfo("No tables", "Could not detect base tables from the MV query.")
            return
        # Simple confirmation dialog
        if not messagebox.askyesno("Create Logs", f"Create materialized view logs on: {', '.join(tables)}?"):
            return
        try:
            cur = conn.cursor()
            create_materialized_view_logs(cur, conn, tables, 'ROWID', include_new_values=True)
            cur.close()
            messagebox.showinfo("Logs", "Attempted to create logs. Check logs for details.")
            load_mviews()
        except Exception as e:
            logger.exception(f"Failed to create logs: {e}")
            messagebox.showerror("Error", str(e))

    tk.Button(btn_frame, text="Refresh MV", command=do_refresh).pack(side="right", padx=6)
    tk.Button(btn_frame, text="Create Logs", command=do_create_logs).pack(side="right", padx=6)

    mview_listbox.bind('<<ListboxSelect>>', on_select)

    load_mviews()

    def on_close():
        try:
            conn.close()
        except Exception:
            pass
        root.destroy()
        if on_finish:
            on_finish()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
