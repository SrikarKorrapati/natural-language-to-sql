"""Offline tests for hybrid ranking, fresh embeddings, fallback, and history scope."""

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
    # Keyword order is 0, 1; semantic order is 2, 1, 0, 3.
    # RRF puts 0 just ahead of 1 and includes the semantic-only synonym 2.
    assert retriever.rank(query, documents, 3) == ([0, 1, 2], "hybrid")


def test_equal_rank_weights_balance_opposite_rankings():
    query = "revenue cost"
    documents = ["revenue", "revenue cost forecast"]
    vectors = {query: [1, 0], documents[0]: [1, 0], documents[1]: [0, 1]}
    retriever = Retriever(lambda texts: [vectors[text] for text in texts])
    assert keyword_rank(query, documents) == [1, 0]
    # Opposite first/second ranks contribute equally; input order breaks the tie.
    assert retriever.rank(query, documents, 2) == ([0, 1], "hybrid")


def test_semantic_search_finds_synonyms_and_uses_cosine_similarity():
    # A much larger vector must not outrank a closer direction after normalization.
    vectors = {"buyers": [1, 0], "customers": [3, 0], "products": [100, 100]}
    retriever = Retriever(lambda texts: [vectors[text] for text in texts])
    assert keyword_rank("buyers", ["customers", "products"]) == []
    assert retriever.rank("buyers", ["customers", "products"], 1) == ([0], "hybrid")


def test_every_search_embeds_the_query_and_all_history_questions():
    batches = []

    def embed(texts):
        batches.append(list(texts))
        return [[1, 2] for _ in texts]

    retriever = Retriever(embed)
    documents = ["List customers", "past question", "past question"]
    # Identical searches still request every vector, including repeated question text.
    assert retriever.rank("question", documents, 3)[1] == "hybrid"
    assert retriever.rank("question", documents, 3)[1] == "hybrid"
    assert (
        retriever.rank("question", [*documents, "new history question"], 3)[1]
        == "hybrid"
    )
    assert retriever.rank("changed question", documents, 3)[1] == "hybrid"
    assert batches == [
        ["question", *documents],
        ["question", *documents],
        ["question", *documents, "new history question"],
        ["changed question", *documents],
    ]


def test_every_search_uses_its_own_vectors_and_dimensions():
    responses = iter(
        [
            [[1, 0], [1, 0], [0, 1]],
            [[1, 0, 0], [0, 1, 0], [1, 0, 0]],
        ]
    )
    retriever = Retriever(lambda texts: next(responses))
    # The same question can get different vectors; only the current response is used.
    assert retriever.rank("buyers", ["customers", "products"], 1) == ([0], "hybrid")
    assert retriever.rank("buyers", ["customers", "products"], 1) == ([1], "hybrid")


def test_embedding_failure_falls_back_clearly_for_each_question(capsys):
    calls = []

    def unavailable(texts):
        calls.append(texts)
        raise RuntimeError("Provider detail that should not be printed")

    retriever = Retriever(unavailable)
    documents = ["customers in the North", "shipping rates", "customers in the South"]
    assert retriever.rank("customers", documents, 3) == ([0, 2], "keyword")
    message = capsys.readouterr().err.lower()
    assert "keyword" in message and "runtimeerror" in message
    assert "provider detail" not in message
    assert retriever.rank("customers", documents, 3) == ([0, 2], "keyword")
    assert "keyword-only" in capsys.readouterr().err
    assert calls == [["customers", *documents], ["customers", *documents]]


def test_embeddings_can_recover_on_the_next_question(capsys):
    calls = []

    def embed(texts):
        calls.append(list(texts))
        if len(calls) == 1:
            raise RuntimeError("Temporarily unavailable")
        return [[1, 0], [1, 0], [0, 1]]

    retriever = Retriever(embed)
    assert retriever.rank("buyers", ["customers", "products"], 1) == ([], "keyword")
    assert "keyword-only" in capsys.readouterr().err
    assert retriever.rank("buyers", ["customers", "products"], 1) == ([0], "hybrid")
    assert capsys.readouterr().err == ""
    assert len(calls) == 2


# Each malformed response is rejected before semantic ranking can use its vectors.
@pytest.mark.parametrize(
    "vectors",
    [
        [[0, 0], [1, 0]],
        [[1, 0]],
        [[1, 0], [1, 0], [1, 0]],
        [[float("nan"), 1], [1, 0]],
        [[1, 0], [1, 0, 0]],
        [],
    ],
)
def test_invalid_embedding_response_uses_keyword_fallback(vectors, capsys):
    retriever = Retriever(lambda texts: vectors)
    assert retriever.rank("customers", ["customers"], 1) == ([0], "keyword")
    assert "keyword-only" in capsys.readouterr().err


@pytest.mark.parametrize("separate_provider", [False, True])
def test_embedding_provider_configuration_and_independent_retrievers(
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
        vectors = [[1, 0], [0, 1], [-1, 0], [1, 1]]
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "configured-model",
                "data": [
                    {"object": "embedding", "index": i, "embedding": vectors[i]}
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
    documents = ["inventory", "shipping", "customers"]
    # API indexes associate inputs with vectors even when response rows are reversed.
    assert first.rank("buyers", documents, 3) == ([2, 0, 1], "hybrid")
    assert first.rank("buyers", documents, 3) == ([2, 0, 1], "hybrid")
    second = configured_retriever()
    assert second is not first
    assert second.rank("buyers", documents, 3) == ([2, 0, 1], "hybrid")
    assert len(requests) == 3
    assert all(
        json.loads(request.content)["input"] == ["buyers", *documents]
        for request in requests
    )
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
    third = configured_retriever()
    assert third is not first
    assert third.rank("buyers", documents, 3) == ([2, 0, 1], "hybrid")
    assert json.loads(requests[-1].content)["model"] == "another-model"


def test_explicit_keyword_mode_never_constructs_embedding_client(monkeypatch):
    import app.retrieval as retrieval_module

    monkeypatch.setenv("RETRIEVAL_MODE", "keyword")
    monkeypatch.setattr(
        retrieval_module,
        "OpenAI",
        lambda **kwargs: pytest.fail("Unexpected provider call"),
    )
    retriever = configured_retriever()
    assert retriever.rank("customers", ["customers", "orders"], 2) == ([0], "keyword")


def test_empty_candidates_do_not_request_embeddings():
    retriever = Retriever(lambda texts: pytest.fail("No history to embed"))
    assert retriever.rank("customers", [], 3) == ([], "none")


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

    # Repeated questions still load the current schema and request fresh embeddings.
    with sqlite3.connect(path) as connection:
        connection.execute("ALTER TABLE unrelated_c ADD COLUMN note TEXT")
    agent.propose(question, "session", "test-model")
    assert contexts[-1]["schema"] == [table["sql"] for table in database.schema()]
    assert any("note TEXT" in ddl for ddl in contexts[-1]["schema"])
    assert not any("note TEXT" in ddl for ddl in contexts[0]["schema"])
    assert batches == [[question, previous_question], [question, previous_question]]


def test_empty_history_sends_full_schema_without_retrieval(tmp_path, monkeypatch):
    database = load_database("s01_retail", tmp_path)
    history = History(tmp_path / "history.db", dataset=str(database.path))
    retriever = Retriever()
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


def test_history_scope_limits_question_only_embeddings_and_updated_candidates(
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
    # A new history entry changes the candidate pool; all current candidates are sent.
    agent.propose("Customer spending", "session", "test-model")
    assert len(batches) == 2
    assert batches[-1] == [
        "Customer spending Session question 6 Session question 7",
        *(item["question"] for item in history.successful()),
    ]
    assert len(batches[-1]) == 201
    assert "Fresh receipt question" in batches[-1]


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
    assert len(requests) == 2
    assert all(
        str(request.url) == "https://chat-only.test/v1/embeddings"
        for request in requests
    )
