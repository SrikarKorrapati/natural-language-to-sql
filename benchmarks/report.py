#!/usr/bin/env python3
"""Create auditable reports from benchmarks.parallel output; makes no API calls."""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import html
import json
import math
import os
from pathlib import Path
from urllib.parse import quote


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def usage_number(value):
    return number(value) and value >= 0


def percentile(values, p):
    """Linear interpolation between adjacent ordered observations."""
    values = sorted(x for x in values if number(x))
    if not values:
        return None
    position = (len(values) - 1) * p
    low = math.floor(position)
    high = math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def read_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else default


def read_records(path):
    records, warnings = [], []
    if not path.exists():
        return [], ["No checkpoint exists yet; no cases have been recorded."]
    # A concurrent writer can stop in the middle of a UTF-8 character, not just JSON.
    lines = path.read_bytes().splitlines(keepends=True)
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            if i != len(lines) - 1 or line.endswith((b"\n", b"\r")):
                raise ValueError(f"Invalid checkpoint record {i + 1}: {exc}") from exc
            warnings.append(f"Ignored incomplete final checkpoint line {i + 1}; the source file was not modified.")
            continue
        if not isinstance(record, dict) or any(not isinstance(record.get(key), str) or not record[key] for key in ("model", "id")):
            raise ValueError(f"Invalid checkpoint record {i + 1}: model and case ID must be nonempty strings")
        status = record.get("status", "completed")
        if not isinstance(status, str) or status not in {"completed", "blocked", "interrupted"}:
            raise ValueError(f"Invalid checkpoint record {i + 1}: unknown status")
        calls = record.get("calls")
        if calls is not None and (not isinstance(calls, list) or any(not isinstance(call, dict) for call in calls)):
            raise ValueError(f"Invalid checkpoint record {i + 1}: calls must be a list")
        declared_attempts = record.get("http_attempts")
        if declared_attempts is not None and (type(declared_attempts) is not int or declared_attempts != len(calls or [])):
            raise ValueError(f"Invalid checkpoint record {i + 1}: HTTP attempt count does not match recorded calls")
        if any(call.get("usage") is not None and not isinstance(call["usage"], dict) for call in (calls or [])):
            raise ValueError(f"Invalid checkpoint record {i + 1}: call usage must be an object or null")
        if record.get("stage_calls") is not None and not isinstance(record["stage_calls"], dict):
            raise ValueError(f"Invalid checkpoint record {i + 1}: stage_calls must be an object")
        records.append(record)
    return records, warnings


def model_mapping(config):
    """Reject ambiguous labels rather than silently dropping a configured model."""
    if not isinstance(config, dict) or not isinstance(config.get("models", []), list):
        raise ValueError("Model configuration must contain a models list")
    models = {}
    for item in config.get("models", []):
        if not isinstance(item, dict):
            raise ValueError("Configured model entries must be objects")
        model_id = item.get("model_id")
        label = item.get("label", model_id)
        if not isinstance(model_id, str) or not model_id or not isinstance(label, str) or not label:
            raise ValueError("Configured models require nonempty model IDs and labels")
        if label in models:
            raise ValueError(f"Duplicate configured model label: {label}")
        models[label] = item
    return models


def checkpoint_reference(checkpoint, output):
    """Keep generated reports portable without exposing a machine's absolute path."""
    if not checkpoint.exists():
        return "an initialized run awaiting its first checkpoint"
    try:
        shared = Path(os.path.commonpath([checkpoint.resolve(), output.resolve()]))
        if shared == Path(checkpoint.resolve().anchor):
            # Cross-root exports cannot have a useful portable source link.
            return "an external checkpoint JSONL file"
        relative = Path(os.path.relpath(checkpoint.resolve(), output)).as_posix()
    except ValueError:  # Different Windows drives cannot have a relative link.
        return "the checkpoint JSONL file"
    return f"[checkpoint JSONL]({quote(relative, safe='/')})"


def fmt(value, digits=1):
    return "—" if value is None else f"{value:,.{digits}f}"


def percent(numerator, denominator):
    return None if not denominator else 100 * numerator / denominator


def pct(value):
    return "—" if value is None else f"{value:.1f}%"


def cost_cell(row, key):
    if row[key] is None:
        return "Unavailable"
    text = "$" + fmt(row[key], 4)
    if row[key + "_observed_calls"] < row["http_attempts"]:
        text += " (partial)"
    return text


def cell(value):
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    return "\n".join(["| " + " | ".join(map(cell, headers)) + " |", "| " + " | ".join("---" for _ in headers) + " |"] + ["| " + " | ".join(map(cell, row)) + " |" for row in rows])


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in row.items() if k in fields})


def calls_summary(records):
    calls = [call for record in records for call in (record.get("calls") or [])]
    usage_fields = ("input_tokens", "output_tokens", "total_tokens", "cached_input_tokens", "reasoning_tokens", "provider_cost_usd", "estimated_cost_usd")
    result = {"http_attempts": len(calls), "successful_http_calls": sum(call.get("succeeded") is True for call in calls),
              "length_truncated_calls": sum(call.get("finish_reason") == "length" for call in calls)}
    for key in usage_fields:
        observed = [(call.get("usage") or {}).get(key) for call in calls
                    if usage_number((call.get("usage") or {}).get(key))]
        result[key] = sum(observed) if observed else None
        result[key + "_observed_calls"] = len(observed)
        result[key + "_all_calls_complete"] = bool(calls) and len(observed) == len(calls)
    result["usage_missing_successful_calls"] = sum(call.get("succeeded") is True and not all(usage_number((call.get("usage") or {}).get(key)) for key in ("input_tokens", "output_tokens")) for call in calls)
    for stage in ("classify", "generate", "critique"):
        result[stage + "_logical_calls"] = sum((record.get("stage_calls") or {}).get(stage, 0) or 0 for record in records)
    return result


def summarize(label, all_records, latest_records, cases, config_model, summary_model):
    completed = [row for row in latest_records if row.get("status", "completed") == "completed"]
    correct = [row for row in completed if row.get("correct") is True]
    valid = sum(row.get("valid_sql") is True for row in completed)
    rejected = sum(row.get("input_valid") is False for row in completed)
    latency_all = [row.get("latency_ms") for row in latest_records if number(row.get("latency_ms"))]
    latency_correct = [row.get("latency_ms") for row in correct if number(row.get("latency_ms"))]
    # results.json is a derived cache and can lag behind the append-only checkpoint.
    planned = len(cases)
    model_ids = sorted({row.get("model_id") for row in all_records if row.get("model_id")})
    if not model_ids and config_model.get("model_id"):
        model_ids = [config_model["model_id"]]
    if not model_ids and summary_model.get("model_id"):
        model_ids = [summary_model["model_id"]]
    result = {
        "model": label, "model_id": ", ".join(model_ids), "planned_cases": planned,
        "observed_cases": len(latest_records), "completed_cases": len(completed), "correct_cases": len(correct),
        "coverage_pct": percent(len(completed), planned), "execution_accuracy_pct": percent(len(correct), len(completed)),
        "valid_sql_cases": valid, "valid_sql_pct": percent(valid, len(completed)),
        "classifier_rejected_cases": rejected, "classifier_rejection_pct": percent(rejected, len(completed)),
        "blocked_cases": sum(row.get("status") == "blocked" for row in latest_records),
        "interrupted_cases": sum(row.get("status") == "interrupted" for row in latest_records),
        "not_observed_cases": max(planned - len(latest_records), 0),
        "median_latency_all_latest_ms": percentile(latency_all, .5), "p95_latency_all_latest_ms": percentile(latency_all, .95),
        "median_latency_correct_ms": percentile(latency_correct, .5), "p95_latency_correct_ms": percentile(latency_correct, .95),
        "sql_generation_passes_completed": sum(row.get("attempts") or 0 for row in completed),
        "sql_revisions_completed": sum(max((row.get("attempts") or 0) - 1, 0) for row in completed),
        "cases_with_sql_revisions": sum((row.get("attempts") or 0) > 1 for row in completed),
        "critique_rounds_completed": sum(row.get("critique_rounds") or 0 for row in completed),
        "critic_approved_cases": sum(row.get("critique_approved") is True for row in completed),
        "critic_rejected_cases": sum(row.get("critique_approved") is False for row in completed),
        "critic_not_reviewed_cases": sum(row.get("critique_approved") is None for row in completed),
        "critic_approved_incorrect_cases": sum(row.get("critique_approved") is True and row.get("correct") is not True for row in completed),
        "checkpoint_records": len(all_records), "superseded_records": len(all_records) - len(latest_records),
        "status": "complete" if len(completed) == planned else "partial",
    }
    result.update(calls_summary(all_records))
    expected = Counter(row.get("difficulty") or "unspecified" for row in cases)
    difficulty = []
    for name in list(dict.fromkeys(["easy", "medium", "hard"] + sorted(expected))):
        rows = [row for row in completed if (row.get("difficulty") or "unspecified") == name]
        count = sum(row.get("correct") is True for row in rows)
        if expected.get(name, 0) or rows:
            difficulty.append({"model": label, "difficulty": name, "expected_cases": expected.get(name, 0), "completed_cases": len(rows), "correct_cases": count, "accuracy_pct": percent(count, len(rows))})
    return result, difficulty


def accuracy_svg(path, metrics, difficulties):
    colors = {"easy": "#16a34a", "medium": "#2563eb", "hard": "#9333ea"}
    groups = {row["model"]: [d for d in difficulties if d["model"] == row["model"]] for row in metrics}
    height = 140 + sum(36 + len(group) * 34 for group in groups.values())
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="{height}" viewBox="0 0 1080 {height}" role="img" aria-labelledby="title desc">', '<title id="title">SQL benchmark execution accuracy by difficulty</title>', '<desc id="desc">Bars use completed cases only. Each label includes correct and completed case counts.</desc>', '<rect width="1080" height="100%" fill="#f8fafc"/>', '<style>text{font-family:Arial,sans-serif;fill:#0f172a}.muted{fill:#475569}</style>', '<text x="32" y="38" font-size="23" font-weight="700">Execution accuracy by difficulty</text>', '<text x="32" y="63" font-size="13" class="muted">Full classifier → SQL generation → validation/repair → critique pipeline; completed cases only</text>']
    y = 100
    for model, group in groups.items():
        parts.append(f'<text x="32" y="{y}" font-size="17" font-weight="700">{html.escape(model)}</text>')
        y += 28
        for d in group:
            value = d["accuracy_pct"] or 0
            name = d["difficulty"]
            parts.extend([f'<text x="32" y="{y + 16}" font-size="14">{html.escape(name.title())}</text>', f'<rect x="112" y="{y}" width="680" height="23" rx="4" fill="#e2e8f0"/>', f'<rect x="112" y="{y}" width="{680 * value / 100:.2f}" height="23" rx="4" fill="{colors.get(name, "#64748b")}"/>', f'<text x="810" y="{y + 16}" font-size="14">{pct(d["accuracy_pct"])} · {d["correct_cases"]}/{d["completed_cases"]} correct</text>'])
            y += 34
        y += 8
    parts.extend([f'<text x="32" y="{height - 24}" font-size="12" class="muted">Partial runs are not directly comparable; see report.md for coverage and limitations.</text>', '</svg>'])
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def leaderboard_svg(path, metrics):
    """Ten rows stay compact; incomplete coverage is visible on each row."""
    width, height = 1240, 175 + 63 * len(metrics)
    incomplete = any(row["completed_cases"] != row["planned_cases"] for row in metrics)
    latencies = [row["median_latency_all_latest_ms"] for row in metrics if number(row["median_latency_all_latest_ms"])]
    maximum_latency = max(latencies, default=1) or 1
    title = "SQL benchmark comparison" + (" — partial run" if incomplete else "")
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">', f'<title id="title">{html.escape(title)}</title>', '<desc id="desc">Execution accuracy among completed cases and median latency among all latest observed case attempts. Coverage is displayed for every model. Partial models are not a final ranking.</desc>', '<rect width="100%" height="100%" fill="#f8fafc"/>', '<style>text{font-family:Arial,sans-serif;fill:#0f172a}.muted{fill:#475569}</style>', f'<text x="30" y="37" font-size="24" font-weight="700">{html.escape(title)}</text>', '<text x="30" y="62" font-size="13" class="muted">Same model handles classification, SQL generation and critique. No conversation history.</text>', '<text x="30" y="97" font-size="13" font-weight="700">MODEL · COMPLETED / PLANNED</text>', '<text x="355" y="97" font-size="13" font-weight="700">EXECUTION ACCURACY · HIGHER IS BETTER</text>', '<text x="905" y="97" font-size="13" font-weight="700">MEDIAN LATENCY · LOWER IS BETTER</text>']
    for i, row in enumerate(metrics):
        y = 117 + i * 63
        partial = row["completed_cases"] != row["planned_cases"]
        label = row["model"]
        color = "#b45309" if partial else "#2563eb"
        accuracy = row["execution_accuracy_pct"]
        latency = row["median_latency_all_latest_ms"]
        coverage = f"{row['completed_cases']}/{row['planned_cases']} completed"
        if partial:
            coverage += " · PARTIAL"
        parts.extend([f'<text x="30" y="{y + 15}" font-size="15" font-weight="700">{html.escape(label)}</text>', f'<text x="30" y="{y + 34}" font-size="12" class="muted">{html.escape(coverage)}</text>', f'<rect x="355" y="{y + 1}" width="385" height="22" rx="4" fill="#e2e8f0"/>'])
        if accuracy is not None:
            parts.append(f'<rect x="355" y="{y + 1}" width="{385 * accuracy / 100:.2f}" height="22" rx="4" fill="{color}"/>')
        parts.extend([f'<text x="752" y="{y + 17}" font-size="15" font-weight="700">{pct(accuracy)}</text>', f'<text x="355" y="{y + 40}" font-size="12" class="muted">{row["correct_cases"]} correct of {row["completed_cases"]} completed</text>', f'<rect x="905" y="{y + 1}" width="215" height="22" rx="4" fill="#e2e8f0"/>'])
        if latency is not None:
            parts.append(f'<rect x="905" y="{y + 1}" width="{215 * latency / maximum_latency:.2f}" height="22" rx="4" fill="#0f766e"/>')
        latency_text = f"{latency / 1000:.1f} s" if latency is not None else "—"
        parts.extend([f'<text x="1132" y="{y + 17}" font-size="15" font-weight="700">{latency_text}</text>', f'<text x="905" y="{y + 40}" font-size="12" class="muted">All {row["observed_cases"]} latest observed cases</text>'])
    footer = "Partial models remain in configured order; wait for equal coverage before comparing." if incomplete else "Ordered by execution accuracy; tied scores use median latency. One run on synthetic fixtures."
    parts.extend([f'<text x="30" y="{height - 28}" font-size="12" class="muted">{footer}</text>', f'<text x="30" y="{height - 10}" font-size="11" class="muted">Latency includes early failures and concurrent request contention; see correct-case timings in report.md.</text>', '</svg>'])
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def generate(args):
    run = args.run_dir.resolve()
    output = (args.output_dir or run).resolve()
    checkpoint = (args.checkpoint or run / "cases.jsonl").resolve()
    manifest = read_json(run / "manifest.json", {})
    # An initialized dry run (or a run awaiting its first response) has no checkpoint.
    # An explicit missing path is a typo, not an empty successful experiment.
    if not checkpoint.exists() and (args.checkpoint is not None or not manifest):
        raise FileNotFoundError(f"Checkpoint does not exist: {checkpoint}")
    records, warnings = read_records(checkpoint)
    cases = read_json(args.cases, [])
    if isinstance(cases, dict):
        cases = cases.get("cases", [])
    if not cases:
        raise ValueError("Cases metadata is empty")
    for case in cases:
        if case.get("difficulty") is not None and not isinstance(case["difficulty"], str):
            raise ValueError("Case difficulty must be a string or null")
        case["difficulty"] = case.get("difficulty") or "unspecified"
    if manifest.get("dataset_cases") is not None and manifest["dataset_cases"] != len(cases):
        raise ValueError("Cases metadata count does not match the run manifest")
    metadata = {row["id"]: row for row in cases}
    if len(metadata) != len(cases):
        raise ValueError("Cases metadata contains duplicate IDs")
    unknown = {record.get("id") for record in records} - set(metadata)
    if unknown:
        raise ValueError(f"Checkpoint contains cases absent from metadata: {sorted(map(str, unknown))}")
    for record in records:
        for key in ("schema_id", "difficulty", "question"):
            if record.get(key) is None and record.get("id") in metadata:
                record[key] = metadata[record["id"]].get(key)
    summary = read_json(run / "results.json", {})
    supplied_config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else None
    # The manifest records the settings used for requests; an edited config is not
    # evidence that the completed run used new budgets or request parameters.
    config = manifest.get("config") or supplied_config or {}
    if manifest.get("fingerprint") and summary.get("fingerprint") and manifest["fingerprint"] != summary["fingerprint"]:
        raise ValueError("Manifest and summary fingerprints disagree")
    config_models = model_mapping(config)
    summary_models = summary.get("models", {})
    if not isinstance(summary_models, dict):
        summary_models = {}
    manifest_models = model_mapping(manifest.get("config") or {})
    supplied_models = model_mapping(supplied_config) if supplied_config is not None else {}
    if manifest_models and supplied_config is not None:
        if set(supplied_models) != set(manifest_models) or any(supplied_models[label]["model_id"] != manifest_models[label]["model_id"] for label in supplied_models):
            raise ValueError("Supplied config models do not match the run manifest")
    if config_models:
        unknown_models = (set(summary_models) | {row["model"] for row in records}) - set(config_models)
        if unknown_models:
            raise ValueError(f"Checkpoint or summary contains unconfigured models: {sorted(unknown_models)}")
    for label in set(config_models) | set(manifest_models) | set(summary_models):
        identities = {source.get(label, {}).get("model_id") for source in (config_models, manifest_models, summary_models)}
        identities.discard(None)
        if len(identities) > 1:
            raise ValueError(f"Model ID mismatch for label {label}: {sorted(identities)}")
    for row in records:
        identities = {row.get("model_id")}
        identities.update(source.get(row["model"], {}).get("model_id") for source in (config_models, manifest_models, summary_models))
        identities.discard(None)
        if len(identities) > 1:
            raise ValueError(f"Model ID mismatch for label {row['model']}: {sorted(identities)}")
    for label in {row["model"] for row in records}:
        if len({row.get("model_id") for row in records if row["model"] == label}) > 1:
            raise ValueError(f"Mixed model IDs in checkpoint for label {label}")
    labels = list(dict.fromkeys(list(config_models) + list(summary_models) + [r["model"] for r in records]))
    latest = {}
    by_model = defaultdict(list)
    for row in records:
        latest[row["model"], row["id"]] = row
        by_model[row["model"]].append(row)
    metrics, difficulties = [], []
    for label in labels:
        rows = [row for (model, _), row in latest.items() if model == label]
        metric, breakdown = summarize(label, by_model[label], rows, cases, config_models.get(label, {}), summary_models.get(label, {}))
        metrics.append(metric)
        difficulties.extend(breakdown)
    complete = all(row["completed_cases"] == row["planned_cases"] for row in metrics) and bool(metrics)
    if complete:
        metrics.sort(key=lambda row: (-row["execution_accuracy_pct"], row["median_latency_all_latest_ms"] if row["median_latency_all_latest_ms"] is not None else float("inf")))
    failures = []
    for row in latest.values():
        if row.get("status", "completed") == "completed" and row.get("correct") is True:
            continue
        case = metadata.get(row["id"], {})
        error = row.get("error") or {}
        if row.get("status", "completed") != "completed":
            kind = row.get("status")
        elif row.get("input_valid") is False:
            kind = "classifier_rejection"
        elif row.get("valid_sql") is not True:
            kind = "invalid_or_missing_sql"
        else:
            kind = "execution_result_mismatch" if not error else "execution_error"
        failures.append({**row, "failure_kind": kind, "reference_sql": case.get("expected_sql"), "category": case.get("category"), "error_type": error.get("type"), "error_message": error.get("message")})
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "leaderboard.csv", metrics, list(metrics[0]) if metrics else ["model"])
    write_csv(output / "difficulty.csv", difficulties, ["model", "difficulty", "expected_cases", "completed_cases", "correct_cases", "accuracy_pct"])
    write_csv(output / "failures.csv", sorted(failures, key=lambda r: (r["model"], r["id"])), ["model", "model_id", "id", "schema_id", "difficulty", "category", "status", "failure_kind", "question", "sql", "reference_sql", "input_valid", "classification_explanation", "valid_sql", "correct", "attempts", "critique_rounds", "critique_approved", "critique_issues", "latency_ms", "error_type", "error_message"])
    accuracy_svg(output / "accuracy-by-difficulty.svg", metrics, difficulties)
    leaderboard_svg(output / "leaderboard.svg", metrics)
    lines = ["# Natural-language-to-SQL benchmark", "", f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} from {checkpoint_reference(checkpoint, output)}.", "", f"Dataset: **{len(cases)} questions across {len({c['schema_id'] for c in cases})} SQLite schemas**. Difficulty distribution: " + ", ".join(f"{n} {name}" for name, n in Counter(c['difficulty'] for c in cases).items()) + ".", "", "This evaluates the full application pipeline, using the same selected model for classification, SQL generation and critique. It is not a bare-model SQL-generation score. Each case receives its full schema and an empty history; reference SQL/results are used only by the evaluator. No embeddings or prior approved examples are used in this benchmark.", ""]
    if not complete:
        lines.extend(["**Partial run:** accuracy uses completed cases only. Blocked, interrupted and unstarted cases are not counted as incorrect. Unequal coverage can bias a ranking; models remain in configured order until all finish.", ""])
    if warnings:
        lines.extend(["Data notes: " + " ".join(warnings), ""])
    lines.extend(["## Results", "", "![Execution accuracy and latency](leaderboard.svg)", "", table(["Model", "Completed / planned", "Correct", "Execution accuracy", "Valid SQL", "Classifier rejects"], [[r["model"], f"{r['completed_cases']}/{r['planned_cases']}", r["correct_cases"], pct(r["execution_accuracy_pct"]), pct(r["valid_sql_pct"]), r["classifier_rejected_cases"]] for r in metrics]), "", "Execution accuracy compares generated result values to the reference on the fixture, preserving column order and duplicates. Aliases may differ. Row order is checked where the case requires it; numeric values use absolute tolerance 1e-6. Truncated results and completed errors fail. Valid SQL is the runner's SQLite validation flag; it does not establish that the query answers the question. All dataset inputs are intended to be valid database questions, so recorded classifier rejections fail the case.", "", "## Difficulty", "", "![Execution accuracy by difficulty](accuracy-by-difficulty.svg)", "", table(["Model", "Difficulty", "Correct / completed", "Expected", "Accuracy"], [[r["model"], r["difficulty"], f"{r['correct_cases']}/{r['completed_cases']}", r["expected_cases"], pct(r["accuracy_pct"])] for r in difficulties]), "", "## Latency", "", table(["Model", "All latest cases: median / p95", "Correct cases: median / p95", "Blocked / interrupted / unstarted"], [[r["model"], f"{fmt((r['median_latency_all_latest_ms'] / 1000) if r['median_latency_all_latest_ms'] is not None else None)} / {fmt((r['p95_latency_all_latest_ms'] / 1000) if r['p95_latency_all_latest_ms'] is not None else None)} s", f"{fmt((r['median_latency_correct_ms'] / 1000) if r['median_latency_correct_ms'] is not None else None)} / {fmt((r['p95_latency_correct_ms'] / 1000) if r['p95_latency_correct_ms'] is not None else None)} s", f"{r['blocked_cases']} / {r['interrupted_cases']} / {r['not_observed_cases']}"] for r in metrics]), "", "All-latest latency uses the last recorded attempt for each observed case, including infrastructure-blocked and interrupted attempts. Correct-case latency includes only completed cases with matching results. This report recomputes percentiles from raw records; they can differ from the runner summary's nearest-observation percentiles. These are end-to-end per-case durations recorded by the runner, including model calls, validation, critique, repairs and execution; they exclude worker-queue waiting. Superseded attempts' durations are not added to a later case's latency. p95 uses linear interpolation. Parallel request contention affects latency; these are not isolated model-speed measurements.", "", "## Calls, tokens and cost", "", table(["Model", "HTTP attempts", "Input / output tokens", "Cached input / reasoning tokens", "Estimated cost", "Provider-reported cost"], [[r["model"], r["http_attempts"], f"{fmt(r['input_tokens'], 0)} / {fmt(r['output_tokens'], 0)}", f"{fmt(r['cached_input_tokens'], 0)} / {fmt(r['reasoning_tokens'], 0)}", cost_cell(r, "estimated_cost_usd"), cost_cell(r, "provider_cost_usd")] for r in metrics]), "", "Tokens and costs sum the actual usage objects from **all checkpoint records**, including superseded blocked attempts and retries. Missing values are left unavailable rather than treated as measured zero. Cached-input and reasoning tokens are subsets, not extra tokens to add to input/output totals. Estimated cost applies the configured model prices to actual recorded input/output usage, with cache pricing when configured; it is not an invoice. Provider-reported cost is shown only when returned. A partial cost total means at least one HTTP attempt lacks that cost field; a timed-out request may still have consumed unreported work. Unreported usage, taxes or other provider fees are not included.", "", table(["Model", "Successful HTTP calls", "Missing token usage", "Calls with cost estimate", "Calls with provider cost"], [[r["model"], r["successful_http_calls"], r["usage_missing_successful_calls"], r["estimated_cost_usd_observed_calls"], r["provider_cost_usd_observed_calls"]] for r in metrics]), "", "## Revisions and critique", "", table(["Model", "Generation passes", "SQL revisions", "Cases revised", "Critique rounds", "Critic approved / rejected / unreviewed", "Approved but incorrect"], [[r["model"], r["sql_generation_passes_completed"], r["sql_revisions_completed"], r["cases_with_sql_revisions"], r["critique_rounds_completed"], f"{r['critic_approved_cases']} / {r['critic_rejected_cases']} / {r['critic_not_reviewed_cases']}", r["critic_approved_incorrect_cases"]] for r in metrics]), "", "These counts use the final completed record for each case. SQL revisions are max(generation attempts − 1, 0), covering both SQLite-error repairs and critic-requested rewrites; the available telemetry does not separate those causes. Critic approval and execution correctness are independent measurements. The final SQL is scored even when the critic rejects it. A model-response failure can leave proposal-level attempt/critique counters unset; recorded logical calls below still capture completed work before the failure.", "", table(["Model", "Classifier logical calls", "Generator logical calls", "Critic logical calls", "Superseded checkpoint records"], [[r["model"], r["classify_logical_calls"], r["generate_logical_calls"], r["critique_logical_calls"], r["superseded_records"]] for r in metrics]), "", "Logical-call totals above include all attempts in the checkpoint; HTTP attempts also include transport retries.", "", "## Method and limits", "", "- This is a single run on this project's synthetic development dataset, not Spider/BIRD or a representative production workload.", "- One fixed data fixture per question can let a semantically wrong query happen to return the expected rows. A match is not proof of SQL equivalence on every database.", "- Difficulty labels are local author judgments. The run does not measure follow-up conversation, hybrid retrieval quality, or safety on adversarial/unanswerable requests.", "- Empty case histories prevent within-run examples from leaking between cases. This does not establish that a model never saw similar public material during training.", "- Sampling and provider execution can vary. Small score differences need repeated runs or more fixtures before drawing a strong model-quality conclusion.", "- Classifier, generator and critic share one model in each configuration; the score includes their combined decisions and the configured retry budget. The terminal human-review step is excluded.", ""])
    lines.extend(["## Model identity", "", table(["Label", "Requested model ID", "Observed response model IDs"], [[r["model"], r["model_id"], ", ".join(sorted({call["response_model"] for record in by_model[r["model"]] for call in (record.get("calls") or []) if call.get("response_model")})) or "Unavailable"] for r in metrics]), ""])
    if config:
        lines.extend([f"Configured budgets: {config.get('max_repairs', 5)} SQLite-error repairs and {config.get('max_critiques', 3)} critique rounds. Request settings are preserved in the run configuration.", ""])
    if summary.get("fingerprint"):
        lines.extend([f"Run fingerprint: `{summary['fingerprint']}`.", ""])
    lines.extend(["Artifacts: [leaderboard.csv](leaderboard.csv), [difficulty.csv](difficulty.csv), [failures.csv](failures.csv), [accuracy/latency comparison](leaderboard.svg), [difficulty chart](accuracy-by-difficulty.svg). Failures include blocked/interrupted records, separately labeled; reference SQL appears only in this post-run report.", ""])
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"output_dir": str(output), "models": len(metrics), "completed_cases": sum(r["completed_cases"] for r in metrics), "all_complete": complete, "warnings": warnings}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output-dir", type=Path)
    generate(parser.parse_args())


if __name__ == "__main__":
    main()
