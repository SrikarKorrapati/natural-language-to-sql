"""Bounded, read-only column inspection for model-requested tools.

Only identifiers are accepted, never SQL. Counts describe a single SQLite read
snapshot; displayed values are bounded and carry explicit truncation metadata.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
import math
import sqlite3
import time

from app.db import Database


MAX_VALUES = 20
MAX_TEXT_CHARACTERS = 256
MAX_BLOB_BYTES = 64
VALUE_GROUPING = (
    "SQLite equality and column collation; equal integer/real values share a group."
)


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or len(value) > 256:
        raise ValueError(f"{label} must be a nonempty identifier of at most 256 characters.")
    return '"' + value.replace('"', '""') + '"'


def _validate_arguments(table: str, column: str, limit: int) -> tuple[str, str]:
    quoted_table = _identifier(table, "table")
    quoted_column = _identifier(column, "column")
    if table.lower().startswith("sqlite_"):
        raise ValueError("Internal SQLite tables cannot be inspected.")
    if type(limit) is not int or not 1 <= limit <= MAX_VALUES:
        raise ValueError(f"limit must be an integer between 1 and {MAX_VALUES}.")
    return '"main".' + quoted_table, quoted_column


@contextmanager
def _inspection(database: Database, table: str, column: str, limit: int):
    quoted_table, quoted_column = _validate_arguments(table, column, limit)
    deadline = time.monotonic() + database.timeout_seconds
    with closing(database.connect()) as conn:
        conn.execute("PRAGMA query_only = ON")
        # The lock wait and all SQL statements share the operation's time budget.
        conn.execute(f"PRAGMA busy_timeout = {max(1, math.ceil(database.timeout_seconds * 1000))}")
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2_000_000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 50_000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        conn.execute("BEGIN")
        conn.set_authorizer(database.authorize)
        conn.set_progress_handler(lambda: time.monotonic() >= deadline, 1000)

        def query(sql, parameters=()):
            if time.monotonic() >= deadline:
                raise sqlite3.OperationalError("Column inspection timed out.")
            cursor = conn.execute(sql, parameters)
            if time.monotonic() >= deadline:
                raise sqlite3.OperationalError("Column inspection timed out.")
            return cursor

        exists = query(
            "SELECT 1 FROM main.sqlite_master WHERE name = ? COLLATE BINARY "
            "AND type IN ('table', 'view')", (table,),
        ).fetchone()
        if not exists:
            raise ValueError("Unknown table or view.")
        # Validate actual metadata before quoting a requested column: SQLite can
        # otherwise interpret an unknown double-quoted identifier as a literal.
        columns = query(f"SELECT * FROM {quoted_table} LIMIT 0").description
        if column not in {entry[0] for entry in columns}:
            raise ValueError("Unknown column in the requested table or view.")
        yield query, quoted_table, quoted_column


def _number(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "Infinity" if value > 0 else "-Infinity" if value < 0 else "NaN"
    return value


def _value(value, storage_type: str) -> dict:
    item = {"value": value, "storage_type": storage_type, "value_truncated": False}
    if isinstance(value, str):
        item.update(value=value[:MAX_TEXT_CHARACTERS], original_length=len(value))
        item["value_truncated"] = len(value) > MAX_TEXT_CHARACTERS
    elif isinstance(value, bytes):
        item.update(value=value[:MAX_BLOB_BYTES].hex(), encoding="hex", original_length=len(value))
        item["value_truncated"] = len(value) > MAX_BLOB_BYTES
    elif isinstance(value, float) and not math.isfinite(value):
        item.update(value=_number(value), encoding="nonfinite_number")
    return item


def _frequencies(query, table: str, column: str, limit: int) -> tuple[list[dict], bool]:
    # MIN with binary collation chooses a stable representative when the column
    # uses case-insensitive collation. Equal INTEGER/REAL values form one group;
    # choose INTEGER when both are present, consistent with COUNT(DISTINCT).
    rows = query(
        f"SELECT CASE WHEN MIN(typeof({column})) = 'integer' "
        f"THEN CAST(MIN({column} COLLATE BINARY) AS INTEGER) "
        f"ELSE MIN({column} COLLATE BINARY) END AS value, "
        f"COUNT(*) AS frequency, MIN(typeof({column})) AS storage_type "
        f"FROM {table} WHERE {column} IS NOT NULL GROUP BY {column} "
        "ORDER BY frequency DESC, storage_type, value COLLATE BINARY LIMIT ?",
        (limit + 1,),
    ).fetchall()
    values = [dict(_value(value, kind), count=count) for value, count, kind in rows[:limit]]
    return values, len(rows) > limit


def get_column_values(database: Database, table: str, column: str, limit: int = 10) -> dict:
    """Return frequent distinct non-NULL values, without arbitrary SQL execution."""
    with _inspection(database, table, column, limit) as (query, quoted_table, quoted_column):
        entries, truncated = _frequencies(query, quoted_table, quoted_column, limit)
    return {
        "table": table, "column": column, "limit": limit,
        "values": [{key: value for key, value in item.items() if key != "count"} for item in entries],
        "truncated": truncated, "value_grouping": VALUE_GROUPING,
    }


def get_column_profile(database: Database, table: str, column: str, limit: int = 10) -> dict:
    """Return exact counts and bounded frequencies, plus actual numeric statistics."""
    with _inspection(database, table, column, limit) as (query, quoted_table, quoted_column):
        row_count, present, distinct = query(
            f"SELECT COUNT(*), COUNT({quoted_column}), COUNT(DISTINCT {quoted_column}) "
            f"FROM {quoted_table}"
        ).fetchone()
        kinds = {kind: 0 for kind in ("null", "integer", "real", "text", "blob")}
        kinds.update(query(
            f"SELECT typeof({quoted_column}), COUNT(*) FROM {quoted_table} "
            f"GROUP BY typeof({quoted_column})"
        ).fetchall())
        count, minimum, maximum, average = query(
            f"SELECT COUNT(*), MIN({quoted_column}), MAX({quoted_column}), AVG({quoted_column}) "
            f"FROM {quoted_table} WHERE typeof({quoted_column}) IN ('integer', 'real')"
        ).fetchone()
        entries, truncated = _frequencies(query, quoted_table, quoted_column, limit)
    return {
        "table": table, "column": column, "limit": limit,
        "row_count": row_count, "null_count": row_count - present,
        "distinct_non_null_count": distinct, "storage_type_counts": kinds,
        "numeric": {
            "count": count, "min": _number(minimum), "max": _number(maximum),
            "avg": _number(average),
            "note": "Only INTEGER/REAL storage; infinities are strings, indeterminate averages are null.",
        },
        "value_counts": entries, "truncated": truncated, "value_grouping": VALUE_GROUPING,
    }
