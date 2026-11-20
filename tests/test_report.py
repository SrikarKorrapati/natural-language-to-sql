"""Offline regressions for reporting checkpoints without changing recorded results."""
import copy
import csv
import json
from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import pytest

from benchmarks import report


@pytest.fixture
def run(tmp_path):
    directory = tmp_path / "run data"
    directory.mkdir()
    cases = [
        {"id": "one", "schema_id": "s01", "question": "Return one", "expected_sql": "SELECT 1", "difficulty": "easy"},
        {"id": "two", "schema_id": "s01", "question": "Return two", "expected_sql": "SELECT 2", "difficulty": None},
    ]
    config = {"max_repairs": 1, "max_critiques": 2, "models": [
        {"model_id": "model-a", "label": "A"}, {"model_id": "model-b", "label": "B"},
    ]}
    metadata = tmp_path / "cases.json"
    metadata.write_text(json.dumps(cases), encoding="utf-8")
    (directory / "manifest.json").write_text(json.dumps({
        "fingerprint": "test-run", "dataset_cases": 2, "config": config,
    }), encoding="utf-8")
    return SimpleNamespace(directory=directory, cases=metadata, config=config,
                           output=tmp_path / "exported report")


def args_for(run, **overrides):
    args = dict(run_dir=run.directory, cases=run.cases, config=None,
                checkpoint=None, output_dir=run.output)
    return SimpleNamespace(**{**args, **overrides})


def record(model="A", case="one", *, status="completed", correct=True, calls=None, **extra):
    return {
        "model": model, "model_id": "model-" + model.lower(), "id": case,
        "status": status, "correct": correct, "valid_sql": correct,
        "attempts": 1 if correct else 0, "critique_rounds": 1 if correct else 0,
        "critique_approved": True if correct else None, "input_valid": True,
        "latency_ms": 100, "calls": calls if calls is not None else [],
        "stage_calls": {}, "error": None, **extra,
    }


def usage_call(input_tokens, output_tokens, cost):
    return {"succeeded": True, "stage": "generate", "usage": {
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "estimated_cost_usd": cost, "provider_cost_usd": None,
    }}


def checkpoint(run, records):
    path = run.directory / "cases.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    return path


def csv_rows(run, filename="leaderboard.csv"):
    with (run.output / filename).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_resume_uses_latest_outcomes_but_keeps_all_usage_and_unknown_cost(run):
    checkpoint(run, [
        record(status="interrupted", correct=False, calls=[usage_call(10, 2, .1), {"succeeded": False}]),
        record(calls=[usage_call(20, 4, .2)]),
        record(case="two", correct=False, input_valid=False, calls=[{"succeeded": True, "usage": None}]),
    ])
    report.generate(args_for(run))
    first, unstarted = csv_rows(run)
    assert first["completed_cases"] == "2"
    assert first["correct_cases"] == "1"
    assert first["execution_accuracy_pct"] == "50.0"
    assert first["superseded_records"] == "1"
    assert first["http_attempts"] == "4"
    assert first["input_tokens"] == "30"
    assert first["output_tokens"] == "6"
    assert float(first["estimated_cost_usd"]) == pytest.approx(.3)
    assert first["estimated_cost_usd_all_calls_complete"] == "False"
    assert first["usage_missing_successful_calls"] == "1"
    assert first["provider_cost_usd"] == ""
    assert unstarted["model_id"] == "model-b"
    assert unstarted["execution_accuracy_pct"] == ""
    assert unstarted["estimated_cost_usd"] == ""
    failures = csv_rows(run, "failures.csv")
    assert [(r["id"], r["failure_kind"]) for r in failures] == [("two", "classifier_rejection")]
    assert "$0.3000 (partial)" in (run.output / "report.md").read_text()


def test_stale_summary_cannot_mark_a_partial_checkpoint_complete(run):
    checkpoint(run, [record()])
    (run.directory / "results.json").write_text(json.dumps({
        "fingerprint": "test-run", "models": {"A": {
            "model_id": "model-a", "total_cases": 1, "status": "complete",
        }},
    }))
    report.generate(args_for(run))
    first = csv_rows(run)[0]
    assert first["planned_cases"] == "2"
    assert first["coverage_pct"] == "50.0"
    assert first["status"] == "partial"
    assert "Partial run" in (run.output / "report.md").read_text()


def test_initial_run_without_checkpoint_is_reported_as_pending(run):
    report.generate(args_for(run))
    rows = csv_rows(run)
    assert len(rows) == 2
    assert all(row["completed_cases"] == "0" and row["status"] == "partial" for row in rows)
    assert all(row["estimated_cost_usd"] == "" for row in rows)
    text = (run.output / "report.md").read_text()
    assert "No checkpoint exists yet" in text
    assert "(cases.jsonl)" not in text
    assert not (run.directory / "cases.jsonl").exists()


def test_explicit_missing_checkpoint_is_not_treated_as_an_empty_run(run):
    with pytest.raises(FileNotFoundError, match="Checkpoint does not exist"):
        report.generate(args_for(run, checkpoint=run.directory / "typo.jsonl"))
    assert not run.output.exists()


def test_null_difficulty_and_optional_telemetry_do_not_break_artifacts(run):
    row = record(case="two", stage_calls=None, difficulty=None)
    row["calls"] = None
    checkpoint(run, [row])
    report.generate(args_for(run))
    difficulty = csv_rows(run, "difficulty.csv")
    unspecified = next(r for r in difficulty if r["model"] == "A" and r["difficulty"] == "unspecified")
    assert unspecified["correct_cases"] == "1"
    assert unspecified["completed_cases"] == "1"
    assert csv_rows(run)[0]["estimated_cost_usd"] == ""
    ET.parse(run.output / "leaderboard.svg")
    ET.parse(run.output / "accuracy-by-difficulty.svg")


def test_torn_utf8_tail_is_ignored_without_mutating_checkpoint(run):
    path = checkpoint(run, [record()])
    original = path.read_bytes() + b'{"model":"A","id":"tw\xc3'
    path.write_bytes(original)
    report.generate(args_for(run))
    assert csv_rows(run)[0]["completed_cases"] == "1"
    assert path.read_bytes() == original
    assert "Ignored incomplete final checkpoint" in (run.output / "report.md").read_text()


@pytest.mark.parametrize("bad_record", [b'{"model":\n', b'[]', b'{}\n'])
def test_complete_corrupt_final_record_is_not_silently_dropped(run, bad_record):
    path = checkpoint(run, [record()])
    original = path.read_bytes() + bad_record
    path.write_bytes(original)
    with pytest.raises(ValueError, match="Invalid checkpoint record 2"):
        report.generate(args_for(run))
    assert path.read_bytes() == original
    assert not run.output.exists()


def test_report_links_are_relative_escaped_and_resolve_after_export(run):
    checkpoint(run, [record()])
    report.generate(args_for(run))
    text = (run.output / "report.md").read_text()
    assert str(run.directory) not in text
    assert "../run%20data/cases.jsonl" in text
    for link in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", text):
        assert not link.startswith("/")
        assert (run.output / unquote(link)).exists(), link


def test_manifest_settings_remain_authoritative_when_config_is_edited(run):
    checkpoint(run, [record()])
    edited = copy.deepcopy(run.config)
    edited.update(max_repairs=99, max_critiques=99)
    config_path = run.directory / "edited-config.json"
    config_path.write_text(json.dumps(edited))
    report.generate(args_for(run, config=config_path))
    text = (run.output / "report.md").read_text()
    assert "Configured budgets: 1 SQLite-error repairs and 2 critique rounds" in text
    edited["models"][0]["model_id"] = "a-different-model"
    config_path.write_text(json.dumps(edited))
    with pytest.raises(ValueError, match="Supplied config models do not match"):
        report.generate(args_for(run, config=config_path))


def test_unconfigured_checkpoint_model_is_rejected(run):
    checkpoint(run, [record(model="C")])
    with pytest.raises(ValueError, match="unconfigured models"):
        report.generate(args_for(run))


def test_missing_call_records_cannot_silently_reduce_usage_totals(run):
    checkpoint(run, [record(http_attempts=2, calls=[usage_call(10, 5, .1)])])
    with pytest.raises(ValueError, match="HTTP attempt count does not match recorded calls"):
        report.generate(args_for(run))
    assert not run.output.exists()


def test_zero_latency_is_a_valid_tiebreaker(run):
    checkpoint(run, [record(model=model, case=case, latency_ms=latency)
                     for model, latency in [("A", 100), ("B", 0)]
                     for case in ["one", "two"]])
    report.generate(args_for(run))
    assert [row["model"] for row in csv_rows(run)] == ["B", "A"]


def test_invalid_usage_values_remain_unknown_instead_of_reducing_cost():
    summary = report.calls_summary([record(calls=[usage_call(None, None, None), usage_call(-1, float("nan"), -5)])])
    assert summary["input_tokens"] is None
    assert summary["output_tokens"] is None
    assert summary["estimated_cost_usd"] is None
    assert summary["usage_missing_successful_calls"] == 2
    assert summary["estimated_cost_usd_all_calls_complete"] is False
