import json
import sqlite3
from collections import Counter
from pathlib import Path

import pytest
import httpx
from openai import PermissionDeniedError

from benchmarks import run as runner
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
    # The first actual row matches both expected rows; the second matches only the first.
    assert rows_equal([[1.0000009], [1.0]], [[1.0000001], [1.0000018]])


def test_large_integer_float_comparison_does_not_erase_real_differences():
    exact = 2 ** 53
    assert rows_equal([[exact]], [[float(exact)]])
    assert not rows_equal([[exact + 1]], [[float(exact)]])
    assert not rows_equal([[float(exact)]], [[exact + 1]])
    assert not rows_equal([[2 ** 63 - 1]], [[float(2 ** 63 - 1)]])
    assert rows_equal([[1]], [[1.0000001]])
    assert not rows_equal([[1]], [[1.00001]])


@pytest.mark.parametrize('models,cases', [([], []), (['test'], []), ([], [{}])])
def test_empty_benchmark_input_is_rejected_before_setup(models, cases):
    with pytest.raises(ValueError):
        run(models, cases)


@pytest.mark.parametrize('schema_id', ['../outside', '/absolute', 'nested/name', 'nested\\name', '..'])
def test_fixture_name_cannot_escape_schema_directory(schema_id, tmp_path):
    with pytest.raises(ValueError, match='fixture name'):
        load_database(schema_id, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_provider_errors_are_redacted_and_cli_reports_failure(tmp_path, monkeypatch):
    class BrokenAgent:
        def __init__(self, database, history):
            pass

        def propose(self, *args):
            response = httpx.Response(403, request=httpx.Request('POST', 'https://example.test'))
            raise PermissionDeniedError('private-provider-detail', response=response, body=None)

    cases = [dict(id='one', schema_id='s01_retail', question='Return one', expected_sql='SELECT 1')]
    report = run(['test-model'], cases, agent_factory=BrokenAgent)
    result = report['models']['test-model']['results'][0]
    assert result['provider_error']
    assert 'private-provider-detail' not in result['error']
    path = tmp_path / 'cases.json'
    path.write_text(json.dumps(cases))
    monkeypatch.setattr(runner, 'run', lambda *args: report)
    assert runner.main(['--models', 'test-model', '--cases', str(path),
                        '--output', str(tmp_path / 'results.json')]) == 1


def test_runner_switches_schemas_and_keeps_failures(tmp_path, monkeypatch):
    for name, value in (("first", 1), ("second", 2)):
        (tmp_path / f"{name}.sql").write_text(
            f"CREATE TABLE numbers (value INTEGER); INSERT INTO numbers VALUES ({value});"
        )
    monkeypatch.setattr("benchmarks.run.SCHEMAS", tmp_path)

    class FakeAgent:
        def __init__(self, database, history):
            # Write a marker so the next case detects any accidental sharing of history.
            assert history.successful() == []
            history.save("benchmark", "previous question", "test-model", "SELECT 1")

        def propose(self, question, session_id, model):
            if question == "clarification":
                return {"sql": None, "explanation": "Please clarify.", "attempts": 1}
            queries = {
                # Changed SQL and column aliases can still produce the correct answer.
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
        for name in ("equivalent", "wrong", "invalid", "truncated", "clarification")
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
    assert scores["execution_accuracy"] == pytest.approx(2 / 6)
    assert scores["valid_sql_rate"] == pytest.approx(4 / 6)
    assert scores["results"][2]["error"]
    assert scores["results"][3]["error"] == "Generated result is truncated."
    assert scores["results"][4]["error"] == "No SQL generated: Please clarify."
    assert scores["results"][5]["schema_id"] == "second"
    assert scores["results"][5]["correct"]


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
        # Saved reference results detect changes to fixture data or expected SQL behavior.
        assert not result["truncated"], case["id"]
        assert result["columns"] == expected[case["id"]]["columns"], case["id"]
        assert rows_equal(
            result["rows"],
            expected[case["id"]]["rows"],
            ordered=case["order_sensitive"],
        ), case["id"]
