def safe_messagebox(fn_name: str, *args, dlg=None, parent=None):
    """Call tkinter.messagebox.<fn_name> with safe parenting and fallbacks.

    Preference order: dlg -> parent -> unparented. Returns conservative
    defaults for ask* dialogs on failure.
    """
    try:
        from tkinter import messagebox as _messagebox
    except Exception:
        _messagebox = None

    def _call(p):
        if _messagebox is None:
            return None
        try:
            if p is not None:
                return getattr(_messagebox, fn_name)(*args, parent=p)
            return getattr(_messagebox, fn_name)(*args)
        except Exception:
            return None

    for p in (dlg, parent, None):
        try:
            res = _call(p)
            if res is not None:
                return res
        except Exception:
            pass

    if fn_name.startswith('ask'):
        return False
    return None
