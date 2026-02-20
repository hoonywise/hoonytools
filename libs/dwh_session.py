"""Central DWH session management helpers.

Provide a small utility to close on-window DWH connections and clear
in-memory DWH credentials when they were not persisted to config.ini.
This lets UIs call a single cleanup method on window close so sessions
are not leaked and in-memory credentials do not persist unexpectedly.
"""
from configparser import ConfigParser
import logging
from libs import session
from libs.paths import PROJECT_PATH as BASE_PATH

logger = logging.getLogger(__name__)


def close_dwh_connection(root=None):
    """Close and remove a DWH connection stored on the given root window.

    If the calling code attached the DWH connection as `root._dwh_conn`,
    this will attempt to close it and remove the attribute.
    """
    try:
        if root is None:
            return
        # Support a single connection stored as _dwh_conn or multiple
        # connections registered in a list attribute _dwh_conns.
        conns = []
        single = getattr(root, '_dwh_conn', None)
        if single:
            conns.append(single)
        list_conns = getattr(root, '_dwh_conns', None)
        if list_conns:
            try:
                conns.extend(list(list_conns))
            except Exception:
                pass

        for c in conns:
            if not c:
                continue
            try:
                c.close()
            except Exception:
                logger.debug("Failed closing DWH connection", exc_info=True)

        # remove attributes to avoid accidental reuse
        try:
            if hasattr(root, '_dwh_conn'):
                delattr(root, '_dwh_conn')
        except Exception:
            logger.debug('Could not delete attribute _dwh_conn', exc_info=True)
        try:
            if hasattr(root, '_dwh_conns'):
                delattr(root, '_dwh_conns')
        except Exception:
            logger.debug('Could not delete attribute _dwh_conns', exc_info=True)
    except Exception:
        logger.exception("Error while closing DWH connection")


def clear_in_memory_dwh_if_not_saved():
    """Clear in-memory DWH credentials when there's no [dwh] section.

    This avoids automatic reuse of a DWH login that was never persisted
    to libs/config.ini. If the user saved credentials, we keep them.
    """
    try:
        cfg = ConfigParser()
        cfg.read(BASE_PATH / "libs" / "config.ini")
        if not cfg.has_section('dwh'):
            session.dwh_credentials = None
            session.stored_credentials = None
            logger.debug("Cleared in-memory DWH credentials (not saved to config.ini)")
    except Exception:
        logger.exception("Failed to clear in-memory DWH credentials")


def register_connection(root, conn):
    """Register a DWH connection object on a window/root for centralized cleanup.

    The connection will be closed when `cleanup(root)` is called. This avoids
    storing a single attribute and permits multiple registrations per window.
    """
    try:
        if root is None or conn is None:
            return
        lst = getattr(root, '_dwh_conns', None)
        if lst is None:
            try:
                setattr(root, '_dwh_conns', [conn])
            except Exception:
                # last-resort: attach single conn attr
                try:
                    setattr(root, '_dwh_conn', conn)
                except Exception:
                    logger.debug('Failed to register dwh connection on root', exc_info=True)
        else:
            try:
                lst.append(conn)
            except Exception:
                # try to replace attribute
                try:
                    setattr(root, '_dwh_conns', list(lst) + [conn])
                except Exception:
                    logger.debug('Failed to append dwh connection to root list', exc_info=True)
    except Exception:
        logger.exception('Error registering DWH connection')


def unregister_connection(root, conn):
    """Remove a previously registered connection from the window's registry."""
    try:
        if root is None or conn is None:
            return
        lst = getattr(root, '_dwh_conns', None)
        if lst:
            try:
                lst.remove(conn)
            except Exception:
                # rebuild without conn
                try:
                    setattr(root, '_dwh_conns', [c for c in list(lst) if c is not conn])
                except Exception:
                    pass
        else:
            # fallback to single attr
            single = getattr(root, '_dwh_conn', None)
            if single is conn:
                try:
                    delattr(root, '_dwh_conn')
                except Exception:
                    pass
    except Exception:
        logger.exception('Error unregistering DWH connection')


def cleanup(root=None):
    """Perform full DWH session cleanup for the given window/root."""
    close_dwh_connection(root)
    clear_in_memory_dwh_if_not_saved()
