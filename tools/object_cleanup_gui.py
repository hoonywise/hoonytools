"""Backward-compatible wrapper: expose object cleanup functions.

This module re-exports `drop_user_tables` and `delete_dwh_rows` from the
original `table_cleanup_gui` implementation so callers can import
`tools.object_cleanup_gui` while the main implementation remains in
`tools/table_cleanup_gui.py`.
"""
from .table_cleanup_gui import drop_user_tables, delete_dwh_rows

__all__ = ["drop_user_tables", "delete_dwh_rows"]
