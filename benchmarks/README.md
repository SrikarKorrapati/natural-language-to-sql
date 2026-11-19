# SQL benchmark

**200 natural-language questions and reference SQL answers across 20 independent schemas.** Each schema has 10 cases: 3 easy, 4 medium, and 3 hard. All people, organizations, and records are fictional.

## Files

| File | Contents |
| --- | --- |
| [pairs.md](pairs.md) | Readable catalog of all 200 input → SQL pairs, grouped by schema |
| [cases.json](cases.json) | Machine-readable questions, reference SQL, schema IDs, difficulty, categories, features, and ordering rules |
| [schemas/](schemas/) | 20 SQL files containing table definitions, foreign keys, and deterministic seed data |
| [expected-results.jsonl](expected-results.jsonl) | Executed reference columns and rows, one case per line |
| [run.py](run.py) | Evaluator for one or more models |

The schema ID maps directly to `schemas/<schema_id>.sql`. Give the model the table definitions and question; keep reference SQL and expected results out of its prompt. The runner sends the full schema with every question.

## Coverage

- **Joins:** INNER, LEFT, RIGHT, FULL OUTER, CROSS, self joins, multi-table joins, composite keys, date-range joins, and anti joins.
- **Filtering and text:** comparisons, AND/OR, IN lists and subqueries, BETWEEN, LIKE, DISTINCT, LIMIT/OFFSET pagination, NULL handling, and string functions.
- **Aggregation:** COUNT, SUM, AVG, MIN/MAX, GROUP BY, HAVING, conditional and weighted aggregates, percentages, nested aggregation, and avoiding double counting across related tables.
- **Subqueries and sets:** scalar and correlated subqueries, EXISTS/NOT EXISTS, relational division, UNION, UNION ALL, INTERSECT, and EXCEPT.
- **Windows and recursion:** ROW_NUMBER, RANK, DENSE_RANK, PERCENT_RANK, NTILE, LAG, LEAD, running totals, moving averages, hierarchies, dependencies, and generated calendars.
- **Dates and edge cases:** fixed date ranges, historical prices and tariffs, overlapping intervals, ties, NULLs, missing matches, empty groups, repeated rows, zero denominators, and negative values.

These are read-only SQLite queries. DDL, writes, stored procedures, and dialect-specific features from other database engines are outside this benchmark. SQLite 3.39+ is required for RIGHT and FULL OUTER JOIN; validation used SQLite 3.42.

## Run and score

From the project root, with `OPENAI_API_KEY` configured:

```bash
python -m benchmarks.run --models gpt-4.1-mini gpt-4.1 --output benchmarks/results.json
```

Each model gets the same fixtures, full schema, and empty history for every question. As a result, `retrieval_mode` is `none` and the benchmark makes no embedding requests. This benchmark includes input classification, SQL generation, and correction; evaluate hybrid history retrieval separately using conversations with prior approved queries. Reference SQL is executed locally. Generated SQL is read-only and runs automatically within the benchmark. The terminal app's human review step is excluded from evaluation.

Execution accuracy compares the result values, preserving duplicate rows and output-column order. Column aliases may differ. Row order matters when `order_sensitive` is true; otherwise rows are compared as a multiset. Numeric values use absolute tolerance `1e-6`. NULLs must match. Truncated results and errors fail the case.

The score includes up to five SQLite error repairs and three critique rounds (the initial review plus at most two reviews of revised SQL). `SQL_MAX_REPAIRS=0` disables SQLite error repairs only; critique can still request revisions. Latency includes context preparation, classification, generation, repairs, validation, critique, and execution. Use the same budgets and chat-provider settings when comparing models.

Each result records `input_valid` and `classification_explanation`. A classifier rejection has zero generation attempts and fails the case; it never reaches retrieval or SQL generation. Each result also records `critique_rounds`, `critique_approved`, and `critique_issues`. The benchmark evaluates the final SQL even if the critic rejects it; execution accuracy and the critic's judgment are separate measurements. `critique_approved: null` means the final proposal was not reviewed, for example when it failed SQLite validation or requested clarification.

All 200 references were executed through the application's read-only boundary and reviewed against their questions. The fixtures include cases designed to expose common mistakes, such as join multiplication, omitted status filters, mishandled ties, and averaging at the wrong level. Tests check the exact 20×10 layout, foreign keys, and saved reference results.

Execution agreement on one fixture is not proof that two queries are equivalent for every possible database. These are small synthetic fixtures, useful for a reproducible development benchmark. The [November 19, 2026 ten-model evaluation](results-openai-10-2026-11-19/README.md) is published with [scores](results-openai-10-2026-11-19/report.md), [interpretation](results-openai-10-2026-11-19/analysis.md), charts, CSVs, and raw results. This snapshot is tracked in Git; other result directories remain ignored.

## Sources and provenance

These 200 cases and their fixtures were authored for this project with AI assistance, reviewed for question/SQL alignment, and executed locally. Difficulty labels describe this project's intended complexity. The dataset is an original synthetic development set.

The following public benchmarks were inspected to cross-check the design:

| Reference | Useful conventions |
| --- | --- |
| [Spider](https://github.com/taoyds/spider) | Questions tied to database schemas; multi-table queries, grouping, nested queries, and set operations |
| [Spider test-suite evaluation](https://github.com/taoyds/test-suite-sql-eval) | Evaluate query behavior across database contents; a result match on one fixture can miss semantic errors |
| [BIRD Mini-Dev](https://huggingface.co/datasets/birdsql/bird_mini_dev) | Explicit business definitions, NULL and zero rules, ranking ties, and dialect-specific SQL |
| [WikiSQL](https://github.com/salesforce/WikiSQL) | Single-table filtering and aggregation; separate logical-form and execution metrics |

Our coverage review used these references and added an explicit LIMIT/OFFSET case. Source questions, database records, and SQL files are not redistributed here. Public-benchmark scores require the corresponding original data and evaluator; this runner reports accuracy on the 200 local cases only. Use the official links above for those datasets and their release terms.

## Parallel model benchmark

The parallel runner compares configured models on all **200 questions across 20 SQLite schemas**: 60 easy, 80 medium and 60 hard. A configuration with 10 models creates 2,000 model–question evaluations. Each evaluation normally makes classifier, generator and critic calls; SQL corrections, critique revisions and transport retries can add calls.

Use the same model for all three roles within each configuration. Every case starts with its full schema and an empty history, so the benchmark makes no embedding requests and cannot reuse another case's approved SQL. Reference SQL and expected results stay outside model prompts. The score measures the application's full pipeline; the terminal's human approval step is excluded.

Put model IDs, provider URLs, credential **environment variable names**, request settings and published token prices in `benchmarks/models.openai.json`. Do not put API keys in this file. The runner reads credentials from the environment or the project's `.env` file. Model-specific request settings override shared settings; `max_tokens` replaces `max_completion_tokens` when supplied. JSON response formatting is set by the runner.

From the project root, activate the project's Python environment and validate fixtures/configuration without making model requests:

```bash
python -m benchmarks.parallel \
  --config benchmarks/models.openai.json \
  --output-dir benchmarks/results/openai-comparison \
  --dry-run
```

Run all configured models and all cases:

```bash
python -m benchmarks.parallel \
  --config benchmarks/models.openai.json \
  --output-dir benchmarks/results/openai-comparison \
  --workers 20 \
  --per-model-workers 2
```

Worker limits control concurrent **cases**, not requests per minute. Adjust concurrency to the provider's limits. A pilot can use `--case-ids s01_q01 s01_q04 s01_q08` in the same output directory; the full command then fills the remaining cases. `--models` accepts configured labels or model IDs. The `--limit-cases N` option takes the first N dataset cases, not a random sample.

Resume by repeating the same command; `--resume` is also accepted. Completed cases are skipped, while blocked/interrupted cases remain eligible. The runner fingerprints the model configuration, dataset, fixture SQL and application/evaluator sources. A changed fingerprint requires a new output directory. An interrupted run checkpoints completed in-flight work; no new model request starts after the runner's stop flag is observed.

Create the report locally, without further model calls:

```bash
python -m benchmarks.report \
  --run-dir benchmarks/results/openai-comparison \
  --cases benchmarks/cases.json
```

The report reads the configuration saved in `manifest.json`. An explicit `--config` is optional and must describe the same model IDs.

| Artifact | Contents |
| --- | --- |
| `manifest.json` | Model settings, source hashes, dataset fingerprint and launch history |
| `cases.jsonl` | Append-only checkpoint with SQL, outcomes, errors, stage calls and returned usage |
| `results.json` | Current machine-readable runner summary |
| `report.md` | Accuracy, validity, classification, latency, usage, revisions and limitations |
| `leaderboard.csv` / `leaderboard.svg` | Overall comparison with coverage and latency |
| `difficulty.csv` / `accuracy-by-difficulty.svg` | Easy/medium/hard performance |
| `failures.csv` | Final incorrect, blocked or interrupted cases with generated/reference SQL |

Execution accuracy compares returned values on the fixed fixture, preserving duplicates and output-column order. Aliases may differ; row order matters when the case says so. Numeric values use absolute tolerance `1e-6`; NULLs must match. Model-output errors, classifier rejections, invalid SQL and truncated results fail completed cases. Provider/authentication/connection errors are marked blocked, excluded from the completed accuracy denominator and shown through coverage; the runner stops scheduling further cases for that model during the launch. They are not model-quality failures.

The latest checkpoint record for each `(model label, case ID)` determines its outcome. Usage and estimated cost include **all** recorded calls, including superseded attempts and transport retries, so resuming does not hide earlier consumption. Missing usage/cost remains unknown; partial estimates are labeled. Estimates use returned token counts and the configured input/output/cache prices, not guessed tokens or an invoice.

The report distinguishes latency among all latest observed cases from latency among correct cases. It recomputes median/p95 with linear interpolation; these can differ from the runner summary's nearest-observation percentiles. End-to-end case timings include the pipeline and its corrections, exclude worker-queue waiting, and are affected by concurrency. SQL revisions are generation passes after the first, combining SQLite-error repairs and critic-requested rewrites; the current telemetry does not separate those causes.

This is one run on small synthetic development fixtures, not a public Spider/BIRD score or proof of general SQL equivalence. It does not evaluate conversation follow-ups, hybrid history retrieval, or adversarial/unanswerable-input safety. Compare models at equal completed coverage; repeat runs before relying on small differences.
