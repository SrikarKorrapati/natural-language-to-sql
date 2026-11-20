# Column inspection tools

The generator and critic can ask the application to inspect one database column. These are real Chat Completions function calls: the model requests a tool by name, Python checks the arguments and queries SQLite, then a `tool` message with the matching call ID returns the result. The model continues to its normal SQL proposal or critique JSON. The classifier has no tools.

## Example

Suppose `shipments.status` contains 1,000 rows: 200 pending, 300 in transit, 475 delivered, and 25 NULLs. This is illustrative data, not an added project fixture.

```python
get_column_values(database, "shipments", "status", limit=10)
```

The result contains `values`, ordered by frequency, such as `delivered`, `in_transit`, and `pending`. Each entry includes `value`, `storage_type`, and `value_truncated`. Text entries also include `original_length`; BLOB entries use hexadecimal with `encoding: "hex"`. The list excludes NULLs. `truncated: true` means more distinct values exist than the returned list contains.

```python
get_column_profile(database, "shipments", "status", limit=10)
```

The profile returns `row_count: 1000`, `null_count: 25`, `distinct_non_null_count: 3`, `storage_type_counts`, and `value_counts`. Frequency entries use the same typed value format plus `count`; they are a list rather than a JSON object so strings, numbers and BLOBs remain distinguishable. A `numeric` object contains `count`, `min`, `max` and `avg` over values actually stored as INTEGER or REAL. Numeric-looking text is not silently converted. Empty numeric populations have count zero and null statistics.

For “What percentage of **all** shipments are delivered?”, the profile exposes the difference between `COUNT(*)` (1,000) and `COUNT(status)` (975). The user's wording determines the correct denominator. The critic can inspect the same column to check this assumption. Profile statistics do not determine how unknown statuses should be interpreted for other questions.

## Limits and behavior

- Arguments are `table`, `column`, and `limit` (default 10, permitted 1–20). Names must exactly match an existing table/view and its column. Internal SQLite tables, unknown names, expressions, and extra arguments are rejected.
- Each inspection uses a single read-only transaction, SQLite authorization, and a shared deadline across its internal queries. Counts are exact for that snapshot if the operation completes. A timeout returns an error, never a partial profile presented as complete.
- Text values are capped at 256 characters and BLOBs at 64 bytes. Per-value truncation is independent of list truncation. Truncated strings must not be treated as exact SQL filter literals. Infinite numeric values are encoded as strings, not invalid JSON numbers.
- Distinct values follow SQLite equality and the column's collation. Equal INTEGER and REAL values can share a group; numeric values and numeric-looking TEXT remain distinct. Type counts report actual storage types. No date format or business meaning is inferred automatically.
- `SQL_MAX_TOOL_CALLS` sets the shared per-question budget (default 4, range 0–20). Generator, SQLite repairs, and all critique rounds share it. Invalid requests count. Extra calls in a batch receive budget errors; subsequent requests set `tool_choice: "none"`. A provider that ignores this restriction produces a readable model-response error.
- Tool errors are returned to the model so it can use existing evidence or request clarification. Tool results are explicitly treated as untrusted data.
- Evidence is shared across generation and critique for the current question, then discarded. A new question receives a fresh budget. Final proposals report `tool_calls`, and the terminal displays the number of column inspections.

Inspection is automatic when requested by the model and occurs **before** human approval of the final SQL. Its bounded values and statistics reach the configured chat provider. Final query result rows stay local. Disable inspection with `SQL_MAX_TOOL_CALLS=0` when the provider lacks function calling or column data should not be sent.

## Development and benchmarking

Implementations are in [inspection.py](../app/inspection.py); schemas and dispatch are in [tools.py](../app/tools.py). [agent.py](../app/agent.py) maintains the bounded conversation, and [completion.py](../app/completion.py) distinguishes provider tool calls from final JSON. Ordinary model JSON containing a `tool_calls` key never triggers execution.

The default adapter supports tools. Injected completion callbacks retain their two-argument interface by default. A tool-capable callback opts in with `callback.supports_tools = True`, accepts keyword arguments `tools` and `tool_choice`, and uses `parse_model_response` to return either final JSON or a `ToolRequest`. The parallel benchmark adapter implements this contract and counts every model response and its usage.

For parallel benchmarks, set the configuration field `max_tool_calls` (default 4); it is independent of the terminal environment setting. Use `0` for a comparison without inspection. Run into a new output directory: new tool code and budgets change the source/configuration fingerprint, and the historical published benchmark remains unchanged.
