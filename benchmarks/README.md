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

Each model gets the same fixtures, full schema, and empty history for every question. As a result, `retrieval_mode` is `none` and the benchmark makes no embedding requests. This benchmark measures SQL generation and correction; evaluate hybrid history retrieval separately using conversations with prior approved queries. Reference SQL is executed locally. Generated SQL is read-only and runs automatically within the benchmark. The terminal app's human review step is excluded from evaluation.

Execution accuracy compares the result values, preserving duplicate rows and output-column order. Column aliases may differ. Row order matters when `order_sensitive` is true; otherwise rows are compared as a multiset. Numeric values use absolute tolerance `1e-6`. NULLs must match. Truncated results and errors fail the case.

The score includes up to five correction attempts. Set `SQL_MAX_REPAIRS=0` for a single-proposal comparison. Latency includes context preparation, generation, corrections, validation, and execution. Use the same retry budget and chat-provider settings when comparing models.

All 200 references were executed through the application's read-only boundary and reviewed against their questions. The fixtures include cases designed to expose common mistakes, such as join multiplication, omitted status filters, mishandled ties, and averaging at the wrong level. Tests check the exact 20×10 layout, foreign keys, and saved reference results.

Execution agreement on one fixture is not proof that two queries are equivalent for every possible database. These are small synthetic fixtures, useful for a reproducible development benchmark. No LLM scores have been recorded for this 200-case set.

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
