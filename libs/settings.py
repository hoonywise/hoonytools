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
            from ctypes import Structure, byref, c_long, c_ulong, windll

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
        from libs import gui_utils
        return gui_utils.is_dark_theme()
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
    container = tk.Frame(parent_frame, bg='#f0f0f0')
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

    # Collect all widgets for theme styling
    entries = [s1_user_entry, s1_pass_entry, s1_dsn_entry, s2_user_entry, s2_pass_entry, s2_dsn_entry]
    labels = [s1_user_label, s1_pass_label, s1_dsn_label, s2_user_label, s2_pass_label, s2_dsn_label]
    labelframes = [schema1_frame, schema2_frame]
    checkboxes = [s1_show_check, s2_show_check]

    # Store widgets for theme callback
    entry_refs['_conn_entries'] = entries
    entry_refs['_conn_labels'] = labels
    entry_refs['_conn_labelframes'] = labelframes
    entry_refs['_conn_checkboxes'] = checkboxes
    entry_refs['_conn_container'] = container

    def _apply_connections_theme(is_dark_unused=None):
        """Apply current theme to all connection panel widgets."""
        from libs import gui_utils
        
        # Apply to container frame
        try:
            gui_utils.apply_theme_to_window(container)
        except Exception:
            pass
        
        # Apply to LabelFrames
        for lf in labelframes:
            try:
                gui_utils.apply_theme_to_labelframe(lf)
            except Exception:
                pass
        
        # Apply to labels
        for label in labels:
            try:
                gui_utils.apply_theme_to_label(label)
            except Exception:
                pass
        
        # Apply to entry fields
        for entry in entries:
            try:
                gui_utils.apply_theme_to_entry(entry)
            except Exception:
                pass
        
        # Apply to checkboxes
        for cb in checkboxes:
            try:
                gui_utils.apply_theme_to_checkbox(cb)
            except Exception:
                pass

    # Store the theme function for external access
    entry_refs['_conn_apply_theme'] = _apply_connections_theme

    # Apply initial theme
    _apply_connections_theme()

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
    from libs import gui_utils
    
    # Main container
    container = tk.Frame(parent_frame, bg='#f0f0f0')
    container.pack(fill='both', expand=True, padx=10, pady=10)

    # Theme LabelFrame
    theme_frame = tk.LabelFrame(container, text="Themes", padx=10, pady=10)
    theme_frame.pack(fill='x', pady=(0, 10))

    # Theme selection row
    theme_row = tk.Frame(theme_frame)
    theme_row.pack(fill='x', pady=5)
    
    tk.Label(theme_row, text="Theme Preset:").pack(side='left', padx=(0, 10))
    
    # Get display names for dropdown (ordered from dark to light)
    theme_names = gui_utils.get_theme_names()
    display_names = [gui_utils.get_theme_display_name(k) for k in theme_names]
    
    # Get current theme
    current_theme_key = gui_utils.get_current_theme()
    current_display_name = gui_utils.get_theme_display_name(current_theme_key)
    
    # Create dropdown
    theme_var = tk.StringVar(value=current_display_name)
    entry_refs['theme_var'] = theme_var
    
    theme_dropdown = ttk.Combobox(
        theme_row,
        textvariable=theme_var,
        values=display_names,
        state='readonly',
        width=20
    )
    theme_dropdown.pack(side='left')
    
    def _on_theme_change(event=None):
        """Apply theme immediately when selection changes (live preview)."""
        selected_display_name = theme_var.get()
        # Convert display name to theme key
        name_to_key = gui_utils.get_display_name_to_key()
        theme_key = name_to_key.get(selected_display_name, 'system_light')
        # Set theme (this saves to config and triggers callbacks)
        gui_utils.set_theme(theme_key)
    
    theme_dropdown.bind('<<ComboboxSelected>>', _on_theme_change)
    
    # Store reference to theme_var for customize dialog
    entry_refs['_theme_dropdown'] = theme_dropdown
    
    def _on_customize():
        """Open the Customize Colors dialog."""
        # Get the base preset to start from (current theme, including 'custom')
        # get_colors_for_preset() handles 'custom' by loading saved custom colors
        current_key = gui_utils.get_current_theme()
        base_preset = current_key
        
        # Open customize dialog
        # Theme dropdown update is handled automatically by _apply_theme() callback
        # which is triggered via gui_utils.register_theme_callback() system
        dialog = CustomizeColorsDialog(parent_frame.winfo_toplevel(), base_preset)
    
    # Customize button (now enabled)
    customize_btn = tk.Button(
        theme_row,
        text="Customize...",
        command=_on_customize
    )
    customize_btn.pack(side='left', padx=(10, 0))
    
    # Theme description
    desc_label = tk.Label(
        theme_frame,
        text="Choose a preset or click Customize to create your own theme.",
        fg='gray'
    )
    desc_label.pack(anchor='w', pady=(10, 0))
    
    # Get reference to the "Theme Preset:" label (it was created anonymously)
    theme_preset_label = theme_row.winfo_children()[0]  # First child is the label

    # --- Splash Screen Settings ---
    splash_frame = tk.LabelFrame(container, text="Splash Screen", padx=10, pady=10)
    splash_frame.pack(fill='x', pady=(0, 10))
    
    # Load splash settings from config
    cfg = _load_config()
    try:
        splash_enabled = cfg.getboolean('Appearance', 'splash_enabled')
    except Exception:
        splash_enabled = True  # Default enabled
    try:
        current_opacity = cfg.getfloat('Appearance', 'splash_opacity')
    except Exception:
        current_opacity = 1.0
    
    # Splash enabled checkbox
    splash_enabled_var = tk.BooleanVar(value=splash_enabled)
    entry_refs['splash_enabled_var'] = splash_enabled_var
    
    splash_checkbox = tk.Checkbutton(
        splash_frame,
        text="Show splash screen on startup",
        variable=splash_enabled_var
    )
    splash_checkbox.pack(anchor='w', pady=(0, 8))
    
    # Splash opacity row
    opacity_row = tk.Frame(splash_frame)
    opacity_row.pack(fill='x', pady=5)
    
    opacity_label = tk.Label(opacity_row, text="Opacity:")
    opacity_label.pack(side='left', padx=(0, 10))
    
    # Opacity slider (Scale widget)
    opacity_var = tk.DoubleVar(value=current_opacity)
    entry_refs['splash_opacity_var'] = opacity_var
    
    opacity_slider = tk.Scale(
        opacity_row,
        from_=0.0,
        to=1.0,
        resolution=0.05,
        orient='horizontal',
        variable=opacity_var,
        length=200,
        showvalue=True
    )
    opacity_slider.pack(side='left', padx=(0, 10))
    
    # Opacity value label showing percentage
    opacity_pct_label = tk.Label(opacity_row, text=f"{int(current_opacity * 100)}%", width=5)
    opacity_pct_label.pack(side='left')
    
    # Splash opacity description
    opacity_desc_label = tk.Label(
        splash_frame,
        text="Controls the maximum opacity of the startup splash screen.",
        fg='gray'
    )
    opacity_desc_label.pack(anchor='w', pady=(5, 0))
    
    def _update_opacity_widgets_state():
        """Enable/disable opacity widgets based on splash enabled state."""
        enabled = splash_enabled_var.get()
        state = 'normal' if enabled else 'disabled'
        try:
            opacity_slider.config(state=state)
            opacity_label.config(state=state)
            opacity_pct_label.config(state=state)
            opacity_desc_label.config(state=state)
        except Exception:
            pass
    
    def _on_splash_enabled_change():
        """Save splash enabled state to config and update widget states."""
        try:
            enabled = splash_enabled_var.get()
            cfg = _load_config()
            if not cfg.has_section('Appearance'):
                cfg.add_section('Appearance')
            cfg.set('Appearance', 'splash_enabled', str(enabled))
            _save_config(cfg)
            _update_opacity_widgets_state()
        except Exception:
            pass
    
    splash_checkbox.config(command=_on_splash_enabled_change)
    
    def _on_opacity_change(value):
        """Update percentage label and save to config immediately."""
        try:
            val = float(value)
            opacity_pct_label.config(text=f"{int(val * 100)}%")
            # Save to config immediately
            cfg = _load_config()
            if not cfg.has_section('Appearance'):
                cfg.add_section('Appearance')
            cfg.set('Appearance', 'splash_opacity', str(val))
            _save_config(cfg)
        except Exception:
            pass
    
    opacity_slider.config(command=_on_opacity_change)
    
    # Apply initial state
    _update_opacity_widgets_state()
    
    # Store splash widgets for theme callback
    entry_refs['_appearance_splash_frame'] = splash_frame
    entry_refs['_appearance_splash_checkbox'] = splash_checkbox
    entry_refs['_appearance_opacity_row'] = opacity_row
    entry_refs['_appearance_opacity_label'] = opacity_label
    entry_refs['_appearance_opacity_slider'] = opacity_slider
    entry_refs['_appearance_opacity_pct_label'] = opacity_pct_label
    entry_refs['_appearance_opacity_desc_label'] = opacity_desc_label
    entry_refs['_update_opacity_widgets_state'] = _update_opacity_widgets_state

    # Store widgets for theme callback
    entry_refs['_appearance_container'] = container
    entry_refs['_appearance_theme_frame'] = theme_frame
    entry_refs['_appearance_theme_row'] = theme_row
    entry_refs['_appearance_desc_label'] = desc_label
    entry_refs['_appearance_customize_btn'] = customize_btn
    entry_refs['_appearance_preset_label'] = theme_preset_label
    
    def _apply_appearance_theme():
        """Apply current theme to all appearance panel widgets."""
        from libs import gui_utils
        
        try:
            gui_utils.apply_theme_to_window(container)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_labelframe(theme_frame)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_window(theme_row)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_label(theme_preset_label)
        except Exception:
            pass
        try:
            # desc_label keeps gray fg for muted appearance
            desc_label.config(bg=gui_utils.get_color('labelframe_bg'))
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_button(customize_btn)
        except Exception:
            pass
        # Splash screen section theming
        try:
            gui_utils.apply_theme_to_labelframe(splash_frame)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_checkbox(splash_checkbox)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_window(opacity_row)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_label(opacity_label)
        except Exception:
            pass
        try:
            gui_utils.apply_theme_to_label(opacity_pct_label)
        except Exception:
            pass
        try:
            # opacity_desc_label keeps gray fg for muted appearance
            opacity_desc_label.config(bg=gui_utils.get_color('labelframe_bg'))
        except Exception:
            pass
        try:
            # Theme the Scale widget
            opacity_slider.config(
                bg=gui_utils.get_color('labelframe_bg'),
                fg=gui_utils.get_color('label_fg'),
                troughcolor=gui_utils.get_color('entry_bg'),
                highlightbackground=gui_utils.get_color('labelframe_bg'),
                activebackground=gui_utils.get_color('button_active_bg')
            )
        except Exception:
            pass
    
    entry_refs['_appearance_apply_theme'] = _apply_appearance_theme
    
    # Apply initial theme
    _apply_appearance_theme()

    # Pack button frame at bottom with right alignment
    button_frame.pack(side='bottom', fill='x', padx=10, pady=(10, 10))

    return container


# Category registry - maps category name to builder function
CATEGORIES = {
    "Connections": _build_connections_panel,
    "Appearance": _build_appearance_panel,
}


# --------------------------------------------------------------------------
# Customize Colors Dialog
# --------------------------------------------------------------------------

# Human-readable labels for color keys, grouped by category
COLOR_KEY_LABELS = {
    # Content Panes
    'pane_bg': ('Content Panes', 'Background'),
    'pane_fg': ('Content Panes', 'Text'),
    'select_bg': ('Content Panes', 'Selection'),
    'insert_bg': ('Content Panes', 'Cursor'),
    # Window Chrome
    'window_bg': ('Window Chrome', 'Background'),
    'border_bg': ('Window Chrome', 'Borders'),
    # Labels
    'label_bg': ('Labels', 'Background'),
    'label_fg': ('Labels', 'Text'),
    # LabelFrame
    'labelframe_bg': ('LabelFrame', 'Background'),
    'labelframe_fg': ('LabelFrame', 'Title Text'),
    # Buttons
    'button_bg': ('Buttons', 'Background'),
    'button_fg': ('Buttons', 'Text'),
    'button_active_bg': ('Buttons', 'Active Background'),
    'button_active_fg': ('Buttons', 'Active Text'),
    # Entry Fields
    'entry_bg': ('Entry Fields', 'Background'),
    'entry_fg': ('Entry Fields', 'Text'),
    # Menus
    'menu_bg': ('Menus', 'Background'),
    'menu_fg': ('Menus', 'Text'),
    'menu_active_bg': ('Menus', 'Hover Background'),
    'menu_active_fg': ('Menus', 'Hover Text'),
    # Checkboxes
    'checkbox_bg': ('Checkboxes', 'Background'),
    'checkbox_fg': ('Checkboxes', 'Text'),
    'checkbox_select': ('Checkboxes', 'Checkmark Area'),
    # Scrollbars
    'scrollbar_bg': ('Scrollbars', 'Track'),
    'scrollbar_fg': ('Scrollbars', 'Thumb'),
    # Splash Screen
    'splash_bg': ('Splash Screen', 'Background'),
    'splash_fg': ('Splash Screen', 'Title Text'),
    'splash_muted_fg': ('Splash Screen', 'Footer Text'),
}

# Order of groups for display
COLOR_GROUP_ORDER = [
    'Content Panes',
    'Window Chrome',
    'Labels',
    'LabelFrame',
    'Buttons',
    'Entry Fields',
    'Menus',
    'Checkboxes',
    'Scrollbars',
    'Splash Screen',
]


class CustomizeColorsDialog:
    """
    Dialog for customizing theme colors.
    
    Shows all 22 color keys in a scrollable list with color swatches
    and color picker buttons. Changes can be previewed live.
    """
    
    def __init__(self, parent, base_preset_key='charcoal'):
        """
        Initialize the Customize Colors dialog.
        
        Args:
            parent: Parent window
            base_preset_key: Starting preset to copy colors from
        """
        from libs import gui_utils
        
        self.parent = parent
        self.gui_utils = gui_utils
        
        # Get starting colors from base preset
        self.colors = gui_utils.get_colors_for_preset(base_preset_key)
        self.original_theme = gui_utils.get_current_theme()
        self.swatch_widgets = {}  # key -> Label widget for color swatch
        
        # Create dialog window
        self.win = tk.Toplevel(parent)
        self.win.title("Customize Theme Colors")
        self.win.resizable(True, True)
        self.win.minsize(450, 500)
        
        # Set icon (Windows taskbar .ico + cross-platform .png fallback)
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
        except Exception:
            pass
        try:
            icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
            self.win.iconbitmap(default=icon_path)
        except Exception:
            pass
        try:
            icon_png = ASSETS_PATH / "assets" / "hoonywise_300.png"
            _icon_img = tk.PhotoImage(file=icon_png)
            self.win.iconphoto(False, _icon_img)
            self.win._icon_img = _icon_img
        except Exception:
            pass
        
        # Center on screen
        _center_window(self.win, 480, 600)
        
        # Make modal
        try:
            self.win.transient(parent)
            self.win.grab_set()
        except Exception:
            pass
        
        self._build_ui()
        
        # Focus
        try:
            self.win.focus_force()
            self.win.lift()
        except Exception:
            pass
    
    def _build_ui(self):
        """Build the dialog UI."""
        # Main frame
        main_frame = tk.Frame(self.win)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Instructions
        instr_label = tk.Label(
            main_frame,
            text="Click a swatch to change its color. Click Apply to preview.",
            fg='gray'
        )
        instr_label.pack(anchor='w', pady=(0, 10))
        
        # Scrollable canvas for color rows
        canvas_frame = tk.Frame(main_frame)
        canvas_frame.pack(fill='both', expand=True)
        
        self.canvas = tk.Canvas(canvas_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)
        
        # Inner frame for content
        self.inner_frame = tk.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner_frame, anchor='nw')
        
        def _on_configure(event=None):
            self.canvas.configure(scrollregion=self.canvas.bbox('all'))
            self.canvas.itemconfig(self.canvas_window, width=self.canvas.winfo_width())
        
        self.inner_frame.bind('<Configure>', _on_configure)
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        
        # Mousewheel scrolling - bind to specific widgets, not globally
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        
        self.canvas.bind('<MouseWheel>', _on_mousewheel)
        self.inner_frame.bind('<MouseWheel>', _on_mousewheel)
        canvas_frame.bind('<MouseWheel>', _on_mousewheel)
        
        # Build color rows grouped by category
        self._build_color_rows()
        
        # Force widget realization and update swatches
        # (winfo_rgb needs widgets to be mapped before it can resolve colors)
        self.inner_frame.update_idletasks()
        self.win.after(50, self._update_all_swatches)  # Small delay ensures full realization
        
        # Button frame
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill='x', pady=(10, 0))
        
        # Reset button on left
        reset_btn = tk.Button(
            btn_frame,
            text="Reset to Preset",
            command=self._on_reset
        )
        reset_btn.pack(side='left')
        
        # OK, Cancel, Apply on right
        apply_btn = tk.Button(btn_frame, text="Apply", width=8, command=self._on_apply)
        apply_btn.pack(side='right', padx=(5, 0))
        
        cancel_btn = tk.Button(btn_frame, text="Cancel", width=8, command=self._on_cancel)
        cancel_btn.pack(side='right', padx=(5, 0))
        
        ok_btn = tk.Button(btn_frame, text="OK", width=8, command=self._on_ok)
        ok_btn.pack(side='right', padx=(5, 0))
        
        # Store button refs for theming
        self._buttons = [reset_btn, apply_btn, cancel_btn, ok_btn]
        self._instr_label = instr_label
        
        # Apply initial theme to dialog
        self._apply_dialog_theme()
        
        # Clean up on close
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)
    
    def _build_color_rows(self):
        """Build rows for each color key, grouped by category."""
        current_group = None
        row = 0
        
        # Group colors by category
        for group_name in COLOR_GROUP_ORDER:
            # Find all keys in this group
            keys_in_group = [
                (key, label[1]) 
                for key, label in COLOR_KEY_LABELS.items() 
                if label[0] == group_name
            ]
            
            if not keys_in_group:
                continue
            
            # Group header
            header = tk.Label(
                self.inner_frame,
                text=group_name,
                font=('TkDefaultFont', 9, 'bold'),
                anchor='w'
            )
            header.grid(row=row, column=0, columnspan=3, sticky='w', pady=(10 if row > 0 else 0, 5))
            row += 1
            
            # Color rows
            for key, label_text in keys_in_group:
                self._build_color_row(row, key, label_text)
                row += 1
    
    def _build_color_row(self, row, key, label_text):
        """Build a single color row with label, swatch, and pick button."""
        # Label
        label = tk.Label(self.inner_frame, text=f"  {label_text}:", anchor='w', width=20)
        label.grid(row=row, column=0, sticky='w', padx=(10, 5), pady=2)
        
        # Color swatch (clickable)
        color_value = self.colors.get(key, '#000000')
        
        swatch = tk.Label(
            self.inner_frame,
            width=8,
            height=1,
            relief='solid',
            borderwidth=1,
            cursor='hand2'
        )
        swatch.grid(row=row, column=1, sticky='w', padx=5, pady=2)
        
        # Set swatch color
        self._set_swatch_color(swatch, color_value)
        
        # Store reference
        self.swatch_widgets[key] = swatch
        
        # Click handler for swatch
        def _on_swatch_click(event, k=key):
            self._pick_color(k)
        
        swatch.bind('<Button-1>', _on_swatch_click)
        
        # Hex value label
        hex_label = tk.Label(self.inner_frame, text=color_value, width=12, anchor='w')
        hex_label.grid(row=row, column=2, sticky='w', padx=5, pady=2)
        
        # Store hex label for updating
        swatch._hex_label = hex_label
    
    def _set_swatch_color(self, swatch, color_value):
        """Set the background color of a swatch, handling system colors."""
        # For system color names (like "SystemWindow"), we need to resolve them
        # to actual hex values since tk Labels don't always render them correctly
        if color_value.startswith('System'):
            try:
                # Use winfo_rgb to resolve system color to RGB
                rgb = swatch.winfo_rgb(color_value)
                hex_color = '#{:02x}{:02x}{:02x}'.format(rgb[0]//256, rgb[1]//256, rgb[2]//256)
                swatch.config(bg=hex_color)
            except Exception:
                swatch.config(bg='#808080')  # Fallback gray
        else:
            try:
                swatch.config(bg=color_value)
            except Exception:
                swatch.config(bg='#808080')  # Fallback gray
    
    def _update_all_swatches(self):
        """Update all swatch colors after widgets are fully realized."""
        for key, swatch in self.swatch_widgets.items():
            color_value = self.colors.get(key, '#000000')
            self._set_swatch_color(swatch, color_value)
            # Also update hex label if it exists
            if hasattr(swatch, '_hex_label'):
                try:
                    swatch._hex_label.config(text=color_value)
                except Exception:
                    pass
    
    def _pick_color(self, key):
        """Open color picker for a specific key."""
        current_color = self.colors.get(key, '#000000')
        
        # Handle system color names
        if current_color.startswith('System'):
            try:
                swatch = self.swatch_widgets.get(key)
                if swatch:
                    rgb = swatch.winfo_rgb(current_color)
                    current_color = '#{:02x}{:02x}{:02x}'.format(rgb[0]//256, rgb[1]//256, rgb[2]//256)
            except Exception:
                current_color = '#808080'
        
        # Open color chooser with persistent custom colors
        title = f"Choose color for {COLOR_KEY_LABELS.get(key, ('', key))[1]}"
        new_color = self.gui_utils.ask_color_with_persistence(
            initial_color=current_color,
            title=title,
            parent=self.win
        )
        
        if new_color:
            self.colors[key] = new_color
            
            # Update swatch
            swatch = self.swatch_widgets.get(key)
            if swatch:
                self._set_swatch_color(swatch, new_color)
                if hasattr(swatch, '_hex_label'):
                    swatch._hex_label.config(text=new_color)
    
    def _apply_dialog_theme(self):
        """Apply current theme colors to the dialog itself."""
        # Since we're customizing, use the colors being edited
        bg = self.colors.get('window_bg', '#252525')
        fg = self.colors.get('label_fg', '#e0e0e0')
        
        try:
            self.win.config(bg=bg)
            self.canvas.config(bg=bg)
            self.inner_frame.config(bg=bg)
            self._instr_label.config(bg=bg, fg='gray')
            
            # Apply to all children in inner_frame
            for widget in self.inner_frame.winfo_children():
                try:
                    widget.config(bg=bg, fg=fg)
                except Exception:
                    pass
            
            # Apply to buttons
            btn_bg = self.colors.get('button_bg', '#3a3a3a')
            btn_fg = self.colors.get('button_fg', '#e0e0e0')
            for btn in self._buttons:
                try:
                    btn.config(bg=btn_bg, fg=btn_fg)
                except Exception:
                    pass
        except Exception:
            pass
    
    def _on_apply(self):
        """Apply colors as preview without closing."""
        # Save all custom colors
        self.gui_utils.save_all_custom_colors(self.colors)
        
        # Set theme to 'custom' to use these colors
        self.gui_utils.set_theme('custom', save=True)
    
    def _on_ok(self):
        """Save and close."""
        self._on_apply()
        self._cleanup_and_close()
    
    def _on_cancel(self):
        """Cancel and restore original theme."""
        # Restore original theme
        self.gui_utils.set_theme(self.original_theme, save=True)
        self._cleanup_and_close()
    
    def _on_reset(self):
        """Reset colors to current preset base."""
        from tkinter import messagebox
        
        # Ask which preset to reset to
        result = messagebox.askyesno(
            "Reset Colors",
            "Reset all colors to the current preset's defaults?\n\n"
            "This will discard your customizations.",
            parent=self.win
        )
        
        if result:
            # Get colors from original theme (before customization started)
            base_preset = self.original_theme if self.original_theme != 'custom' else 'charcoal'
            self.colors = self.gui_utils.get_colors_for_preset(base_preset)
            
            # Update all swatches
            for key, swatch in self.swatch_widgets.items():
                color_value = self.colors.get(key, '#000000')
                self._set_swatch_color(swatch, color_value)
                if hasattr(swatch, '_hex_label'):
                    swatch._hex_label.config(text=color_value)
    
    def _cleanup_and_close(self):
        """Clean up and close the dialog."""
        self.win.destroy()


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

    # Set icon (Windows taskbar .ico + cross-platform .png fallback)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hoonywise.hoonytools")
    except Exception:
        pass
    try:
        icon_path = ASSETS_PATH / "assets" / "hoonywise_gui.ico"
        win.iconbitmap(default=icon_path)
    except Exception:
        pass
    try:
        icon_png = ASSETS_PATH / "assets" / "hoonywise_300.png"
        _icon_img = tk.PhotoImage(file=icon_png)
        win.iconphoto(False, _icon_img)
        win._icon_img = _icon_img
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

    # Store original values for Cancel restoration
    from libs import gui_utils
    entry_refs['_original_theme'] = gui_utils.get_current_theme()
    
    # Load original splash settings from config
    _orig_cfg = _load_config()
    try:
        entry_refs['_original_splash_enabled'] = _orig_cfg.getboolean('Appearance', 'splash_enabled')
    except Exception:
        entry_refs['_original_splash_enabled'] = True
    try:
        entry_refs['_original_splash_opacity'] = _orig_cfg.getfloat('Appearance', 'splash_opacity')
    except Exception:
        entry_refs['_original_splash_opacity'] = 1.0

    # Track current content frame for category switching
    current_content = {'frame': None}

    # --------------------------------------------------------------------------
    # Status bar at the bottom of the window
    # --------------------------------------------------------------------------
    # Separator line above status bar
    status_separator = tk.Frame(win, height=1, bg='#c0c0c0')
    status_separator.pack(side='bottom', fill='x')

    status_frame = tk.Frame(win, bg='#f0f0f0')
    status_frame.pack(side='bottom', fill='x')

    status_label = tk.Label(status_frame, text='', fg='#005a9e', bg='#f0f0f0', anchor='w', font=('TkDefaultFont', 9, 'bold'))
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
    category_frame = tk.Frame(main_paned, width=150, bg='#f0f0f0')
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
    content_outer_frame = tk.Frame(main_paned, bg='#f0f0f0')

    # Canvas for scrolling
    content_canvas = tk.Canvas(content_outer_frame, bg='#f0f0f0', highlightthickness=0)
    content_scrollbar = ttk.Scrollbar(content_outer_frame, orient='vertical', command=content_canvas.yview)
    content_canvas.configure(yscrollcommand=content_scrollbar.set)

    # Inner frame that holds actual content
    content_inner_frame = tk.Frame(content_canvas, bg='#f0f0f0')
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

    # Enable mousewheel scrolling - bind to specific widgets, not globally
    # This prevents capturing scroll events meant for combobox dropdowns
    # Only scroll when content exceeds viewport height
    def _on_mousewheel(event):
        # Only scroll if content is larger than viewport
        try:
            content_height = content_inner_frame.winfo_height()
            viewport_height = content_canvas.winfo_height()
            if content_height > viewport_height:
                content_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        except Exception:
            pass

    def _bind_mousewheel_recursive(widget):
        """Bind mousewheel to widget and all its children recursively."""
        try:
            # Skip binding to Combobox widgets to avoid conflicts
            if widget.winfo_class() not in ('TCombobox', 'Listbox'):
                widget.bind('<MouseWheel>', _on_mousewheel)
        except Exception:
            pass
        for child in widget.winfo_children():
            _bind_mousewheel_recursive(child)
    
    # Bind to canvas and outer frame
    content_canvas.bind('<MouseWheel>', _on_mousewheel)
    content_outer_frame.bind('<MouseWheel>', _on_mousewheel)
    content_inner_frame.bind('<MouseWheel>', _on_mousewheel)
    
    # Re-bind mousewheel when content changes (new widgets added)
    def _rebind_mousewheel_on_configure(event=None):
        _bind_mousewheel_recursive(content_inner_frame)
    
    content_inner_frame.bind('<Map>', _rebind_mousewheel_on_configure)

    # Pack canvas and scrollbar
    content_scrollbar.pack(side='right', fill='y')
    content_canvas.pack(side='left', fill='both', expand=True)

    main_paned.add(content_outer_frame, minsize=300)

    # --------------------------------------------------------------------------
    # Button frame (will be packed inside content by category builder)
    # --------------------------------------------------------------------------
    button_frame = tk.Frame(content_inner_frame, bg='#f0f0f0')

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
            # Entry widgets exist (on Connections tab) - read from them
            s1_user_val = s1_user.get().strip()
            s1_pass_val = s1_pass.get().strip()
            s1_dsn_val = s1_dsn.get().strip()
        else:
            # Entry widgets don't exist (on different tab) - preserve existing config.ini values
            if cfg.has_section('schema1'):
                s1_user_val = cfg.get('schema1', 'user', fallback='')
                s1_pass_val = cfg.get('schema1', 'password', fallback='')
                s1_dsn_val = cfg.get('schema1', 'dsn', fallback='')

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
            # Entry widgets exist (on Connections tab) - read from them
            s2_user_val = s2_user.get().strip()
            s2_pass_val = s2_pass.get().strip()
            s2_dsn_val = s2_dsn.get().strip()
        else:
            # Entry widgets don't exist (on different tab) - preserve existing config.ini values
            if cfg.has_section('schema2'):
                s2_user_val = cfg.get('schema2', 'user', fallback='')
                s2_pass_val = cfg.get('schema2', 'password', fallback='')
                s2_dsn_val = cfg.get('schema2', 'dsn', fallback='')

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

        # Note: Theme settings are saved automatically via gui_utils.set_theme()
        # when the user changes the dropdown (live preview)

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

            # Note: Theme changes are applied live via gui_utils.set_theme()
            # No sync needed here anymore

            # Show non-invasive confirmation message in status bar
            _show_status_message("Settings saved")
            return True
        else:
            _show_status_message("Failed to save settings", error=True)
            return False

    def _on_ok():
        if _validate():
            if _save():
                win.destroy()

    def _on_cancel():
        # Restore original theme if it was changed
        from libs import gui_utils
        original_theme = entry_refs.get('_original_theme')
        if original_theme:
            gui_utils.set_theme(original_theme, save=True)
        
        # Restore original splash settings
        cfg = _load_config()
        if not cfg.has_section('Appearance'):
            cfg.add_section('Appearance')
        cfg.set('Appearance', 'splash_enabled', str(entry_refs.get('_original_splash_enabled', True)))
        cfg.set('Appearance', 'splash_opacity', str(entry_refs.get('_original_splash_opacity', 1.0)))
        _save_config(cfg)
        
        win.destroy()

    def _on_apply():
        if _validate():
            if _save():
                # Update original values to match what was just saved
                # so Cancel/X won't revert these changes
                from libs import gui_utils
                entry_refs['_original_theme'] = gui_utils.get_current_theme()
                
                # Read back splash settings from config
                cfg = _load_config()
                try:
                    entry_refs['_original_splash_enabled'] = cfg.getboolean('Appearance', 'splash_enabled')
                except Exception:
                    pass
                try:
                    entry_refs['_original_splash_opacity'] = cfg.getfloat('Appearance', 'splash_opacity')
                except Exception:
                    pass

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

        # Clear entry refs for fresh build, but preserve system references and original values
        preserved = {
            '_parent': entry_refs.get('_parent'),
            '_status_label': entry_refs.get('_status_label'),
            '_win': entry_refs.get('_win'),
            '_original_theme': entry_refs.get('_original_theme'),
            '_original_splash_enabled': entry_refs.get('_original_splash_enabled'),
            '_original_splash_opacity': entry_refs.get('_original_splash_opacity'),
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
    def _apply_theme(theme_key=None):
        """Apply current theme from gui_utils to the Settings dialog."""
        from libs import gui_utils
        
        try:
            # Configure Settings.Treeview style
            style.configure('Settings.Treeview',
                            background=gui_utils.get_color('pane_bg'),
                            fieldbackground=gui_utils.get_color('pane_bg'),
                            foreground=gui_utils.get_color('pane_fg'),
                            rowheight=24)
            style.map('Settings.Treeview',
                      background=[('selected', gui_utils.get_color('select_bg'))],
                      foreground=[('selected', gui_utils.get_color('menu_active_fg'))])
        except Exception:
            pass
        
        # Apply theme to dialog window
        try:
            gui_utils.apply_theme_to_window(win)
        except Exception:
            pass
        
        # Apply theme to category frame
        try:
            gui_utils.apply_theme_to_window(category_frame)
        except Exception:
            pass
        
        # Apply theme to main paned window
        try:
            main_paned.config(bg=gui_utils.get_color('border_bg'))
        except Exception:
            pass
        
        # Apply theme to status bar
        try:
            status_frame.config(bg=gui_utils.get_color('window_bg'))
            status_label.config(bg=gui_utils.get_color('window_bg'), fg=gui_utils.get_color('label_fg'))
            status_separator.config(bg=gui_utils.get_color('border_bg'))
        except Exception:
            pass
        
        # Apply theme to buttons
        try:
            for btn in (btn_ok, btn_cancel, btn_apply):
                gui_utils.apply_theme_to_button(btn)
        except Exception:
            pass
        
        # Apply theme to content canvas and inner frame
        try:
            content_canvas.config(bg=gui_utils.get_color('window_bg'))
            content_inner_frame.config(bg=gui_utils.get_color('window_bg'))
            content_outer_frame.config(bg=gui_utils.get_color('window_bg'))
        except Exception:
            pass
        
        # Apply theme to connections panel if it exists
        conn_apply_theme = entry_refs.get('_conn_apply_theme')
        if conn_apply_theme:
            try:
                conn_apply_theme()
            except Exception:
                pass
        
        # Apply theme to appearance panel if it exists
        appearance_apply_theme = entry_refs.get('_appearance_apply_theme')
        if appearance_apply_theme:
            try:
                appearance_apply_theme()
            except Exception:
                pass
        
        # Apply theme to button frame
        try:
            button_frame.config(bg=gui_utils.get_color('window_bg'))
        except Exception:
            pass
        
        # Update theme dropdown to reflect current theme (e.g., after Apply in Customize dialog)
        try:
            current_theme = gui_utils.get_current_theme()
            current_display = gui_utils.get_theme_display_name(current_theme)
            theme_var = entry_refs.get('theme_var')
            if theme_var and theme_var.get() != current_display:
                theme_var.set(current_display)
        except Exception:
            pass

    # Register with gui_utils theme callback system
    from libs import gui_utils
    gui_utils.register_theme_callback(_apply_theme)

    def _on_destroy(event=None):
        if event.widget == win:  # Only on main window destroy
            # Unregister theme callback from gui_utils
            try:
                gui_utils.unregister_theme_callback(_apply_theme)
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
