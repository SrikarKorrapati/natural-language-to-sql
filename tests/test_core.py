"""Behavior tests for read-only execution, review, memory, and repair."""

import json
import sqlite3

import httpx
import pytest

from app.db import Database, History
from benchmarks.run import load_database


@pytest.fixture(autouse=True)
def keyword_retrieval(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_MODE", "keyword")


@pytest.fixture
def source(tmp_path):
    return load_database("s01_retail", tmp_path)


@pytest.fixture
def history(tmp_path, source):
    return History(tmp_path / "history.db", dataset=str(source.path))


def test_select_and_cte_with_comments(source):
    query = "-- reviewed query\n/* comment */ WITH c AS (SELECT 42 AS value) SELECT value FROM c"
    source.validate(query)
    assert source.execute(query)["rows"][0][0] == 42


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",
        "INSERT INTO customers VALUES (99, 'Injected', 'North')",
        "UPDATE customers SET name = 'Changed'",
        "DROP TABLE customers",
        "WITH c AS (SELECT 1) DELETE FROM customers",
        "SELECT 1; DELETE FROM customers",
        "SELECT 1; SELECT 2",
        "ATTACH DATABASE ':memory:' AS other",
        "PRAGMA query_only = OFF",
        "SELECT load_extension('anything')",
    ],
)
def test_read_only_boundary_rejects_unsafe_statements(source, sql):
    before = source.execute("SELECT id, name, region FROM customers ORDER BY id")[
        "rows"
    ]
    with pytest.raises(sqlite3.Error):
        source.validate(sql)
    with pytest.raises(sqlite3.Error):
        source.execute(sql)
    assert (
        source.execute("SELECT id, name, region FROM customers ORDER BY id")["rows"]
        == before
    )


def test_result_limit_is_reported_without_changing_aggregate(source):
    expected_count = len(source.execute("SELECT id FROM customers")["rows"])
    limited = Database(source.path, max_rows=3)
    result = limited.execute("SELECT id FROM customers ORDER BY id")
    assert [row[0] for row in result["rows"]] == [1, 2, 3]
    assert result["row_count"] == 3
    assert result["truncated"] is True
    total = limited.execute("SELECT COUNT(*) FROM customers")
    assert total["rows"][0][0] == expected_count
    assert total["truncated"] is False


def test_expensive_query_times_out(source):
    bounded = Database(source.path, timeout_seconds=0.005)
    sql = "WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x + 1 FROM n WHERE x < 100000000) SELECT SUM(x) FROM n"
    with pytest.raises(sqlite3.OperationalError, match="interrupted"):
        bounded.execute(sql)


def test_memory_is_scoped_to_conversation_and_database(history):
    history.save(
        "session-one",
        "Approved question",
        "test-model",
        "SELECT name FROM customers WHERE region = 'North'",
    )
    history.save(
        "session-two", "Other conversation", "test-model", "SELECT name FROM customers"
    )

    memory = history.recent("session-one")
    assert [item["question"] for item in memory] == ["Approved question"]
    assert "WHERE region" in memory[0]["sql"]
    assert {item["question"] for item in history.successful()} == {
        "Approved question",
        "Other conversation",
    }
    other_dataset = History(history.path, dataset="another-database")
    assert other_dataset.recent("session-one") == []
    assert other_dataset.successful() == []


def test_graph_repairs_invalid_sql_before_review(source, history):
    from app.agent import SQLAgent

    prompts = []

    def complete(model, messages):
        prompts.append(json.dumps(messages))
        sql = (
            "SELECT missing_column FROM customers"
            if len(prompts) == 1
            else "SELECT name FROM customers"
        )
        return {"sql": sql, "explanation": "List customer names."}

    result = SQLAgent(source, history, complete=complete, max_repairs=2).propose(
        "List customer names", "session-one", "test-model"
    )
    assert result["attempts"] == 2
    assert result["validation_error"] is None
    assert result["sql"] == "SELECT name FROM customers"
    assert "missing_column" in prompts[1]
    assert "customers" in prompts[0]
    assert history.successful() == []


@pytest.mark.parametrize("max_repairs", [0, 1, 2, 5])
def test_graph_has_a_finite_repair_budget(source, history, max_repairs):
    from app.agent import SQLAgent

    calls = []

    def complete(model, messages):
        calls.append(messages)
        return {"sql": "SELECT absent FROM customers", "explanation": "Invalid draft."}

    result = SQLAgent(
        source, history, complete=complete, max_repairs=max_repairs
    ).propose("List customers", "session-one", "test-model")
    assert len(calls) == max_repairs + 1
    assert result["attempts"] == max_repairs + 1
    assert result["validation_error"]


def test_repair_budget_can_be_configured_by_environment(source, history, monkeypatch):
    from app.agent import SQLAgent

    monkeypatch.setenv("SQL_MAX_REPAIRS", "1")
    assert SQLAgent(source, history).max_repairs == 1
    assert SQLAgent(source, history, max_repairs=0).max_repairs == 0


def test_model_adapter_uses_json_chat_completion(monkeypatch):
    import app.agent as agent_module
    from openai import OpenAI

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chat-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"sql":"SELECT 1","explanation":"Return one."}',
                        },
                    }
                ],
            },
        )

    def client(**kwargs):
        return OpenAI(
            api_key="test-only",
            base_url="https://provider.test/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
            **kwargs
        )

    monkeypatch.setattr(agent_module, "OpenAI", client)
    messages = [{"role": "user", "content": "Return SQL as JSON."}]
    assert agent_module.model_completion("test-model", messages) == {
        "sql": "SELECT 1",
        "explanation": "Return one.",
    }
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/chat/completions"
    body = json.loads(requests[0].content)
    assert body["model"] == "test-model"
    assert body["messages"] == messages
    assert body["response_format"] == {"type": "json_object"}


def test_follow_up_receives_only_approved_conversation_context(source, history):
    from app.agent import SQLAgent

    history.save(
        "session-one",
        "Show customer names and regions",
        "test-model",
        "SELECT name, region FROM customers",
    )
    prompts = []

    def complete(model, messages):
        prompts.append(json.dumps(messages))
        return {
            "sql": "SELECT name, region FROM customers WHERE region = 'North'",
            "explanation": "Filter the earlier query.",
        }

    agent = SQLAgent(source, history, complete=complete)
    agent.propose("UNAPPROVED_MARKER", "session-one", "test-model")
    agent.propose("Now only North", "session-one", "test-model")
    assert "Show customer names and regions" in prompts[-1]
    assert "UNAPPROVED_MARKER" not in prompts[-1]


@pytest.fixture
def agent(source, history):
    from app.agent import SQLAgent

    def complete(model, messages):
        return {"sql": "SELECT name FROM customers", "explanation": "List customers."}

    return SQLAgent(source, history, complete=complete)


@pytest.mark.parametrize("answer", ["", "n", None])
def test_terminal_never_executes_without_approval(agent, monkeypatch, answer):
    from app.main import run_question

    def refuse(prompt=""):
        if answer is None:
            raise EOFError
        return answer

    def unexpected_execution(sql):
        pytest.fail("SQL executed without approval")

    monkeypatch.setattr("builtins.input", refuse)
    monkeypatch.setattr(agent.database, "execute", unexpected_execution)
    try:
        run_question(agent, "List customers", "session-one", "test-model")
    except EOFError:
        pass  # The outer conversation loop may own EOF handling.
    assert agent.history.successful() == []


def test_terminal_shows_sql_then_executes_only_after_yes(agent, monkeypatch, capsys):
    from app.main import run_question

    executions = []
    execute = agent.database.execute

    def tracked(sql):
        executions.append(sql)
        return execute(sql)

    def approve(prompt=""):
        output = capsys.readouterr().out
        assert "SELECT name FROM customers" in output
        assert "History retrieval: none" in output
        assert executions == []
        assert agent.history.successful() == []
        return "yes"

    monkeypatch.setattr(agent.database, "execute", tracked)
    monkeypatch.setattr("builtins.input", approve)
    run_question(agent, "List customers", "session-one", "test-model")
    assert executions == ["SELECT name FROM customers"]
    assert agent.history.recent("session-one")[0]["sql"] == executions[0]
    assert "name" in capsys.readouterr().out


@pytest.mark.parametrize("approval", ["y", "n"])
def test_terminal_edit_requires_fresh_approval(agent, monkeypatch, capsys, approval):
    from app.main import run_question

    edited = "SELECT name FROM customers WHERE region = 'North' ORDER BY name"
    answers = iter(["edit", edited, "", approval])
    executions = []
    execute = agent.database.execute

    def tracked(sql):
        executions.append(sql)
        return execute(sql)

    def reply(prompt=""):
        answer = next(answers)
        if answer == approval:
            assert edited in capsys.readouterr().out
            assert executions == []
        return answer

    monkeypatch.setattr(agent.database, "execute", tracked)
    monkeypatch.setattr("builtins.input", reply)
    run_question(agent, "List customers", "session-one", "test-model")
    if approval == "y":
        assert executions == [edited]
        assert agent.history.recent("session-one")[0]["sql"] == edited
    else:
        assert executions == []
        assert agent.history.successful() == []


def test_terminal_does_not_remember_failed_execution(agent, monkeypatch):
    from app.main import run_question

    before = agent.database.execute("SELECT COUNT(*) FROM customers")["rows"]
    answers = iter(["edit", "DELETE FROM customers", "", "yes", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    with pytest.raises(sqlite3.Error):
        run_question(agent, "List customers", "session-one", "test-model")
    assert agent.history.successful() == []
    assert agent.database.execute("SELECT COUNT(*) FROM customers")["rows"] == before


def test_terminal_displays_nonfinite_numbers_and_blobs(source, capsys):
    from app.main import print_result

    result = source.execute(
        "SELECT 1e999 AS positive, -1e999 AS negative, x'ff' AS bytes"
    )
    print_result(result)
    output = capsys.readouterr().out
    assert "positive" in output and "inf" in output and "ff" in output
