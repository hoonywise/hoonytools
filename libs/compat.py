"""
Cross-platform widget compatibility layer.

On macOS, tkinter.Button ignores bg/fg configuration due to the Aqua backend.
tkmacosx.Button is a Canvas-based drop-in replacement that respects colors.

However, tkmacosx.Button interprets width/height as **pixels** while
tk.Button interprets them as **character units**.  This wrapper converts
character units to pixels so callers can use the same values on all platforms.

Usage:
    from libs.compat import Button
    btn = Button(parent, text="OK", bg="#0078d4", fg="#ffffff")

On Windows/Linux this re-exports the standard tkinter.Button unchanged.
"""

import sys
import tkinter as tk
import tkinter.font as tkfont

if sys.platform == "darwin":
    try:
        from tkmacosx import Button as _TkMacOSXButton
    except ImportError:
        # tkmacosx not installed -- fall back to standard (colors won't apply)
        Button = tk.Button
    else:

        def _resolve_font(font_spec):
            """Return a tkinter Font object from *font_spec*.

            *font_spec* may be a ``tkinter.font.Font`` instance, a font
            descriptor string (``"TkDefaultFont"``), a tuple
            (``("Helvetica", 12)``), or ``None`` (returns the default font).
            """
            if font_spec is None:
                return tkfont.nametofont("TkDefaultFont")
            if isinstance(font_spec, tkfont.Font):
                return font_spec
            # tuple or string descriptor -- wrap in Font so we can measure
            try:
                return tkfont.Font(font=font_spec)
            except Exception:
                return tkfont.nametofont("TkDefaultFont")

        class Button(_TkMacOSXButton):
            """tkmacosx.Button wrapper that accepts character-unit sizes.

            ``tkmacosx.Button`` treats *width* / *height* as pixels, while
            ``tk.Button`` treats them as character / line counts.  This
            subclass converts the tk convention to pixels so every caller
            gets the sizing it expects.
            """

            def __init__(self, master=None, cnf={}, **kw):
                # Default padding closer to tk.Button's visual spacing
                kw.setdefault("padx", 7)
                kw.setdefault("pady", 3)

                # Convert character-unit width / height to pixels
                if "width" in kw or "height" in kw:
                    font_obj = _resolve_font(kw.get("font"))
                    if "width" in kw:
                        char_px = font_obj.measure("0")
                        kw["width"] = int(
                            kw["width"] * char_px + 2 * kw["padx"]
                        )
                    if "height" in kw:
                        linespace = font_obj.metrics("linespace")
                        kw["height"] = int(
                            kw["height"] * linespace + 2 * kw["pady"]
                        )

                super().__init__(master, cnf, **kw)

else:
    Button = tk.Button
