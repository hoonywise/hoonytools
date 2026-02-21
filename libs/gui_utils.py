"""
Shared GUI utility functions for HoonyTools.

Provides theme management, widget styling, and common helpers.
"""

import configparser
import logging
import os
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Theme Constants
# =============================================================================

# Ordered list of theme keys (spectrum from darkest to lightest)
THEME_ORDER = [
    'pure_black',
    'midnight',
    'charcoal',
    'slate',
    'graphite',
    'silver',
    'system_light',
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
}

# Preset theme color definitions
# Keys: pane_bg, pane_fg, select_bg, insert_bg
PRESET_THEMES = {
    'pure_black': {
        'pane_bg': '#000000',
        'pane_fg': '#ffffff',
        'select_bg': '#333333',
        'insert_bg': '#ffffff',
    },
    'midnight': {
        'pane_bg': '#0d1117',
        'pane_fg': '#c9d1d9',
        'select_bg': '#264f78',
        'insert_bg': '#c9d1d9',
    },
    'charcoal': {
        'pane_bg': '#1e1e1e',
        'pane_fg': '#d4d4d4',
        'select_bg': '#264f78',
        'insert_bg': '#d4d4d4',
    },
    'slate': {
        'pane_bg': '#2d2d2d',
        'pane_fg': '#e0e0e0',
        'select_bg': '#3d5a80',
        'insert_bg': '#e0e0e0',
    },
    'graphite': {
        'pane_bg': '#3c3f41',
        'pane_fg': '#bbbbbb',
        'select_bg': '#4b6eaf',
        'insert_bg': '#bbbbbb',
    },
    'silver': {
        'pane_bg': '#f0f0f0',
        'pane_fg': '#1e1e1e',
        'select_bg': '#0078d4',
        'insert_bg': '#1e1e1e',
    },
    'system_light': {
        'pane_bg': 'SystemWindow',
        'pane_fg': 'SystemWindowText',
        'select_bg': 'SystemHighlight',
        'insert_bg': 'SystemWindowText',
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
        key: Color key ('pane_bg', 'pane_fg', 'select_bg', 'insert_bg')
    
    Returns:
        Color value (hex string or system color name)
    """
    theme = PRESET_THEMES.get(_current_theme, PRESET_THEMES['system_light'])
    return theme.get(key, '')


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
        theme_key: Theme key from THEME_ORDER
        save: Whether to persist to config.ini
    """
    global _current_theme
    
    if theme_key not in PRESET_THEMES:
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
        if theme_key in PRESET_THEMES:
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


# =============================================================================
# Widget Styling Functions
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


def style_pane(widget) -> None:
    """
    Alias for apply_theme_to_pane for backward compatibility.
    """
    apply_theme_to_pane(widget)


# =============================================================================
# Dark Mode Detection (Legacy - for backward compatibility)
# =============================================================================

def is_dark_mode_active() -> bool:
    """
    Check if dark mode is currently active.
    
    Now uses the theme system instead of ttk Style lookup.
    
    Returns:
        bool: True if current theme is a dark theme
    """
    return is_dark_theme()


# =============================================================================
# Legacy Widget Styling (for backward compatibility)
# =============================================================================

def apply_dark_mode_to_widget(widget, widget_type='generic'):
    """
    Apply dark mode styling to a widget if dark mode is active.
    
    This function is kept for backward compatibility.
    For new code, use apply_theme_to_pane() for text widgets.
    
    Args:
        widget: The tkinter widget to style
        widget_type: Type of widget - 'button', 'label', 'frame', 'text', 'checkbox', 'generic'
    """
    if not is_dark_mode_active():
        return
    
    try:
        if widget_type == 'button':
            widget.config(
                bg=DARK_BTN_BG,
                fg=DARK_FG,
                activebackground=DARK_BTN_ACTIVE_BG,
                activeforeground=DARK_FG
            )
        elif widget_type == 'label':
            widget.config(bg=DARK_BG, fg=DARK_FG)
        elif widget_type == 'frame':
            widget.config(bg=DARK_BG)
        elif widget_type == 'text':
            apply_theme_to_pane(widget)
        elif widget_type == 'checkbox':
            widget.config(
                bg=DARK_BG,
                fg=DARK_FG,
                activebackground=DARK_BG,
                activeforeground=DARK_FG,
                selectcolor=DARK_SELECT_BG
            )
        elif widget_type == 'toplevel':
            widget.config(bg=DARK_BG)
        else:
            # Generic - try common options
            try:
                widget.config(bg=DARK_BG)
            except Exception:
                pass
            try:
                widget.config(fg=DARK_FG)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Could not apply dark mode to widget: {e}")


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
    if not is_dark_mode_active():
        return
    
    # Style the dialog window itself
    apply_dark_mode_to_widget(dialog, 'toplevel')
    
    # Style labels
    if labels:
        for label in labels:
            apply_dark_mode_to_widget(label, 'label')
    
    # Style frames
    if frames:
        for frame in frames:
            apply_dark_mode_to_widget(frame, 'frame')
    
    # Style buttons
    if buttons:
        for button in buttons:
            apply_dark_mode_to_widget(button, 'button')
    
    # Style text widgets
    if text_widgets:
        for text_widget in text_widgets:
            apply_theme_to_pane(text_widget)
    
    # Style checkboxes
    if checkboxes:
        for checkbox in checkboxes:
            apply_dark_mode_to_widget(checkbox, 'checkbox')


# =============================================================================
# Convenience Functions for Pane Styling (Legacy wrappers)
# =============================================================================

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
