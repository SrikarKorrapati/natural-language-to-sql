"""Behavior tests for read-only execution, review, memory, and repair."""

import json
import sqlite3

import httpx
import pytest

from app.db import Database, History
from benchmarks.run import load_database


@pytest.fixture(autouse=True)
def keyword_retrieval(monkeypatch):
    # Keep core behavior tests offline; semantic retrieval has separate tests.
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
    # Test both entry points and confirm rejected SQL leaves the source unchanged.
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
    # The cap limits returned rows, not how many source rows an aggregate can count.
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

    result = SQLAgent(
        source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, complete=complete, max_repairs=2,
        critique_complete=lambda *_: {"approved": True, "issues": []},
    ).propose(
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
        source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, complete=complete, max_repairs=max_repairs
    ).propose("List customers", "session-one", "test-model")
    # Corrections are additional to the initial generation attempt.
    assert len(calls) == max_repairs + 1
    assert result["attempts"] == max_repairs + 1
    assert result["validation_error"]


def test_repair_budget_can_be_configured_by_environment(source, history, monkeypatch):
    from app.agent import SQLAgent

    monkeypatch.setenv("SQL_MAX_REPAIRS", "1")
    assert SQLAgent(source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}).max_repairs == 1
    assert SQLAgent(source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, max_repairs=0).max_repairs == 0


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

    # Use the real SDK with a fake HTTP response to check request serialization.
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

    agent = SQLAgent(
        source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, complete=complete,
        critique_complete=lambda *_: {"approved": True, "issues": []},
    )
    # Generating a proposal alone must not add it to later conversation context.
    agent.propose("UNAPPROVED_MARKER", "session-one", "test-model")
    agent.propose("Now only North", "session-one", "test-model")
    assert "Show customer names and regions" in prompts[-1]
    assert "UNAPPROVED_MARKER" not in prompts[-1]


@pytest.fixture
def agent(source, history):
    from app.agent import SQLAgent

    def complete(model, messages):
        return {"sql": "SELECT name FROM customers", "explanation": "List customers."}

    return SQLAgent(
        source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, complete=complete,
        critique_complete=lambda *_: {"approved": True, "issues": []},
    )


@pytest.mark.parametrize("greeting", ["hi", " HELLO! ", "Hey there?"])
def test_greetings_do_not_request_sql_or_approval(agent, monkeypatch, capsys, greeting):
    from app.main import run_question

    agent.classify_complete = lambda *_: {
        "valid": False, "explanation": "Ask a question about your database."
    }
    agent.complete = lambda *_: pytest.fail("A greeting must not call the generator")
    monkeypatch.setattr(
        "builtins.input", lambda *_: pytest.fail("A greeting needs no approval")
    )
    run_question(agent, greeting, "session-one", "test-model")
    output = capsys.readouterr().out
    assert "Ask a question about your database" in output
    assert agent.history.successful() == []


def test_chat_accepts_a_query_after_a_greeting(agent, monkeypatch, capsys):
    from app.main import chat

    # A greeting prefix must not swallow an actual database request.
    question = "Hi, list customers"
    decisions = iter([False, True])
    agent.classify_complete = lambda *_: {
        "valid": next(decisions), "explanation": "Ask about your database."
    }
    answers = iter(["hi", question, "yes", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    chat(agent, "session-one", "test-model")
    output = capsys.readouterr().out
    assert output.count("Thinking") == 2
    assert "SELECT name FROM customers" in output
    assert [item["question"] for item in agent.history.successful()] == [question]


def test_model_clarification_skips_validation_approval_and_history(
    agent, monkeypatch, capsys
):
    from app.main import chat

    calls = []
    explanation = "Please ask a question about the data in your database."

    def complete(model, messages):
        calls.append(messages)
        return {"sql": None, "explanation": explanation}

    agent.complete = complete
    monkeypatch.setattr(
        agent.database, "validate", lambda *_: pytest.fail("No SQL to validate")
    )
    monkeypatch.setattr(
        agent.database, "execute", lambda *_: pytest.fail("No SQL to execute")
    )
    answers = iter(["Tell me a joke", "/exit"])

    def reply(prompt):
        assert prompt == "\nAsk> "
        return next(answers)

    monkeypatch.setattr("builtins.input", reply)
    chat(agent, "session-one", "test-model")
    assert len(calls) == 1
    assert "sql: null" in calls[0][0]["content"]
    assert explanation in capsys.readouterr().out
    assert agent.history.successful() == []


@pytest.mark.parametrize(
    "response",
    [None, {}, {"sql": 123, "explanation": "Wrong type"},
     {"sql": "", "explanation": "Empty SQL"}, {"sql": None, "explanation": None}],
)
def test_malformed_model_answer_returns_to_chat(agent, monkeypatch, capsys, response):
    from app.main import chat

    agent.complete = lambda *_: response
    answers = iter(["List customers", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    chat(agent, "session-one", "test-model")
    assert "The model returned an invalid answer" in capsys.readouterr().out
    assert agent.history.successful() == []


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

    # Inspect the moment approval is requested: SQL is visible but has not run.
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
    # A blank line finishes the edit; the final reply approves or rejects that SQL.
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


def test_terminal_does_not_remember_failed_execution(agent, monkeypatch, capsys):
    from app.main import run_question

    before = agent.database.execute("SELECT COUNT(*) FROM customers")["rows"]
    # Approval cannot bypass SQLite's read-only checks, even for manually edited SQL.
    answers = iter(["edit", "DELETE FROM customers", "", "yes", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    run_question(agent, "List customers", "session-one", "test-model")
    assert "Could not execute SQL" in capsys.readouterr().out
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


def test_schema_keeps_user_tables_with_sqlite_prefix(source):
    with sqlite3.connect(source.path) as connection:
        connection.executescript("""
            CREATE TABLE sqliteanalytics(id INTEGER PRIMARY KEY AUTOINCREMENT);
            CREATE VIEW sqliteaudit AS SELECT id FROM sqliteanalytics;
        """)
    names = {table["name"] for table in source.schema()}
    assert {"sqliteanalytics", "sqliteaudit"} <= names
    assert "sqlite_sequence" not in names


@pytest.mark.parametrize("hardlink", [False, True])
def test_history_cannot_modify_the_source_database(source, tmp_path, hardlink):
    target = source.path
    if hardlink:
        target = tmp_path / "journal-alias.db"
        target.hardlink_to(source.path)
    before = source.path.read_bytes()
    with pytest.raises(ValueError, match="different file"):
        History(target, dataset=str(source.path))
    assert source.path.read_bytes() == before
    assert "queries" not in {table["name"] for table in source.schema()}


@pytest.mark.parametrize("sql", ["", "  ", "-- no query\n", "/* no query */", ";"])
def test_empty_sql_fails_as_a_database_error(source, sql):
    with pytest.raises(sqlite3.Error):
        source.validate(sql)
    with pytest.raises(sqlite3.Error):
        source.execute(sql)


@pytest.mark.parametrize("settings", [
    {"max_rows": 0}, {"max_rows": -1}, {"max_rows": 1.5}, {"max_rows": True},
    {"timeout_seconds": 0}, {"timeout_seconds": -1},
    {"timeout_seconds": float("inf")}, {"timeout_seconds": float("nan")},
])
def test_database_rejects_invalid_resource_limits(source, settings):
    with pytest.raises(ValueError):
        Database(source.path, **settings)


def test_failed_execution_can_be_edited_and_approved_again(agent, monkeypatch, capsys):
    from app.main import run_question

    fixed = "SELECT COUNT(*) AS count FROM customers"
    answers = iter(["edit", "SELECT absent FROM customers", "", "y", "edit", fixed, "", "y"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    run_question(agent, "Count customers", "session", "model")
    assert "Could not execute SQL" in capsys.readouterr().out
    assert [row["sql"] for row in agent.history.successful()] == [fixed]


@pytest.mark.parametrize("kind", ["configuration", "connection", "rate_limit"])
def test_chat_recovers_from_provider_errors_without_printing_private_details(
    agent, monkeypatch, capsys, kind
):
    from openai import APIConnectionError, APIStatusError, OpenAIError
    from app.main import chat

    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    errors = {
        "configuration": OpenAIError("PRIVATE_PROVIDER_DETAIL"),
        "connection": APIConnectionError(message="PRIVATE_PROVIDER_DETAIL", request=request),
        "rate_limit": APIStatusError("PRIVATE_PROVIDER_DETAIL", response=httpx.Response(429, request=request), body=None),
    }
    generate = agent.complete
    attempts = []

    def complete(*args):
        attempts.append(1)
        if len(attempts) == 1:
            raise errors[kind]
        return generate(*args)

    agent.complete = complete
    answers = iter(["List customers", "List customers", "y", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    chat(agent, "session", "model")
    output = capsys.readouterr().out
    assert "Model provider request failed" in output
    assert "PRIVATE_PROVIDER_DETAIL" not in output
    assert len(agent.history.successful()) == 1


def test_chat_recovers_from_schema_command_error(agent, monkeypatch, capsys):
    from app.main import chat

    schema = agent.database.schema
    calls = []

    def read_schema():
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return schema()

    monkeypatch.setattr(agent.database, "schema", read_schema)
    answers = iter(["/schema", "List customers", "y", "/exit"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    chat(agent, "session", "model")
    assert "Database error: database is locked" in capsys.readouterr().out
    assert len(agent.history.successful()) == 1


def test_history_save_failure_keeps_successful_results_visible(agent, monkeypatch, capsys):
    from app.main import run_question

    def fail_save(*_):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(agent.history, "save", fail_save)
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    run_question(agent, "List customers", "session", "model")
    output = capsys.readouterr().out
    assert "rows in" in output
    assert "Query ran, but conversation history could not be saved" in output
    assert agent.history.successful() == []


@pytest.mark.parametrize("exists", [False, True])
def test_startup_rejects_missing_or_invalid_databases_before_creating_history(
    tmp_path, monkeypatch, capsys, exists
):
    import app.main as main_module

    path = tmp_path / "source.db"
    if exists:
        path.write_text("This is not a SQLite database")
    monkeypatch.setattr(main_module, "ROOT", tmp_path)
    monkeypatch.setattr(main_module, "SQLAgent", lambda *_: pytest.fail("Invalid database must not start an agent"))
    with pytest.raises(SystemExit) as exc:
        main_module.main(["--database", str(path)])
    assert exc.value.code == 2
    assert "Cannot start" in capsys.readouterr().err
    assert not (tmp_path / "data" / "history.db").exists()
