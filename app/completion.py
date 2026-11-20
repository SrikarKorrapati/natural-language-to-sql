"""Decode chat responses without confusing model JSON with real tool calls."""

from dataclasses import dataclass
import json


class ModelResponseError(ValueError):
    """A provider response cannot be used as a decision or proposal."""


@dataclass
class ToolRequest:
    message: dict


def parse_model_response(response, *, allow_tools=False):
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        raise ModelResponseError("The model returned no answer.")
    choice = choices[0]
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason == "length":
        raise ModelResponseError(
            "The model response was truncated at the completion token limit (finish_reason=length)."
        )
    message = getattr(choice, "message", None)
    if message is None or not hasattr(message, "content"):
        raise ModelResponseError("The model returned no message.")
    if finish_reason == "content_filter" or getattr(message, "refusal", None):
        raise ModelResponseError("The provider refused or filtered the model response.")
    if message.content is not None and not isinstance(message.content, str):
        raise ModelResponseError("The model returned invalid message content.")
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        if not allow_tools:
            raise ModelResponseError("The model requested a tool where tools are disabled.")
        if not isinstance(tool_calls, list) or len(tool_calls) > 20:
            raise ModelResponseError("The model requested too many tools in one response.")
        calls, ids = [], set()
        for call in tool_calls:
            if (getattr(call, "type", None) != "function" or not isinstance(getattr(call, "id", None), str)
                    or not call.id or len(call.id) > 128 or call.id in ids):
                raise ModelResponseError("The model returned an invalid tool call.")
            function = getattr(call, "function", None)
            if (not isinstance(getattr(function, "name", None), str) or not function.name
                    or len(function.name) > 64 or not isinstance(getattr(function, "arguments", None), str)
                    or len(function.arguments) > 4000):
                raise ModelResponseError("The model returned invalid tool arguments.")
            ids.add(call.id)
            calls.append({"id": call.id, "type": "function", "function": {
                "name": function.name, "arguments": function.arguments,
            }})
        return ToolRequest({"role": "assistant", "content": message.content, "tool_calls": calls})
    try:
        return json.loads(message.content)
    except (json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise ModelResponseError("The model returned an unreadable JSON answer.") from exc
