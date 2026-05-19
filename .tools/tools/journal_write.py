"""
FILE: journal_write.py
ROLE: Write tool for _app-journal v2.
WHAT IT DOES: Creates, updates, or appends to journal entries with CAS body storage.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import parse_tags, write_entry


FILE_METADATA = {
    "tool_name": "journal_write",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_write.py",
    "category": "write",
    "summary": "Create, update, or append to a journal entry.",
    "mcp_name": "journal_write",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "action": {"type": "string", "enum": ["create", "update", "append"], "default": "create"},
            "entry_uid": {"type": "string"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "append_text": {"type": "string"},
            "kind": {"type": "string"},
            "source": {"type": "string"},
            "author": {"type": "string"},
            "tags": {},
            "status": {"type": "string"},
            "importance": {"type": "number"},
            "related_path": {"type": "string"},
            "related_ref": {"type": "string"},
            "metadata": {"type": "object"},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    entry = write_entry(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
        action=arguments.get("action", "create"),
        entry_uid=arguments.get("entry_uid"),
        title=arguments.get("title", ""),
        body=arguments.get("body", ""),
        append_text=arguments.get("append_text", ""),
        kind=arguments.get("kind", "note"),
        source=arguments.get("source"),
        author=arguments.get("author"),
        tags=parse_tags(arguments.get("tags")),
        status=arguments.get("status"),
        importance=arguments.get("importance"),
        related_path=arguments.get("related_path"),
        related_ref=arguments.get("related_ref"),
        metadata=arguments.get("metadata"),
    )
    return tool_result(FILE_METADATA["tool_name"], arguments, {"entry": entry})


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
