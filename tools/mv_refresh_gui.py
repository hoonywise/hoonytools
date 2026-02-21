import tkinter as tk
import logging
try:
    import tkinter.ttk as ttk
except Exception:
    ttk = None
from libs.oracle_db_connector import get_db_connection
from libs import session
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
    # If we obtained a connection for the user/schema1, update session label
    try:
        if hasattr(conn, 'username') and conn.username:
            session.set_label('schema1', conn.username)
    except Exception:
        pass

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
    # If this dialog was launched from the main launcher, make it modal so
    # the main GUI cannot be interacted with while the MV Manager is open.
    grabbed = False
    try:
        if parent is not None:
            try:
                root.transient(parent)
                root.update_idletasks()
                root.deiconify()
                root.lift()
            except Exception:
                pass
            try:
                root.grab_set()
                grabbed = True
            except Exception:
                grabbed = False
    except Exception:
        pass

    left = tk.Frame(root)
    left.pack(side="left", fill="y", padx=8, pady=8)
    right = tk.Frame(root)
    right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

    # List to track all buttons for dark mode styling
    _all_buttons = []

    # User MVs pane (LabelFrame with dynamic header and count)
    user_frame = tk.LabelFrame(left, padx=6, pady=6)
    user_frame.pack(fill="both", pady=(0, 8), expand=True)

    # Dynamic schema label for user pane
    user_label_frame = tk.Frame(user_frame)
    user_schema_label = tk.Label(user_label_frame, text=session.get_label('schema1') + (" MVs" if session.get_label('schema1') != 'Not Connected' else ""), font=("Arial", 9, "bold"))
    user_schema_label.pack(side="left")
    user_frame.configure(labelwidget=user_label_frame)

    user_btn_frame = tk.Frame(user_frame)
    user_btn_frame.pack(fill="x")
    btn_refresh_user = tk.Button(user_btn_frame, text="Refresh", width=8, command=lambda: load_user_mviews())
    btn_refresh_user.pack(side="left")
    _all_buttons.append(btn_refresh_user)

    mview_listbox_user = tk.Listbox(user_frame, width=40, height=14, selectmode=tk.EXTENDED, exportselection=False)
    mview_listbox_user.pack(fill="both", expand=True)

    # DWH MVs pane (LabelFrame with dynamic header and count, lazy login)
    dwh_frame = tk.LabelFrame(left, padx=6, pady=6)
    dwh_frame.pack(fill="both", expand=True)

    dwh_label_frame = tk.Frame(dwh_frame)
    dwh_schema_label = tk.Label(dwh_label_frame, text=session.get_label('schema2') + (" MVs" if session.get_label('schema2') != 'Not Connected' else ""), font=("Arial", 9, "bold"))
    dwh_schema_label.pack(side="left")
    dwh_frame.configure(labelwidget=dwh_label_frame)

    dwh_btn_frame = tk.Frame(dwh_frame)
    dwh_btn_frame.pack(fill="x")
    btn_refresh_dwh = tk.Button(dwh_btn_frame, text="Refresh", width=8, command=lambda: refresh_dwh_mviews())
    btn_refresh_dwh.pack(side="left")
    _all_buttons.append(btn_refresh_dwh)

    mview_listbox_dwh = tk.Listbox(dwh_frame, width=40, height=14, selectmode=tk.EXTENDED, exportselection=False)
    mview_listbox_dwh.pack(fill="both", expand=True)

    # External count labels positioned at right edge of each LabelFrame title (like hoonytools)
    user_count_label = tk.Label(left, text="", font=("Arial", 8))
    dwh_count_label = tk.Label(left, text="", font=("Arial", 8))

    def position_count_labels(event=None):
        try:
            left.update_idletasks()
            right_padding = 20

            # User frame count label
            uy = user_frame.winfo_y()
            frame_x = user_frame.winfo_x()
            frame_w = user_frame.winfo_width()
            label_w = user_count_label.winfo_reqwidth()
            user_count_label.place(x=frame_x + frame_w - label_w - right_padding, y=uy)

            # DWH frame count label
            dy = dwh_frame.winfo_y()
            frame2_x = dwh_frame.winfo_x()
            frame2_w = dwh_frame.winfo_width()
            label2_w = dwh_count_label.winfo_reqwidth()
            dwh_count_label.place(x=frame2_x + frame2_w - label2_w - right_padding, y=dy)
        except Exception:
            pass

    left.bind('<Configure>', position_count_labels)
    root.after(100, position_count_labels)

    info_text = tk.Text(right, height=8)
    info_text.pack(fill="x")

    sql_text = tk.Text(right, height=16)
    sql_text.pack(fill="both", expand=True, pady=(6, 0))

    # Theme helper: detect launcher pane-only dark mode by checking ttk style
    # lookups (launcher configures Pane.Treeview when toggling). Prefer using
    # the launcher's callback registration API when available; fall back to
    # polling the style lookup.
    last_dark = None
    def _detect_dark_from_style():
        try:
            if ttk:
                st = ttk.Style()
                bg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
                if isinstance(bg, str) and bg.strip():
                    b = bg.strip().lower()
                    if b in ('#000000', '#000') or 'black' in b:
                        return True
        except Exception:
            pass
        return False

    def _apply_text_theme(dark):
        try:
            if dark:
                info_text.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff', selectbackground='#2a6bd6')
                sql_text.config(bg='#000000', fg='#ffffff', insertbackground='#ffffff', selectbackground='#2a6bd6')
                try:
                    info_text.tag_configure('logtype', foreground='#66ccff', selectforeground='#ffffff')
                except Exception:
                    pass
            else:
                info_text.config(bg='white', fg='black', insertbackground='black', selectbackground='#2a6bd6')
                sql_text.config(bg='white', fg='black', insertbackground='black', selectbackground='#2a6bd6')
                try:
                    info_text.tag_configure('logtype', foreground='blue', selectforeground='#ffffff')
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

    # Helpers to update dynamic header labels and counts
    def update_user_header():
        try:
            label = session.get_label('schema1')
            if label and label != 'Not Connected':
                user_schema_label.config(text=f"{label} MVs")
            else:
                user_schema_label.config(text="Not Connected")
        except Exception:
            pass

    def update_dwh_header():
        try:
            label = session.get_label('schema2')
            if label and label != 'Not Connected':
                dwh_schema_label.config(text=f"{label} MVs")
            else:
                dwh_schema_label.config(text="Not Connected")
        except Exception:
            pass

    # Callback invoked by launcher when theme toggles
    def _theme_cb(enable_dark: bool):
        try:
            _apply_text_theme(bool(enable_dark))
        except Exception:
            pass

    # Register with parent if possible; otherwise start polling as a fallback
    try:
        if parent and hasattr(parent, 'register_theme_callback'):
            try:
                parent.register_theme_callback(_theme_cb)
            except Exception:
                pass

            # Ensure we unregister when this window is destroyed
            def _on_destroy(event=None):
                try:
                    if parent and hasattr(parent, 'unregister_theme_callback'):
                        parent.unregister_theme_callback(_theme_cb)
                except Exception:
                    pass
            try:
                root.bind('<Destroy>', _on_destroy)
            except Exception:
                pass

            # Apply current style immediately
            try:
                _apply_text_theme(_detect_dark_from_style())
            except Exception:
                pass
        else:
            # Polling fallback
            def _poll_theme():
                nonlocal last_dark
                try:
                    dark = _detect_dark_from_style()
                    if dark is not last_dark:
                        last_dark = dark
                        _apply_text_theme(dark)
                except Exception:
                    pass
                try:
                    root.after(600, _poll_theme)
                except Exception:
                    pass
            try:
                _apply_text_theme(_detect_dark_from_style())
            except Exception:
                pass
            try:
                root.after(600, _poll_theme)
            except Exception:
                pass
    except Exception:
        pass

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

    def load_user_mviews(selected_name=None):
        try:
            cur = conn.cursor()
            # include REFRESH_MODE (ON DEMAND / ON COMMIT) when available
            try:
                cur.execute("SELECT mview_name, build_mode, refresh_method, refresh_mode, rewrite_enabled, last_refresh_date, QUERY FROM user_mviews ORDER BY mview_name")
            except Exception:
                # fallback for DBs that don't expose REFRESH_MODE column
                cur.execute("SELECT mview_name, build_mode, refresh_method, rewrite_enabled, last_refresh_date, QUERY FROM user_mviews ORDER BY mview_name")
            rows = cur.fetchall()
            mview_listbox_user.delete(0, tk.END)
            for r in rows:
                name = r[0]
                mview_listbox_user.insert(tk.END, name)
            # store metadata
            # attach as normal attribute for later lookup
            setattr(root, '_mview_rows_user', {r[0]: r for r in rows})
            cur.close()
            # update count label and header
            try:
                cnt = mview_listbox_user.size()
                user_count_label.config(text=f"{cnt} MVs" if cnt > 0 else "No MVs")
                try:
                    position_count_labels()
                except Exception:
                    pass
            except Exception:
                pass
            try:
                update_user_header()
            except Exception:
                pass
            # restore selection if requested
            try:
                if selected_name:
                    # find index of the selected name
                    for i in range(mview_listbox_user.size()):
                        if mview_listbox_user.get(i) == selected_name:
                            mview_listbox_user.selection_clear(0, tk.END)
                            mview_listbox_user.selection_set(i)
                            mview_listbox_user.activate(i)
                            # update right pane to reflect restored selection
                            on_select(None, source='user')
                            break
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Failed to load materialized views: {e}")

    def load_dwh_mviews(dwh_conn, owner='DWH', selected_name=None):
        try:
            cur = dwh_conn.cursor()
            # attempt to retrieve same columns as user view
            try:
                cur.execute(
                    "SELECT mview_name, build_mode, refresh_method, refresh_mode, rewrite_enabled, last_refresh_date, QUERY FROM ALL_MVIEWS WHERE OWNER = :o ORDER BY mview_name",
                    (owner,)
                )
            except Exception:
                cur.execute(
                    "SELECT mview_name, build_mode, refresh_method, rewrite_enabled, last_refresh_date, QUERY FROM ALL_MVIEWS WHERE OWNER = :o ORDER BY mview_name",
                    (owner,)
                )
            rows = cur.fetchall()
            mview_listbox_dwh.delete(0, tk.END)
            for r in rows:
                name = r[0]
                display = f"{owner}.{name}"
                mview_listbox_dwh.insert(tk.END, display)
            setattr(root, '_mview_rows_dwh', {f"{owner}.{r[0]}": (owner,) + r for r in rows})
            cur.close()

            # update count label and header
            try:
                cnt = mview_listbox_dwh.size()
                dwh_count_label.config(text=f"{cnt} MVs" if cnt > 0 else "No MVs")
            except Exception:
                pass
            try:
                update_dwh_header()
            except Exception:
                pass

            # restore selection if requested
            try:
                if selected_name:
                    for i in range(mview_listbox_dwh.size()):
                        if mview_listbox_dwh.get(i) == selected_name:
                            mview_listbox_dwh.selection_clear(0, tk.END)
                            mview_listbox_dwh.selection_set(i)
                            mview_listbox_dwh.activate(i)
                            on_select(None, source='dwh')
                            break
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Failed to load DWH materialized views: {e}")
            mview_listbox_dwh.delete(0, tk.END)
            mview_listbox_dwh.insert(tk.END, "(no access or error)")
            try:
                dwh_count_label.config(text="No MVs")
            except Exception:
                pass

    def refresh_dwh_mviews():
        # Prompt for DWH login only when user asks to refresh DWH list
        dconn = getattr(root, '_dwh_conn', None)
        if not dconn:
            dconn = get_db_connection(schema='schema2', root=root)
            if not dconn:
                _safe_messagebox('showwarning', "DWH Login", "DWH login cancelled or failed.", dlg=root)
                return
            setattr(root, '_dwh_conn', dconn)
            try:
                session.register_connection(root, dconn, 'schema2')
            except Exception:
                logger.debug('Failed to register connection', exc_info=True)
            try:
                # update the persistent session label and header
                username = dconn.username if hasattr(dconn, 'username') else None
                if username:
                    session.set_label('schema2', username)
                update_dwh_header()
            except Exception:
                try:
                    update_dwh_header()
                except Exception:
                    pass
        # load using owner DWH
        try:
            load_dwh_mviews(dconn, 'DWH')
        except Exception as e:
            logger.exception(f"Failed refreshing DWH mviews: {e}")

    # Bring this window back on top after modal dialogs (messagebox) so the
    # smaller MV window does not get hidden behind the main app window.
    def ensure_root_on_top(delay=50):
        try:
            root.lift()
            # Temporarily set topmost to ensure it appears above other windows,
            # then clear the flag shortly after to restore normal stacking.
            root.attributes('-topmost', True)
            root.after(delay, lambda: root.attributes('-topmost', False))
        except Exception:
            pass

    def on_select(event=None, source='user'):
        # Multi-select summary: allow selections in both listboxes concurrently
        user_sel = ()
        dwh_sel = ()
        try:
            user_sel = mview_listbox_user.curselection()
        except Exception:
            user_sel = ()
        try:
            dwh_sel = mview_listbox_dwh.curselection()
        except Exception:
            dwh_sel = ()
        user_count = len(user_sel)
        dwh_count = len(dwh_sel)
        total = user_count + dwh_count

        if total == 0:
            return

        # If multiple selections, show a summary in the right pane (non-invasive)
        if total > 1:
            info_text.delete('1.0', tk.END)
            summary_lines = []
            if user_count and dwh_count:
                summary_lines.append(f"{user_count} User MV(s) + {dwh_count} DWH MV(s) selected")
            elif user_count:
                summary_lines.append(f"{user_count} User MV(s) selected")
            else:
                summary_lines.append(f"{dwh_count} DWH MV(s) selected")
            summary_lines.append("")
            summary_lines.append("Click 'Refresh MV' to refresh all selected materialized views.")
            info_text.insert(tk.END, '\n'.join(summary_lines))
            sql_text.delete('1.0', tk.END)
            sql_text.insert(tk.END, "(Multiple selections)")
            # store last_selected as a combined selection for do_refresh
            try:
                setattr(root, '_last_selected', {'user_selected': [mview_listbox_user.get(i) for i in user_sel], 'dwh_selected': [mview_listbox_dwh.get(i) for i in dwh_sel]})
            except Exception:
                pass
            return

        # Single selection - fall back to previous detailed view behavior
        # Determine which pane has the single selection
        try:
            if user_count == 1:
                try:
                    idx = next(iter(user_sel), None)
                    if idx is None:
                        return
                    name = mview_listbox_user.get(idx)
                except Exception:
                    return
                row = getattr(root, '_mview_rows_user', {}).get(name)
                qualified = name
                active_conn = conn
                source = 'user'
            else:
                try:
                    idx = next(iter(dwh_sel), None)
                    if idx is None:
                        return
                    display = mview_listbox_dwh.get(idx)
                except Exception:
                    return
                name = display.split('.', 1)[-1]
                qualified = display
                row = getattr(root, '_mview_rows_dwh', {}).get(display)
                active_conn = getattr(root, '_dwh_conn', None)
                source = 'dwh'
        except Exception:
            return
        if not row:
            return
        # store last selected for action buttons
        try:
            setattr(root, '_last_selected', {'source': source, 'qualified': qualified, 'name': name})
        except Exception:
            pass
        # normalize row so both user and dwh use same indexing: row_data[0] == mview_name
        if source == 'user':
            owner = None
            row_data = row
        else:
            owner = row[0] if len(row) > 0 else 'DWH'
            row_data = row[1:]
        # defensive extraction because REFRESH_MODE may not be available in older DBs
        build = row_data[1] if len(row_data) > 1 else ''
        refresh_method = row_data[2] if len(row_data) > 2 else ''
        refresh_mode = row_data[3] if len(row_data) > 3 else ''
        rewrite_enabled = row_data[4] if len(row_data) > 4 else (row_data[3] if len(row_data) > 3 else '')
        last_refresh = row_data[5] if len(row_data) > 5 else (row_data[4] if len(row_data) > 4 else '')
        query = row_data[6] if len(row_data) > 6 else (row_data[5] if len(row_data) > 5 else '')

        info_text.delete('1.0', tk.END)
        mv_display_name = row_data[0] if row_data and len(row_data) > 0 else (row[0] if row else '')
        info_text.insert(tk.END, f"Name: {mv_display_name}\nBuild: {build}\nRefresh Method: {refresh_method}\nRefresh Type: {refresh_mode or 'ON DEMAND'}\nRewrite Enabled: {rewrite_enabled}\nLast Refresh: {last_refresh}\n")
        # Insert current log type information (bold, blue)
        try:
            # Choose a readable logtype color depending on pane theme
            fg = 'blue'
            try:
                if ttk:
                    st = ttk.Style()
                    sbg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
                    if isinstance(sbg, str) and sbg.strip():
                        sb = sbg.strip().lower()
                        if sb in ('#000000', '#000') or 'black' in sb:
                            fg = '#66ccff'
            except Exception:
                pass
            info_text.tag_configure('logtype', foreground=fg, font=('Arial', 10, 'bold'), selectforeground='#ffffff')
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
                    # Use the active connection where possible (DWH vs user)
                    cur = active_conn.cursor() if active_conn else conn.cursor()
                    try:
                        # If connected as the owning schema, USER_DEPENDENCIES is preferred
                        cur.execute(
                            "SELECT REFERENCED_OWNER, REFERENCED_NAME FROM USER_DEPENDENCIES WHERE NAME = :mv AND REFERENCED_TYPE = 'TABLE'",
                            (row[0] if source == 'user' else name,)
                        )
                        dep_rows = cur.fetchall()
                        if dep_rows:
                            bases = [ (r[0] + '.' + r[1]) if r[0] else r[1] for r in dep_rows ]
                        else:
                            try:
                                # try ALL_DEPENDENCIES with current user as owner
                                cur.execute("SELECT USER FROM DUAL")
                                cur_user = cur.fetchone()[0]
                                cur.execute(
                                    "SELECT REFERENCED_OWNER, REFERENCED_NAME FROM ALL_DEPENDENCIES WHERE OWNER = :own AND NAME = :mv AND REFERENCED_TYPE = 'TABLE'",
                                    (cur_user, row[0] if source == 'user' else name)
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
                mv_basename = mv_display_name.split('.')[-1].upper()
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
                    cur = active_conn.cursor() if active_conn else conn.cursor()
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
        sel = getattr(root, '_last_selected', None)
        # Determine selected items from both listboxes (support cross-schema selections)
        try:
            user_sel = mview_listbox_user.curselection()
        except Exception:
            user_sel = ()
        try:
            dwh_sel = mview_listbox_dwh.curselection()
        except Exception:
            dwh_sel = ()

        user_mvs = [mview_listbox_user.get(i) for i in user_sel] if user_sel else []
        dwh_mvs = [mview_listbox_dwh.get(i) for i in dwh_sel] if dwh_sel else []

        if not user_mvs and not dwh_mvs:
            _safe_messagebox('showwarning', "Select MV", "Please select at least one materialized view.", dlg=root)
            return

        # Non-invasive confirmation shown in right pane
        total = len(user_mvs) + len(dwh_mvs)
        info_text.delete('1.0', tk.END)
        info_text.insert(tk.END, f"Confirm refresh of {len(user_mvs)} User MV(s) and {len(dwh_mvs)} DWH MV(s).\nClick 'Refresh MV' again to proceed.")
        sql_text.delete('1.0', tk.END)
        sql_text.insert(tk.END, "(Pending confirmation - click 'Refresh MV' to proceed)")

        # If this call is the confirmation step (user clicked Refresh MV twice), proceed
        # Use sel marker to detect pending confirmation
        if sel and sel.get('confirm_pending'):
            # clear the pending marker
            sel['confirm_pending'] = False
        else:
            # store pending selection and return
            try:
                setattr(root, '_last_selected', {'user_selected': user_mvs, 'dwh_selected': dwh_mvs, 'confirm_pending': True})
            except Exception:
                pass
            return

        # Proceed with actual refresh (schema1 then schema2)
        mode = 'C'
        success = []
        failures = []

        # Refresh User MVs
        try:
            if user_mvs:
                cur = conn.cursor()
                for mv_name in user_mvs:
                    try:
                        cur.execute(f"BEGIN DBMS_MVIEW.REFRESH('{mv_name}','{mode}'); END;")
                        conn.commit()
                        success.append(mv_name)
                    except Exception as e:
                        failures.append((mv_name, str(e)))
                cur.close()
        except Exception as e:
            logger.exception("Error refreshing user MVs: %s", e)

        # Refresh DWH MVs
        dconn = getattr(root, '_dwh_conn', None)
        if dwh_mvs:
            if not dconn:
                dconn = get_db_connection(schema='schema2', root=root)
                if not dconn:
                    failures.extend([(mv, 'DWH login failed') for mv in dwh_mvs])
                    dwh_mvs = []
                else:
                    setattr(root, '_dwh_conn', dconn)
                    try:
                        session.register_connection(root, dconn, 'schema2')
                    except Exception:
                        logger.debug('Failed to register connection', exc_info=True)
                    try:
                        username = dconn.username if hasattr(dconn, 'username') else None
                        if username:
                            session.set_label('schema2', username)
                        update_dwh_header()
                    except Exception:
                        try:
                            update_dwh_header()
                        except Exception:
                            pass

            try:
                if dwh_mvs and dconn:
                    cur = dconn.cursor()
                    for mv_display in dwh_mvs:
                        try:
                            cur.execute(f"BEGIN DBMS_MVIEW.REFRESH('{mv_display}','{mode}'); END;")
                            dconn.commit()
                            success.append(mv_display)
                        except Exception as e:
                            failures.append((mv_display, str(e)))
                    cur.close()
            except Exception as e:
                logger.exception("Error refreshing DWH MVs: %s", e)

        # Show results summary in right pane
        info_text.delete('1.0', tk.END)
        summary = []
        summary.append(f"Refresh complete: {len(success)} succeeded, {len(failures)} failed")
        if success:
            summary.append("\nSucceeded:\n" + '\n'.join(success))
        if failures:
            summary.append("\nFailed:\n" + '\n'.join([f'{m}: {err}' for m, err in failures]))
        info_text.insert(tk.END, '\n'.join(summary))
        sql_text.delete('1.0', tk.END)

        # Reload lists
        try:
            load_user_mviews()
        except Exception:
            pass
        try:
            dconn = getattr(root, '_dwh_conn', None)
            if dconn:
                load_dwh_mviews(dconn, 'DWH')
        except Exception:
            pass

    def do_create_logs():
        sel = getattr(root, '_last_selected', None)
        if not sel:
            _safe_messagebox('showwarning', "Select MV", "Please select a materialized view first.", dlg=root)
            return
        source = sel.get('source')
        qualified = sel.get('qualified')
        # lookup row and query
        if source == 'user':
            row = getattr(root, '_mview_rows_user', {}).get(sel.get('name'))
            mv_query = row[6] if row and len(row) > 6 else (row[5] if row and len(row) > 5 else '')
            active_cursor = conn.cursor()
        else:
            # ensure DWH conn
            dconn = getattr(root, '_dwh_conn', None)
            if not dconn:
                dconn = get_db_connection(schema='schema2', root=root)
                if not dconn:
                    _safe_messagebox('showwarning', "DWH Login", "DWH login cancelled or failed.", dlg=root)
                    return
                setattr(root, '_dwh_conn', dconn)
                try:
                    session.register_connection(root, dconn, 'schema2')
                except Exception:
                    logger.debug('Failed to register connection', exc_info=True)
                try:
                    username = dconn.username if hasattr(dconn, 'username') else None
                    if username:
                        session.set_label('schema2', username)
                    update_dwh_header()
                except Exception:
                    try:
                        update_dwh_header()
                    except Exception:
                        pass
            row = getattr(root, '_mview_rows_dwh', {}).get(qualified)
            # stored as (owner,) + row
            mv_row = row[1:] if row else None
            mv_query = mv_row[6] if mv_row and len(mv_row) > 6 else (mv_row[5] if mv_row and len(mv_row) > 5 else '')
            active_cursor = getattr(root, '_dwh_conn').cursor()
        tables = detect_tables_from_sql(mv_query)
        if not tables:
            _safe_messagebox('showinfo', "No tables", "Could not detect base tables from the MV query.", dlg=root)
            try:
                ensure_root_on_top()
            except Exception:
                pass
            return
        # Ask user to confirm table list and chosen options
        opt_label = f"Create materialized view logs on: {', '.join(tables)}\nType: {log_type_var.get()}\nINCLUDING NEW VALUES: {include_new_var.get()}"
        if not _safe_messagebox('askyesno', "Create Logs", opt_label, dlg=root):
            return

        results = []
        try:
            cur = active_cursor
            sql = None
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
                                    ans = _safe_messagebox('askyesno', "Existing MV Log Detected", f"A materialized view log already exists on {table_name}.\nDrop and recreate?", dlg=root)
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
                                            mlog_name = None
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
                                                # If mlog_name was not set above, set a safe default
                                                if mlog_name is None:
                                                    mlog_name = f"MLOG$_{master_name}"
                                                cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                                                diag_lines.append(f"all_tables_mlog_count: {cursor.fetchone()[0]}")
                                            except Exception:
                                                diag_lines.append("all_tables_mlog_count: (no access)")
                                            try:
                                                cursor.close()
                                            except Exception:
                                                pass
                                        except Exception:
                                            diag_lines = ["(could not collect diag counts)"]
                                        txt = f"detect_existing_mlog meta: {meta_text}\n" + '\n'.join(diag_lines)
                                        _safe_messagebox('showinfo', 'Debug Info', txt, dlg=dlg)
                                    except Exception as e:
                                        try:
                                            _safe_messagebox('showwarning', 'Debug Failed', f'Could not show debug info: {e}', dlg=dlg)
                                        except Exception:
                                            pass

                                btn_debug = tk.Button(dlg, text='Show debug info', command=show_diag)
                                btn_debug.pack(padx=12, anchor='w', pady=(4,0))

                                ack = tk.BooleanVar(value=False)
                                ack_cb = tk.Checkbutton(dlg, text=f"I understand this will affect the {len(deps)} listed materialized view(s).", variable=ack)
                                ack_cb.pack(padx=12, pady=(4,4), anchor='w')

                                choice_result = None

                                def do_reuse():
                                    nonlocal choice_result
                                    choice_result = 'reuse'
                                    dlg.destroy()

                                def do_drop():
                                    nonlocal choice_result
                                    if not ack.get():
                                        return
                                    choice_result = 'drop'
                                    dlg.destroy()

                                def do_cancel():
                                    nonlocal choice_result
                                    choice_result = None
                                    dlg.destroy()
                                btnf = tk.Frame(dlg)
                                btnf.pack(pady=8)
                                btn_reuse = tk.Button(btnf, text=f"Reuse Existing Log - {meta_info.get('existing_type','UNKNOWN')}", command=do_reuse, width=26)
                                btn_cancel_dlg = tk.Button(btnf, text="Cancel", command=do_cancel, width=10)
                                btn_drop = tk.Button(btnf, text="Drop & Recreate", command=do_drop, width=14)
                                btn_reuse.pack(side='left', padx=(0,6))
                                btn_cancel_dlg.pack(side='left', padx=6)
                                btn_drop.pack(side='left', padx=6)
                                # Apply dark mode styling to dialog buttons
                                _dlg_btns = [btn_debug, btn_reuse, btn_cancel_dlg, btn_drop]
                                try:
                                    if _detect_dark_from_style():
                                        for btn in _dlg_btns:
                                            btn.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')
                                except Exception:
                                    pass

                                dlg.update_idletasks()
                                dlg.geometry(f"{dlg.winfo_width()}x{dlg.winfo_height()}+{(dlg.winfo_screenwidth()//2)-(dlg.winfo_width()//2)}+{(dlg.winfo_screenheight()//2)-(dlg.winfo_height()//2)}")
                                try:
                                    dlg.wait_window(dlg)
                                except Exception:
                                    try:
                                        dlg.mainloop()
                                    except Exception:
                                        pass
                                return choice_result

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
                                do_drop = _safe_messagebox('askyesno', 'Existing MV Log', f"The database reports a materialized view log already exists on {t}.\nDrop and recreate with the selected options?", dlg=root)
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
                _safe_messagebox('showinfo', "MV Logs Created", "\n".join(msgs), dlg=root)
                try:
                    ensure_root_on_top()
                except Exception:
                    pass
            if failed:
                msg_lines = [f"{t}: {err}" for (t, err) in failed]
                _safe_messagebox('showwarning', "Some logs failed", "\n".join(msg_lines), dlg=root)
                try:
                    ensure_root_on_top()
                except Exception:
                    pass
            # preserve selection and reload appropriate list
            try:
                last = getattr(root, '_last_selected', None)
                if last:
                    if last.get('source') == 'user':
                        load_user_mviews(last.get('name') or last.get('qualified'))
                    else:
                        dconn = getattr(root, '_dwh_conn', None)
                        if dconn:
                            owner = last.get('qualified').split('.', 1)[0]
                            load_dwh_mviews(dconn, owner, last.get('qualified'))
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Failed to create logs: {e}")
            _safe_messagebox('showerror', "Error", str(e), dlg=root)
            try:
                ensure_root_on_top()
            except Exception:
                pass

    btn_refresh_mv = tk.Button(btn_frame, text="Refresh MV", command=do_refresh)
    btn_create_logs = tk.Button(btn_frame, text="Create Logs", command=do_create_logs)
    btn_refresh_mv.pack(side="right", padx=6)
    btn_create_logs.pack(side="right", padx=6)
    _all_buttons.extend([btn_refresh_mv, btn_create_logs])

    # Apply initial dark mode styling to buttons
    try:
        if _detect_dark_from_style():
            for btn in _all_buttons:
                try:
                    btn.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')
                except Exception:
                    pass
    except Exception:
        pass

    # bind both listboxes to the shared handler
    mview_listbox_user.bind('<<ListboxSelect>>', lambda e: on_select(e, source='user'))
    mview_listbox_dwh.bind('<<ListboxSelect>>', lambda e: on_select(e, source='dwh'))

    # Ctrl+A bindings for select-all
    def select_all_user(event=None):
        try:
            mview_listbox_user.select_set(0, tk.END)
            # Show summary in right pane
            on_select(None, source='user')
        except Exception:
            pass
        return "break"

    def select_all_dwh(event=None):
        try:
            mview_listbox_dwh.select_set(0, tk.END)
            on_select(None, source='dwh')
        except Exception:
            pass
        return "break"

    mview_listbox_user.bind('<Control-a>', select_all_user)
    mview_listbox_user.bind('<Control-A>', select_all_user)
    mview_listbox_dwh.bind('<Control-a>', select_all_dwh)
    mview_listbox_dwh.bind('<Control-A>', select_all_dwh)

    # initial load of user and dwh mviews (auto-refresh both panes)
    load_user_mviews()
    # Attempt to load DWH list if saved credentials exist or lazy login is desired
    try:
        # If session has saved credentials for schema2, attempt to establish connection silently
        creds2 = session.get_credentials('schema2')
        if creds2:
            try:
                dconn = get_db_connection(schema='schema2', root=root)
                if dconn:
                    setattr(root, '_dwh_conn', dconn)
                    try:
                        session.register_connection(root, dconn, 'schema2')
                    except Exception:
                        logger.debug('Failed to register connection', exc_info=True)
                    try:
                        username = dconn.username if hasattr(dconn, 'username') else None
                        if username:
                            session.set_label('schema2', username)
                        load_dwh_mviews(dconn, 'DWH')
                    except Exception:
                        try:
                            update_dwh_header()
                        except Exception:
                            pass
            except Exception:
                # Ignore failures on silent dwh auto-connect
                pass
    except Exception:
        pass

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

        # Session cleanup: close connections and clear credentials
        try:
            session.close_connections(root)
        except Exception:
            logger.debug("Session cleanup failed", exc_info=True)

        # Release modal grab if we set it
        try:
            if grabbed:
                try:
                    root.grab_release()
                except Exception:
                    pass
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
        # If a parent was provided, block until this dialog is closed so the
        # caller (launcher) cannot be interacted with — matching modal behavior
        # of other tools. Otherwise run a normal mainloop for standalone use.
        if parent is not None:
            try:
                root.wait_window()
            except Exception:
                # ignore errors from wait_window
                pass
        else:
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
