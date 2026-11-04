"""Hybrid ranking, embedding reuse, provider fallback, and retrieval boundaries."""

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


def test_semantic_search_finds_synonyms_and_uses_cosine_similarity():
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
    initial = ["question", "CREATE TABLE people (id INT)", "past question"]
    assert retriever.prepare([*initial, "past question"])
    assert retriever.prepare(initial)
    assert retriever.prepare([*initial, "new history question"])
    assert retriever.prepare(["question", "CREATE TABLE people (id INT, name TEXT)"])
    assert batches == [
        initial,
        ["new history question"],
        ["CREATE TABLE people (id INT, name TEXT)"],
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
    assert first.prepare(["provider configuration query", "customer schema"])
    second = configured_retriever()
    assert second is first
    assert second.prepare(["provider configuration query", "customer schema"])
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


def test_schema_embedding_includes_views_and_preserves_foreign_key_expansion(tmp_path):
    path = tmp_path / "source.db"
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
    embedded = []

    def embed(texts):
        embedded.extend(texts)
        ranks = {
            "orders": [1, 0],
            "unrelated_a": [0.9, 0.1],
            "unrelated_b": [0.8, 0.2],
            "unrelated_c": [0.7, 0.3],
        }
        return [
            (
                next(
                    (
                        vector
                        for name, vector in ranks.items()
                        if f"CREATE TABLE {name} " in text
                    ),
                    [0, 1],
                )
                if "CREATE " in text
                else [1, 0]
            )
            for text in texts
        ]

    database = Database(path)
    agent = SQLAgent(
        database,
        History(tmp_path / "history.db", dataset=str(path)),
        complete=lambda model, messages: {"sql": "SELECT 1", "explanation": "One."},
        retriever=Retriever(embed),
    )
    proposal = agent.propose("Who purchased recently?", "session", "test-model")
    assert proposal["retrieval_mode"] == "hybrid"
    assert set(proposal["tables"]) == {
        "orders",
        "customers",
        "items",
        "unrelated_a",
        "unrelated_b",
        "unrelated_c",
    }
    assert any("CREATE VIEW customer_names" in text for text in embedded)
    order_document = next(text for text in embedded if "CREATE TABLE orders " in text)
    assert "foreign_keys" in order_document and "customer_id" in order_document
    assert "customers" in order_document


def test_history_scope_limits_question_only_embeddings_and_incremental_updates(
    tmp_path,
):
    source = load_database("s01_retail", tmp_path)
    history = History(tmp_path / "history.db", dataset=str(source.path))
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
    assert not any(
        "SQL_TEXT_MARKER" in text
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
