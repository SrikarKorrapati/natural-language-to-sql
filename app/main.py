"""Terminal SQL assistant. Run with: python -m app.main --database PATH"""

import argparse
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from app.agent import SQLAgent
from app.db import Database, History

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = "Commands: /new, /schema, /history, /exit"


def print_result(result: dict) -> None:
    """Print query results as an aligned text table with row count and timing."""

    def cell(value):
        if value is None:
            return "NULL"
        # repr keeps newlines and terminal control characters inside a table cell.
        return repr(value)[1:-1] if isinstance(value, str) else str(value)

    rows = [
        [cell(value) for value in row] for row in [result["columns"], *result["rows"]]
    ]
    # Include headers when sizing columns so both labels and values fit.
    widths = [
        max(len(row[index]) for row in rows) for index in range(len(result["columns"]))
    ]
    for index, row in enumerate(rows):
        print(" | ".join(value.ljust(width) for value, width in zip(row, widths)))
        if index == 0:
            print("-+-".join("-" * width for width in widths))
    suffix = " (results truncated)" if result["truncated"] else ""
    print(f"{result['row_count']} rows in {result['duration_ms']} ms{suffix}")


def run_question(agent: SQLAgent, question: str, session_id: str, model: str) -> None:
    """Generate a proposal, get approval, then execute and remember successful SQL."""
    print("Generating SQL…")
    proposal = agent.propose(question, session_id, model)
    sql = proposal["sql"]
    print(f"\n{proposal['explanation']}\n\n{sql}")
    print(f"\nAttempts: {proposal['attempts']}")
    print(f"History retrieval: {proposal['retrieval_mode']}")
    if proposal["validation_error"]:
        print(f"Validation error: {proposal['validation_error']}")

    while True:
        answer = input("Run this SQL? [y/N/edit]: ").strip().lower()
        if answer in {"edit", "e"}:
            print("Enter SQL; finish with a blank line:")
            lines = []
            while line := input():
                lines.append(line)
            sql = "\n".join(lines)
            print(f"\n{sql}\n")
            # Editing changes the proposal, so ask for fresh approval before running.
            continue
        if answer not in {"y", "yes"}:
            print("Skipped.")
            return
        result = agent.database.execute(sql)
        # Saving happens after execution, keeping skipped and failed SQL out of history.
        agent.history.save(session_id, question, model, sql)
        print_result(result)
        return


def chat(agent: SQLAgent, session_id: str, model: str) -> None:
    """Read questions and slash commands until the user exits."""
    print(
        f"Database: {agent.database.path.name} | Model: {model} | Session: {session_id}"
    )
    print(COMMANDS)
    while True:
        try:
            question = input("\nAsk> ").strip()
            if question == "/exit":
                return
            if question == "/new":
                # A new ID starts fresh session memory; historical examples remain.
                session_id = str(uuid4())
                print(f"New session: {session_id}")
            elif question == "/schema":
                for table in agent.database.schema():
                    print(table["sql"])
            elif question == "/history":
                for item in agent.history.recent(session_id, limit=20):
                    print(f"\n{item['question']}\n{item['sql']}")
            elif question.startswith("/"):
                print(COMMANDS)
            elif question:
                run_question(agent, question, session_id, model)
        except (EOFError, KeyboardInterrupt):
            print()
            return


def main(argv=None) -> None:
    # Resolve local settings and history relative to the project, not the shell's cwd.
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    parser.add_argument(
        "--session", default="default", help="Conversation name to start or resume"
    )
    args = parser.parse_args(argv)
    database = Database(args.database.expanduser())
    # The resolved database path keeps each source's saved queries separate.
    history = History(ROOT / "data" / "history.db", dataset=str(database.path))
    agent = SQLAgent(database, history)
    chat(agent, args.session, args.model)


if __name__ == "__main__":
    main()
