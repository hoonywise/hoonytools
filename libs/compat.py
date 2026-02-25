"""
Cross-platform widget compatibility layer.

On macOS, tkinter.Button ignores bg/fg configuration due to the Aqua backend.
tkmacosx.Button is a Canvas-based drop-in replacement that respects colors.

Usage:
    from libs.compat import Button
    btn = Button(parent, text="OK", bg="#0078d4", fg="#ffffff")

On Windows/Linux this re-exports the standard tkinter.Button unchanged.
"""

import sys
import tkinter as tk

if sys.platform == "darwin":
    try:
        from tkmacosx import Button
    except ImportError:
        # tkmacosx not installed -- fall back to standard (colors won't apply)
        Button = tk.Button
else:
    Button = tk.Button
