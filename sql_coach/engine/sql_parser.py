"""SQL parser using sqlparse."""
import re
from typing import List

import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Where, Comparison
from sqlparse.tokens import Keyword, DML

from ..models import SQLInfo


def _extract_tables(stmt) -> List[str]:
    """Extract table names from a parsed statement."""
    tables = []
    from_seen = False
    join_seen = False
    update_seen = False
    for token in stmt.tokens:
        if token.is_keyword:
            if token.normalized.upper() == "FROM":
                from_seen = True
                continue
            elif token.normalized.upper() in ("JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN"):
                join_seen = True
                continue
            elif token.normalized.upper() == "INTO":
                # INSERT INTO <table>
                from_seen = True
                continue
            elif token.normalized.upper() in ("WHERE", "GROUP", "ORDER", "LIMIT", "SET"):
                from_seen = False
                join_seen = False
                update_seen = False
                continue

        # UPDATE <table> — UPDATE is a DML token, not a keyword
        if token.ttype is DML and token.normalized.upper() == "UPDATE":
            update_seen = True
            continue

        if from_seen or join_seen or update_seen:
            if isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    name = _get_table_name(identifier)
                    if name:
                        tables.append(name)
            elif isinstance(token, Identifier):
                name = _get_table_name(token)
                if name:
                    tables.append(name)
            elif token.ttype is not None and not token.is_whitespace:
                from_seen = False
                join_seen = False
                update_seen = False
    return tables


def _get_table_name(identifier) -> str:
    """Get the actual table name from an identifier (strip alias)."""
    if isinstance(identifier, Identifier):
        return identifier.get_real_name()
    return str(identifier).strip()


def _extract_columns(stmt) -> List[str]:
    """Extract column names from SELECT clause."""
    columns = []
    select_seen = False
    for token in stmt.tokens:
        if token.ttype is DML and token.normalized.upper() == "SELECT":
            select_seen = True
            continue
        if select_seen:
            if token.is_keyword and token.normalized.upper() == "FROM":
                break
            if isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    columns.append(str(identifier).strip())
            elif isinstance(token, Identifier):
                columns.append(str(token).strip())
            elif token.ttype is not None and not token.is_whitespace:
                columns.append(str(token).strip())
    return columns


def _extract_where_conditions(stmt) -> List[str]:
    """Extract WHERE conditions."""
    conditions = []
    for token in stmt.tokens:
        if isinstance(token, Where):
            where_text = str(token)
            # Remove "WHERE" prefix
            cleaned = re.sub(r"^WHERE\s+", "", where_text, flags=re.IGNORECASE)
            # Split by AND/OR
            parts = re.split(r"\s+(?:AND|OR)\s+", cleaned, flags=re.IGNORECASE)
            conditions = [p.strip() for p in parts if p.strip()]
            break
    return conditions


def _extract_order_by(stmt) -> List[str]:
    """Extract ORDER BY columns."""
    order_by = []
    sql_str = str(stmt)
    match = re.search(r"ORDER\s+BY\s+(.+?)(?:LIMIT|GROUP|HAVING|$)",
                      sql_str, re.IGNORECASE | re.DOTALL)
    if match:
        cols = match.group(1).strip().rstrip(";")
        order_by = [c.strip() for c in cols.split(",")]
    return order_by


def _get_sql_type(stmt) -> str:
    """Determine SQL type (SELECT/UPDATE/DELETE/INSERT)."""
    for token in stmt.tokens:
        if token.ttype is DML:
            return token.normalized.upper()
    return "UNKNOWN"


def parse(sql: str) -> SQLInfo:
    """Parse a SQL string and extract structured info."""
    sql = sql.strip().rstrip(";")
    parsed = sqlparse.parse(sql)
    if not parsed:
        return SQLInfo(
            raw_sql=sql, sql_type="UNKNOWN",
            tables=[], columns=[], where_conditions=[],
            join_tables=[], order_by=[],
        )

    stmt = parsed[0]
    sql_type = _get_sql_type(stmt)
    tables = _extract_tables(stmt)
    columns = _extract_columns(stmt) if sql_type == "SELECT" else []
    where_conditions = _extract_where_conditions(stmt)
    order_by = _extract_order_by(stmt)

    # Identify join tables (all tables except the first one if FROM+JOIN)
    join_tables = tables[1:] if len(tables) > 1 else []
    main_tables = tables[:1] if tables else []

    return SQLInfo(
        raw_sql=sql,
        sql_type=sql_type,
        tables=tables,
        columns=columns,
        where_conditions=where_conditions,
        join_tables=join_tables,
        order_by=order_by,
    )
