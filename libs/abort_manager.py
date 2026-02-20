should_abort = False
created_tables = set()

import logging
logger = logging.getLogger(__name__)

def set_abort(value=True):
    global should_abort
    should_abort = value

def reset():
    global should_abort, created_tables
    should_abort = False
    created_tables.clear()

def register_created_table(table_name):
    created_tables.add(table_name.upper())

def cleanup_on_abort(conn, cursor):
    try:
        logger.warning("⏹️ Aborting operation. Rolling back and cleaning up...")
        conn.rollback()

        # Get current schema
        cursor.execute("SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') FROM dual")
        schema = cursor.fetchone()[0]

        try:
            for table in created_tables:
                try:
                    cursor.execute(f'DROP TABLE {schema}."{table}" PURGE')
                    logger.info(f"🗑️ Dropped table from abort cleanup: {schema}.{table}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not drop {table} during abort cleanup: {e}")
        except Exception as e:
            logger.error(f"❌ Failed during abort cleanup table iteration: {e}")

    finally:
        try:
            conn.close()
        except:
            pass
        # Clear abort state and created table tracking so caller/monitor can resume
        try:
            reset()
        except Exception:
            pass
