import re
import logging
import tkinter as tk
from tkinter import Toplevel, Listbox, Scrollbar, Button, Label, Entry, StringVar, Checkbutton, IntVar, messagebox
from tkinter.constants import MULTIPLE, END, LEFT, RIGHT, Y, BOTH

from libs.oracle_db_connector import get_db_connection

logger = logging.getLogger(__name__)


def center_window(window, width, height):
    window.update_idletasks()
    sw = window.winfo_screenwidth()
    sh = window.winfo_screenheight()
    x = int((sw - width) / 2)
    y = int((sh - height) / 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def _ensure_dialog_parent(parent):
    # return a Toplevel (modal) attached to parent or a new Tk when None
    if parent:
        win = Toplevel(parent)
        try:
            # Configure window before grabbing focus to avoid invisible modal
            win.transient(parent)
            win.update_idletasks()
            win.deiconify()
            win.lift()
            win.focus_force()
            # briefly force topmost to ensure visibility
            try:
                win.attributes('-topmost', True)
                win.after(150, lambda: win.attributes('-topmost', False))
            except Exception:
                pass
            # wait until window is actually visible
            for _ in range(60):
                win.update()
                if win.winfo_ismapped():
                    break
        except Exception:
            pass
        return win
    else:
        root = tk.Tk()
        return root


def prompt_schema_choice(parent=None):
    choice = None

    win = _ensure_dialog_parent(parent)
    win.title('Select Schema Scope')
    center_window(win, 320, 140)
    win.resizable(False, False)

    Label(win, text='Choose schema scope:', font=("Arial", 11, 'bold')).pack(pady=(10, 8))

    def pick_user():
        nonlocal choice
        choice = 'user'
        win.destroy()

    def pick_dwh():
        nonlocal choice
        choice = 'dwh'
        win.destroy()

    def on_close():
        nonlocal choice
        choice = None
        win.destroy()

    frm = tk.Frame(win)
    frm.pack(pady=6)
    Button(frm, text='User Schema', width=12, command=pick_user).pack(side=LEFT, padx=6)
    Button(frm, text='DWH Schema', width=12, command=pick_dwh).pack(side=LEFT, padx=6)
    Button(frm, text='Cancel', width=10, command=on_close).pack(side=LEFT, padx=6)

    win.protocol('WM_DELETE_WINDOW', on_close)

    # ensure visible and modal
    try:
        win.deiconify()
        win.lift()
        win.update()
        try:
            win.wait_visibility()
        except tk.TclError:
            # window may have been destroyed by a fast user click; continue
            logger.info('Schema dialog destroyed before visibility; returning choice if set')
            if parent:
                try:
                    win.update()
                except Exception:
                    pass
            # skip further modal setup
            if parent:
                try:
                    # avoid calling wait_window on destroyed widget
                    if win.winfo_exists():
                        win.wait_window()
                except tk.TclError:
                    pass
            else:
                try:
                    if win.winfo_exists():
                        win.mainloop()
                except tk.TclError:
                    pass
            return choice
        try:
            win.attributes('-topmost', True)
            win.after(200, lambda: win.attributes('-topmost', False))
        except Exception:
            pass
        win.grab_set()
    except Exception:
        logger.exception('Failed to show schema dialog')

    if parent:
        try:
            win.wait_window()
        except tk.TclError:
            # window was destroyed; return what was chosen
            logger.info('Schema dialog closed/removed before wait_window completed')
    else:
        try:
            win.mainloop()
        except tk.TclError:
            logger.info('Schema dialog mainloop terminated unexpectedly')

    return choice


def _quote_ident(name):
    # Simple quoting for identifiers; assume name is safe-ish
    return f'"{name}"'


def _sanitize_constraint_name(name: str) -> str:
    # Upper, replace non-alnum with _, truncate to 30 chars (Oracle limit)
    cand = re.sub(r'[^A-Za-z0-9]', '_', name).upper()
    return cand[:30]


def main(parent=None):
    """Entry point for the PK designate tool. Accepts optional parent for proper dialog parenting."""
    schema_choice = prompt_schema_choice(parent)
    if schema_choice is None:
        return

    # Acquire DB connection
    conn = get_db_connection(force_shared=(schema_choice == 'dwh'), root=parent)
    if not conn:
        logger.error('Failed to get DB connection')
        return

    owner = 'DWH' if schema_choice == 'dwh' else conn.username.upper()

    win = _ensure_dialog_parent(parent)
    win.title(f'Designate PRIMARY KEY - {owner}')
    center_window(win, 1100, 560)

    try:
        try:
            win.attributes('-topmost', True)
            win.after(200, lambda: win.attributes('-topmost', False))
        except Exception:
            pass
        win.grab_set()
    except Exception:
        logger.exception('Failed to grab_set pk main window')

    # Layout: main horizontal frame with left, center, right columns
    main_frame = tk.Frame(win)
    main_frame.pack(fill=BOTH, expand=True, padx=8, pady=8)

    left_frame = tk.Frame(main_frame)
    left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0,6))

    center_frame = tk.Frame(main_frame, width=220)
    center_frame.pack(side=LEFT, fill='y', padx=(6,6))

    right_frame = tk.Frame(main_frame)
    right_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(6,0))

    Label(left_frame, text='Tables', font=("Arial", 10, 'bold')).pack()
    tbl_list = Listbox(left_frame, width=40, height=24, exportselection=False)
    tbl_scroll = Scrollbar(left_frame, command=tbl_list.yview)
    tbl_list.config(yscrollcommand=tbl_scroll.set)
    tbl_list.pack(side=LEFT, fill=BOTH, expand=True)
    tbl_scroll.pack(side=RIGHT, fill=Y)

    Label(right_frame, text='Columns (select 1 or more for composite PK)', font=("Arial", 10, 'bold')).pack()
    col_list = Listbox(right_frame, width=60, height=24, selectmode=MULTIPLE, exportselection=False)
    col_scroll = Scrollbar(right_frame, command=col_list.yview)
    col_list.config(yscrollcommand=col_scroll.set)
    col_list.pack(side=LEFT, fill=BOTH, expand=True)
    col_scroll.pack(side=RIGHT, fill=Y)

    # Controls in center column (stacked)
    ctrl = tk.Frame(center_frame)
    ctrl.pack(pady=8)

    expensive_var = IntVar(value=0)
    Checkbutton(ctrl, text='Allow expensive DISTINCT checks', variable=expensive_var).pack(pady=(0,8))

    constraint_name_var = StringVar()
    Label(ctrl, text='Constraint name:').pack(pady=(0,4))
    cname_entry = Entry(ctrl, textvariable=constraint_name_var, width=28)
    cname_entry.pack()
    # Button to restore full column list after detect filtered it
    Button(ctrl, text='Show All Columns', command=lambda: on_table_select(), width=20).pack(pady=(6,0))

    def load_tables():
        cur = conn.cursor()
        try:
            cur.execute('SELECT table_name FROM all_tables WHERE owner = :own ORDER BY table_name', [owner])
            rows = cur.fetchall()
            tbl_list.delete(0, END)
            for r in rows:
                tbl_list.insert(END, r[0])
        except Exception as e:
            logger.exception('Failed to list tables: %s', e)
            messagebox.showerror('Error', f'Failed to list tables: {e}')
        finally:
            cur.close()

    def on_table_select(evt=None):
        sel = tbl_list.curselection()
        col_list.delete(0, END)
        if not sel:
            return
        tbl = tbl_list.get(sel[0])
        cur = conn.cursor()
        try:
            cur.execute('''
                SELECT column_name, nullable FROM all_tab_columns
                WHERE owner = :own AND table_name = :tbl
                ORDER BY column_id
            ''', [owner, tbl])
            for col, nullable in cur.fetchall():
                label = f"{col} {'(NULLABLE)' if nullable == 'Y' else ''}"
                col_list.insert(END, col)
            # pre-generate a sane constraint name
            cname = _sanitize_constraint_name(f'PK_{tbl}')
            constraint_name_var.set(cname)
        except Exception as e:
            logger.exception('Failed to list columns: %s', e)
            messagebox.showerror('Error', f'Failed to list columns: {e}')
        finally:
            cur.close()

    tbl_list.bind('<<ListboxSelect>>', on_table_select)

    def detect_candidates():
        sel = tbl_list.curselection()
        if not sel:
            messagebox.showwarning('Select table', 'Please select a table first')
            return
        tbl = tbl_list.get(sel[0])
        # ensure columns are loaded in case user didn't click the table list
        if col_list.size() == 0:
            on_table_select()
        cur = conn.cursor()
        try:
            # get row count
            count_sql = f'SELECT COUNT(*) FROM { _quote_ident(owner) }.{ _quote_ident(tbl) }'
            logger.info('Running row count SQL: %s', count_sql)
            cur.execute(count_sql)
            total = cur.fetchone()[0]
            logger.info('Table %s total rows: %s', tbl, total)
            candidates = []
            cur.execute('SELECT column_name, nullable FROM all_tab_columns WHERE owner = :own AND table_name = :tbl ORDER BY column_id', [owner, tbl])
            cols_info = cur.fetchall()
            for col, nullable in cols_info:
                # If column is declared nullable, run a data-level null check; skip if any nulls
                if nullable == 'Y':
                    try:
                        null_cur = conn.cursor()
                        null_sql = f'SELECT COUNT(*) FROM {_quote_ident(owner)}.{_quote_ident(tbl)} WHERE {_quote_ident(col)} IS NULL'
                        logger.info('Running null check SQL: %s', null_sql)
                        null_cur.execute(null_sql)
                        nulls = null_cur.fetchone()[0]
                        null_cur.close()
                    except Exception:
                        nulls = 1
                        logger.exception('Null check failed for %s.%s', tbl, col)
                    if nulls > 0:
                        # column contains nulls -> cannot be single-column PK
                        logger.info('Column %s contains %s null(s); skipping', col, nulls)
                        continue
                # quick heuristic: if table empty, treat column as candidate
                if total == 0:
                    candidates.append(col)
                    continue
                check_needed = total <= 10000 or expensive_var.get()
                if check_needed:
                    try:
                        distinct_sql = f'SELECT COUNT(DISTINCT {_quote_ident(col)}) FROM {_quote_ident(owner)}.{_quote_ident(tbl)}'
                        logger.info('Running distinct SQL: %s', distinct_sql)
                        cur.execute(distinct_sql)
                        distinct = cur.fetchone()[0]
                        logger.info('Column %s distinct=%s (nullable=%s)', col, distinct, nullable)
                    except Exception:
                        distinct = -1
                        logger.exception('Distinct count failed for %s.%s', tbl, col)
                    if distinct == total:
                        candidates.append(col)
                else:
                    # assume candidate if non-nullable and small table unknown
                    candidates.append(col)

            # If candidates were found, replace the column list with only candidates
            if candidates:
                col_list.delete(0, END)
                for c in candidates:
                    col_list.insert(END, c)
                col_list.selection_set(0)
            else:
                logger.info('No PK candidates found for %s.%s; candidates list empty', owner, tbl)
                messagebox.showinfo('No candidates', 'No single-column PK candidates detected. You can still select columns for a composite PK.')
        except Exception as e:
            logger.exception('Candidate detection failed: %s', e)
            messagebox.showerror('Error', f'Candidate detection failed: {e}')
        finally:
            cur.close()

    def add_primary_key():
        sel = tbl_list.curselection()
        if not sel:
            messagebox.showwarning('Select table', 'Please select a table first')
            return
        tbl = tbl_list.get(sel[0])
        cols_idx = col_list.curselection()
        if not cols_idx:
            messagebox.showwarning('Select columns', 'Select one or more columns for the primary key')
            return
        cols = [col_list.get(i) for i in cols_idx]

        # preliminary checks: nulls
        cur = conn.cursor()
        try:
            null_where = ' OR '.join([f'{_quote_ident(c)} IS NULL' for c in cols])
            cur.execute(f'SELECT COUNT(*) FROM {_quote_ident(owner)}.{_quote_ident(tbl)} WHERE {null_where}')
            nulls = cur.fetchone()[0]
            if nulls > 0:
                if not messagebox.askyesno('Nulls found', f'{nulls} row(s) have NULL in selected column(s). Proceed?'):
                    return

            # duplicate check
            group_cols = ', '.join([_quote_ident(c) for c in cols])
            dup_sql = f'SELECT COUNT(*) FROM (SELECT {group_cols} FROM {_quote_ident(owner)}.{_quote_ident(tbl)} GROUP BY {group_cols} HAVING COUNT(*) > 1)'
            cur.execute(dup_sql)
            dups = cur.fetchone()[0]
            if dups > 0:
                messagebox.showerror('Duplicates found', f'{dups} duplicate key value(s) found. Cannot create PK.')
                return

            # constraint name
            cname = constraint_name_var.get().strip() or _sanitize_constraint_name(f'PK_{tbl}_' + '_'.join(cols))
            cname = _sanitize_constraint_name(cname)

            sql = f'ALTER TABLE {_quote_ident(owner)}.{_quote_ident(tbl)} ADD CONSTRAINT {_quote_ident(cname)} PRIMARY KEY ({group_cols})'
            if not messagebox.askyesno('Confirm', f'Execute:\n{sql}'):
                return

            try:
                cur.execute(sql)
                conn.commit()
                messagebox.showinfo('Success', f'Primary key {cname} created on {tbl}.')
                logger.info('Created PK %s on %s.%s', cname, owner, tbl)
            except Exception as e:
                conn.rollback()
                logger.exception('Failed to create PK: %s', e)
                messagebox.showerror('Error', f'Failed to create PK: {e}')
        finally:
            cur.close()

    # Buttons
    btn_frame = tk.Frame(win)
    btn_frame.pack(fill='x', pady=6)
    Button(btn_frame, text='Reload Tables', command=load_tables, width=14).pack(side=LEFT, padx=6)
    Button(btn_frame, text='Detect PK Candidates', command=detect_candidates, width=18).pack(side=LEFT, padx=6)
    Button(btn_frame, text='Add PRIMARY KEY', command=add_primary_key, width=16).pack(side=LEFT, padx=6)
    Button(btn_frame, text='Close', command=win.destroy, width=10).pack(side=RIGHT, padx=6)

    load_tables()

    # Wait appropriately
    if parent:
        try:
            win.wait_window()
        except tk.TclError:
            logger.info('PK main window closed before wait_window completed')
    else:
        try:
            win.mainloop()
        except tk.TclError:
            logger.info('PK mainloop terminated unexpectedly')


if __name__ == '__main__':
    main()
