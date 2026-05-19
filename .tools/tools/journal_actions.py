"""
FILE: journal_actions.py
ROLE: Action ledger query tool for _app-journal v2.
WHAT IT DOES: Queries the shared human/AI action log.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import query_actions


FILE_METADATA = {
    "tool_name": "journal_actions",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_actions.py",
    "category": "ledger",
    "summary": "Query the shared human/AI action log.",
    "mcp_name": "journal_actions",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "actor_type": {"type": "string"},
            "action_type": {"type": "string"},
            "limit": {"type": "number", "default": 50},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    result = query_actions(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
        actor_type=arguments.get("actor_type", ""),
        action_type=arguments.get("action_type", ""),
        limit=int(arguments.get("limit", 50)),
    )
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
