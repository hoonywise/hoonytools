"""
Shared GUI utility functions for HoonyTools.

Provides common helpers for dark mode detection, widget styling, etc.
"""

import logging

logger = logging.getLogger(__name__)

# =============================================================================
# Dark Mode Constants
# =============================================================================

DARK_BG = '#000000'
DARK_FG = '#ffffff'
DARK_BTN_BG = '#000000'
DARK_BTN_ACTIVE_BG = '#222222'
DARK_SELECT_BG = '#333333'
DARK_INSERT_BG = '#ffffff'  # Cursor color in text widgets

LIGHT_BG = 'SystemButtonFace'
LIGHT_FG = 'black'


# =============================================================================
# Dark Mode Detection
# =============================================================================

def is_dark_mode_active():
    """
    Detect if dark mode is currently active by checking ttk Style.
    
    Returns:
        bool: True if dark mode is active, False otherwise
    """
    try:
        import tkinter.ttk as ttk
        st = ttk.Style()
        # Check the Pane.Treeview style first (used by HoonyTools), fallback to Treeview
        bg = st.lookup('Pane.Treeview', 'background') or st.lookup('Treeview', 'background')
        if isinstance(bg, str) and bg.strip().lower() in ('#000000', '#000', 'black'):
            return True
    except Exception:
        pass
    return False


# =============================================================================
# Widget Styling Helpers
# =============================================================================

def apply_dark_mode_to_widget(widget, widget_type='generic'):
    """
    Apply dark mode styling to a widget if dark mode is active.
    
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
            widget.config(
                bg=DARK_BG,
                fg=DARK_FG,
                insertbackground=DARK_INSERT_BG
            )
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
            apply_dark_mode_to_widget(text_widget, 'text')
    
    # Style checkboxes
    if checkboxes:
        for checkbox in checkboxes:
            apply_dark_mode_to_widget(checkbox, 'checkbox')
