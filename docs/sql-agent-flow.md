# SQL agent flow

The graph below shows how a question moves through LangGraph, where SQL repair loops, and what happens after the graph returns a proposal.

```mermaid
flowchart TD
    subgraph LangGraph["LangGraph · SQLAgent.propose()"]
        direction TD
        Start([START]) --> Retrieve["retrieve · _retrieve<br/>Read the full SQLite schema<br/>Load up to 6 successful turns for this session<br/>Search up to 200 successful questions for this database<br/>Use hybrid keyword + semantic ranking for history<br/>Add up to 3 examples and build model messages"]
        Retrieve --> Generate["generate · _generate<br/>Call the chat model for JSON: SQL + explanation<br/>On repair, include the previous SQL and validation error<br/>Increment attempts"]
        Generate --> Validate["validate · _validate<br/>Run SQLite EXPLAIN only<br/>Set validation_error to the error or None"]
        Validate -->|Valid · no validation error| GraphEnd([END · return proposal])
        Validate -->|Invalid · attempts ≤ max_repairs| Generate
        Validate -->|Invalid · repair budget exhausted| GraphEnd
    end

    subgraph Review["Terminal · human review (outside LangGraph)"]
        direction TD
        Show["Print SQL, explanation, attempts,<br/>retrieval mode, and any final validation error"] --> Choice{"What do you choose?"}
        Choice -->|Edit| Edit["Read replacement SQL<br/>until a blank line"]
        Edit --> Recheck["Show edited SQL<br/>ask for approval again"]
        Recheck --> Choice
        Choice -->|Enter / no| Skip([Skip · do not execute or save])
        Choice -->|Yes| Execute["Execute against source database<br/>read-only connection · 3-second limit · 500-row cap"]
        Execute --> Save["On success, save question + SQL<br/>under database path and session ID"]
        Save --> Results["Print result table"]
    end

    GraphEnd --> Show

    classDef process fill:#eaf1ff,stroke:#5472a5,color:#17243b
    classDef decision fill:#fff4ce,stroke:#9a771e,color:#30260e
    classDef success fill:#e8f4e8,stroke:#538255,color:#19351c
    classDef stop fill:#f2f2f2,stroke:#777,color:#222
    class Retrieve,Generate,Validate,Show,Edit,Recheck,Execute,Save process
    class Choice decision
    class Results success
    class Start,GraphEnd,Skip stop
```

## What the shared state carries

`State` is a typed dictionary that LangGraph passes between nodes. Each node returns only the fields it adds or updates; LangGraph merges those updates into the shared state.

| Stage | Important state fields |
| --- | --- |
| Initial input | `question`, `session_id`, `model`, `attempts = 0` |
| `retrieve` | `messages`, `tables`, `examples`, `retrieval_mode` |
| `generate` | `sql`, `explanation`, incremented `attempts`, clears `validation_error` before checking again |
| `validate` | Sets `validation_error` to `None` on success or to SQLite's error text on failure |

The schema is sent in full to the chat model. Hybrid retrieval applies only to historical questions: keyword and semantic rankings are fused to choose up to three successful question/SQL examples. If no history is available, `retrieval_mode` is `none`; if embeddings fail, the retriever falls back to keyword-only search.

With `SQL_MAX_REPAIRS=5`, the graph can make six proposals total: the first proposal plus five repairs. If the final proposal still fails validation, the graph returns it with its validation error so the terminal can show it for review. The terminal approval step is outside LangGraph; only a successful execution is written to history.
