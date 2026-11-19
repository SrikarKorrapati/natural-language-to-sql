"""Classifier routing and context, using controlled model decisions."""

import json

import pytest

from app.agent import SQLAgent
from app.db import History
from app.main import chat
from app.retrieval import Retriever
from benchmarks.run import load_database, run


@pytest.fixture
def source(tmp_path):
    return load_database("s01_retail", tmp_path)


@pytest.fixture
def history(tmp_path, source):
    return History(tmp_path / "history.db", dataset=str(source.path))


@pytest.mark.parametrize("question", [
    "hi", "tell me a joke", "what's the weather?", "asdfgh",
    "Show employee salaries", "Delete all customers",
])
def test_rejected_decision_stops_before_retrieval_and_generation(
    source, history, monkeypatch, question
):
    history.save("session", "List customers", "model", "SELECT name FROM customers")
    before = history.successful()
    calls = []

    def classify(model, messages):
        calls.append(messages)
        assert messages[-1]["content"] == question
        return {"valid": False, "explanation": "Please restate your database question."}

    def unexpected(*_):
        pytest.fail("Rejected input must not reach downstream work")

    agent = SQLAgent(
        source, history, classify_complete=classify, complete=unexpected,
        critique_complete=unexpected, retriever=Retriever(unexpected),
    )
    # Candidate loading itself is skipped, as well as embedding and SQL operations.
    monkeypatch.setattr(history, "successful", unexpected)
    monkeypatch.setattr(source, "validate", unexpected)
    monkeypatch.setattr(source, "execute", unexpected)
    monkeypatch.setattr(history, "save", unexpected)
    result = agent.propose(question, "session", "model")
    assert len(calls) == 1
    assert result["input_valid"] is False
    assert result["sql"] is None
    assert result["explanation"] == result["classification_explanation"]
    assert result["attempts"] == result["critique_rounds"] == 0
    assert result["validation_error"] is result["critique_approved"] is None
    assert result["examples"] == []
    assert result["retrieval_mode"] == "none"
    assert History(history.path, history.dataset).successful() == before


def test_context_is_scoped_shared_and_classification_runs_once_before_repairs(
    source, history, monkeypatch
):
    for i in range(8):
        history.save("session", f"List customers {i}", "model", "SELECT name FROM customers")
    history.save("elsewhere", "OTHER_SESSION", "model", "SELECT 1")
    History(history.path, "other-database").save("session", "OTHER_DATABASE", "model", "SELECT 1")
    expected = history.recent("session")
    events, classifier_contexts = [], []
    read_schema = source.schema
    schema_reads = []

    def schema():
        schema_reads.append(1)
        return read_schema()

    monkeypatch.setattr(source, "schema", schema)

    def classify(model, messages):
        events.append("classify")
        context = json.loads(messages[1]["content"])
        classifier_contexts.append(context)
        assert context["schema"] == [table["sql"] for table in read_schema()]
        assert context["conversation"] == [
            {"question": item["question"], "sql": item["sql"]} for item in expected
        ]
        assert len(context["conversation"]) == 6
        assert messages[-1]["content"] == "Only North"
        assert "OTHER_SESSION" not in json.dumps(messages)
        assert "OTHER_DATABASE" not in json.dumps(messages)
        assert "successful_examples" not in context
        return {"valid": True, "explanation": "Filters the earlier customer query."}

    def embed(texts):
        events.append("retrieve")
        assert texts[0] == "Only North List customers 6 List customers 7"
        return [[1, 0] for _ in texts]

    def generate(model, messages):
        events.append("generate")
        context = json.loads(messages[1]["content"])
        assert context["schema"] == classifier_contexts[0]["schema"]
        assert context["conversation"] == classifier_contexts[0]["conversation"]
        sql = "SELECT absent" if events.count("generate") == 1 else "SELECT name FROM customers WHERE region = 'North'"
        return {"sql": sql, "explanation": "Customer names."}

    def critique(*_):
        events.append("critique")
        return {"approved": True, "issues": []}

    result = SQLAgent(
        source, history, classify_complete=classify, complete=generate,
        critique_complete=critique, retriever=Retriever(embed),
    ).propose("Only North", "session", "model")
    assert events == ["classify", "retrieve", "generate", "generate", "critique"]
    assert len(schema_reads) == 1
    assert result["input_valid"] is True
    assert result["attempts"] == 2
    assert result["critique_approved"] is True


@pytest.mark.parametrize("decision", [
    None, {}, {"valid": "true", "explanation": "Not a boolean."},
    {"valid": 1, "explanation": "Not a boolean."}, {"valid": True},
    {"valid": False, "explanation": None}, {"valid": True, "explanation": " "},
])
def test_malformed_classifier_decision_returns_to_chat_without_generation(
    source, history, monkeypatch, capsys, decision
):
    agent = SQLAgent(
        source, history, classify_complete=lambda *_: decision,
        complete=lambda *_: pytest.fail("Malformed decisions must stop generation"),
    )
    answers = iter(["List customers", "/exit"])

    def reply(prompt):
        assert prompt == "\nAsk> "
        return next(answers)

    monkeypatch.setattr("builtins.input", reply)
    chat(agent, "session", "model")
    assert "classifier returned an invalid decision" in capsys.readouterr().out
    assert history.successful() == []


def test_benchmark_records_classifier_rejection():
    def factory(database, history):
        return SQLAgent(
            database, history,
            classify_complete=lambda *_: {"valid": False, "explanation": "Please clarify."},
            complete=lambda *_: pytest.fail("Rejected request must not generate SQL"),
        )

    cases = [{"id": "rejected", "schema_id": "s01_retail", "question": "Unclear",
              "expected_sql": "SELECT 1"}]
    result = run(["model"], cases, agent_factory=factory)["models"]["model"]["results"][0]
    assert result["input_valid"] is False
    assert result["classification_explanation"] == "Please clarify."
    assert result["error"] == "No SQL generated: Please clarify."
    assert result["attempts"] == 0
    assert not result["valid_sql"] and not result["correct"]
