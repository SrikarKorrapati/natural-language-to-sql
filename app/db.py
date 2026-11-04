"""SQLite source access and a separate, small conversation journal."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from uuid import uuid4


class Database:
    def __init__(self, path: Path, max_rows: int = 500, timeout_seconds: float = 3):
        self.path = Path(path).resolve()
        self.max_rows = max_rows
        self.timeout_seconds = timeout_seconds

    def connect(self):
        return sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=3)

    def schema(self) -> list[dict]:
        with closing(self.connect()) as conn:
            tables = conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            return [{"name": name, "sql": sql} for name, sql in tables]

    @staticmethod
    def authorize(action, arg1, arg2, database, trigger):
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            sqlite3.SQLITE_RECURSIVE,
        }
        if action not in allowed:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in {
            "load_extension",
            "readfile",
            "writefile",
            "eval",
            "randomblob",
            "zeroblob",
        }:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def _run(self, sql: str, validate: bool = False) -> dict:
        started = time.perf_counter()
        with closing(self.connect()) as conn:
            conn.execute("PRAGMA query_only = ON")
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2_000_000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 50_000)
            conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
            conn.set_authorizer(self.authorize)
            conn.set_progress_handler(
                lambda: time.perf_counter() - started > self.timeout_seconds, 1000
            )
            cursor = conn.execute(("EXPLAIN " if validate else "") + sql)
            if validate:
                return {}
            rows = cursor.fetchmany(self.max_rows + 1)
            return {
                "columns": [column[0] for column in cursor.description],
                "rows": [list(row) for row in rows[: self.max_rows]],
                "row_count": min(len(rows), self.max_rows),
                "truncated": len(rows) > self.max_rows,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            }

    def validate(self, sql: str) -> None:
        self._run(sql, validate=True)

    def execute(self, sql: str) -> dict:
        return self._run(sql)


class History:
    def __init__(self, path: Path, dataset: str):
        self.path, self.dataset = Path(path), dataset
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queries (
                    id TEXT PRIMARY KEY,
                    dataset TEXT,
                    session_id TEXT,
                    question TEXT,
                    sql TEXT,
                    model TEXT,
                    status TEXT,
                    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
            """)

    def _read(self, where: str, params: tuple, limit: int = 200) -> list[dict]:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM queries WHERE dataset = ? AND {where} "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (self.dataset, *params, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def recent(self, session_id: str, limit: int = 6) -> list[dict]:
        return list(
            reversed(
                self._read(
                    "session_id = ? AND status = 'success'", (session_id,), limit
                )
            )
        )

    def successful(self, limit: int = 200) -> list[dict]:
        return self._read("status = 'success'", (), limit)

    def save(self, session_id: str, question: str, model: str, sql: str) -> None:
        """Remember only SQL that the user approved and successfully executed."""
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute(
                """
                INSERT INTO queries (id, dataset, session_id, question, sql, model, status)
                VALUES (?, ?, ?, ?, ?, ?, 'success')
                """,
                (str(uuid4()), self.dataset, session_id, question, sql, model),
            )
