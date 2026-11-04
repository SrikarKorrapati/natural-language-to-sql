import json
import sqlite3
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.run import load_database, rows_equal, run


def test_result_comparison_respects_duplicates_order_and_float_tolerance():
    assert rows_equal([["a", 1.00000001], ["b", None]], [["b", None], ["a", 1]])
    assert not rows_equal([["a"], ["a"]], [["a"], ["b"]])
    assert not rows_equal([[1], [2]], [[2], [1]], ordered=True)
    assert not rows_equal([[1, 2]], [[1]])
    assert not rows_equal([[1]], [["1"]])
    assert not rows_equal([[1_000_000]], [[1_000_001]])
    assert not rows_equal([[1_000_000.01]], [[1_000_000.02]])
    assert rows_equal([], [])


def test_ambiguous_float_matches_do_not_depend_on_row_order():
    assert rows_equal([[1.0000009], [1.0]], [[1.0000001], [1.0000018]])


def test_runner_switches_schemas_and_keeps_failures(tmp_path, monkeypatch):
    for name, value in (("first", 1), ("second", 2)):
        (tmp_path / f"{name}.sql").write_text(
            f"CREATE TABLE numbers (value INTEGER); INSERT INTO numbers VALUES ({value});"
        )
    monkeypatch.setattr("benchmarks.run.SCHEMAS", tmp_path)

    class FakeAgent:
        def __init__(self, database, history):
            assert history.successful() == []
            history.save("benchmark", "previous question", "test-model", "SELECT 1")

        def propose(self, question, session_id, model):
            queries = {
                "equivalent": "SELECT value AS alternate_name FROM numbers",
                "wrong": "SELECT 2",
                "invalid": "SELECT missing_column",
                "truncated": "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL "
                "SELECT x+1 FROM n WHERE x<501) SELECT x FROM n",
            }
            return {"sql": queries[question], "attempts": 1}

    cases = [
        {
            "id": name,
            "schema_id": "first",
            "question": name,
            "expected_sql": "SELECT 1",
        }
        for name in ("equivalent", "wrong", "invalid", "truncated")
    ]
    cases.append(
        {
            "id": "second-schema",
            "schema_id": "second",
            "question": "equivalent",
            "expected_sql": "SELECT 2",
        }
    )
    report = run(["test-model"], cases, agent_factory=FakeAgent)
    scores = report["models"]["test-model"]
    assert scores["execution_accuracy"] == pytest.approx(2 / 5)
    assert scores["valid_sql_rate"] == pytest.approx(4 / 5)
    assert scores["results"][2]["error"]
    assert scores["results"][3]["error"] == "Generated result is truncated."
    assert scores["results"][4]["schema_id"] == "second"
    assert scores["results"][4]["correct"]


def test_reference_queries_execute_on_all_twenty_schemas(tmp_path):
    path = Path(__file__).parents[1] / "benchmarks" / "cases.json"
    cases = json.loads(path.read_text())
    assert len(cases) == len({case["id"] for case in cases}) == 200
    assert len({case["question"] for case in cases}) == 200
    schemas = Counter(case["schema_id"] for case in cases)
    assert len(schemas) == 20
    assert set(schemas.values()) == {10}
    assert set(schemas) == {
        fixture.stem for fixture in (path.parent / "schemas").glob("*.sql")
    }
    records = [
        json.loads(line)
        for line in (path.parent / "expected-results.jsonl").read_text().splitlines()
    ]
    expected = {record["id"]: record for record in records}
    assert len(records) == len(expected) == 200
    assert set(expected) == {case["id"] for case in cases}
    for schema_id in schemas:
        assert Counter(
            case["difficulty"] for case in cases if case["schema_id"] == schema_id
        ) == {"easy": 3, "medium": 4, "hard": 3}
        database = load_database(schema_id, tmp_path)
        with sqlite3.connect(database.path) as connection:
            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    for case in cases:
        database = load_database(case["schema_id"], tmp_path)
        database.validate(case["expected_sql"])
        result = database.execute(case["expected_sql"])
        assert not result["truncated"], case["id"]
        assert result["columns"] == expected[case["id"]]["columns"], case["id"]
        assert rows_equal(
            result["rows"],
            expected[case["id"]]["rows"],
            ordered=case["order_sensitive"],
        ), case["id"]
