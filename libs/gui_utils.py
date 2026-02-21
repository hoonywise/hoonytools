"""
Shared GUI utility functions for HoonyTools.

Provides theme management, widget styling, and common helpers.
"""

import configparser
import logging
import os
from typing import Callable, List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# =============================================================================
# Theme Constants
# =============================================================================

# Ordered list of theme keys (spectrum from darkest to lightest, plus Custom)
THEME_ORDER = [
    'pure_black',
    'midnight',
    'charcoal',
    'slate',
    'graphite',
    'silver',
    'system_light',
    'custom',
]

# Display names for UI
THEME_DISPLAY_NAMES = {
    'pure_black': 'Pure Black',
    'midnight': 'Midnight',
    'charcoal': 'Charcoal',
    'slate': 'Slate',
    'graphite': 'Graphite',
    'silver': 'Silver',
    'system_light': 'System Light',
    'custom': 'Custom',
}

# Complete list of color keys for full chrome theming
COLOR_KEYS = [
    # Content panes (ScrolledText, Text, Treeview)
    'pane_bg',            # Background color for content panes
    'pane_fg',            # Text/foreground color in panes
    'select_bg',          # Selection highlight background
    'insert_bg',          # Cursor/insertion point color
    
    # Window chrome
    'window_bg',          # Frame, Toplevel, root window backgrounds
    'border_bg',          # Border/separator color
    
    # Labels
    'label_bg',           # Label background
    'label_fg',           # Label text color
    
    # LabelFrame
    'labelframe_bg',      # LabelFrame background
    'labelframe_fg',      # LabelFrame title text color
    
    # Buttons
    'button_bg',          # Button background
    'button_fg',          # Button text
    'button_active_bg',   # Button when pressed/hovered
    'button_active_fg',   # Button text when pressed/hovered
    
    # Entry fields
    'entry_bg',           # Entry/input field background
    'entry_fg',           # Entry text color
    
    # Menu
    'menu_bg',            # Menu background
    'menu_fg',            # Menu text
    'menu_active_bg',     # Menu item hover/selected
    'menu_active_fg',     # Menu item text when selected
    
    # Checkbox/Radio
    'checkbox_bg',        # Checkbox background
    'checkbox_fg',        # Checkbox text
    'checkbox_select',    # Checkmark/indicator color
    
    # Scrollbar
    'scrollbar_bg',       # Scrollbar track/trough
    'scrollbar_fg',       # Scrollbar thumb/slider
    
    # Splash screen
    'splash_bg',          # Splash window background
    'splash_fg',          # Splash title text color
    'splash_muted_fg',    # Splash footer/version text (muted)
]

# =============================================================================
# Preset Theme Definitions (Full Chrome)
# =============================================================================

PRESET_THEMES = {
    'pure_black': {
        # Content panes
        'pane_bg': '#000000',
        'pane_fg': '#ffffff',
        'select_bg': '#2a6bd6',
        'insert_bg': '#ffffff',
        # Window chrome
        'window_bg': '#000000',
        'border_bg': '#333333',
        # Labels
        'label_bg': '#000000',
        'label_fg': '#ffffff',
        # LabelFrame
        'labelframe_bg': '#000000',
        'labelframe_fg': '#ffffff',
        # Buttons
        'button_bg': '#1a1a1a',
        'button_fg': '#ffffff',
        'button_active_bg': '#333333',
        'button_active_fg': '#ffffff',
        # Entry fields
        'entry_bg': '#000000',
        'entry_fg': '#ffffff',
        # Menu
        'menu_bg': '#000000',
        'menu_fg': '#ffffff',
        'menu_active_bg': '#333333',
        'menu_active_fg': '#ffffff',
        # Checkbox/Radio
        'checkbox_bg': '#000000',
        'checkbox_fg': '#ffffff',
        'checkbox_select': '#333333',
        # Scrollbar
        'scrollbar_bg': '#1a1a1a',
        'scrollbar_fg': '#444444',
        # Splash screen
        'splash_bg': '#000000',
        'splash_fg': '#ffffff',
        'splash_muted_fg': '#888888',
    },
    'midnight': {
        # Content panes
        'pane_bg': '#0d1117',
        'pane_fg': '#c9d1d9',
        'select_bg': '#264f78',
        'insert_bg': '#c9d1d9',
        # Window chrome
        'window_bg': '#010409',
        'border_bg': '#30363d',
        # Labels
        'label_bg': '#010409',
        'label_fg': '#c9d1d9',
        # LabelFrame
        'labelframe_bg': '#010409',
        'labelframe_fg': '#c9d1d9',
        # Buttons
        'button_bg': '#21262d',
        'button_fg': '#c9d1d9',
        'button_active_bg': '#30363d',
        'button_active_fg': '#ffffff',
        # Entry fields
        'entry_bg': '#0d1117',
        'entry_fg': '#c9d1d9',
        # Menu
        'menu_bg': '#161b22',
        'menu_fg': '#c9d1d9',
        'menu_active_bg': '#30363d',
        'menu_active_fg': '#ffffff',
        # Checkbox/Radio
        'checkbox_bg': '#010409',
        'checkbox_fg': '#c9d1d9',
        'checkbox_select': '#21262d',
        # Scrollbar
        'scrollbar_bg': '#161b22',
        'scrollbar_fg': '#30363d',
        # Splash screen
        'splash_bg': '#010409',
        'splash_fg': '#c9d1d9',
        'splash_muted_fg': '#6e7681',
    },
    'charcoal': {
        # Content panes
        'pane_bg': '#1e1e1e',
        'pane_fg': '#d4d4d4',
        'select_bg': '#264f78',
        'insert_bg': '#d4d4d4',
        # Window chrome
        'window_bg': '#181818',
        'border_bg': '#3c3c3c',
        # Labels
        'label_bg': '#181818',
        'label_fg': '#d4d4d4',
        # LabelFrame
        'labelframe_bg': '#181818',
        'labelframe_fg': '#d4d4d4',
        # Buttons
        'button_bg': '#2d2d2d',
        'button_fg': '#d4d4d4',
        'button_active_bg': '#3e3e3e',
        'button_active_fg': '#ffffff',
        # Entry fields
        'entry_bg': '#1e1e1e',
        'entry_fg': '#d4d4d4',
        # Menu
        'menu_bg': '#252526',
        'menu_fg': '#d4d4d4',
        'menu_active_bg': '#094771',
        'menu_active_fg': '#ffffff',
        # Checkbox/Radio
        'checkbox_bg': '#181818',
        'checkbox_fg': '#d4d4d4',
        'checkbox_select': '#2d2d2d',
        # Scrollbar
        'scrollbar_bg': '#1e1e1e',
        'scrollbar_fg': '#424242',
        # Splash screen
        'splash_bg': '#181818',
        'splash_fg': '#d4d4d4',
        'splash_muted_fg': '#808080',
    },
    'slate': {
        # Content panes
        'pane_bg': '#2d2d2d',
        'pane_fg': '#e0e0e0',
        'select_bg': '#3d5a80',
        'insert_bg': '#e0e0e0',
        # Window chrome
        'window_bg': '#252525',
        'border_bg': '#484848',
        # Labels
        'label_bg': '#252525',
        'label_fg': '#e0e0e0',
        # LabelFrame
        'labelframe_bg': '#252525',
        'labelframe_fg': '#e0e0e0',
        # Buttons
        'button_bg': '#3a3a3a',
        'button_fg': '#e0e0e0',
        'button_active_bg': '#4a4a4a',
        'button_active_fg': '#ffffff',
        # Entry fields
        'entry_bg': '#2d2d2d',
        'entry_fg': '#e0e0e0',
        # Menu
        'menu_bg': '#303030',
        'menu_fg': '#e0e0e0',
        'menu_active_bg': '#4a4a4a',
        'menu_active_fg': '#ffffff',
        # Checkbox/Radio
        'checkbox_bg': '#252525',
        'checkbox_fg': '#e0e0e0',
        'checkbox_select': '#3a3a3a',
        # Scrollbar
        'scrollbar_bg': '#2d2d2d',
        'scrollbar_fg': '#505050',
        # Splash screen
        'splash_bg': '#252525',
        'splash_fg': '#e0e0e0',
        'splash_muted_fg': '#888888',
    },
    'graphite': {
        # Content panes
        'pane_bg': '#3c3f41',
        'pane_fg': '#bbbbbb',
        'select_bg': '#4b6eaf',
        'insert_bg': '#bbbbbb',
        # Window chrome
        'window_bg': '#313335',
        'border_bg': '#555555',
        # Labels
        'label_bg': '#313335',
        'label_fg': '#bbbbbb',
        # LabelFrame
        'labelframe_bg': '#313335',
        'labelframe_fg': '#bbbbbb',
        # Buttons
        'button_bg': '#45484a',
        'button_fg': '#bbbbbb',
        'button_active_bg': '#55585a',
        'button_active_fg': '#ffffff',
        # Entry fields
        'entry_bg': '#3c3f41',
        'entry_fg': '#bbbbbb',
        # Menu
        'menu_bg': '#3c3f41',
        'menu_fg': '#bbbbbb',
        'menu_active_bg': '#4b6eaf',
        'menu_active_fg': '#ffffff',
        # Checkbox/Radio
        'checkbox_bg': '#313335',
        'checkbox_fg': '#bbbbbb',
        'checkbox_select': '#45484a',
        # Scrollbar
        'scrollbar_bg': '#3c3f41',
        'scrollbar_fg': '#5a5d5e',
        # Splash screen
        'splash_bg': '#313335',
        'splash_fg': '#bbbbbb',
        'splash_muted_fg': '#888888',
    },
    'silver': {
        # Content panes
        'pane_bg': '#d0d0d0',
        'pane_fg': '#1a1a1a',
        'select_bg': '#0078d4',
        'insert_bg': '#1a1a1a',
        # Window chrome
        'window_bg': '#c0c0c0',
        'border_bg': '#a0a0a0',
        # Labels
        'label_bg': '#c0c0c0',
        'label_fg': '#1a1a1a',
        # LabelFrame
        'labelframe_bg': '#c0c0c0',
        'labelframe_fg': '#1a1a1a',
        # Buttons
        'button_bg': '#b8b8b8',
        'button_fg': '#1a1a1a',
        'button_active_bg': '#a8a8a8',
        'button_active_fg': '#000000',
        # Entry fields
        'entry_bg': '#d0d0d0',
        'entry_fg': '#1a1a1a',
        # Menu
        'menu_bg': '#c8c8c8',
        'menu_fg': '#1a1a1a',
        'menu_active_bg': '#0078d4',
        'menu_active_fg': '#ffffff',
        # Checkbox/Radio
        'checkbox_bg': '#c0c0c0',
        'checkbox_fg': '#1a1a1a',
        'checkbox_select': '#a0a0a0',
        # Scrollbar
        'scrollbar_bg': '#c0c0c0',
        'scrollbar_fg': '#888888',
        # Splash screen
        'splash_bg': '#c0c0c0',
        'splash_fg': '#1a1a1a',
        'splash_muted_fg': '#555555',
    },
    'system_light': {
        # Content panes
        'pane_bg': 'SystemWindow',
        'pane_fg': 'SystemWindowText',
        'select_bg': 'SystemHighlight',
        'insert_bg': 'SystemWindowText',
        # Window chrome
        'window_bg': 'SystemButtonFace',
        'border_bg': 'SystemButtonShadow',
        # Labels
        'label_bg': 'SystemButtonFace',
        'label_fg': 'SystemButtonText',
        # LabelFrame
        'labelframe_bg': 'SystemButtonFace',
        'labelframe_fg': 'SystemButtonText',
        # Buttons
        'button_bg': 'SystemButtonFace',
        'button_fg': 'SystemButtonText',
        'button_active_bg': 'SystemButtonFace',
        'button_active_fg': 'SystemButtonText',
        # Entry fields
        'entry_bg': 'SystemWindow',
        'entry_fg': 'SystemWindowText',
        # Menu
        'menu_bg': 'SystemMenu',
        'menu_fg': 'SystemMenuText',
        'menu_active_bg': 'SystemHighlight',
        'menu_active_fg': 'SystemHighlightText',
        # Checkbox/Radio
        'checkbox_bg': 'SystemButtonFace',
        'checkbox_fg': 'SystemButtonText',
        'checkbox_select': 'SystemWindow',
        # Scrollbar
        'scrollbar_bg': 'SystemScrollbar',
        'scrollbar_fg': 'SystemButtonFace',
        # Splash screen
        'splash_bg': 'SystemButtonFace',
        'splash_fg': 'SystemButtonText',
        'splash_muted_fg': '#444444',
    },
}

# =============================================================================
# Legacy Constants (for backward compatibility)
# =============================================================================

DARK_BG = '#000000'
DARK_FG = '#ffffff'
DARK_BTN_BG = '#000000'
DARK_BTN_ACTIVE_BG = '#222222'
DARK_SELECT_BG = '#333333'
DARK_INSERT_BG = '#ffffff'

LIGHT_BG = 'SystemButtonFace'
LIGHT_FG = 'black'

# =============================================================================
# Module State
# =============================================================================

_current_theme: str = 'system_light'
_theme_change_callbacks: List[Callable] = []

# =============================================================================
# Theme Management Functions
# =============================================================================

def get_theme_names() -> List[str]:
    """Return ordered list of theme keys."""
    return THEME_ORDER.copy()


def get_theme_display_name(theme_key: str) -> str:
    """Get human-readable display name for a theme key."""
    return THEME_DISPLAY_NAMES.get(theme_key, theme_key)


def get_display_name_to_key() -> dict:
    """Return mapping of display names to theme keys."""
    return {v: k for k, v in THEME_DISPLAY_NAMES.items()}


def get_current_theme() -> str:
    """Return the current theme key."""
    return _current_theme


def get_color(key: str) -> str:
    """
    Get a color value from the current theme.
    
    Args:
        key: Color key from COLOR_KEYS
    
    Returns:
        Color value (hex string or system color name)
    """
    if _current_theme == 'custom':
        custom_colors = load_custom_colors_from_config()
        if key in custom_colors:
            return custom_colors[key]
        # Fallback to charcoal for missing keys
        return PRESET_THEMES['charcoal'].get(key, '')
    
    theme = PRESET_THEMES.get(_current_theme, PRESET_THEMES['system_light'])
    return theme.get(key, '')


def get_all_colors() -> Dict[str, str]:
    """
    Get all color values from the current theme.
    
    Returns:
        Dict mapping color keys to their values
    """
    if _current_theme == 'custom':
        # Start with charcoal as base, overlay custom colors
        colors = PRESET_THEMES['charcoal'].copy()
        custom_colors = load_custom_colors_from_config()
        colors.update(custom_colors)
        return colors
    
    theme = PRESET_THEMES.get(_current_theme, PRESET_THEMES['system_light'])
    return theme.copy()


def is_dark_theme() -> bool:
    """
    Check if the current theme is a dark theme.
    
    Returns:
        True if current theme is dark (pure_black through graphite)
    """
    dark_themes = {'pure_black', 'midnight', 'charcoal', 'slate', 'graphite'}
    return _current_theme in dark_themes


def set_theme(theme_key: str, save: bool = True) -> None:
    """
    Set the current theme and notify callbacks.
    
    Args:
        theme_key: Theme key from THEME_ORDER (includes 'custom')
        save: Whether to persist to config.ini
    """
    global _current_theme
    
    # Valid themes include all presets plus 'custom'
    valid_themes = set(PRESET_THEMES.keys()) | {'custom'}
    
    if theme_key not in valid_themes:
        logger.warning(f"Unknown theme '{theme_key}', defaulting to 'system_light'")
        theme_key = 'system_light'
    
    _current_theme = theme_key
    logger.debug(f"Theme set to: {theme_key}")
    
    if save:
        save_theme_to_config(theme_key)
    
    # Notify all registered callbacks
    for callback in _theme_change_callbacks:
        try:
            callback(theme_key)
        except Exception as e:
            logger.error(f"Theme callback error: {e}")


def register_theme_callback(callback: Callable) -> None:
    """
    Register a callback to be called when theme changes.
    
    Args:
        callback: Function that accepts theme_key as argument
    """
    if callback not in _theme_change_callbacks:
        _theme_change_callbacks.append(callback)


def unregister_theme_callback(callback: Callable) -> None:
    """Remove a previously registered callback."""
    if callback in _theme_change_callbacks:
        _theme_change_callbacks.remove(callback)


# =============================================================================
# Config I/O
# =============================================================================

def _get_config_path() -> str:
    """Get the path to config.ini."""
    return os.path.join(os.path.dirname(__file__), 'config.ini')


def load_theme_from_config() -> None:
    """
    Load theme from config.ini on startup.
    
    Handles migration from legacy dark_mode setting.
    """
    global _current_theme
    
    config_path = _get_config_path()
    config = configparser.ConfigParser()
    
    try:
        config.read(config_path)
    except Exception as e:
        logger.error(f"Failed to read config: {e}")
        _current_theme = 'system_light'
        return
    
    # Check for new [theme] section first
    if config.has_section('theme') and config.has_option('theme', 'preset'):
        theme_key = config.get('theme', 'preset', fallback='system_light')
        if theme_key in THEME_ORDER:
            _current_theme = theme_key
            logger.debug(f"Loaded theme from config: {theme_key}")
            return
    
    # Migration: Check legacy dark_mode setting
    if config.has_section('preferences') and config.has_option('preferences', 'dark_mode'):
        dark_mode = config.getboolean('preferences', 'dark_mode', fallback=False)
        
        # Migrate to new theme system
        if dark_mode:
            _current_theme = 'pure_black'
        else:
            _current_theme = 'system_light'
        
        logger.info(f"Migrated dark_mode={dark_mode} to theme={_current_theme}")
        
        # Remove legacy key and save new format
        config.remove_option('preferences', 'dark_mode')
        
        # Clean up empty preferences section
        if config.has_section('preferences') and len(config.options('preferences')) == 0:
            config.remove_section('preferences')
        
        # Add new theme section
        if not config.has_section('theme'):
            config.add_section('theme')
        config.set('theme', 'preset', _current_theme)
        
        # Write updated config
        try:
            with open(config_path, 'w') as f:
                config.write(f)
            logger.debug("Config migrated to new theme format")
        except Exception as e:
            logger.error(f"Failed to write migrated config: {e}")
        
        return
    
    # Default
    _current_theme = 'system_light'


def save_theme_to_config(theme_key: str) -> None:
    """
    Save the current theme preset to config.ini.
    
    Args:
        theme_key: Theme key to save
    """
    config_path = _get_config_path()
    config = configparser.ConfigParser()
    
    try:
        config.read(config_path)
    except Exception as e:
        logger.error(f"Failed to read config for saving: {e}")
        return
    
    # Ensure theme section exists
    if not config.has_section('theme'):
        config.add_section('theme')
    
    config.set('theme', 'preset', theme_key)
    
    # Remove legacy dark_mode if still present
    if config.has_section('preferences') and config.has_option('preferences', 'dark_mode'):
        config.remove_option('preferences', 'dark_mode')
        if len(config.options('preferences')) == 0:
            config.remove_section('preferences')
    
    try:
        with open(config_path, 'w') as f:
            config.write(f)
        logger.debug(f"Saved theme to config: {theme_key}")
    except Exception as e:
        logger.error(f"Failed to save theme to config: {e}")


def load_custom_colors_from_config() -> Dict[str, str]:
    """
    Load custom color values from config.ini.
    
    Custom colors are stored under [theme] section with 'custom_' prefix.
    E.g., custom_pane_bg = #1a1a2e
    
    Returns:
        Dict mapping color keys to their custom values (without 'custom_' prefix)
    """
    config_path = _get_config_path()
    config = configparser.ConfigParser()
    custom_colors = {}
    
    try:
        config.read(config_path)
    except Exception as e:
        logger.error(f"Failed to read config for custom colors: {e}")
        return custom_colors
    
    if not config.has_section('theme'):
        return custom_colors
    
    # Read all custom_* options
    for option in config.options('theme'):
        if option.startswith('custom_'):
            key = option[7:]  # Remove 'custom_' prefix
            if key in COLOR_KEYS:
                custom_colors[key] = config.get('theme', option)
    
    return custom_colors


def save_custom_color_to_config(key: str, hex_value: str) -> None:
    """
    Save a single custom color value to config.ini.
    
    Args:
        key: Color key from COLOR_KEYS (e.g., 'pane_bg')
        hex_value: Hex color value (e.g., '#1a1a2e')
    """
    if key not in COLOR_KEYS:
        logger.warning(f"Invalid color key: {key}")
        return
    
    config_path = _get_config_path()
    config = configparser.ConfigParser()
    
    try:
        config.read(config_path)
    except Exception as e:
        logger.error(f"Failed to read config for custom color: {e}")
        return
    
    # Ensure theme section exists
    if not config.has_section('theme'):
        config.add_section('theme')
    
    config.set('theme', f'custom_{key}', hex_value)
    
    try:
        with open(config_path, 'w') as f:
            config.write(f)
        logger.debug(f"Saved custom color {key}={hex_value}")
    except Exception as e:
        logger.error(f"Failed to save custom color: {e}")


def save_all_custom_colors(colors: Dict[str, str]) -> None:
    """
    Save all custom colors to config.ini at once.
    
    Args:
        colors: Dict mapping color keys to hex values
    """
    config_path = _get_config_path()
    config = configparser.ConfigParser()
    
    try:
        config.read(config_path)
    except Exception as e:
        logger.error(f"Failed to read config for custom colors: {e}")
        return
    
    # Ensure theme section exists
    if not config.has_section('theme'):
        config.add_section('theme')
    
    # Save each color with custom_ prefix
    for key, value in colors.items():
        if key in COLOR_KEYS:
            config.set('theme', f'custom_{key}', value)
    
    try:
        with open(config_path, 'w') as f:
            config.write(f)
        logger.debug(f"Saved {len(colors)} custom colors")
    except Exception as e:
        logger.error(f"Failed to save custom colors: {e}")


def get_colors_for_preset(preset_key: str) -> Dict[str, str]:
    """
    Get all colors for a specific preset (without changing current theme).
    
    Args:
        preset_key: Preset key (e.g., 'charcoal', 'midnight')
    
    Returns:
        Dict mapping color keys to values for that preset
    """
    if preset_key == 'custom':
        # For custom, start with charcoal and overlay saved custom colors
        colors = PRESET_THEMES['charcoal'].copy()
        custom_colors = load_custom_colors_from_config()
        colors.update(custom_colors)
        return colors
    
    return PRESET_THEMES.get(preset_key, PRESET_THEMES['charcoal']).copy()


# =============================================================================
# Widget Styling Functions (New - Full Chrome Theming)
# =============================================================================

def apply_theme_to_pane(widget) -> None:
    """
    Apply current theme colors to a text/pane widget.
    
    This is the primary function for styling ScrolledText and Text widgets.
    
    Args:
        widget: A Text or ScrolledText widget
    """
    try:
        widget.config(
            bg=get_color('pane_bg'),
            fg=get_color('pane_fg'),
            insertbackground=get_color('insert_bg'),
            selectbackground=get_color('select_bg'),
        )
    except Exception as e:
        logger.debug(f"Could not apply theme to pane: {e}")


def apply_theme_to_window(widget) -> None:
    """
    Apply current theme colors to a window/frame background.
    
    Args:
        widget: A Tk, Toplevel, or Frame widget
    """
    try:
        widget.config(bg=get_color('window_bg'))
    except Exception as e:
        logger.debug(f"Could not apply theme to window: {e}")


def apply_theme_to_label(widget) -> None:
    """
    Apply current theme colors to a label.
    
    Args:
        widget: A Label widget
    """
    try:
        widget.config(
            bg=get_color('label_bg'),
            fg=get_color('label_fg'),
        )
    except Exception as e:
        logger.debug(f"Could not apply theme to label: {e}")


def apply_theme_to_labelframe(widget) -> None:
    """
    Apply current theme colors to a LabelFrame.
    
    Args:
        widget: A LabelFrame widget
    """
    try:
        widget.config(
            bg=get_color('labelframe_bg'),
            fg=get_color('labelframe_fg'),
        )
    except Exception as e:
        logger.debug(f"Could not apply theme to labelframe: {e}")


def apply_theme_to_button(widget) -> None:
    """
    Apply current theme colors to a button.
    
    Args:
        widget: A Button widget
    """
    try:
        widget.config(
            bg=get_color('button_bg'),
            fg=get_color('button_fg'),
            activebackground=get_color('button_active_bg'),
            activeforeground=get_color('button_active_fg'),
        )
    except Exception as e:
        logger.debug(f"Could not apply theme to button: {e}")


def apply_theme_to_entry(widget) -> None:
    """
    Apply current theme colors to an entry field.
    
    Args:
        widget: An Entry widget
    """
    try:
        widget.config(
            bg=get_color('entry_bg'),
            fg=get_color('entry_fg'),
            insertbackground=get_color('insert_bg'),
            selectbackground=get_color('select_bg'),
        )
    except Exception as e:
        logger.debug(f"Could not apply theme to entry: {e}")


def apply_theme_to_menu(widget) -> None:
    """
    Apply current theme colors to a menu.
    
    Args:
        widget: A Menu widget
    """
    try:
        widget.config(
            bg=get_color('menu_bg'),
            fg=get_color('menu_fg'),
            activebackground=get_color('menu_active_bg'),
            activeforeground=get_color('menu_active_fg'),
        )
    except Exception as e:
        logger.debug(f"Could not apply theme to menu: {e}")


def apply_theme_to_checkbox(widget) -> None:
    """
    Apply current theme colors to a checkbox/checkbutton.
    
    Args:
        widget: A Checkbutton widget
    """
    try:
        widget.config(
            bg=get_color('checkbox_bg'),
            fg=get_color('checkbox_fg'),
            activebackground=get_color('checkbox_bg'),
            activeforeground=get_color('checkbox_fg'),
            selectcolor=get_color('checkbox_select'),
        )
    except Exception as e:
        logger.debug(f"Could not apply theme to checkbox: {e}")


def apply_theme_to_scrollbar(widget) -> None:
    """
    Apply current theme colors to a scrollbar.
    
    Args:
        widget: A Scrollbar widget
    """
    try:
        widget.config(
            bg=get_color('scrollbar_fg'),
            troughcolor=get_color('scrollbar_bg'),
        )
    except Exception as e:
        logger.debug(f"Could not apply theme to scrollbar: {e}")


def apply_theme_to_widget(widget, widget_type: str = 'auto') -> None:
    """
    Apply current theme colors to a widget based on its type.
    
    Args:
        widget: Any tkinter widget
        widget_type: One of 'pane', 'window', 'frame', 'label', 'labelframe',
                     'button', 'entry', 'menu', 'checkbox', 'scrollbar', 'auto'
                     If 'auto', attempts to detect widget type.
    """
    if widget_type == 'auto':
        # Attempt to detect widget type from class name
        class_name = widget.winfo_class()
        type_map = {
            'Text': 'pane',
            'Scrolledtext': 'pane',
            'Toplevel': 'window',
            'Frame': 'frame',
            'Label': 'label',
            'Labelframe': 'labelframe',
            'Button': 'button',
            'Entry': 'entry',
            'Menu': 'menu',
            'Checkbutton': 'checkbox',
            'Radiobutton': 'checkbox',
            'Scrollbar': 'scrollbar',
        }
        widget_type = type_map.get(class_name, 'frame')
    
    apply_funcs = {
        'pane': apply_theme_to_pane,
        'text': apply_theme_to_pane,
        'window': apply_theme_to_window,
        'frame': apply_theme_to_window,
        'toplevel': apply_theme_to_window,
        'label': apply_theme_to_label,
        'labelframe': apply_theme_to_labelframe,
        'button': apply_theme_to_button,
        'entry': apply_theme_to_entry,
        'menu': apply_theme_to_menu,
        'checkbox': apply_theme_to_checkbox,
        'radiobutton': apply_theme_to_checkbox,
        'scrollbar': apply_theme_to_scrollbar,
    }
    
    func = apply_funcs.get(widget_type)
    if func:
        func(widget)
    else:
        # Fallback: try to set bg
        try:
            widget.config(bg=get_color('window_bg'))
        except Exception:
            pass


def configure_ttk_styles(style=None) -> None:
    """
    Configure ttk Style for current theme.
    
    This updates ttk widget styles (Treeview, Combobox, etc.) to match
    the current theme.
    
    Args:
        style: A ttk.Style instance. If None, creates one.
    """
    try:
        import tkinter.ttk as ttk
        if style is None:
            style = ttk.Style()
        
        # Use clam theme as base for dark themes (better color support)
        if is_dark_theme():
            try:
                style.theme_use('clam')
            except Exception:
                pass
        
        # Configure Treeview
        style.configure(
            'Treeview',
            background=get_color('pane_bg'),
            fieldbackground=get_color('pane_bg'),
            foreground=get_color('pane_fg'),
            rowheight=18
        )
        style.map(
            'Treeview',
            background=[('selected', get_color('select_bg'))],
            foreground=[('selected', get_color('menu_active_fg'))]
        )
        
        # Pane.Treeview variant
        style.configure(
            'Pane.Treeview',
            background=get_color('pane_bg'),
            fieldbackground=get_color('pane_bg'),
            foreground=get_color('pane_fg'),
            rowheight=18
        )
        style.map(
            'Pane.Treeview',
            background=[('selected', get_color('select_bg'))],
            foreground=[('selected', get_color('menu_active_fg'))]
        )
        
        # Treeview Heading
        style.configure(
            'Treeview.Heading',
            background=get_color('button_bg'),
            foreground=get_color('button_fg')
        )
        
        # Combobox
        style.configure(
            'TCombobox',
            fieldbackground=get_color('entry_bg'),
            background=get_color('button_bg'),
            foreground=get_color('entry_fg')
        )
        style.map(
            'TCombobox',
            fieldbackground=[('readonly', get_color('entry_bg')), ('focus', get_color('entry_bg'))],
            foreground=[('readonly', get_color('entry_fg')), ('focus', get_color('entry_fg'))]
        )
        
        # Pane.TCombobox variant
        style.configure(
            'Pane.TCombobox',
            fieldbackground=get_color('pane_bg'),
            background=get_color('pane_bg'),
            foreground=get_color('pane_fg')
        )
        style.map(
            'Pane.TCombobox',
            fieldbackground=[('readonly', get_color('pane_bg')), ('focus', get_color('pane_bg'))],
            foreground=[('readonly', get_color('pane_fg')), ('focus', get_color('pane_fg'))]
        )
        
        # TButton
        style.configure(
            'TButton',
            background=get_color('button_bg'),
            foreground=get_color('button_fg')
        )
        style.map(
            'TButton',
            background=[('active', get_color('button_active_bg'))]
        )
        
        # TEntry
        style.configure(
            'TEntry',
            fieldbackground=get_color('entry_bg'),
            foreground=get_color('entry_fg')
        )
        
        # TLabel
        style.configure(
            'TLabel',
            background=get_color('label_bg'),
            foreground=get_color('label_fg')
        )
        
        # TFrame
        style.configure(
            'TFrame',
            background=get_color('window_bg')
        )
        
        # TLabelframe
        style.configure(
            'TLabelframe',
            background=get_color('labelframe_bg')
        )
        style.configure(
            'TLabelframe.Label',
            background=get_color('labelframe_bg'),
            foreground=get_color('labelframe_fg')
        )
        
    except Exception as e:
        logger.debug(f"Could not configure ttk styles: {e}")


def configure_root_options(root) -> None:
    """
    Configure root window option database for theme colors.
    
    This sets default colors for tk widgets that read from the option database.
    
    Args:
        root: The root Tk window
    """
    try:
        # Listbox (for Combobox dropdowns)
        root.option_add('*Listbox.background', get_color('pane_bg'))
        root.option_add('*Listbox.foreground', get_color('pane_fg'))
        root.option_add('*Listbox.selectBackground', get_color('select_bg'))
        
        # Button
        root.option_add('*Button.background', get_color('button_bg'))
        root.option_add('*Button.foreground', get_color('button_fg'))
        root.option_add('*Button.activeBackground', get_color('button_active_bg'))
        root.option_add('*Button.activeForeground', get_color('button_active_fg'))
        root.option_add('*Button.highlightBackground', get_color('window_bg'))
        
        # Menu
        root.option_add('*Menu.background', get_color('menu_bg'))
        root.option_add('*Menu.foreground', get_color('menu_fg'))
        root.option_add('*Menu.activeBackground', get_color('menu_active_bg'))
        root.option_add('*Menu.activeForeground', get_color('menu_active_fg'))
        
        # Label
        root.option_add('*Label.background', get_color('label_bg'))
        root.option_add('*Label.foreground', get_color('label_fg'))
        
        # Frame
        root.option_add('*Frame.background', get_color('window_bg'))
        
        # Entry
        root.option_add('*Entry.background', get_color('entry_bg'))
        root.option_add('*Entry.foreground', get_color('entry_fg'))
        
        # Checkbutton
        root.option_add('*Checkbutton.background', get_color('checkbox_bg'))
        root.option_add('*Checkbutton.foreground', get_color('checkbox_fg'))
        root.option_add('*Checkbutton.selectColor', get_color('checkbox_select'))
        
    except Exception as e:
        logger.debug(f"Could not configure root options: {e}")


# =============================================================================
# Legacy Alias Functions (for backward compatibility)
# =============================================================================

def style_pane(widget) -> None:
    """Alias for apply_theme_to_pane for backward compatibility."""
    apply_theme_to_pane(widget)


def is_dark_mode_active() -> bool:
    """
    Check if dark mode is currently active.
    
    Now uses the theme system instead of ttk Style lookup.
    
    Returns:
        bool: True if current theme is a dark theme
    """
    return is_dark_theme()


def apply_dark_mode_to_widget(widget, widget_type='generic'):
    """
    Apply dark mode styling to a widget if dark mode is active.
    
    This function is kept for backward compatibility.
    For new code, use apply_theme_to_widget().
    
    Args:
        widget: The tkinter widget to style
        widget_type: Type of widget - 'button', 'label', 'frame', 'text', 'checkbox', 'generic'
    """
    if not is_dark_theme():
        return
    
    type_map = {
        'button': 'button',
        'label': 'label',
        'frame': 'frame',
        'text': 'pane',
        'checkbox': 'checkbox',
        'toplevel': 'window',
        'generic': 'frame',
    }
    apply_theme_to_widget(widget, type_map.get(widget_type, 'frame'))


def style_dialog_for_dark_mode(dialog, labels=None, frames=None, buttons=None, 
                                text_widgets=None, checkboxes=None):
    """
    Apply dark mode styling to an entire dialog and its widgets.
    
    This function is kept for backward compatibility.
    
    Args:
        dialog: The Toplevel dialog window
        labels: List of Label widgets
        frames: List of Frame widgets
        buttons: List of Button widgets
        text_widgets: List of Text/ScrolledText widgets
        checkboxes: List of Checkbutton widgets
    """
    if not is_dark_theme():
        return
    
    apply_theme_to_window(dialog)
    
    if labels:
        for label in labels:
            apply_theme_to_label(label)
    
    if frames:
        for frame in frames:
            apply_theme_to_window(frame)
    
    if buttons:
        for button in buttons:
            apply_theme_to_button(button)
    
    if text_widgets:
        for text_widget in text_widgets:
            apply_theme_to_pane(text_widget)
    
    if checkboxes:
        for checkbox in checkboxes:
            apply_theme_to_checkbox(checkbox)


def set_panes_dark(*panes) -> None:
    """
    Legacy function: Set panes to dark mode.
    
    Now sets theme to 'pure_black' and applies to given panes.
    """
    set_theme('pure_black', save=False)
    for pane in panes:
        apply_theme_to_pane(pane)


def set_panes_light(*panes) -> None:
    """
    Legacy function: Set panes to light mode.
    
    Now sets theme to 'system_light' and applies to given panes.
    """
    set_theme('system_light', save=False)
    for pane in panes:
        apply_theme_to_pane(pane)
