# Natural language to SQL

A small Python terminal app built with **LangGraph**. Ask a question, review or edit the generated SQL, and approve it to print results. It retrieves relevant schema and successful past queries, remembers conversation context, and repairs SQL validation errors.

## Run

Requires Python 3.11+. The benchmark fixtures require SQLite 3.39+ for RIGHT and FULL OUTER JOIN.

```bash
git clone https://github.com/SrikarKorrapati/natural-language-to-sql.git
cd natural-language-to-sql
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set `OPENAI_API_KEY` in your environment or the project's `.env`, then point the app at an existing SQLite database:

```bash
python -m app.main --database /absolute/path/to/data.db --model gpt-4.1-mini
```

The default model is `OPENAI_MODEL`, or `gpt-4.1-mini`. Optional `OPENAI_BASE_URL` selects an OpenAI-compatible Chat Completions provider with JSON mode. Use `--session sales-analysis` to start or resume a named conversation.

## Terminal workflow

The app prints SQL, a short explanation, and the attempt count, then asks:

```text
Run this SQL? [y/N/edit]:
```

Enter `y` to execute, press Enter to skip, or enter `edit` to replace the SQL. Finish multiline edits with a blank line and approve the replacement.

- `/new` starts a fresh conversation.
- `/schema` prints the schema.
- `/history` shows successful queries.
- `/exit` quits.

LangGraph runs **retrieve → generate → validate**, returning invalid SQL to the model for up to **five correction attempts** after the first proposal. Set `SQL_MAX_REPAIRS` to change that limit. Validation uses SQLite `EXPLAIN`; execution requires approval in the terminal. If validation still fails, edit or skip the final proposal.

Memory includes the last six approved, successful turns in the conversation. Historical retrieval uses successful queries from the same database. Both persist in `data/history.db`. Source databases open read-only, with a three-second execution limit and a 500-row result cap.

## Benchmark models

[Browse all 200 input → SQL pairs](benchmarks/pairs.md): **20 schemas × 10 questions**, with 60 easy, 80 medium, and 60 hard cases. The dataset covers filters, joins, aggregation, subqueries, set operations, recursive queries, windows, dates, NULLs, ties, and duplicate rows.

```bash
python -m benchmarks.run --models gpt-4.1-mini gpt-4.1
```

The runner creates the 20 fixture databases, generates SQL with empty memory for each case, and compares executed results with the reference SQL. It saves accuracy, SQL validity, latency, attempts, generated SQL, and errors to `benchmarks/results.json`. This runs the complete agent, including its correction attempts.

[Benchmark format and scoring](benchmarks/README.md). All 200 reference queries have been executed and checked locally; no model accuracy is claimed for this new dataset.

## Code and tests

Core code lives in three files: `app/main.py` for the terminal, `app/agent.py` for LangGraph and retrieval, and `app/db.py` for SQLite and memory. Tests use controlled model responses.

```bash
python -m pytest -q -p no:cacheprovider
```

The provider receives the question, selected schema, and relevant historical questions/SQL. Result rows stay local. `.env`, databases, and conversation history are excluded from Git.
