"""Offline tests for hybrid ranking, embedding reuse, fallback, and history scope."""

import json
import sqlite3

import httpx
import pytest
from openai import OpenAI

from app.agent import SQLAgent
from app.db import Database, History
from app.retrieval import Retriever, configured_retriever, keyword_rank
from benchmarks.run import load_database


def test_rank_fusion_uses_both_rankings_instead_of_raw_scores():
    query = "revenue"
    documents = ["revenue revenue", "revenue cost", "turnover", "expenses"]
    # Small, fixed vectors control semantic rankings without an embedding API.
    vectors = {
        query: [1, 0],
        documents[0]: [0.6, 0.8],
        documents[1]: [0.8, 0.6],
        documents[2]: [1, 0],
        documents[3]: [-1, 0],
    }
    retriever = Retriever(lambda texts: [vectors[text] for text in texts])
    assert keyword_rank(query, documents) == [0, 1]
    assert retriever.prepare([query, *documents])
    # Keyword order is 0, 1; semantic order is 2, 1, 0, 3.
    # RRF puts 0 just ahead of 1 and includes the semantic-only synonym 2.
    assert retriever.rank(query, documents, 3) == [0, 1, 2]


def test_equal_rank_weights_balance_opposite_rankings():
    query = "revenue cost"
    documents = ["revenue", "revenue cost forecast"]
    vectors = {query: [1, 0], documents[0]: [1, 0], documents[1]: [0, 1]}
    retriever = Retriever(lambda texts: [vectors[text] for text in texts])
    assert keyword_rank(query, documents) == [1, 0]
    retriever.prepare([query, *documents])
    # Opposite first/second ranks contribute equally; input order breaks the tie.
    assert retriever.rank(query, documents, 2) == [0, 1]


def test_semantic_search_finds_synonyms_and_uses_cosine_similarity():
    # A much larger vector must not outrank a closer direction after normalization.
    vectors = {"buyers": [1, 0], "customers": [3, 0], "products": [100, 100]}
    retriever = Retriever(lambda texts: [vectors[text] for text in texts])
    assert keyword_rank("buyers", ["customers", "products"]) == []
    retriever.prepare(list(vectors))
    assert retriever.rank("buyers", ["customers", "products"], 1) == [0]


def test_cache_embeds_only_new_or_changed_text():
    batches = []

    def embed(texts):
        batches.append(list(texts))
        return [[1, 2] for _ in texts]

    retriever = Retriever(embed)
    initial = ["question", "List customers", "past question"]
    # Repeated text is deduplicated within a batch and reused across later batches.
    assert retriever.prepare([*initial, "past question"])
    assert retriever.prepare(initial)
    assert retriever.prepare([*initial, "new history question"])
    assert retriever.prepare(["question", "List customer names"])
    assert batches == [
        initial,
        ["new history question"],
        ["List customer names"],
    ]


def test_embedding_failure_falls_back_clearly_and_does_not_repeat(capsys):
    calls = []

    def unavailable(texts):
        calls.append(texts)
        raise RuntimeError("Provider detail that should not be printed")

    retriever = Retriever(unavailable)
    documents = ["customers in the North", "shipping rates", "customers in the South"]
    assert not retriever.prepare(["customers", *documents])
    message = capsys.readouterr().err.lower()
    assert "keyword" in message and "runtimeerror" in message
    assert "provider detail" not in message
    assert retriever.rank("customers", documents, 3) == [0, 2]
    assert not retriever.prepare(["customers", *documents])
    assert len(calls) == 1


# Cover a zero vector, the wrong response count, and a non-finite vector.
@pytest.mark.parametrize("vectors", [[[0, 0]], [[1, 0], [1, 0]], [[float("nan"), 1]]])
def test_invalid_embedding_response_uses_keyword_fallback(vectors, capsys):
    retriever = Retriever(lambda texts: vectors)
    assert not retriever.prepare(["customers"])
    assert retriever.rank("customers", ["customers"], 1) == [0]
    assert "keyword-only" in capsys.readouterr().err


@pytest.mark.parametrize("separate_provider", [False, True])
def test_embedding_provider_configuration_and_process_cache(
    monkeypatch, separate_provider
):
    import app.retrieval as retrieval_module

    for name in ("EMBEDDING_MODEL", "EMBEDDING_BASE_URL", "EMBEDDING_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RETRIEVAL_MODE", "hybrid")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://chat.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "chat-test-key")
    if separate_provider:
        monkeypatch.setenv("EMBEDDING_BASE_URL", "https://vectors.test/v1")
        monkeypatch.setenv("EMBEDDING_API_KEY", "vector-test-key")
        monkeypatch.setenv("EMBEDDING_MODEL", "custom-vector-model")
    requests = []

    def respond(request):
        requests.append(request)
        inputs = json.loads(request.content)["input"]
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "configured-model",
                "data": [
                    {"object": "embedding", "index": i, "embedding": [i + 1, 1]}
                    for i in reversed(range(len(inputs)))
                ],
                "usage": {"prompt_tokens": len(inputs), "total_tokens": len(inputs)},
            },
        )

    def client(**kwargs):
        return OpenAI(
            http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs
        )

    monkeypatch.setattr(retrieval_module, "OpenAI", client)
    first = configured_retriever()
    assert first.prepare(["provider configuration query", "past customer question"])
    second = configured_retriever()
    assert second is first
    assert second.prepare(["provider configuration query", "past customer question"])
    assert len(requests) == 1
    # API indexes associate inputs with vectors even when response rows are reversed.
    assert first.cache["provider configuration query"] == pytest.approx([2**-0.5] * 2)
    request = requests[0]
    assert request.url.host == ("vectors.test" if separate_provider else "chat.test")
    assert request.url.path == "/v1/embeddings"
    key = "vector-test-key" if separate_provider else "chat-test-key"
    assert request.headers["authorization"] == f"Bearer {key}"
    body = json.loads(request.content)
    assert body["model"] == (
        "custom-vector-model" if separate_provider else "text-embedding-3-small"
    )
    assert body["encoding_format"] == "float"
    monkeypatch.setenv("EMBEDDING_MODEL", "another-model")
    assert configured_retriever() is not first


def test_explicit_keyword_mode_never_constructs_embedding_client(monkeypatch):
    import app.retrieval as retrieval_module

    monkeypatch.setenv("RETRIEVAL_MODE", "keyword")
    monkeypatch.setattr(
        retrieval_module,
        "OpenAI",
        lambda **kwargs: pytest.fail("Unexpected provider call"),
    )
    retriever = configured_retriever()
    assert not retriever.prepare(["customers", "orders"])
    assert retriever.rank("customers", ["customers", "orders"], 2) == [0]


def test_full_schema_sent_each_time_and_only_history_questions_embedded(tmp_path):
    path = tmp_path / "source.db"
    # Unrelated tables and a view prove retrieval never narrows the schema.
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id REFERENCES customers(id));
            CREATE TABLE items (id INTEGER PRIMARY KEY, order_id REFERENCES orders(id));
            CREATE VIEW customer_names AS SELECT name FROM customers;
            CREATE TABLE unrelated_a (value TEXT);
            CREATE TABLE unrelated_b (value TEXT);
            CREATE TABLE unrelated_c (value TEXT);
        """)
    batches, contexts = [], []

    def embed(texts):
        batches.append(list(texts))
        return [[1, 0] for _ in texts]

    def complete(model, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return {"sql": "SELECT 1", "explanation": "One."}

    database = Database(path)
    history = History(tmp_path / "history.db", dataset=str(path))
    previous_question = "List customer names"
    history.save("past", previous_question, "test", "SELECT name FROM customers")
    agent = SQLAgent(database, history, complete=complete, retriever=Retriever(embed))
    question = "Who purchased recently?"
    proposal = agent.propose(question, "session", "test-model")
    schema = database.schema()
    assert proposal["retrieval_mode"] == "hybrid"
    assert proposal["tables"] == [table["name"] for table in schema]
    assert contexts[-1]["schema"] == [table["sql"] for table in schema]
    assert len(schema) == 7
    assert any("CREATE VIEW customer_names" in ddl for ddl in contexts[-1]["schema"])
    assert any("REFERENCES customers(id)" in ddl for ddl in contexts[-1]["schema"])
    assert batches == [[question, previous_question]]

    # Schema changes must appear even when the query and history embeddings are cached.
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE unrelated_c ADD COLUMN note TEXT")
    agent.propose(question, "session", "test-model")
    assert contexts[-1]["schema"] == [table["sql"] for table in database.schema()]
    assert any("note TEXT" in ddl for ddl in contexts[-1]["schema"])
    assert not any("note TEXT" in ddl for ddl in contexts[0]["schema"])
    assert batches == [[question, previous_question]]


def test_empty_history_sends_full_schema_without_retrieval(tmp_path, monkeypatch):
    database = load_database("s01_retail", tmp_path)
    history = History(tmp_path / "history.db", dataset=str(database.path))
    retriever = Retriever()
    monkeypatch.setattr(
        retriever, "prepare", lambda *_: pytest.fail("No history to embed")
    )
    monkeypatch.setattr(retriever, "rank", lambda *_: pytest.fail("No history to rank"))
    contexts = []

    def complete(model, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return {"sql": "SELECT 1", "explanation": "One."}

    proposal = SQLAgent(
        database, history, complete=complete, retriever=retriever
    ).propose("List customers", "session", "test-model")
    assert proposal["retrieval_mode"] == "none"
    assert proposal["examples"] == []
    assert contexts[0]["schema"] == [table["sql"] for table in database.schema()]


def test_history_scope_limits_question_only_embeddings_and_incremental_updates(
    tmp_path,
):
    source = load_database("s01_retail", tmp_path)
    history = History(tmp_path / "history.db", dataset=str(source.path))
    # Exceed the 200-history and six-turn limits to check which records reach context.
    for i in range(201):
        history.save(
            "archive",
            f"Archive question {i:03}",
            "test",
            f"SELECT {i} AS SQL_TEXT_MARKER",
        )
    for i in range(8):
        history.save(
            "session", f"Session question {i}", "test", f"SELECT {i} AS SQL_TEXT_MARKER"
        )
    other = History(history.path, dataset="another-database")
    other.save("session", "OTHER_DATABASE_QUESTION", "test", "SELECT 99")
    history.save("session", "FAILED_QUESTION", "test", "SELECT missing")
    # Simulate a legacy failed record; the current save() method only writes successes.
    with sqlite3.connect(history.path) as connection:
        connection.execute(
            "UPDATE queries SET status = 'failed' WHERE question = 'FAILED_QUESTION'"
        )
    batches, contexts = [], []

    def embed(texts):
        batches.append(list(texts))
        return [[1, 0] for _ in texts]

    def complete(model, messages):
        contexts.append(json.loads(messages[1]["content"]))
        return {"sql": "SELECT 1", "explanation": "One."}

    retriever = Retriever(embed)
    agent = SQLAgent(source, history, complete=complete, retriever=retriever)
    proposal = agent.propose("Customer spending", "session", "test-model")
    candidates = history.successful()
    assert len(candidates) == 200
    embedded = {text for batch in batches for text in batch}
    assert {item["question"] for item in candidates} <= embedded
    assert "Archive question 000" not in embedded
    # Distinct markers expose accidental SQL, schema, or excluded-history embeddings.
    assert not any(
        "CREATE TABLE" in text
        or "SQL_TEXT_MARKER" in text
        or "FAILED_QUESTION" in text
        or "OTHER_DATABASE_QUESTION" in text
        for text in embedded
    )
    assert [item["question"] for item in contexts[-1]["conversation"]] == [
        f"Session question {i}" for i in range(2, 8)
    ]
    assert len(proposal["examples"]) == 3
    selected_questions = {item["question"] for item in proposal["examples"]}
    assert selected_questions <= {item["question"] for item in candidates}
    assert all("SQL_TEXT_MARKER" in item["sql"] for item in proposal["examples"])
    history.save(
        "archive", "Fresh receipt question", "test", "SELECT 42 AS SQL_TEXT_MARKER"
    )
    # The same search reuses its cache and embeds only the newly saved question.
    agent.propose("Customer spending", "session", "test-model")
    assert batches[-1] == ["Fresh receipt question"]


def test_chat_only_provider_reports_keyword_mode_without_changing_endpoint(
    tmp_path, monkeypatch, capsys
):
    import app.retrieval as retrieval_module

    monkeypatch.setenv("RETRIEVAL_MODE", "hybrid")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://chat-only.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "chat-only-test-key")
    for name in ("EMBEDDING_BASE_URL", "EMBEDDING_API_KEY", "EMBEDDING_MODEL"):
        monkeypatch.delenv(name, raising=False)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            404,
            json={"error": {"message": "Embeddings unsupported", "type": "not_found"}},
        )

    monkeypatch.setattr(
        retrieval_module,
        "OpenAI",
        lambda **kwargs: OpenAI(
            http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs
        ),
    )
    source = load_database("s01_retail", tmp_path)
    history = History(tmp_path / "history.db", dataset=str(source.path))
    history.save("past", "List customers", "test", "SELECT name FROM customers")
    agent = SQLAgent(
        source,
        history,
        complete=lambda model, messages: {"sql": "SELECT 1", "explanation": "One."},
    )
    proposal = agent.propose("List customers", "session", "test")
    assert proposal["retrieval_mode"] == "keyword"
    assert proposal["examples"] == [
        {"question": "List customers", "sql": "SELECT name FROM customers"}
    ]
    assert "keyword-only" in capsys.readouterr().err
    assert (
        agent.propose("List products", "session", "test")["retrieval_mode"] == "keyword"
    )
    assert len(requests) == 1
    assert str(requests[0].url) == "https://chat-only.test/v1/embeddings"
