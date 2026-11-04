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

from app.agent import SQLAgent
from app.db import Database, History

SCHEMAS = Path(__file__).with_name("schemas")


def load_database(schema_id, directory):
    """Create a schema fixture once within a benchmark run."""
    path = Path(directory) / f"{schema_id}.db"
    if not path.exists():
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript((SCHEMAS / f"{schema_id}.sql").read_text())
    return Database(path)


def rows_equal(actual, expected, ordered=False):
    """Compare result values, preserving duplicates and tolerating float noise."""

    def cell_equal(left, right):
        if isinstance(left, int) and isinstance(right, int):
            return left == right
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            return math.isclose(left, right, rel_tol=0, abs_tol=1e-6)
        return left == right

    def row_equal(left, right):
        return len(left) == len(right) and all(map(cell_equal, left, right))

    if len(actual) != len(expected):
        return False
    if ordered:
        return all(map(row_equal, actual, expected))

    # A matching, rather than a set, keeps duplicate rows significant. Backtracking
    # also handles multiple nearby floating-point values without greedy mismatches.
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
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "models": {}}

    with tempfile.TemporaryDirectory(prefix="queryroom-benchmark-") as directory:
        root = Path(directory)
        for model_index, model in enumerate(dict.fromkeys(models)):
            results = []
            for case_index, case in enumerate(cases):
                database = load_database(case["schema_id"], root)
                expected = database.execute(case["expected_sql"])
                if expected["truncated"]:
                    raise ValueError(f"Reference result is truncated: {case['id']}")
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
                    "error": None,
                }
                started = perf_counter()
                try:
                    proposal = agent.propose(case["question"], "benchmark", model)
                    result.update(sql=proposal["sql"], attempts=proposal["attempts"])
                    database.validate(proposal["sql"])
                    result["valid_sql"] = True
                    actual = database.execute(proposal["sql"])
                    if actual["truncated"]:
                        raise ValueError("Generated result is truncated.")
                    result["correct"] = len(actual["columns"]) == len(
                        expected["columns"]
                    ) and rows_equal(
                        actual["rows"],
                        expected["rows"],
                        case.get("order_sensitive", False),
                    )
                except Exception as exc:
                    result["error"] = str(exc)
                result["latency_ms"] = round((perf_counter() - started) * 1000, 2)
                results.append(result)
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


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument(
        "--cases", type=Path, default=Path(__file__).with_name("cases.json")
    )
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results.json"))
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    report = run(args.models, cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for model, scores in report["models"].items():
        print(
            f"{model}: accuracy {scores['execution_accuracy']:.1%}, "
            f"valid SQL {scores['valid_sql_rate']:.1%}, "
            f"mean {scores['average_latency_ms']:.0f} ms"
        )
    print(f"Full report: {args.output}")


if __name__ == "__main__":
    main()
