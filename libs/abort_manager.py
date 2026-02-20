should_abort = False
created_tables = set()
current_connection = None
cleanup_done = False
prompt_event = None

import logging
import threading
import oracledb
from libs import session
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

def register_prompt_event(ev):
    """Register an Event that a background worker is waiting on for a
    main-thread prompt. This allows the launcher abort handler to set the
    Event so the worker wakes immediately. Pass None to clear the
    registration."""
    global prompt_event
    try:
        prompt_event = ev
    except Exception:
        prompt_event = None


def cancel_prompt_event():
    """If a prompt Event is registered, set it so any waiting worker will
    unblock, and clear the registration."""
    global prompt_event
    try:
        if prompt_event is not None:
            try:
                prompt_event.set()
            except Exception as e:
                logger.debug(f"Failed to set prompt event during cancel: {e}")
    finally:
        try:
            prompt_event = None
        except Exception:
            prompt_event = None

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
        try:
            logger.debug(f"cleanup_on_abort: created_tables={created_tables}")
        except Exception:
            pass

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
                # Downgrade DPY-1001 "not connected" to debug when it is
                # expected during an abort/cleanup or when seen on a
                # background/worker thread.
                if is_expected_disconnect(e):
                    logger.debug(f"Could not determine schema via cursor (expected during abort): {e}")
                else:
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
                        try:
                            # Remove from tracking so fallback does not retry already-dropped tables
                            created_tables.discard(table)
                        except Exception:
                            pass
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

        # If there are remaining created_tables that we couldn't drop because
        # the provided cursor/connection was unavailable, try a best-effort
        # fallback: open a fresh connection using saved session credentials
        # (prefer DWH creds when the tables appear to be in DWH) and drop
        # fully-qualified names. This helps when the worker's connection was
        # closed to interrupt DB calls and the original cursor is unusable.
        try:
            if created_tables:
                # Determine whether any created table looks like DWH.<TABLE>
                needs_dwh = any(isinstance(t, str) and t.upper().startswith('DWH.') for t in created_tables)
                creds = None
                # Prefer DWH credentials for DWH-targeted drops
                try:
                    if needs_dwh and getattr(session, 'dwh_credentials', None):
                        creds = session.dwh_credentials
                    elif getattr(session, 'user_credentials', None):
                        creds = session.user_credentials
                except Exception:
                    creds = None

                if creds:
                    try:
                        logger.debug(f"Attempting fallback cleanup connection to drop remaining tables: {created_tables}")
                        try:
                            # use oracledb directly to avoid UI prompts
                            fb_conn = oracledb.connect(user=creds.get('username'), password=creds.get('password'), dsn=creds.get('dsn'))
                        except Exception as e:
                            logger.debug(f"Could not open fallback connection for abort cleanup: {e}")
                            fb_conn = None
                        if fb_conn:
                            fb_cur = None
                            try:
                                fb_cur = fb_conn.cursor()
                                for table in list(created_tables):
                                    try:
                                        # table may already be fully-qualified (SCHEMA.TABLE)
                                        fb_cur.execute(f"DROP TABLE {table} PURGE")
                                        logger.info(f"🗑️ Dropped table from abort cleanup (fallback): {table}")
                                        try:
                                            created_tables.discard(table)
                                        except Exception:
                                            pass
                                    except Exception as e:
                                        if is_expected_disconnect(e):
                                            logger.debug(f"Could not drop {table} during fallback cleanup (expected): {e}")
                                        else:
                                            logger.warning(f"⚠️ Could not drop {table} during fallback cleanup: {e}")
                                try:
                                    fb_conn.commit()
                                except Exception:
                                    pass
                            finally:
                                try:
                                    if fb_cur:
                                        fb_cur.close()
                                except Exception:
                                    pass
                                try:
                                    fb_conn.close()
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"Fallback abort cleanup attempt failed: {e}")
        except Exception:
            pass
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
