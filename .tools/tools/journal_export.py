"""
FILE: journal_export.py
ROLE: Export tool for _app-journal v2.
WHAT IT DOES: Exports filtered journal entries to Markdown or JSON files.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import export_entries, parse_tags


FILE_METADATA = {
    "tool_name": "journal_export",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_export.py",
    "category": "export",
    "summary": "Export filtered journal entries to Markdown or JSON.",
    "mcp_name": "journal_export",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "query": {"type": "string"},
            "kind": {"type": "string"},
            "source": {"type": "string"},
            "status": {"type": "string"},
            "tags": {},
            "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            "limit": {"type": "number", "default": 200},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    result = export_entries(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
        query=arguments.get("query", ""),
        kind=arguments.get("kind", ""),
        source=arguments.get("source", ""),
        status=arguments.get("status", ""),
        tags=parse_tags(arguments.get("tags")),
        format_name=arguments.get("format", "markdown"),
        limit=int(arguments.get("limit", 200)),
    )
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
