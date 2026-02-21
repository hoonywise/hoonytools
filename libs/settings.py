"""
Settings GUI for HoonyTools.
Provides a modal dialog for configuring application settings.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from configparser import ConfigParser
from pathlib import Path
import ctypes
import sys

from libs.paths import PROJECT_PATH as BASE_PATH
from libs import session

# Constants
ASSETS_PATH = BASE_PATH
CONFIG_PATH = BASE_PATH / "libs" / "config.ini"


# --------------------------------------------------------------------------
# Helper: Center window on screen/monitor
# --------------------------------------------------------------------------
def _center_window(window, width, height):
    """Center window on the screen or monitor containing the cursor."""
    try:
        window.geometry(f"{width}x{height}")
    except Exception:
        pass
    window.update_idletasks()

    # Try DPI-aware, multi-monitor centering on Windows
    try:
        if sys.platform.startswith("win"):
            from ctypes import Structure, byref, c_long, c_ulong, windll, POINTER

            class POINT(Structure):
                _fields_ = [("x", c_long), ("y", c_long)]

            class RECT(Structure):
                _fields_ = [
                    ("left", c_long),
                    ("top", c_long),
                    ("right", c_long),
                    ("bottom", c_long),
                ]

            class MONITORINFO(Structure):
                _fields_ = [
                    ("cbSize", c_ulong),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", c_ulong),
                ]

            try:
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                pass

            pt = POINT()
            windll.user32.GetCursorPos(byref(pt))
            hmon = windll.user32.MonitorFromPoint(pt, 2)
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if windll.user32.GetMonitorInfoW(hmon, byref(mi)):
                work = mi.rcWork
                mw = work.right - work.left
                mh = work.bottom - work.top
                x = work.left + (mw - width) // 2
                y = work.top + (mh - height) // 2
                window.geometry(f"{width}x{height}+{x}+{y}")
                return
    except Exception:
        pass

    # Fallback: center on primary screen
    sw = window.winfo_screenwidth()
    sh = window.winfo_screenheight()
    x = int((sw - width) / 2)
    y = int((sh - height) / 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


# --------------------------------------------------------------------------
# Helper: Detect current dark mode state
# --------------------------------------------------------------------------
def _is_dark_mode():
    """Check if dark mode is currently active."""
    try:
        style = ttk.Style()
        bg = style.lookup('Pane.Treeview', 'background') or ''
        return bg.lower() in ('#000000', '#000', 'black')
    except Exception:
        return False


# --------------------------------------------------------------------------
# Helper: Load config
# --------------------------------------------------------------------------
def _load_config():
    """Load and return ConfigParser with current config.ini contents."""
    cfg = ConfigParser()
    try:
        cfg.read(CONFIG_PATH)
    except Exception:
        pass
    return cfg


# --------------------------------------------------------------------------
# Helper: Save config
# --------------------------------------------------------------------------
def _save_config(cfg):
    """Save ConfigParser to config.ini."""
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            cfg.write(f)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# Category content builders
# --------------------------------------------------------------------------
def _build_connections_panel(parent_frame, entry_refs, button_frame):
    """
    Build the Connections settings panel.

    Args:
        parent_frame: The frame to build content in
        entry_refs: Dict to store entry widget references for later access
        button_frame: The button frame to pack at the bottom

    Returns:
        The built frame
    """
    # Main container
    container = tk.Frame(parent_frame, bg='SystemButtonFace')
    container.pack(fill='both', expand=True, padx=10, pady=10)

    # Schema 1 LabelFrame
    schema1_frame = tk.LabelFrame(container, text="Schema 1", padx=10, pady=10)
    schema1_frame.pack(fill='x', pady=(0, 10))

    # Schema 1 - Username
    s1_user_label = tk.Label(schema1_frame, text="Username:")
    s1_user_label.grid(row=0, column=0, sticky='e', padx=(0, 5), pady=2)
    s1_user_entry = tk.Entry(schema1_frame, width=35)
    s1_user_entry.grid(row=0, column=1, sticky='w', pady=2)
    entry_refs['schema1_user'] = s1_user_entry

    # Schema 1 - Password
    s1_pass_label = tk.Label(schema1_frame, text="Password:")
    s1_pass_label.grid(row=1, column=0, sticky='e', padx=(0, 5), pady=2)
    s1_pass_entry = tk.Entry(schema1_frame, width=35, show='*')
    s1_pass_entry.grid(row=1, column=1, sticky='w', pady=2)
    entry_refs['schema1_pass'] = s1_pass_entry

    # Schema 1 - Show password checkbox (below password field)
    s1_show_var = tk.BooleanVar(value=False)
    entry_refs['schema1_show_var'] = s1_show_var

    def _toggle_s1_show():
        s1_pass_entry.config(show='' if s1_show_var.get() else '*')

    s1_show_check = tk.Checkbutton(schema1_frame, text="Show password", variable=s1_show_var, command=_toggle_s1_show)
    s1_show_check.grid(row=2, column=1, sticky='w', pady=(0, 2))

    # Schema 1 - DSN
    s1_dsn_label = tk.Label(schema1_frame, text="DSN:")
    s1_dsn_label.grid(row=3, column=0, sticky='e', padx=(0, 5), pady=2)
    s1_dsn_entry = tk.Entry(schema1_frame, width=35)
    s1_dsn_entry.grid(row=3, column=1, sticky='w', pady=2)
    entry_refs['schema1_dsn'] = s1_dsn_entry

    # Schema 2 LabelFrame
    schema2_frame = tk.LabelFrame(container, text="Schema 2", padx=10, pady=10)
    schema2_frame.pack(fill='x', pady=(0, 10))

    # Schema 2 - Username
    s2_user_label = tk.Label(schema2_frame, text="Username:")
    s2_user_label.grid(row=0, column=0, sticky='e', padx=(0, 5), pady=2)
    s2_user_entry = tk.Entry(schema2_frame, width=35)
    s2_user_entry.grid(row=0, column=1, sticky='w', pady=2)
    entry_refs['schema2_user'] = s2_user_entry

    # Schema 2 - Password
    s2_pass_label = tk.Label(schema2_frame, text="Password:")
    s2_pass_label.grid(row=1, column=0, sticky='e', padx=(0, 5), pady=2)
    s2_pass_entry = tk.Entry(schema2_frame, width=35, show='*')
    s2_pass_entry.grid(row=1, column=1, sticky='w', pady=2)
    entry_refs['schema2_pass'] = s2_pass_entry

    # Schema 2 - Show password checkbox (below password field)
    s2_show_var = tk.BooleanVar(value=False)
    entry_refs['schema2_show_var'] = s2_show_var

    def _toggle_s2_show():
        s2_pass_entry.config(show='' if s2_show_var.get() else '*')

    s2_show_check = tk.Checkbutton(schema2_frame, text="Show password", variable=s2_show_var, command=_toggle_s2_show)
    s2_show_check.grid(row=2, column=1, sticky='w', pady=(0, 2))

    # Schema 2 - DSN
    s2_dsn_label = tk.Label(schema2_frame, text="DSN:")
    s2_dsn_label.grid(row=3, column=0, sticky='e', padx=(0, 5), pady=2)
    s2_dsn_entry = tk.Entry(schema2_frame, width=35)
    s2_dsn_entry.grid(row=3, column=1, sticky='w', pady=2)
    entry_refs['schema2_dsn'] = s2_dsn_entry

    # Load saved values from config.ini
    cfg = _load_config()

    if cfg.has_section('schema1'):
        s1_user_entry.insert(0, cfg.get('schema1', 'user', fallback=''))
        s1_pass_entry.insert(0, cfg.get('schema1', 'password', fallback=''))
        s1_dsn_entry.insert(0, cfg.get('schema1', 'dsn', fallback=''))

    if cfg.has_section('schema2'):
        s2_user_entry.insert(0, cfg.get('schema2', 'user', fallback=''))
        s2_pass_entry.insert(0, cfg.get('schema2', 'password', fallback=''))
        s2_dsn_entry.insert(0, cfg.get('schema2', 'dsn', fallback=''))

    # Collect entry fields that need theme styling (only the input fields, not labels/frames)
    entries = [s1_user_entry, s1_pass_entry, s1_dsn_entry, s2_user_entry, s2_pass_entry, s2_dsn_entry]

    # Store widgets for theme callback
    entry_refs['_conn_entries'] = entries

    # Apply initial theme based on current dark mode state
    parent = entry_refs.get('_parent')
    is_dark = False
    if parent and hasattr(parent, '_dark_mode_var'):
        try:
            is_dark = parent._dark_mode_var.get()
        except Exception:
            pass

    def _apply_connections_theme(dark):
        """Apply dark or light theme to connection panel entry fields only."""
        if dark:
            entry_bg = '#000000'
            entry_fg = '#ffffff'
        else:
            entry_bg = 'white'
            entry_fg = 'black'

        # Apply to entry fields only
        for entry in entries:
            try:
                entry.config(bg=entry_bg, fg=entry_fg, insertbackground=entry_fg)
            except Exception:
                pass

    # Store the theme function for external access
    entry_refs['_conn_apply_theme'] = _apply_connections_theme

    # Apply initial theme
    _apply_connections_theme(is_dark)

    # Pack button frame at bottom with right alignment
    button_frame.pack(side='bottom', fill='x', padx=10, pady=(10, 10))

    return container


def _build_appearance_panel(parent_frame, entry_refs, button_frame):
    """
    Build the Appearance settings panel.

    Args:
        parent_frame: The frame to build content in
        entry_refs: Dict to store widget references for later access
        button_frame: The button frame to pack at the bottom

    Returns:
        The built frame
    """
    # Main container
    container = tk.Frame(parent_frame, bg='SystemButtonFace')
    container.pack(fill='both', expand=True, padx=10, pady=10)

    # Theme LabelFrame
    theme_frame = tk.LabelFrame(container, text="Theme", padx=10, pady=10)
    theme_frame.pack(fill='x', pady=(0, 10))

    # Get current dark mode state - prefer live state from parent, fallback to config.ini
    current_dark_mode = False
    parent = entry_refs.get('_parent')
    if parent and hasattr(parent, '_dark_mode_var'):
        try:
            current_dark_mode = parent._dark_mode_var.get()
        except Exception:
            pass
    else:
        # Fallback: load from config.ini
        cfg = _load_config()
        current_dark_mode = cfg.getboolean('preferences', 'dark_mode', fallback=False)

    # Dark Mode checkbox
    dark_mode_var = tk.BooleanVar(value=current_dark_mode)
    entry_refs['dark_mode_var'] = dark_mode_var

    def _on_dark_mode_toggle():
        """Immediately apply dark mode toggle without requiring OK/Apply."""
        dark_mode_enabled = dark_mode_var.get()
        # Get parent from entry_refs in case it was updated
        _parent = entry_refs.get('_parent')
        if _parent and hasattr(_parent, '_dark_mode_var'):
            parent_var = _parent._dark_mode_var
            # Update parent's var and trigger toggle
            parent_var.set(dark_mode_enabled)
            # Trigger the toggle callback if it exists
            if hasattr(_parent, '_toggle_dark'):
                _parent._toggle_dark()

    dark_mode_check = tk.Checkbutton(
        theme_frame,
        text="Dark Mode (applies to panes and menu bar)",
        variable=dark_mode_var,
        command=_on_dark_mode_toggle
    )
    dark_mode_check.pack(anchor='w', pady=5)

    # Pack button frame at bottom with right alignment
    button_frame.pack(side='bottom', fill='x', padx=10, pady=(10, 10))

    return container


# Category registry - maps category name to builder function
CATEGORIES = {
    "Connections": _build_connections_panel,
    "Appearance": _build_appearance_panel,
}


# --------------------------------------------------------------------------
# Main settings dialog
# --------------------------------------------------------------------------
def show_settings(parent=None):
    """
    Launch the Settings dialog.

    Args:
        parent: Parent window (typically root). Used for modal behavior
                and theme callback registration.
    """
    # Create Toplevel window
    win = tk.Toplevel(parent) if parent else tk.Toplevel()
    win.title("Settings")
    win.resizable(True, True)
    win.minsize(550, 400)

    # Set icon
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        win.iconbitmap(default=icon_path)
    except Exception:
        pass

    # Center on screen
    _center_window(win, 550, 400)

    # Make modal
    try:
        if parent:
            win.transient(parent)
        win.grab_set()
    except Exception:
        pass

    # Entry references dict (for validation/saving)
    entry_refs = {}

    # Store parent reference so panel builders can access it
    entry_refs['_parent'] = parent

    # Track current content frame for category switching
    current_content = {'frame': None}

    # --------------------------------------------------------------------------
    # Status bar at the bottom of the window
    # --------------------------------------------------------------------------
    # Separator line above status bar
    status_separator = tk.Frame(win, height=1, bg='#c0c0c0')
    status_separator.pack(side='bottom', fill='x')

    status_frame = tk.Frame(win, bg='SystemButtonFace')
    status_frame.pack(side='bottom', fill='x')

    status_label = tk.Label(status_frame, text='', fg='#005a9e', bg='SystemButtonFace', anchor='w', font=('TkDefaultFont', 9, 'bold'))
    status_label.pack(side='left', padx=10, pady=(5, 5))

    # Store status label reference for use in _save()
    entry_refs['_status_label'] = status_label
    entry_refs['_win'] = win  # For scheduling auto-hide

    # --------------------------------------------------------------------------
    # Main layout: Left (categories) | Right (content)
    # --------------------------------------------------------------------------
    main_paned = tk.PanedWindow(win, orient='horizontal', sashwidth=4, bg='#c0c0c0')
    main_paned.pack(fill='both', expand=True)

    # --------------------------------------------------------------------------
    # Left pane: Category list (dark mode compatible)
    # --------------------------------------------------------------------------
    category_frame = tk.Frame(main_paned, width=150, bg='SystemButtonFace')
    category_frame.pack_propagate(False)

    # Create Treeview for categories
    style = ttk.Style()

    # Configure Settings.Treeview style (will be updated by theme callback)
    try:
        style.configure('Settings.Treeview', rowheight=24)
    except Exception:
        pass

    category_tree = ttk.Treeview(
        category_frame,
        style='Settings.Treeview',
        selectmode='browse',
        show='tree'  # No headings
    )
    category_tree.pack(fill='both', expand=True, padx=2, pady=2)

    # Populate categories
    for cat_name in CATEGORIES.keys():
        category_tree.insert('', 'end', iid=cat_name, text=cat_name)

    main_paned.add(category_frame, minsize=120, width=150)

    # --------------------------------------------------------------------------
    # Right pane: Content area (default grey, scrollable)
    # --------------------------------------------------------------------------
    content_outer_frame = tk.Frame(main_paned, bg='SystemButtonFace')

    # Canvas for scrolling
    content_canvas = tk.Canvas(content_outer_frame, bg='SystemButtonFace', highlightthickness=0)
    content_scrollbar = ttk.Scrollbar(content_outer_frame, orient='vertical', command=content_canvas.yview)
    content_canvas.configure(yscrollcommand=content_scrollbar.set)

    # Inner frame that holds actual content
    content_inner_frame = tk.Frame(content_canvas, bg='SystemButtonFace')
    canvas_window = content_canvas.create_window((0, 0), window=content_inner_frame, anchor='nw')

    # Update scroll region when content changes
    def _on_content_configure(event=None):
        content_canvas.configure(scrollregion=content_canvas.bbox('all'))
        # Also update the width of the inner frame to match canvas
        content_canvas.itemconfig(canvas_window, width=content_canvas.winfo_width())

    content_inner_frame.bind('<Configure>', _on_content_configure)

    def _on_canvas_configure(event=None):
        content_canvas.itemconfig(canvas_window, width=event.width)

    content_canvas.bind('<Configure>', _on_canvas_configure)

    # Enable mousewheel scrolling
    def _on_mousewheel(event):
        content_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')

    content_canvas.bind_all('<MouseWheel>', _on_mousewheel)

    # Pack canvas and scrollbar
    content_scrollbar.pack(side='right', fill='y')
    content_canvas.pack(side='left', fill='both', expand=True)

    main_paned.add(content_outer_frame, minsize=300)

    # --------------------------------------------------------------------------
    # Button frame (will be packed inside content by category builder)
    # --------------------------------------------------------------------------
    button_frame = tk.Frame(content_inner_frame, bg='SystemButtonFace')

    # Button handlers
    def _validate():
        """Validate all entries. Returns True if valid."""
        errors = []

        # Check Schema 1 - all or nothing
        s1_user = entry_refs.get('schema1_user')
        s1_pass = entry_refs.get('schema1_pass')
        s1_dsn = entry_refs.get('schema1_dsn')

        if s1_user and s1_pass and s1_dsn:
            s1_user_val = s1_user.get().strip()
            s1_pass_val = s1_pass.get().strip()
            s1_dsn_val = s1_dsn.get().strip()

            if any([s1_user_val, s1_pass_val, s1_dsn_val]) and not all([s1_user_val, s1_pass_val, s1_dsn_val]):
                errors.append("Schema 1: All fields (Username, Password, DSN) are required.")

        # Check Schema 2 - all or nothing
        s2_user = entry_refs.get('schema2_user')
        s2_pass = entry_refs.get('schema2_pass')
        s2_dsn = entry_refs.get('schema2_dsn')

        if s2_user and s2_pass and s2_dsn:
            s2_user_val = s2_user.get().strip()
            s2_pass_val = s2_pass.get().strip()
            s2_dsn_val = s2_dsn.get().strip()

            if any([s2_user_val, s2_pass_val, s2_dsn_val]) and not all([s2_user_val, s2_pass_val, s2_dsn_val]):
                errors.append("Schema 2: All fields (Username, Password, DSN) are required.")

        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors), parent=win)
            return False

        return True

    def _show_status_message(message, error=False):
        """Show a status message at the bottom of the window that auto-hides after 3 seconds."""
        status_label = entry_refs.get('_status_label')
        settings_win = entry_refs.get('_win')
        if status_label:
            try:
                # Set color based on error or success (darker blue for success, red for error)
                color = '#cc0000' if error else '#005a9e'
                status_label.config(text=message, fg=color)

                # Schedule auto-hide after 3 seconds
                if settings_win:
                    def _clear_status():
                        try:
                            if status_label.winfo_exists():
                                status_label.config(text='')
                        except Exception:
                            pass

                    settings_win.after(3000, _clear_status)
            except Exception:
                pass

    def _save():
        """Save to config.ini and update session memory."""
        cfg = _load_config()

        # Get current values from entry fields
        s1_user_val = ''
        s1_pass_val = ''
        s1_dsn_val = ''
        s2_user_val = ''
        s2_pass_val = ''
        s2_dsn_val = ''

        # Save Schema 1
        s1_user = entry_refs.get('schema1_user')
        s1_pass = entry_refs.get('schema1_pass')
        s1_dsn = entry_refs.get('schema1_dsn')

        if s1_user and s1_pass and s1_dsn:
            s1_user_val = s1_user.get().strip()
            s1_pass_val = s1_pass.get().strip()
            s1_dsn_val = s1_dsn.get().strip()

            if s1_user_val or s1_pass_val or s1_dsn_val:
                if not cfg.has_section('schema1'):
                    cfg.add_section('schema1')
                cfg.set('schema1', 'user', s1_user_val)
                cfg.set('schema1', 'password', s1_pass_val)
                cfg.set('schema1', 'dsn', s1_dsn_val)
            else:
                # Clear section if all empty
                if cfg.has_section('schema1'):
                    cfg.remove_section('schema1')

        # Save Schema 2
        s2_user = entry_refs.get('schema2_user')
        s2_pass = entry_refs.get('schema2_pass')
        s2_dsn = entry_refs.get('schema2_dsn')

        if s2_user and s2_pass and s2_dsn:
            s2_user_val = s2_user.get().strip()
            s2_pass_val = s2_pass.get().strip()
            s2_dsn_val = s2_dsn.get().strip()

            if s2_user_val or s2_pass_val or s2_dsn_val:
                if not cfg.has_section('schema2'):
                    cfg.add_section('schema2')
                cfg.set('schema2', 'user', s2_user_val)
                cfg.set('schema2', 'password', s2_pass_val)
                cfg.set('schema2', 'dsn', s2_dsn_val)
            else:
                # Clear section if all empty
                if cfg.has_section('schema2'):
                    cfg.remove_section('schema2')

        # Save Appearance settings (Dark Mode)
        dark_mode_var = entry_refs.get('dark_mode_var')
        if dark_mode_var is not None:
            dark_mode_enabled = dark_mode_var.get()
            if not cfg.has_section('preferences'):
                cfg.add_section('preferences')
            cfg.set('preferences', 'dark_mode', str(dark_mode_enabled).lower())

        if _save_config(cfg):
            # Update session memory so login dialog won't appear unnecessarily
            _parent = entry_refs.get('_parent')

            # Schema 1: Update or clear session credentials (critical - no silent failure)
            if s1_user_val and s1_pass_val and s1_dsn_val:
                session.set_credentials('schema1', {
                    'user': s1_user_val,
                    'password': s1_pass_val,
                    'dsn': s1_dsn_val,
                    'save': True
                })
            else:
                session.clear_credentials('schema1')

            # Schema 2: Update or clear session credentials (critical - no silent failure)
            if s2_user_val and s2_pass_val and s2_dsn_val:
                session.set_credentials('schema2', {
                    'user': s2_user_val,
                    'password': s2_pass_val,
                    'dsn': s2_dsn_val,
                    'save': True
                })
            else:
                session.clear_credentials('schema2')

            # Trigger object pane refresh in main GUI after credentials are saved
            # This is non-critical and can fail gracefully
            try:
                if _parent:
                    if hasattr(_parent, '_refresh_schema1') and s1_user_val and s1_pass_val and s1_dsn_val:
                        _parent._refresh_schema1()
                    if hasattr(_parent, '_refresh_schema2') and s2_user_val and s2_pass_val and s2_dsn_val:
                        _parent._refresh_schema2()
            except Exception:
                pass

            # Sync Dark Mode with parent window's View menu toggle
            dark_mode_var = entry_refs.get('dark_mode_var')
            _parent = entry_refs.get('_parent')
            if dark_mode_var is not None and _parent:
                try:
                    dark_mode_enabled = dark_mode_var.get()
                    # Check if parent has the dark_mode_var attribute (set by HoonyTools)
                    if hasattr(_parent, '_dark_mode_var'):
                        parent_var = _parent._dark_mode_var
                        # Only toggle if state is different
                        if parent_var.get() != dark_mode_enabled:
                            parent_var.set(dark_mode_enabled)
                            # Trigger the toggle callback if it exists
                            if hasattr(_parent, '_toggle_dark'):
                                _parent._toggle_dark()
                except Exception:
                    pass

            # Show non-invasive confirmation message in status bar
            _show_status_message("Settings saved")
            return True
        else:
            _show_status_message("Failed to save settings", error=True)
            return False

    def _on_ok():
        if _validate():
            if _save():
                # Unbind mousewheel before destroying
                try:
                    content_canvas.unbind_all('<MouseWheel>')
                except Exception:
                    pass
                win.destroy()

    def _on_cancel():
        # Unbind mousewheel before destroying
        try:
            content_canvas.unbind_all('<MouseWheel>')
        except Exception:
            pass
        win.destroy()

    def _on_apply():
        if _validate():
            _save()

    # Create buttons
    btn_ok = tk.Button(button_frame, text="OK", width=8, command=_on_ok)
    btn_cancel = tk.Button(button_frame, text="Cancel", width=8, command=_on_cancel)
    btn_apply = tk.Button(button_frame, text="Apply", width=8, command=_on_apply)

    # Pack buttons to the right
    btn_apply.pack(side='right', padx=(5, 0))
    btn_cancel.pack(side='right', padx=(5, 0))
    btn_ok.pack(side='right', padx=(5, 0))

    # --------------------------------------------------------------------------
    # Category selection handler
    # --------------------------------------------------------------------------
    def _on_category_select(event=None):
        """Handle category selection - replace right pane content."""
        selected = category_tree.selection()
        if not selected:
            return

        category_name = category_tree.item(selected[0], 'text')

        # Clear current content (except button_frame which we'll re-add)
        for widget in content_inner_frame.winfo_children():
            if widget != button_frame:
                widget.destroy()

        # Clear entry refs for fresh build, but preserve system references
        preserved = {
            '_parent': entry_refs.get('_parent'),
            '_status_label': entry_refs.get('_status_label'),
            '_win': entry_refs.get('_win'),
        }
        entry_refs.clear()
        entry_refs.update(preserved)

        # Unpack button frame so builder can pack it
        button_frame.pack_forget()

        # Build new content
        builder = CATEGORIES.get(category_name)
        if builder:
            current_content['frame'] = builder(content_inner_frame, entry_refs, button_frame)

    category_tree.bind('<<TreeviewSelect>>', _on_category_select)

    # --------------------------------------------------------------------------
    # Theme callback for dark mode support
    # --------------------------------------------------------------------------
    def _apply_theme(dark: bool):
        """Apply dark or light theme to the category pane and content panels."""
        if dark:
            try:
                # Configure dark style for category tree
                style.configure('Settings.Treeview',
                                background='#000000',
                                fieldbackground='#000000',
                                foreground='#ffffff',
                                rowheight=24)
                style.map('Settings.Treeview',
                          background=[('selected', '#2a6bd6')],
                          foreground=[('selected', '#ffffff')])
                category_frame.configure(bg='#000000')
                # Apply dark mode to buttons
                for btn in (btn_ok, btn_cancel, btn_apply):
                    btn.config(bg='#000000', fg='#ffffff', activebackground='#222222', activeforeground='#ffffff')
            except Exception:
                pass
        else:
            try:
                # Restore light style
                style.configure('Settings.Treeview',
                                background='white',
                                fieldbackground='white',
                                foreground='black',
                                rowheight=24)
                style.map('Settings.Treeview',
                          background=[('selected', '#0078d7')],
                          foreground=[('selected', 'white')])
                category_frame.configure(bg='SystemButtonFace')
                # Restore light mode to buttons
                for btn in (btn_ok, btn_cancel, btn_apply):
                    btn.config(bg='SystemButtonFace', fg='SystemButtonText', activebackground='SystemButtonFace', activeforeground='SystemButtonText')
            except Exception:
                pass

        # Apply theme to connections panel if it exists
        conn_apply_theme = entry_refs.get('_conn_apply_theme')
        if conn_apply_theme:
            try:
                conn_apply_theme(dark)
            except Exception:
                pass

    # Register with parent's theme callback system
    if parent and hasattr(parent, 'register_theme_callback'):
        parent.register_theme_callback(_apply_theme)

    def _on_destroy(event=None):
        if event.widget == win:  # Only on main window destroy
            # Unbind mousewheel
            try:
                content_canvas.unbind_all('<MouseWheel>')
            except Exception:
                pass
            # Unregister theme callback
            if parent and hasattr(parent, 'unregister_theme_callback'):
                try:
                    parent.unregister_theme_callback(_apply_theme)
                except Exception:
                    pass

    win.bind('<Destroy>', _on_destroy)

    # Apply initial theme
    _apply_theme(_is_dark_mode())

    # --------------------------------------------------------------------------
    # Initialize: Select first category
    # --------------------------------------------------------------------------
    first_cat = list(CATEGORIES.keys())[0]
    category_tree.selection_set(first_cat)
    _on_category_select()  # Trigger content build

    # Close handler
    win.protocol("WM_DELETE_WINDOW", _on_cancel)

    # Focus
    try:
        win.focus_force()
        win.lift()
        win.attributes('-topmost', True)
        win.after(200, lambda: win.attributes('-topmost', False))
    except Exception:
        pass
