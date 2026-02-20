should_abort = False
created_tables = set()
current_connection = None
cleanup_done = False

import logging
import threading
logger = logging.getLogger(__name__)


def is_expected_disconnect(exc: Exception) -> bool:
    """Return True when the exception is a driver "not connected" (DPY-1001)
    and the disconnect is expected (abort requested or cleanup already running
    or we're on a background thread). This centralizes the decision to
    downgrade DPY-1001 logs in abort/worker contexts.
    """
    try:
        txt = (str(exc) + " " + repr(exc)).lower()
    except Exception:
        txt = ''
    if 'dpy-1001' not in txt:
        return False
    # If an abort is in progress, cleanup has already run, or we're not on the
    # main thread (worker background), treat DPY-1001 as expected.
    if should_abort or cleanup_done or threading.current_thread() != threading.main_thread():
        return True
    return False

def set_abort(value=True):
    global should_abort
    should_abort = value

def reset():
    global should_abort, created_tables, cleanup_done, current_connection
    should_abort = False
    created_tables.clear()
    try:
        current_connection = None
    except Exception:
        pass

    # Allow cleanup to run again for a new workflow by clearing the flag.
    try:
        cleanup_done = False
    except Exception:
        pass

def register_created_table(table_name, schema=None):
    """Register a created table for later cleanup.

    If schema is provided, store as "SCHEMA.TABLE" (both uppercased) so
    cleanup can drop it even if the connection or cursor is unavailable.
    """
    try:
        if schema:
            created_tables.add(f"{schema.upper()}.{table_name.upper()}")
        else:
            created_tables.add(table_name.upper())
    except Exception:
        try:
            created_tables.add(str(table_name).upper())
        except Exception:
            pass

def register_connection(conn):
    """Register the currently active DB connection so external abort handlers
    can attempt to close it and interrupt blocking DB operations."""
    global current_connection
    try:
        current_connection = conn
    except Exception:
        current_connection = None

def close_registered_connection():
    """Best-effort close of the registered connection to interrupt DB calls.
    This is safe to call from another thread and will swallow errors.
    """
    global current_connection
    if not current_connection:
        return
    try:
        try:
            current_connection.close()
        except Exception as e:
            logger.debug(f"Failed to close registered connection: {e}")
    finally:
        try:
            current_connection = None
        except Exception:
            current_connection = None

def cleanup_on_abort(conn, cursor):
    global cleanup_done, current_connection

    # Idempotent: if cleanup has already been performed, return quickly.
    if getattr(globals(), 'cleanup_done', False) or cleanup_done:
        logger.debug("cleanup_on_abort called but cleanup already performed; returning")
        return

    try:
        logger.warning("⏹️ Aborting operation. Rolling back and cleaning up...")

        # Defensive rollback: connection may already be closed/unavailable
        if conn:
            try:
                conn.rollback()
            except Exception as e:
                logger.warning(f"⚠️ Could not rollback connection (may be closed): {e}")
        else:
            logger.warning("⚠️ cleanup_on_abort called without a connection object")

        schema = None
        # Attempt to determine current schema via cursor when possible
        if cursor:
            try:
                cursor.execute("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM dual")
                row = cursor.fetchone()
                if row:
                    schema = row[0]
            except Exception as e:
                logger.warning(f"⚠️ Could not determine schema via cursor: {e}")

        # Fallback to connection username if available
        if not schema and conn:
            try:
                schema = getattr(conn, 'username', None)
            except Exception as e:
                # When the connection is closed we may get DPY-1001 here; treat
                # that as expected during abort and log at debug level.
                if is_expected_disconnect(e):
                    logger.debug(f"Could not get username from connection (expected during abort): {e}")
                else:
                    logger.warning(f"Could not get username from connection: {e}")
                schema = None

        # Drop any created tables when we have enough context
        if created_tables and cursor:
            for table in list(created_tables):
                # If the table is already stored as SCHEMA.TABLE use it directly.
                try:
                    if '.' in table:
                        drop_name = table
                    else:
                        drop_name = f"{schema}.{table}" if schema else table
                    try:
                        cursor.execute(f'DROP TABLE {drop_name} PURGE')
                        logger.info(f"🗑️ Dropped table from abort cleanup: {drop_name}")
                    except Exception as e:
                        # DPY-1001 is expected when the connection/driver has been closed
                        if is_expected_disconnect(e):
                            logger.debug(f"Could not drop {drop_name} during abort cleanup (expected during abort): {e}")
                        else:
                            logger.warning(f"⚠️ Could not drop {drop_name} during abort cleanup: {e}")
                except Exception as e:
                    logger.warning(f"⚠️ Error while attempting to drop table {table}: {e}")
        else:
            if created_tables and not cursor:
                logger.debug("Skipping table drops: no cursor available during abort cleanup")
    finally:
        # Best-effort close and mark cleanup as done. Swallow errors so cleanup
        # remains safe when called multiple times.
        try:
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    if is_expected_disconnect(e):
                        logger.debug(f"Failed to close connection during abort cleanup (expected): {e}")
                    else:
                        logger.debug(f"Failed to close connection during abort cleanup: {e}")
        except Exception:
            pass

        # Clear created table tracking now that we've attempted drops; leave
        # should_abort state for the caller to inspect/reset. Mark cleanup_done
        # so subsequent calls return early.
        try:
            created_tables.clear()
        except Exception:
            pass

        cleanup_done = True
        try:
            # Do not change `should_abort` here — leave it so callers and
            # outer exception handlers can observe that an abort was requested.
            # We may clear the registered connection reference so other
            # threads know it is no longer available.
            global current_connection
            current_connection = None
        except Exception:
            pass
