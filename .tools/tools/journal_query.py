"""
FILE: journal_query.py
ROLE: Query tool for _app-journal v2.
WHAT IT DOES: Searches and filters journal entries, or fetches a single entry by uid.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import get_entry, parse_tags, query_entries


FILE_METADATA = {
    "tool_name": "journal_query",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_query.py",
    "category": "query",
    "summary": "Query or fetch journal entries from the shared SQLite journal.",
    "mcp_name": "journal_query",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "entry_uid": {"type": "string"},
            "query": {"type": "string"},
            "kind": {"type": "string"},
            "source": {"type": "string"},
            "status": {"type": "string"},
            "tags": {},
            "limit": {"type": "number", "default": 50},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    entry_uid = arguments.get("entry_uid")
    if entry_uid:
        entry = get_entry(
            entry_uid=entry_uid,
            project_root=arguments.get("project_root"),
            db_path=arguments.get("db_path"),
        )
        return tool_result(FILE_METADATA["tool_name"], arguments, {"entry": entry})

    result = query_entries(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
        query=arguments.get("query", ""),
        kind=arguments.get("kind", ""),
        source=arguments.get("source", ""),
        status=arguments.get("status", ""),
        tags=parse_tags(arguments.get("tags")),
        limit=int(arguments.get("limit", 50)),
    )
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
