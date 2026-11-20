"""Run with: python -m benchmarks.run --models MODEL_A MODEL_B."""

import argparse
import json
import math
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from openai import APIConnectionError, APIStatusError

from app.agent import SQLAgent
from app.db import Database, History

SCHEMAS = Path(__file__).with_name("schemas")


def validate_schema_id(schema_id):
    if (not isinstance(schema_id, str) or not schema_id.strip()
            or schema_id in {".", ".."} or "/" in schema_id or "\\" in schema_id):
        raise ValueError("schema_id must be a fixture name, not a path")


def validate_cases(cases):
    """Reject malformed datasets before creating fixtures or calling a provider."""
    if not isinstance(cases, list) or not cases:
        raise ValueError("Cases must be a nonempty list")
    ids = set()
    for case in cases:
        if not isinstance(case, dict) or any(
            not isinstance(case.get(field), str) or not case[field].strip()
            for field in ("id", "schema_id", "question", "expected_sql")
        ):
            raise ValueError("Each case needs an ID, schema ID, question, and reference SQL")
        validate_schema_id(case["schema_id"])
        if case["id"] in ids:
            raise ValueError("Case IDs must be unique")
        ids.add(case["id"])
        if "order_sensitive" in case and not isinstance(case["order_sensitive"], bool):
            raise ValueError("order_sensitive must be a boolean")


def load_database(schema_id, directory):
    """Create a schema fixture once within a benchmark run."""
    validate_schema_id(schema_id)
    path = Path(directory) / f"{schema_id}.db"
    if not path.exists():
        with closing(sqlite3.connect(path)) as connection:
            # Each fixture defines its tables and inserts the same sample rows every run.
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript((SCHEMAS / f"{schema_id}.sql").read_text())
    # Subsequent queries use the application's read-only database connection.
    return Database(path)


def rows_equal(actual, expected, ordered=False):
    """Compare result values, preserving duplicates and tolerating float noise."""

    def cell_equal(left, right):
        if isinstance(left, int) and isinstance(right, int):
            return left == right
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if any(isinstance(value, float) and not math.isfinite(value) for value in (left, right)):
                return left == right
            # Compare exact ratios: converting a large SQLite integer to float can
            # erase a difference of one before an absolute-tolerance check.
            left_n, left_d = left.as_integer_ratio()
            right_n, right_d = right.as_integer_ratio()
            return abs(left_n * right_d - right_n * left_d) * 1_000_000 <= left_d * right_d
        return left == right

    def row_equal(left, right):
        return len(left) == len(right) and all(map(cell_equal, left, right))

    if len(actual) != len(expected):
        return False
    if ordered:
        # Ordering matters only for cases whose requested answer depends on it.
        return all(map(row_equal, actual, expected))

    # Pair each actual row with a different expected row, preserving duplicate counts.
    # Reassign earlier pairs when nearby floating-point values have multiple matches.
    matches = {}

    def match(index, seen):
        for candidate, row in enumerate(expected):
            if candidate not in seen and row_equal(actual[index], row):
                seen.add(candidate)
                if candidate not in matches or match(matches[candidate], seen):
                    matches[candidate] = index
                    return True
        return False

    return all(match(index, set()) for index in range(len(actual)))


def run(models, cases, agent_factory=SQLAgent):
    """Each case starts with empty memory; expected SQL never enters the agent."""
    if not isinstance(models, (list, tuple)) or not models or any(
        not isinstance(model, str) or not model.strip() for model in models
    ):
        raise ValueError("Models must be a nonempty list of model IDs")
    validate_cases(cases)
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "models": {}}

    # Fixtures and history are temporary, keeping benchmarks separate from user data.
    with tempfile.TemporaryDirectory(prefix="queryroom-benchmark-") as directory:
        root = Path(directory)
        for model_index, model in enumerate(dict.fromkeys(models)):
            results = []
            for case_index, case in enumerate(cases):
                database = load_database(case["schema_id"], root)
                expected = database.execute(case["expected_sql"])
                if expected["truncated"]:
                    raise ValueError(f"Reference result is truncated: {case['id']}")
                # Fresh history for each model/case prevents earlier answers leaking in.
                history = History(
                    root / f"memory-{model_index}-{case_index}.db",
                    dataset=str(database.path),
                )
                agent = agent_factory(database, history)
                result = {
                    "id": case["id"],
                    "schema_id": case["schema_id"],
                    "question": case["question"],
                    "valid_sql": False,
                    "correct": False,
                    "attempts": 0,
                    "sql": None,
                    "retrieval_mode": None,
                    "input_valid": None,
                    "classification_explanation": None,
                    "critique_rounds": 0,
                    "critique_approved": None,
                    "critique_issues": [],
                    "tool_calls": 0,
                    "error": None,
                    "provider_error": False,
                }
                # Time generation, corrections, validation, and execution; exclude setup.
                started = perf_counter()
                try:
                    proposal = agent.propose(case["question"], "benchmark", model)
                    result.update(
                        sql=proposal["sql"],
                        attempts=proposal["attempts"],
                        retrieval_mode=proposal.get("retrieval_mode"),
                        input_valid=proposal.get("input_valid"),
                        classification_explanation=proposal.get("classification_explanation"),
                        critique_rounds=proposal.get("critique_rounds", 0),
                        critique_approved=proposal.get("critique_approved"),
                        critique_issues=proposal.get("critique_issues", []),
                        tool_calls=proposal.get("tool_calls", 0),
                    )
                    if proposal["sql"] is None:
                        raise ValueError("No SQL generated: " + proposal["explanation"])
                    database.validate(proposal["sql"])
                    result["valid_sql"] = True
                    # Benchmark fixtures run automatically without terminal approval.
                    actual = database.execute(proposal["sql"])
                    if actual["truncated"]:
                        raise ValueError("Generated result is truncated.")
                    # Compare values and column counts, allowing different SQL and aliases.
                    result["correct"] = len(actual["columns"]) == len(
                        expected["columns"]
                    ) and rows_equal(
                        actual["rows"],
                        expected["rows"],
                        case.get("order_sensitive", False),
                    )
                except Exception as exc:
                    # Record the error and continue, keeping failures in the final report.
                    result["provider_error"] = isinstance(exc, (APIConnectionError, APIStatusError))
                    result["error"] = (
                        "Provider request failed" if result["provider_error"] else str(exc)
                    )
                result["latency_ms"] = round((perf_counter() - started) * 1000, 2)
                results.append(result)
            # Valid SQL can answer incorrectly, so report validity and accuracy.
            report["models"][model] = {
                "cases": len(results),
                "execution_accuracy": sum(r["correct"] for r in results) / len(results),
                "valid_sql_rate": sum(r["valid_sql"] for r in results) / len(results),
                "average_latency_ms": round(
                    sum(r["latency_ms"] for r in results) / len(results), 2
                ),
                "results": results,
            }
    return report


def main(argv=None):
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument(
        "--cases", type=Path, default=Path(__file__).with_name("cases.json")
    )
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results.json"))
    args = parser.parse_args(argv)
    try:
        cases = json.loads(args.cases.read_text())
        report = run(args.models, cases)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for model, scores in report["models"].items():
        print(
            f"{model}: accuracy {scores['execution_accuracy']:.1%}, "
            f"valid SQL {scores['valid_sql_rate']:.1%}, "
            f"mean {scores['average_latency_ms']:.0f} ms"
        )
    print(f"Full report: {args.output}")
    return int(any(result.get("provider_error") for scores in report["models"].values()
                   for result in scores["results"]))


if __name__ == "__main__":
    raise SystemExit(main())
