"""Critique context, revision budgets, and human approval behavior."""

import json

import pytest

from app.agent import SQLAgent
from app.db import History
from app.main import run_question
from app.retrieval import Retriever
from benchmarks.run import load_database, run


@pytest.fixture
def source(tmp_path):
    return load_database("s01_retail", tmp_path)


@pytest.fixture
def history(tmp_path, source):
    return History(tmp_path / "history.db", dataset=str(source.path))


def test_critic_shares_full_context_and_repairs_semantic_error(source, history, monkeypatch):
    history.save("session", "List customers", "model", "SELECT name FROM customers")
    before = history.successful()
    generator_calls, critic_calls = [], []
    issue = "The user requested North; add WHERE region = 'North'."
    wrong = "SELECT name FROM customers"
    fixed = "SELECT name FROM customers WHERE region = 'North'"

    def generate(model, messages):
        generator_calls.append((model, messages))
        return {"sql": wrong if len(generator_calls) == 1 else fixed, "explanation": "Names."}

    def critique(model, messages):
        critic_calls.append((model, messages))
        payload = json.loads(messages[1]["content"])
        # The critic gets the exact task messages, including corrections on round two.
        assert payload["generator_context"] == generator_calls[-1][1][1:]
        assert messages[0] != generator_calls[-1][1][0]
        context = json.loads(payload["generator_context"][0]["content"])
        assert context["schema"] == [table["sql"] for table in source.schema()]
        assert context["conversation"] == [{"question": "List customers", "sql": wrong}]
        assert context["successful_examples"] == [{"question": "List customers", "sql": wrong}]
        assert payload["generator_context"][1]["content"] == "Now only North"
        assert payload["validation_error"] is None
        assert payload["proposal"]["sql"] == (wrong if len(critic_calls) == 1 else fixed)
        return {"approved": len(critic_calls) == 2, "issues": [issue] if len(critic_calls) == 1 else []}

    monkeypatch.setattr(source, "execute", lambda *_: pytest.fail("Proposal must not execute"))
    agent = SQLAgent(source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, complete=generate, critique_complete=critique, retriever=Retriever())
    result = agent.propose("Now only North", "session", "test-model")
    assert result["sql"] == fixed
    assert result["attempts"] == result["critique_rounds"] == 2
    assert result["critique_approved"] is True
    assert result["critique_issues"] == []
    assert issue in generator_calls[1][1][-1]["content"]
    assert json.loads(generator_calls[1][1][-2]["content"])["sql"] == wrong
    assert all(model == "test-model" for model, _ in generator_calls + critic_calls)
    assert history.successful() == before


def test_default_threshold_stops_after_exactly_three_reviews(source, history):
    generated, reviewed = [], []

    def generate(*_):
        generated.append(1)
        return {"sql": f"SELECT {len(generated)}", "explanation": "A draft."}

    def critique(_, messages):
        reviewed.append(json.loads(messages[1]["content"])["proposal"]["sql"])
        return {"approved": False, "issues": [f"Unresolved issue {len(reviewed)}"]}

    result = SQLAgent(source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, complete=generate, critique_complete=critique).propose(
        "List customers", "session", "model"
    )
    assert reviewed == ["SELECT 1", "SELECT 2", "SELECT 3"]
    assert result["attempts"] == result["critique_rounds"] == len(generated) == 3
    assert result["sql"] == "SELECT 3"
    assert result["critique_approved"] is False
    assert result["critique_issues"] == ["Unresolved issue 3"]
    assert history.successful() == []


def test_sql_repairs_and_critique_have_separate_budgets(source, history):
    drafts = iter(["SELECT absent", "SELECT 1", "SELECT still_absent", "SELECT 2"])
    generated, reviews = [], []

    def generate(_, messages):
        generated.append(messages)
        return {"sql": next(drafts), "explanation": "Draft."}

    def critique(_, messages):
        reviews.append(json.loads(messages[1]["content"]))
        return {"approved": len(reviews) == 2, "issues": ["Use 2."] if len(reviews) == 1 else []}

    result = SQLAgent(source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, complete=generate, critique_complete=critique, max_repairs=2).propose(
        "Return two", "session", "model"
    )
    assert result["attempts"] == 4
    assert result["critique_rounds"] == 2
    assert result["critique_approved"] is True
    assert "still_absent" in generated[-1][-1]["content"]
    assert "Use 2." in generated[-1][-1]["content"]
    assert reviews[-1]["generator_context"] == generated[-1][1:]


@pytest.mark.parametrize("budget", [0, 1, 15])
def test_invalid_sql_never_reaches_critic_and_respects_repair_budget(source, history, budget):
    agent = SQLAgent(
        source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, max_repairs=budget,
        complete=lambda *_: {"sql": "SELECT absent", "explanation": "Draft."},
        critique_complete=lambda *_: pytest.fail("Invalid SQL must not reach the critic"),
    )
    result = agent.propose("List customers", "session", "model")
    assert result["attempts"] == budget + 1
    assert result["validation_error"]
    assert result["critique_rounds"] == 0
    assert result["critique_approved"] is None


def test_failed_revision_does_not_keep_a_review_of_older_sql(source, history):
    drafts = iter(["SELECT 1", "SELECT absent"])
    result = SQLAgent(
        source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, max_repairs=0,
        complete=lambda *_: {"sql": next(drafts), "explanation": "Draft."},
        critique_complete=lambda *_: {"approved": False, "issues": ["Use 2."]},
    ).propose("Return two", "session", "model")
    assert result["critique_rounds"] == 1
    assert result["validation_error"]
    assert result["critique_approved"] is None
    assert result["critique_issues"] == []


def test_clarification_skips_critic(source, history):
    result = SQLAgent(
        source, history,
        classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."},
        complete=lambda *_: {"sql": None, "explanation": "Which region?"},
        critique_complete=lambda *_: pytest.fail("No SQL to review"),
    ).propose("Filter by that region", "session", "model")
    assert result["sql"] is None
    assert result["critique_rounds"] == 0
    assert result["critique_approved"] is None


def test_reviewer_can_request_clarification(source, history):
    drafts = iter([
        {"sql": "SELECT name FROM customers", "explanation": "Names."},
        {"sql": None, "explanation": "Which region do you mean?"},
    ])
    result = SQLAgent(
        source, history, classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."}, complete=lambda *_: next(drafts),
        critique_complete=lambda *_: {"approved": False, "issues": ["Ask which region the user means."]},
    ).propose("Show customers in my region", "session", "model")
    assert result["sql"] is None
    assert result["critique_rounds"] == 1
    assert result["critique_approved"] is None
    assert history.successful() == []


@pytest.mark.parametrize("review", [
    None, {}, {"approved": "true", "issues": []}, {"approved": True, "issues": "none"},
    {"approved": True, "issues": ["An issue"]}, {"approved": False, "issues": []},
    {"approved": False, "issues": [None]}, {"approved": False, "issues": [" "]},
])
def test_malformed_review_is_not_shown_as_approval(source, history, monkeypatch, capsys, review):
    agent = SQLAgent(
        source, history,
        classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."},
        complete=lambda *_: {"sql": "SELECT 1", "explanation": "One."},
        critique_complete=lambda *_: review,
    )
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("No approval for a malformed review"))
    run_question(agent, "Return one", "session", "model")
    assert "critique model returned an invalid review" in capsys.readouterr().out
    assert history.successful() == []


@pytest.mark.parametrize("answer", ["y", "n"])
def test_unresolved_review_is_shown_before_human_choice(source, history, monkeypatch, capsys, answer):
    agent = SQLAgent(
        source, history,
        classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."},
        complete=lambda *_: {"sql": "SELECT 1", "explanation": "One."},
        critique_complete=lambda *_: {"approved": False, "issues": ["The requested answer is two."]},
    )
    executions = []
    execute = source.execute

    def tracked(sql):
        executions.append(sql)
        return execute(sql)

    def choose(_):
        output = capsys.readouterr().out
        assert "Critique: issues remain (3/3 rounds)" in output
        assert "The requested answer is two." in output
        assert executions == []
        return answer

    monkeypatch.setattr(source, "execute", tracked)
    monkeypatch.setattr("builtins.input", choose)
    run_question(agent, "Return two", "session", "model")
    assert executions == (["SELECT 1"] if answer == "y" else [])
    assert len(history.successful()) == (1 if answer == "y" else 0)


def test_default_provider_performs_classification_generation_and_review(source, history, monkeypatch):
    calls = []

    def complete(model, messages):
        calls.append((model, messages))
        if len(calls) == 1:
            return {"valid": True, "explanation": "Answerable."}
        if len(calls) == 2:
            return {"sql": "SELECT 1", "explanation": "One."}
        return {"approved": True, "issues": []}

    monkeypatch.setattr("app.agent.model_completion", complete)
    result = SQLAgent(source, history).propose("Return one", "session", "same-model")
    assert len(calls) == 3
    assert [model for model, _ in calls] == ["same-model"] * 3
    assert "input classifier" in calls[0][1][0]["content"]
    assert "SQL generator" in calls[1][1][0]["content"]
    assert "SQL critique agent" in calls[2][1][0]["content"]
    assert result["critique_rounds"] == 1
    assert result["critique_approved"] is True


def test_benchmark_records_review_outcome_separately_from_execution_accuracy():
    class Agent:
        def __init__(self, *_):
            pass

        def propose(self, *_):
            return {
                "sql": "SELECT 1", "attempts": 3, "critique_rounds": 3,
                "critique_approved": False, "critique_issues": ["Question is ambiguous."],
            }

    case = {"id": "review", "schema_id": "s01_retail", "question": "Return one", "expected_sql": "SELECT 1"}
    report = run(["model"], [case], agent_factory=Agent)["models"]["model"]["results"][0]
    assert report["correct"] is True
    assert report["critique_rounds"] == 3
    assert report["critique_approved"] is False
    assert report["critique_issues"] == ["Question is ambiguous."]
