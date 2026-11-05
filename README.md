# Natural language to SQL

A small Python terminal app built with **LangGraph**. Ask a question, review or edit the generated SQL, and approve it to print results. It sends the full schema with every question, retrieves successful past queries using keyword and semantic search, remembers conversation context, and repairs SQL validation errors.

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

## Hybrid retrieval

Hybrid retrieval searches previous successful questions. Keyword and semantic rankings have equal weight: each contributes `1 / (60 + rank)` through reciprocal rank fusion. Raw keyword and cosine-similarity scores are never compared directly.

Configure embeddings in your environment or `.env`:

| Setting | Default | Purpose |
| --- | --- | --- |
| `RETRIEVAL_MODE` | `hybrid` | Set to `keyword` to use keyword retrieval without embedding requests |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model served by the embedding provider |
| `EMBEDDING_BASE_URL` | `OPENAI_BASE_URL`, otherwise `https://api.openai.com/v1` | OpenAI-compatible embedding endpoint |
| `EMBEDDING_API_KEY` | `OPENAI_API_KEY` | Credential for that endpoint |

A chat-compatible provider may not support embeddings. Set `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, and `EMBEDDING_MODEL` to a separate provider when needed. The endpoint must support the [embeddings API](https://developers.openai.com/api/reference/python/resources/embeddings/methods/create). An embedding failure prints a clear message and switches to keyword-only retrieval for the rest of the process. Restart after fixing the configuration to retry embeddings. Each proposal reports the history retrieval mode actually used. With no successful history, it reports `none` and makes no embedding requests.

Every question receives the full current schema: all table and view DDL, including declared foreign keys. Historical retrieval searches the question text of the latest **200 successful queries from the same database**, selecting up to **three examples** before including their SQL in the model prompt.

Embeddings are cached in process memory by provider configuration and text. Unchanged question text reuses its vector; new history questions are embedded as needed. The cache is shared across agent instances and cleared when the process exits. No vector database is needed.

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

See the [detailed SQL agent flow](docs/sql-agent-flow.md) for the graph, retry path, shared state, and post-graph approval step.

Memory includes the last six approved, successful turns in the conversation. Historical retrieval uses successful queries from the same database. Both persist in `data/history.db`. Source databases open read-only, with a three-second execution limit and a 500-row result cap.

## Benchmark models

[Browse all 200 input → SQL pairs](benchmarks/pairs.md): **20 schemas × 10 questions**, with 60 easy, 80 medium, and 60 hard cases. The dataset covers filters, joins, aggregation, subqueries, set operations, recursive queries, windows, dates, NULLs, ties, and duplicate rows.

```bash
python -m benchmarks.run --models gpt-4.1-mini gpt-4.1
```

The runner creates the 20 fixture databases, generates SQL with empty memory for each case, and compares executed results with the reference SQL. It saves accuracy, SQL validity, latency, attempts, generated SQL, retrieval mode, and errors to `benchmarks/results.json`. This runs the agent with the full schema and its correction attempts. Each case starts with empty history, so history retrieval reports `none` and makes no embedding requests.

[Benchmark format and scoring](benchmarks/README.md). All 200 reference queries have been executed and checked locally; no model accuracy is claimed for this new dataset.

## Code and tests

Core code lives in four files: `app/main.py` for the terminal, `app/agent.py` for LangGraph, `app/retrieval.py` for keyword and semantic retrieval, and `app/db.py` for SQLite and memory. Tests use controlled chat and embedding responses.

```bash
python -m pytest -q -p no:cacheprovider
```

## Privacy

When successful history exists, the **embedding provider** receives question text only: the current question with the last two successful question texts for follow-up context, plus up to 200 candidate historical questions from the same database. Schema and historical SQL are not embedded. Cached text is sent again only when an embedding is needed.

The **chat provider** receives the current question, the full current schema, up to six successful conversation turns with their SQL, and up to three retrieved question/SQL examples. These providers may be different when separate embedding settings are used.

Result rows stay local. `.env`, databases, and conversation history are excluded from Git. Embedding vectors remain in process memory.
