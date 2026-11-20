"""Real SQLite tests for bounded, read-only model inspection tools."""

import hashlib
import json
import math
import sqlite3
import time

import pytest

from app.db import Database
from app.inspection import get_column_profile, get_column_values


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as conn:
        conn.executescript('''
            CREATE TABLE shipments (id INTEGER PRIMARY KEY, status TEXT, amount);
            INSERT INTO shipments (status, amount) VALUES
                ('pending', 10), ('in_transit', 15.5), ('delivered', 20),
                ('delivered', NULL), (NULL, '25');
            CREATE VIEW shipment_status AS SELECT status AS state FROM shipments;
            CREATE TABLE empty (value);
            CREATE TABLE nulls (value);
            INSERT INTO nulls VALUES (NULL), (NULL);
            CREATE TABLE "odd""table" ("odd""column" TEXT);
            INSERT INTO "odd""table" VALUES ('quoted');
            CREATE TABLE case_insensitive (value TEXT COLLATE NOCASE);
            INSERT INTO case_insensitive VALUES ('north'), ('North');
        ''')
    return Database(path)


def test_profile_counts_nulls_and_actual_numeric_storage(database):
    status = get_column_profile(database, "shipments", "status")
    assert status["row_count"] == 5
    assert status["null_count"] == 1
    assert status["distinct_non_null_count"] == 3
    assert status["storage_type_counts"] == {
        "null": 1, "integer": 0, "real": 0, "text": 4, "blob": 0,
    }
    assert [(item["value"], item["count"]) for item in status["value_counts"]] == [
        ("delivered", 2), ("in_transit", 1), ("pending", 1),
    ]
    assert status["numeric"]["count"] == 0
    assert status["numeric"]["min"] is status["numeric"]["max"] is status["numeric"]["avg"] is None
    amount = get_column_profile(database, "shipments", "amount")
    assert amount["numeric"]["count"] == 3  # Text '25' must not be treated as numeric.
    assert amount["numeric"]["min"] == 10
    assert amount["numeric"]["max"] == 20
    assert amount["numeric"]["avg"] == pytest.approx(45.5 / 3)


def test_values_are_distinct_frequent_non_null_and_report_truncation(database):
    result = get_column_values(database, "shipments", "status", limit=2)
    assert [entry["value"] for entry in result["values"]] == ["delivered", "in_transit"]
    assert result["truncated"] is True
    assert all(entry["storage_type"] == "text" for entry in result["values"])
    assert all(entry["value_truncated"] is False for entry in result["values"])
    assert get_column_values(database, "shipments", "status", limit=3)["truncated"] is False
    assert get_column_profile(database, "shipments", "status", limit=1)["distinct_non_null_count"] == 3


@pytest.mark.parametrize("table, rows", [("empty", 0), ("nulls", 2)])
def test_empty_and_all_null_columns(database, table, rows):
    profile = get_column_profile(database, table, "value")
    assert profile["row_count"] == profile["null_count"] == rows
    assert profile["distinct_non_null_count"] == profile["numeric"]["count"] == 0
    assert profile["value_counts"] == []
    assert profile["truncated"] is False
    assert get_column_values(database, table, "value")["values"] == []


def test_views_quoted_identifiers_and_column_collation(database):
    assert get_column_profile(database, "shipment_status", "state")["row_count"] == 5
    assert get_column_values(database, 'odd"table', 'odd"column')["values"][0]["value"] == "quoted"
    profile = get_column_profile(database, "case_insensitive", "value")
    assert profile["distinct_non_null_count"] == 1
    assert profile["value_counts"][0]["value"] == "North"
    assert profile["value_counts"][0]["count"] == 2


@pytest.mark.parametrize("function", [get_column_values, get_column_profile])
@pytest.mark.parametrize("table,column", [
    ("shipments", "not_a_column"), ("not_a_table", "status"),
    ("sqlite_master", "name"), ("SQLITE_SCHEMA", "name"),
    ("shipments; DROP TABLE shipments; --", "status"),
    ("shipments", 'status"; DELETE FROM shipments; --'),
    ("shipments", "COUNT(*)"), ("shipments", "status || amount"),
    ("main.shipments", "status"), ("shipments", "rowid"),
    ("shipments", "\x00status"), ("", "status"), (None, "status"),
])
def test_identifiers_must_match_real_user_schema(database, function, table, column):
    before = hashlib.sha256(database.path.read_bytes()).digest()
    with pytest.raises(ValueError):
        function(database, table, column)
    assert hashlib.sha256(database.path.read_bytes()).digest() == before


@pytest.mark.parametrize("limit", [0, -1, 21, True, False, 2.0, "2", None])
@pytest.mark.parametrize("function", [get_column_values, get_column_profile])
def test_invalid_limits_are_rejected(database, function, limit):
    with pytest.raises(ValueError, match="limit"):
        function(database, "shipments", "status", limit)


def test_mixed_storage_preserves_types_and_sqlite_numeric_equality(database):
    with sqlite3.connect(database.path) as conn:
        conn.execute("CREATE TABLE mixed (value)")
        conn.executemany("INSERT INTO mixed VALUES (?)", [(1.0,), (1,), ("1",), (b"1",), (None,)])
    profile = get_column_profile(database, "mixed", "value")
    assert profile["distinct_non_null_count"] == 3
    assert profile["storage_type_counts"] == {"null": 1, "integer": 1, "real": 1, "text": 1, "blob": 1}
    assert [(entry["storage_type"], entry["value"], entry["count"]) for entry in profile["value_counts"]] == [
        ("integer", 1, 2), ("blob", "31", 1), ("text", "1", 1),
    ]
    assert profile["numeric"]["count"] == 2
    assert profile["numeric"]["avg"] == 1


def test_long_text_blobs_and_nonfinite_numbers_are_bounded_json(database):
    with sqlite3.connect(database.path) as conn:
        conn.execute("CREATE TABLE unusual (value)")
        conn.executemany("INSERT INTO unusual VALUES (?)", [
            ("x" * 100_000,), (bytes(range(256)) * 1000,), (float("inf"),), (float("-inf"),),
        ])
    profile = get_column_profile(database, "unusual", "value")
    encoded = json.dumps(profile, allow_nan=False)
    assert len(encoded) < 3000
    text = next(item for item in profile["value_counts"] if item["storage_type"] == "text")
    assert len(text["value"]) == 256 and text["original_length"] == 100_000
    assert text["value_truncated"] is True
    blob = next(item for item in profile["value_counts"] if item["storage_type"] == "blob")
    assert len(blob["value"]) == 128 and blob["original_length"] == 256_000
    assert blob["value_truncated"] is True and blob["encoding"] == "hex"
    assert profile["numeric"]["count"] == 2
    assert profile["numeric"]["min"] == "-Infinity"
    assert profile["numeric"]["max"] == "Infinity"
    assert profile["numeric"]["avg"] is None
    json.dumps(get_column_values(database, "unusual", "value"), allow_nan=False)


def test_profile_counts_are_independent_of_execution_display_cap(database):
    database.max_rows = 1
    profile = get_column_profile(database, "shipments", "status", limit=20)
    assert profile["row_count"] == 5
    assert len(profile["value_counts"]) == 3
    assert profile["truncated"] is False


@pytest.mark.parametrize("function", [get_column_values, get_column_profile])
def test_read_only_queries_leave_source_unchanged(database, function):
    before = hashlib.sha256(database.path.read_bytes()).digest()
    function(database, "shipments", "status")
    assert hashlib.sha256(database.path.read_bytes()).digest() == before


def test_same_database_authorizer_blocks_unsafe_view_functions(database):
    with sqlite3.connect(database.path) as conn:
        conn.execute("CREATE VIEW unsafe AS SELECT randomblob(100000) AS value")
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        get_column_profile(database, "unsafe", "value")


@pytest.mark.parametrize("function", [get_column_values, get_column_profile])
def test_inspection_times_out_expensive_views(database, function):
    with sqlite3.connect(database.path) as conn:
        conn.execute("CREATE VIEW expensive AS WITH RECURSIVE n(v) AS "
                     "(VALUES(1) UNION ALL SELECT v + 1 FROM n WHERE v < 100000000) SELECT v FROM n")
    bounded = Database(database.path, timeout_seconds=.01)
    started = time.monotonic()
    with pytest.raises(sqlite3.OperationalError, match="interrupted|timed out"):
        function(bounded, "expensive", "v")
    assert time.monotonic() - started < 2


def test_profile_has_one_read_snapshot_during_concurrent_insert(database, monkeypatch):
    # WAL lets another connection commit during the profile without changing its snapshot.
    with sqlite3.connect(database.path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    connect = database.connect
    inserted = False

    def traced_connection():
        conn = connect()

        def trace(sql):
            nonlocal inserted
            if not inserted and sql.startswith("SELECT typeof("):
                inserted = True
                with sqlite3.connect(database.path) as writer:
                    writer.execute("INSERT INTO shipments (status) VALUES ('new_status')")

        conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(database, "connect", traced_connection)
    profile = get_column_profile(database, "shipments", "status")
    assert inserted
    assert profile["row_count"] == 5
    assert profile["distinct_non_null_count"] == 3
    assert sum(profile["storage_type_counts"].values()) == 5
    assert "new_status" not in {entry["value"] for entry in profile["value_counts"]}
