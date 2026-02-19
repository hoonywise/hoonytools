"""
Shared helpers for materialized view log detection and dependency inspection.

Functions:
 - detect_tables_from_sql(sql_text: str) -> list[str]
 - get_dependent_mviews(cursor, table: str) -> list[str]
 - detect_existing_mlog(cursor, table: str) -> dict

This module centralizes the conservative detection logic used by the SQL MV
loader and the Materialized View Manager. It prefers USER_* dictionary
views and falls back to ALL_* views when necessary. The functions are written
to be defensive against permission errors and missing dictionary objects.
"""
from typing import List, Dict, Any, Optional
import re
import logging

logger = logging.getLogger(__name__)


def detect_tables_from_sql(sql_text: str) -> List[str]:
    """Conservative table detector: finds tokens after FROM and JOIN.

    Returns a list of unique table identifiers (preserves order) in upper-case.
    This intentionally uses a simple heuristic rather than a full SQL parser.
    """
    if not sql_text:
        return []
    text = re.sub(r"\s+", " ", sql_text.replace('\n', ' ')).upper()
    candidates = []
    for m in re.finditer(r"(?:FROM|JOIN)\s+([A-Z0-9_\.]+)", text):
        tbl = m.group(1).strip().rstrip(',')
        candidates.append(tbl)
    seen = set()
    out = []
    for t in candidates:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def get_dependent_mviews(cursor, table: str) -> List[str]:
    """Return a list of dependent materialized view names for the given table.

    Strategy:
      1) Try ALL_DEPENDENCIES (cross-schema) if permitted
      2) Fallback to USER_DEPENDENCIES
      3) Fallback to a text search of USER_MVIEWS (heuristic)

    Returns list of strings like 'OWNER.MVIEW' or 'MVIEW'.
    """
    if not table:
        return []
    parts = table.split('.')
    if len(parts) == 2:
        owner = parts[0].upper()
        base = parts[1].upper()
    else:
        owner = None
        base = parts[-1].upper()

    deps: List[str] = []
    # Try ALL_DEPENDENCIES first
    try:
        if owner:
            cursor.execute(
                "SELECT OWNER, NAME FROM ALL_DEPENDENCIES "
                "WHERE REFERENCED_OWNER = :own AND REFERENCED_NAME = :tbl "
                "AND REFERENCED_TYPE = 'TABLE' AND TYPE = 'MATERIALIZED VIEW' ORDER BY OWNER, NAME",
                (owner, base),
            )
        else:
            cursor.execute("SELECT USER FROM DUAL")
            current_user = cursor.fetchone()[0]
            cursor.execute(
                "SELECT OWNER, NAME FROM ALL_DEPENDENCIES "
                "WHERE REFERENCED_OWNER = :own AND REFERENCED_NAME = :tbl "
                "AND REFERENCED_TYPE = 'TABLE' AND TYPE = 'MATERIALIZED VIEW' ORDER BY OWNER, NAME",
                (current_user, base),
            )
        rows = cursor.fetchall()
        if rows:
            deps = [f"{r[0]}.{r[1]}" for r in rows]
            return deps
    except Exception:
        deps = []

    # Fallback to USER_DEPENDENCIES
    try:
        cursor.execute(
            "SELECT NAME FROM USER_DEPENDENCIES "
            "WHERE REFERENCED_NAME = :tbl AND REFERENCED_TYPE = 'TABLE' AND TYPE = 'MATERIALIZED VIEW'",
            (base,),
        )
        rows = cursor.fetchall()
        if rows:
            deps = [r[0] for r in rows]
            return deps
    except Exception:
        deps = []

    # Last-resort heuristic: text-search USER_MVIEWS
    try:
        cursor.execute(
            "SELECT MVIEW_NAME FROM USER_MVIEWS WHERE UPPER(query) LIKE '%' || :tbl || '%'",
            (base,),
        )
        rows = cursor.fetchall()
        deps = [r[0] for r in rows]
    except Exception:
        deps = []

    return deps


def _get_current_user(cursor) -> Optional[str]:
    try:
        cursor.execute("SELECT USER FROM DUAL")
        return cursor.fetchone()[0]
    except Exception:
        return None


def detect_existing_mlog(cursor, table: str) -> Dict[str, Any]:
    """Detect whether a materialized view log exists for `table` and return metadata.

    Returns a dict with keys:
      - exists: bool
      - log_tables: list[str]
      - cols: list[str]
      - deps: list[str]
      - existing_type: 'PRIMARY KEY'|'ROWID'|'UNKNOWN'
      - pk_cols: list[str]
      - seq_present: bool
      - includes_new: bool

    The function is defensive: permission errors or unreadable dictionary
    objects will cause it to conservatively return exists=False with best-effort
    metadata filled where available.
    """
    result: Dict[str, Any] = {
        'exists': False,
        'log_tables': [],
        'cols': [],
        'deps': [],
        'existing_type': 'UNKNOWN',
        'pk_cols': [],
        'seq_present': False,
        'includes_new': False,
        # diagnostic counters to aid debugging when permissions/dictionary visibility is limited
        'diag': {
            'user_mview_logs_count': None,
            'all_mview_logs_count': None,
            'user_tables_mlog_count': None,
            'all_tables_mlog_count': None,
        },
    }
    if not table:
        return result
    master_name = table.split('.')[-1].upper()

    # Preliminary existence via USER_MVIEW_LOGS / ALL_MVIEW_LOGS (collect counts for diagnostics)
    reported_exists = False
    try:
        try:
            cursor.execute("SELECT COUNT(*) FROM USER_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
            user_cnt = cursor.fetchone()[0]
            result['diag']['user_mview_logs_count'] = user_cnt
            reported_exists = user_cnt > 0
        except Exception:
            result['diag']['user_mview_logs_count'] = None
            # fallback to ALL_MVIEW_LOGS
            try:
                if '.' in table:
                    owner_part = table.split('.')[0].upper()
                    cursor.execute(
                        "SELECT COUNT(*) FROM ALL_MVIEW_LOGS WHERE MASTER = :m AND OWNER = :own",
                        (master_name, owner_part),
                    )
                else:
                    cursor.execute("SELECT COUNT(*) FROM ALL_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                all_cnt = cursor.fetchone()[0]
                result['diag']['all_mview_logs_count'] = all_cnt
                reported_exists = all_cnt > 0
            except Exception:
                result['diag']['all_mview_logs_count'] = None
                reported_exists = False
    except Exception:
        reported_exists = False

    # Try to collect reported LOG_TABLE names (only if USER/ALL_MVIEW_LOGS reported existence)
    log_tables: List[str] = []
    if reported_exists:
        try:
            cursor.execute("SELECT LOG_TABLE FROM USER_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
            rows = cursor.fetchall()
            log_tables = [r[0] for r in rows if r and r[0]]
        except Exception:
            log_tables = []
        if not log_tables:
            try:
                if '.' in table:
                    owner_part = table.split('.')[0].upper()
                    cursor.execute("SELECT LOG_TABLE FROM ALL_MVIEW_LOGS WHERE MASTER = :m AND OWNER = :own", (master_name, owner_part))
                else:
                    cursor.execute("SELECT LOG_TABLE FROM ALL_MVIEW_LOGS WHERE MASTER = :m", (master_name,))
                rows = cursor.fetchall()
                log_tables = [r[0] for r in rows if r and r[0]]
            except Exception:
                log_tables = []

    # If no reported log_tables, check for physical MLOG$_<master> presence (record counts for diagnostics)
    physical_found = False
    try:
        if not log_tables:
            mlog_name = f"MLOG$_{master_name}"
            try:
                cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :tn", (mlog_name,))
                user_tbl_cnt = cursor.fetchone()[0]
                result['diag']['user_tables_mlog_count'] = user_tbl_cnt
            except Exception:
                result['diag']['user_tables_mlog_count'] = None
                user_tbl_cnt = 0

            if user_tbl_cnt == 0:
                # Only consider ALL_TABLES when the master was schema-qualified. This avoids
                # treating an MLOG owned by another schema as 'existing' for the current user
                # when the master name was unqualified.
                if '.' in table:
                    try:
                        owner_part = table.split('.')[0].upper()
                        cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :own AND TABLE_NAME = :tn", (owner_part, mlog_name))
                        all_tbl_cnt = cursor.fetchone()[0]
                        result['diag']['all_tables_mlog_count'] = all_tbl_cnt
                    except Exception:
                        result['diag']['all_tables_mlog_count'] = None
                        all_tbl_cnt = 0
                else:
                    # do not accept ALL_TABLES hits for unqualified masters; treat as not present
                    result['diag']['all_tables_mlog_count'] = 0
                    all_tbl_cnt = 0
            else:
                all_tbl_cnt = user_tbl_cnt

            if (user_tbl_cnt or all_tbl_cnt) and (user_tbl_cnt + all_tbl_cnt) > 0:
                log_tables = [mlog_name]
                physical_found = True
    except Exception:
        # permission or other issues -> be conservative
        physical_found = False

    # If we have candidate log table names, try to verify at least one exists
    verified = []
    if log_tables:
        for lt in log_tables:
            if not lt:
                continue
            lt_str = str(lt).upper()
            if lt_str.endswith(f"MLOG$_{master_name}") or lt_str == f"MLOG$_{master_name}":
                # verify existence
                try:
                    if '.' in lt_str:
                        owner_lt, name_lt = lt_str.split('.', 1)
                        cursor.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = :own AND TABLE_NAME = :tn", (owner_lt.upper(), name_lt.upper()))
                        cnt = cursor.fetchone()[0]
                    else:
                        # For unqualified log table names, only consider USER_TABLES. Avoid
                        # counting ALL_TABLES matches owned by other schemas as 'verified'.
                        cursor.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :tn", (lt_str,))
                        cnt = cursor.fetchone()[0]
                except Exception:
                    cnt = 0
                if cnt > 0:
                    verified.append(lt_str)

    # Decide final existence: require either a verified log table or a discovered physical MLOG
    final_exists = False
    if verified:
        log_tables = verified
        final_exists = True
    elif physical_found:
        final_exists = True
    else:
        # If only a reported_exists (from USER/ALL_MVIEW_LOGS) was present but no verification
        # treat it as stale/not present to avoid false positives caused by dictionary visibility gaps
        final_exists = False

    result['exists'] = bool(final_exists)
    result['log_tables'] = log_tables

    # If exists, attempt to read columns and dependent mviews
    if result['exists']:
        try:
            mlog_name = log_tables[0] if log_tables else f"MLOG$_{master_name}"
            # If qualified name was returned, take last part for USER_TAB_COLUMNS lookup
            lookup_name = mlog_name.split('.')[-1].upper()
            cursor.execute("SELECT COLUMN_NAME FROM USER_TAB_COLUMNS WHERE TABLE_NAME = :tn ORDER BY COLUMN_ID", (lookup_name,))
            cols = [r[0] for r in cursor.fetchall()]
            # If no cols found, try ALL_TAB_COLUMNS using owner if present
            if not cols and '.' in mlog_name:
                owner_lt, name_lt = mlog_name.split('.', 1)
                cursor.execute("SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS WHERE OWNER = :own AND TABLE_NAME = :tn ORDER BY COLUMN_ID", (owner_lt.upper(), name_lt.upper()))
                cols = [r[0] for r in cursor.fetchall()]
            result['cols'] = cols
        except Exception:
            result['cols'] = []

        try:
            result['deps'] = get_dependent_mviews(cursor, table)
        except Exception:
            result['deps'] = []

        # infer existing type by checking for PK cols on master and column names
        try:
            pk_cols = []
            try:
                cursor.execute(
                    "SELECT ucc.column_name FROM user_constraints uc JOIN user_cons_columns ucc ON uc.constraint_name = ucc.constraint_name WHERE uc.table_name = :tn AND uc.constraint_type = 'P'",
                    (master_name,)
                )
                pk_cols = [r[0] for r in cursor.fetchall()]
            except Exception:
                pk_cols = []
            result['pk_cols'] = pk_cols
            cols_upper = [c.upper() for c in result.get('cols', [])]
            if any(c.upper() in [pc.upper() for pc in pk_cols] for c in cols_upper if c):
                result['existing_type'] = 'PRIMARY KEY'
            elif any('ROW' in c or 'M_ROW' in c or 'ROWID' in c for c in cols_upper):
                result['existing_type'] = 'ROWID'
            else:
                result['existing_type'] = 'UNKNOWN'
        except Exception:
            result['existing_type'] = 'UNKNOWN'

        # sequence presence and new values heuristic
        try:
            cols_upper = [c.upper() for c in result.get('cols', [])]
            result['seq_present'] = any('SEQ' in c or 'SNAPTIME' in c for c in cols_upper)
            result['includes_new'] = any('OLD_NEW' in c or 'NEW' in c for c in cols_upper)
        except Exception:
            result['seq_present'] = False
            result['includes_new'] = False

    try:
        logger.debug("detect_existing_mlog result for %s: %s", master_name, result)
    except Exception:
        # ensure logging problems don't break consumer
        pass
    return result
