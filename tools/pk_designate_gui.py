import re
import logging
import json
import tkinter as tk
try:
    import tkinter.ttk as ttk
except Exception:
    ttk = None
from pathlib import Path
from tkinter import Toplevel, Listbox, Scrollbar, Button, Label, Entry, StringVar, Checkbutton, IntVar, messagebox
from tkinter.constants import MULTIPLE, END, LEFT, RIGHT, Y, BOTH
from libs.paths import PROJECT_PATH as base_path

from libs.oracle_db_connector import get_db_connection
from libs import dwh_session

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
    try:
        # register connection on parent if provided so cleanup can clear it
        if schema_choice == 'dwh':
            if parent:
                dwh_session.register_connection(parent, conn)
    except Exception:
        logger.debug('Failed to register dwh connection', exc_info=True)

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

    # cache for table statistics to avoid repeated heavy queries
    table_stats = {}
    # maintain table order mapping: list index -> real table name
    table_order = []

    left_frame = tk.Frame(main_frame)
    left_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0,6))

    center_frame = tk.Frame(main_frame, width=300)
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

    # Row-threshold controls
    threshold_enabled = IntVar(value=0)  # when 0 => threshold disabled => run DISTINCT always
    def _on_threshold_toggle():
        state = 'normal' if threshold_enabled.get() else 'disabled'
        threshold_entry.config(state=state)
        # refresh indicator for currently selected table
        try:
            update_table_indicator()
        except Exception:
            pass

    th_frame = tk.Frame(ctrl)
    th_frame.pack(pady=(0,6))
    Checkbutton(th_frame, text='Use row threshold', variable=threshold_enabled, command=_on_threshold_toggle).pack(side=LEFT)
    threshold_var = StringVar(value='10000')
    Label(th_frame, text='Threshold:').pack(side=LEFT, padx=(8,4))
    # validate threshold input to digits only
    def _validate_threshold(P):
        if P == '':
            return True
        return P.isdigit()

    vcmd = (ctrl.register(_validate_threshold), '%P')
    threshold_entry = Entry(th_frame, textvariable=threshold_var, width=8, validate='key', validatecommand=vcmd)
    threshold_entry.pack(side=LEFT)
    # default disabled until checkbox checked
    threshold_entry.config(state='disabled')

    constraint_name_var = StringVar()
    Label(ctrl, text='Constraint name:').pack(pady=(0,4))
    cname_entry = Entry(ctrl, textvariable=constraint_name_var, width=28)
    cname_entry.pack()
    # Apply pane-aware colors: if the parent/dialog background is dark,
    # make the entry dark background with light text so it matches launcher
    # pane-only dark mode. This detects the window background brightness
    # at creation time and adjusts the entry accordingly.
    def _apply_entry_theme():
        try:
            dark = False
            # Prefer checking the ttk style lookup (launcher toggles this).
            try:
                if ttk:
                    st = ttk.Style()
                    sbg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
                    if isinstance(sbg, str) and sbg.strip():
                        sb = sbg.strip().lower()
                        if sb in ('#000000', '#000') or 'black' in sb:
                            dark = True
            except Exception:
                dark = False

            # Fallback: inspect window bg only if style lookup wasn't decisive
            if not dark:
                try:
                    bg = win.cget('bg')
                    if isinstance(bg, str):
                        b = bg.strip()
                        if b.startswith('#') and len(b) >= 7:
                            try:
                                r = int(b[1:3], 16)
                                g = int(b[3:5], 16)
                                bl = int(b[5:7], 16)
                                lum = 0.2126 * r + 0.7152 * g + 0.0722 * bl
                                dark = lum < 128
                            except Exception:
                                dark = b.lower() in ('#000000', 'black')
                        else:
                            dark = b.lower() in ('black',)
                except Exception:
                    pass

            if dark:
                try:
                    cname_entry.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff')
                except Exception:
                    pass
            else:
                try:
                    cname_entry.config(bg='white', fg='black', insertbackground='black')
                except Exception:
                    pass
        except Exception:
            pass

    _apply_entry_theme()

    # Periodically check the global Pane.Treeview style to detect launcher
    # pane-only dark mode toggles and update the entry colors live. This is
    # best-effort: it reads ttk.Style lookups which the launcher updates when
    # toggling dark mode.
    last_dark = None
    def _poll_theme():
        nonlocal last_dark
        try:
            dark = False
            if ttk:
                try:
                    st = ttk.Style()
                    bg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
                    if isinstance(bg, str) and bg.strip():
                        b = bg.strip().lower()
                        if b in ('#000000', '#000') or 'black' in b:
                            dark = True
                except Exception:
                    dark = False
            # If detection changed, apply new colors
            if dark is not last_dark:
                last_dark = dark
                if dark:
                    try:
                        cname_entry.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff')
                    except Exception:
                        pass
                else:
                    try:
                        cname_entry.config(bg='white', fg='black', insertbackground='black')
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            win.after(600, _poll_theme)
        except Exception:
            pass

    # Start polling for theme changes
    try:
        win.after(600, _poll_theme)
    except Exception:
        pass
    # Button to restore full column list after detect filtered it
    def show_all_columns():
        try:
            on_table_select()
        except Exception:
            pass
        try:
            detect_button.config(state='normal')
        except Exception:
            pass

    Button(ctrl, text='Show All Columns', command=show_all_columns, width=20).pack(pady=(6,0))
    # Help text explaining threshold logic
    help_text = (
        "Threshold behavior: when 'Use row threshold' is checked, DISTINCT checks run only if table rows <= threshold.\n"
        "If unchecked, DISTINCT checks are always performed. Threshold and checkbox state are saved between runs."
    )
    Label(ctrl, text=help_text, wraplength=280, justify='left', fg='#333').pack(pady=(6,0))

    # Settings persistence
    settings_file = Path(base_path) / 'libs' / 'pk_designate_settings.json'

    def load_settings():
        try:
            if settings_file.exists():
                with open(settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    threshold_var.set(str(data.get('threshold', threshold_var.get())))
                    threshold_enabled.set(1 if data.get('use_threshold', False) else 0)
                    _on_threshold_toggle()
        except Exception:
            logger.exception('Failed to load pk_designate settings')

    def save_settings():
        try:
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'threshold': int(threshold_var.get()) if threshold_var.get().isdigit() else 10000,
                'use_threshold': bool(threshold_enabled.get())
            }
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception:
            logger.exception('Failed to save pk_designate settings')

    # bind saving on toggle and when entry loses focus
    threshold_entry.bind('<FocusOut>', lambda e: save_settings())
    th_frame.bind('<ButtonRelease-1>', lambda e: save_settings())
    load_settings()

    def load_tables():
        cur = conn.cursor()
        try:
            cur.execute('SELECT table_name FROM all_tables WHERE owner = :own ORDER BY table_name', [owner])
            rows = cur.fetchall()
            tbl_list.delete(0, END)
            table_order.clear()
            # reset cached stats
            table_stats.clear()
            for r in rows:
                name = r[0]
                tbl_list.insert(END, name)
                table_order.append(name)
            try:
                detect_button.config(state='normal')
            except Exception:
                pass
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
        idx = sel[0]
        # map listbox index to real table name
        try:
            tbl = table_order[idx]
        except Exception:
            tbl = tbl_list.get(idx).split('  (rows:')[0]

        # ensure table_stats structure
        if tbl not in table_stats:
            table_stats[tbl] = {'rowcount': None, 'columns': {}}

        cur = conn.cursor()
        try:
            cur.execute('''
                SELECT column_name, nullable FROM all_tab_columns
                WHERE owner = :own AND table_name = :tbl
                ORDER BY column_id
            ''', [owner, tbl])
            cols = cur.fetchall()
            for col, nullable in cols:
                label = f"{col} {'(NULLABLE)' if nullable == 'Y' else ''}"
                col_list.insert(END, col)
                # cache nullable info
                table_stats[tbl]['columns'][col] = {'nullable': nullable, 'distinct': None}
            # fetch and cache rowcount for tooltip/threshold logic
            if table_stats[tbl]['rowcount'] is None:
                try:
                    rc_cur = conn.cursor()
                    rc_sql = f'SELECT COUNT(*) FROM {_quote_ident(owner)}.{_quote_ident(tbl)}'
                    rc_cur.execute(rc_sql)
                    rc = rc_cur.fetchone()[0]
                    table_stats[tbl]['rowcount'] = rc
                    rc_cur.close()
                except Exception:
                    table_stats[tbl]['rowcount'] = -1
                    logger.exception('Failed to fetch rowcount for %s', tbl)
            # pre-generate a sane constraint name
            cname = _sanitize_constraint_name(f'PK_{tbl}')
            constraint_name_var.set(cname)
            # ensure detect availability updated after loading columns
            try:
                update_table_indicator()
            except Exception:
                pass
        except Exception as e:
            logger.exception('Failed to list columns: %s', e)
            messagebox.showerror('Error', f'Failed to list columns: {e}')
        finally:
            cur.close()

    tbl_list.bind('<<ListboxSelect>>', on_table_select)

    # simple tooltip implementation
    tooltip = None
    def _show_tooltip(widget, text, x, y):
        nonlocal tooltip
        if tooltip:
            try:
                tooltip.destroy()
            except Exception:
                pass
        tooltip = Toplevel(widget)
        tooltip.wm_overrideredirect(True)
        label = Label(tooltip, text=text, bg='#ffffe0', relief='solid', bd=1, padx=4, pady=2)
        label.pack()
        tooltip.wm_geometry(f'+{x}+{y}')

    def _hide_tooltip(event=None):
        nonlocal tooltip
        if tooltip:
            try:
                tooltip.destroy()
            except Exception:
                pass
            tooltip = None

    def on_tbl_motion(event):
        # show rows tooltip for the item under cursor
        idx = tbl_list.nearest(event.y)
        if idx is None:
            _hide_tooltip()
            return
        try:
            item = tbl_list.get(idx)
        except Exception:
            _hide_tooltip()
            return
        # map index to real table name when possible
        try:
            name = table_order[idx]
        except Exception:
            name = item.split('  (rows:')[0]
        rc = table_stats.get(name, {}).get('rowcount')
        if rc is None:
            text = 'rows: unknown'
        else:
            text = f'rows: {rc}'
        x = widget_root_x = win.winfo_rootx() + tbl_list.winfo_x() + 20
        y = win.winfo_rooty() + tbl_list.winfo_y() + event.y + 20
        _show_tooltip(tbl_list, text, x, y)

    tbl_list.bind('<Motion>', on_tbl_motion)
    tbl_list.bind('<Leave>', lambda e: _hide_tooltip())

    def update_table_indicator():
        # Update selected table label to indicate whether DISTINCT will run or be skipped
        sel = tbl_list.curselection()
        if not sel:
            return
        idx = sel[0]
        # determine real name from table_order if available
        try:
            name = table_order[idx]
        except Exception:
            item = tbl_list.get(idx)
            name = item.split('  (rows:')[0]
        stats = table_stats.get(name, {})
        rc = stats.get('rowcount')
        try:
            thr = int(threshold_var.get()) if threshold_var.get().isdigit() else 10000
        except Exception:
            thr = 10000
        if rc is None:
            # rowcount unknown; try to load columns/rowcount
            try:
                on_table_select()
            except Exception:
                pass
            return
        # decide
        if threshold_enabled.get() and rc > thr:
            label = f"{name}  (rows: {rc} — DISTINCT skipped)"
            try:
                detect_button.config(state='disabled')
            except Exception:
                pass
        else:
            label = f"{name}  (rows: {rc})"
            try:
                detect_button.config(state='normal')
            except Exception:
                pass
        # update display
        try:
            tbl_list.delete(idx)
            tbl_list.insert(idx, label)
            tbl_list.selection_set(idx)
        except Exception:
            pass

    # Update when threshold var changes
    try:
        threshold_enabled.trace_add('write', lambda *args: update_table_indicator())
    except Exception:
        try:
            threshold_enabled.trace('w', lambda *args: update_table_indicator())
        except Exception:
            pass
    # Also update when the threshold number itself changes so button state updates immediately
    try:
        threshold_var.trace_add('write', lambda *args: update_table_indicator())
    except Exception:
        try:
            threshold_var.trace('w', lambda *args: update_table_indicator())
        except Exception:
            pass

    def detect_candidates():
        sel = tbl_list.curselection()
        if not sel:
            messagebox.showwarning('Select table', 'Please select a table first')
            return
        idx = sel[0]
        try:
            orig_tbl = table_order[idx]
        except Exception:
            tbl = tbl_list.get(idx)
            orig_tbl = tbl.split('  (rows:')[0].strip()
        tbl = orig_tbl
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
                # Determine whether to run DISTINCT based on threshold settings
                try:
                    threshold = int(threshold_var.get())
                except Exception:
                    threshold = 10000
                if threshold_enabled.get():
                    # use threshold: run DISTINCT only when total <= threshold
                    check_needed = (total <= threshold)
                else:
                    # threshold disabled -> run DISTINCT regardless of row count
                    check_needed = True
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
                # mark the selected table in the table list to indicate DISTINCT ran
                try:
                    sel_idx = idx
                    label = f"{orig_tbl}  (rows: {total} — DISTINCT run)"
                    tbl_list.delete(sel_idx)
                    tbl_list.insert(sel_idx, label)
                    tbl_list.selection_set(sel_idx)
                except Exception:
                    pass
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
        idx = sel[0]
        try:
            tbl = table_order[idx]
        except Exception:
            # fallback: strip any UI suffix
            tbl = tbl_list.get(idx).split('  (rows:')[0].strip()
        cols_idx = col_list.curselection()
        if not cols_idx:
            messagebox.showwarning('Select columns', 'Select one or more columns for the primary key')
            return
        cols = [col_list.get(i) for i in cols_idx]

        # preliminary checks: nulls
        cur = conn.cursor()
        try:
            null_where = ' OR '.join([f'{_quote_ident(c)} IS NULL' for c in cols])
            null_sql = f'SELECT COUNT(*) FROM {_quote_ident(owner)}.{_quote_ident(tbl)} WHERE {null_where}'
            logger.info('Running null check SQL: %s', null_sql)
            cur.execute(null_sql)
            nulls = cur.fetchone()[0]
            if nulls > 0:
                if not messagebox.askyesno('Nulls found', f'{nulls} row(s) have NULL in selected column(s). Proceed?'):
                    return

            # duplicate check
            group_cols = ', '.join([_quote_ident(c) for c in cols])
            dup_sql = f'SELECT COUNT(*) FROM (SELECT {group_cols} FROM {_quote_ident(owner)}.{_quote_ident(tbl)} GROUP BY {group_cols} HAVING COUNT(*) > 1)'
            logger.info('Running duplicate check SQL: %s', dup_sql)
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
    # Move Detect button to center ctrl area (near threshold)
    detect_button = Button(ctrl, text='Detect PK Candidates', command=detect_candidates, width=28)
    detect_button.pack(pady=(8,2))
    # Force detect button (runs detect even when threshold would skip it)
    def force_detect():
        # Temporarily disable threshold enforcement and run detect
        prev = threshold_enabled.get()
        threshold_enabled.set(0)
        _on_threshold_toggle()
        detect_candidates()
        threshold_enabled.set(prev)
        _on_threshold_toggle()

    Button(ctrl, text='Force Detect (override threshold)', command=force_detect, width=28).pack(pady=(0,8))

    btn_frame = tk.Frame(win)
    btn_frame.pack(fill='x', pady=6)
    Button(btn_frame, text='Reload Tables', command=load_tables, width=14).pack(side=LEFT, padx=6)
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

    # Ensure DWH session cleanup for this window/parent
    try:
        target = parent if parent else win
        dwh_session.cleanup(target)
    except Exception:
        logger.debug('DWH cleanup failed', exc_info=True)

if __name__ == '__main__':
    main()
