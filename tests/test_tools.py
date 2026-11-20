"""Inspection conversations, bounded retries, and provider tool-call decoding."""

import json
import sqlite3
from copy import deepcopy

import httpx
from openai import OpenAI
from openai.types.chat import ChatCompletion
import pytest

from app.agent import SQLAgent
from app.completion import ModelResponseError, ToolRequest, parse_model_response
from app.db import History
from app.retrieval import Retriever
from app.tools import execute_inspection
from benchmarks.run import load_database


def request(name="get_column_values", arguments=None, id="inspect-1"):
    return ToolRequest({"role": "assistant", "content": None, "tool_calls": [{
        "id": id, "type": "function", "function": {
            "name": name, "arguments": json.dumps(arguments or {
                "table": "products", "column": "category", "limit": 10,
            }),
        },
    }]})


def capable(callback):
    callback.supports_tools = True
    return callback


@pytest.fixture
def setup(tmp_path):
    database = load_database("s01_retail", tmp_path)
    history = History(tmp_path / "history.db", str(database.path))
    return database, history


def agent(setup, generate, critique=None, **kwargs):
    return SQLAgent(*setup, complete=generate,
                    classify_complete=lambda *_: {"valid": True, "explanation": "Answerable."},
                    critique_complete=critique or (lambda *_: {"approved": True, "issues": []}),
                    retriever=Retriever(), **kwargs)


def test_critic_evidence_reaches_revision_and_budget_is_shared(setup, monkeypatch):
    generator_calls, critic_calls = [], []

    @capable
    def generate(_, messages, **options):
        generator_calls.append(deepcopy(messages))
        if len(generator_calls) == 1:
            return request()
        if len(generator_calls) == 2:
            assert "Electronics" in messages[-1]["content"]
            return {"sql": "SELECT missing FROM products", "explanation": "First draft."}
        assert "Electronics" in json.dumps(messages)
        if len(generator_calls) == 4:
            assert options["tool_choice"] == "none"
            assert '"row_count": 6' in json.dumps(messages).replace('\\"', '"')
        return {"sql": "SELECT category FROM products", "explanation": "Categories."}

    @capable
    def critique(_, messages, **options):
        critic_calls.append(deepcopy(messages))
        if len(critic_calls) == 1:
            return request("get_column_profile", id="profile-1")
        assert options["tool_choice"] == "none"
        return {"approved": len(critic_calls) == 3,
                "issues": [] if len(critic_calls) == 3 else ["Reconsider missing values."]}

    monkeypatch.setattr(setup[0], "execute", lambda *_: pytest.fail("Final SQL needs approval"))
    result = agent(setup, generate, critique, max_tool_calls=2).propose("List categories", "s", "model")
    assert result["tool_calls"] == 2
    assert result["attempts"] == 3  # Initial SQL, validation repair, critique revision.
    assert result["critique_rounds"] == 2
    assert result["critique_approved"]
    assert setup[1].successful() == []


def test_batch_over_budget_gets_correlated_errors_and_final_answer(setup):
    seen = []

    @capable
    def generate(_, messages, **options):
        seen.append(deepcopy(messages))
        if len(seen) == 1:
            batch = request()
            batch.message["tool_calls"].append(request(id="over-budget").message["tool_calls"][0])
            return batch
        assert options["tool_choice"] == "none"
        assert messages[-2]["tool_call_id"] == "inspect-1"
        assert "Electronics" in messages[-2]["content"]
        assert messages[-1]["tool_call_id"] == "over-budget"
        assert "budget exhausted" in messages[-1]["content"]
        return {"sql": "SELECT 1", "explanation": "One."}

    result = agent(setup, generate, max_tool_calls=1).propose("Return one", "s", "m")
    assert result["tool_calls"] == 1
    assert len(seen) == 2


def test_model_cannot_loop_after_budget_or_call_tools_when_disabled(setup):
    calls = []

    @capable
    def repeat(*_, **options):
        calls.append(options)
        return request("unknown_tool")

    with pytest.raises(ModelResponseError, match="disabled"):
        agent(setup, repeat, max_tool_calls=1).propose("Return one", "s", "m")
    assert len(calls) == 2
    assert calls[-1]["tool_choice"] == "none"
    calls.clear()
    with pytest.raises(ModelResponseError, match="disabled"):
        agent(setup, repeat, max_tool_calls=0).propose("Return one", "s", "m")
    assert calls == [{}]


def test_bad_arguments_are_recoverable_and_budget_resets_per_question(setup):
    calls = []

    @capable
    def generate(_, messages, **options):
        calls.append(options)
        if len(calls) % 2:
            bad = request()
            bad.message["tool_calls"][0]["function"]["arguments"] = "not json"
            return bad
        assert "Invalid inspection arguments" in messages[-1]["content"]
        return {"sql": None, "explanation": "Please clarify the category."}

    instance = agent(setup, generate, max_tool_calls=1)
    for question in ("First", "Second"):
        assert instance.propose(question, "s", "m")["tool_calls"] == 1
    assert [o["tool_choice"] for o in calls] == ["auto", "none", "auto", "none"]


@pytest.mark.parametrize("arguments", [
    '[]', '{}', '{"table":"products","column":"category","sql":"DELETE FROM products"}',
    '{"table":"products","column":"category","limit":true}',
    '{"table":"products","column":"missing"}',
])
def test_dispatch_rejects_invalid_arguments_without_changing_source(setup, arguments):
    before = setup[0].path.read_bytes()
    assert "error" in execute_inspection(setup[0], "get_column_values", arguments)
    assert setup[0].path.read_bytes() == before


def test_database_tool_error_does_not_leak_database_details(setup, monkeypatch):
    def fail(*_, **__):
        raise sqlite3.OperationalError("private database detail")
    monkeypatch.setattr("app.tools.get_column_values", fail)
    result = execute_inspection(setup[0], "get_column_values", '{"table":"products","column":"category"}')
    assert "error" in result
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("budget", [True, -1, 21, 1.5, "2"])
def test_agent_rejects_invalid_tool_budgets(setup, budget):
    with pytest.raises(ValueError, match="Tool budget"):
        agent(setup, lambda *_: {}, max_tool_calls=budget)


def test_default_sdk_adapter_round_trips_real_tool_calls(setup, monkeypatch):
    import app.agent as module
    requests = []

    def respond(http_request):
        body = json.loads(http_request.content)
        requests.append(body)
        system = body["messages"][0]["content"]
        if system.startswith("You are the input classifier"):
            assert "tools" not in body
            answer = {"valid": True, "explanation": "Answerable."}
        elif "SQL critique agent" in system:
            assert "Electronics" in json.dumps(body["messages"])
            answer = {"approved": True, "issues": []}
        elif body["messages"][-1]["role"] != "tool":
            assert {t["function"]["name"] for t in body["tools"]} == {
                "get_column_values", "get_column_profile",
            }
            return httpx.Response(200, json={"id": "r", "object": "chat.completion", "created": 0,
                "model": "m", "choices": [{"index": 0, "finish_reason": "tool_calls",
                "message": request().message}]})
        else:
            assert body["messages"][-1]["tool_call_id"] == "inspect-1"
            assert "Electronics" in body["messages"][-1]["content"]
            answer = {"sql": "SELECT category FROM products", "explanation": "Categories."}
        return httpx.Response(200, json={"id": "r", "object": "chat.completion", "created": 0,
            "model": "m", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(answer)}}]})

    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: OpenAI(api_key="test-only",
        base_url="https://provider.test/v1", http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs))
    result = SQLAgent(*setup, retriever=Retriever()).propose("List categories", "s", "m")
    assert result["tool_calls"] == 1
    assert result["critique_approved"]
    assert len(requests) == 4


def response(message, finish_reason="stop"):
    return ChatCompletion.model_validate({"id": "r", "object": "chat.completion", "created": 0,
        "model": "m", "choices": [{"index": 0, "finish_reason": finish_reason, "message": message}]})


def test_json_that_mentions_tools_is_not_a_provider_tool_request():
    content = {"tool_calls": [{"name": "get_column_values"}]}
    decoded = parse_model_response(response({"role": "assistant", "content": json.dumps(content)}), allow_tools=True)
    assert decoded == content
    assert not isinstance(decoded, ToolRequest)


def test_parser_rejects_disabled_duplicate_and_oversized_tool_calls():
    message = request().message
    with pytest.raises(ModelResponseError, match="disabled"):
        parse_model_response(response(message))
    message["tool_calls"] *= 2
    with pytest.raises(ModelResponseError, match="invalid tool call"):
        parse_model_response(response(message), allow_tools=True)
    message = request().message
    message["tool_calls"][0]["function"]["arguments"] = "x" * 4001
    with pytest.raises(ModelResponseError, match="arguments"):
        parse_model_response(response(message), allow_tools=True)


@pytest.mark.parametrize("function", [None, 7])
def test_parser_sanitizes_malformed_sdk_tool_objects(function):
    # The SDK constructs responses without strict validation of provider JSON.
    from openai.types.chat.chat_completion_message import ChatCompletionMessage
    from openai.types.chat.chat_completion_message_function_tool_call import ChatCompletionMessageFunctionToolCall
    malformed = response({"role": "assistant", "content": None})
    malformed.choices[0].message = ChatCompletionMessage.model_construct(role="assistant", content=None,
        tool_calls=[ChatCompletionMessageFunctionToolCall.model_construct(
            id="bad", type="function", function=function)])
    with pytest.raises(ModelResponseError, match="arguments"):
        parse_model_response(malformed, allow_tools=True)


def test_deeply_nested_tool_arguments_return_recoverable_error(setup):
    result = execute_inspection(setup[0], "get_column_values", "[" * 1500 + "0" + "]" * 1500)
    assert "error" in result


@pytest.mark.parametrize("choices", [[None], {"bad": "shape"}, [{"message": False}]])
def test_malformed_provider_envelopes_become_readable_errors(choices, monkeypatch):
    import app.agent as module
    def respond(_):
        return httpx.Response(200, json={"id": "r", "object": "chat.completion", "created": 0,
            "model": "m", "choices": choices})
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: OpenAI(api_key="test-only",
        base_url="https://provider.test/v1", http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs))
    with pytest.raises(ModelResponseError):
        module.model_completion("m", [{"role": "user", "content": "Return JSON"}])
