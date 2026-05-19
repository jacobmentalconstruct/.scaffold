"""
FILE: session_evidence_store.py
ROLE: Bag of Evidence and Evidence Shelf tool.
WHAT IT DOES: Stores, indexes, searches, retrieves, and exports session evidence under ignored runtime state.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.session_evidence_store import (
    append_item,
    archive_window,
    export_store,
    get_item,
    init_store,
    search,
    shelf,
    status,
)
from lib.text_workspace import resolve_project_root


FILE_METADATA = {
    "tool_name": "session_evidence_store",
    "version": "1.0.0",
    "entrypoint": "src/tools/session_evidence_store.py",
    "category": "memory",
    "summary": "Manage the local-agent Bag of Evidence SQLite store and Evidence Shelf.",
    "mcp_name": "session_evidence_store",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "init", "append", "archive_window", "shelf", "search", "get", "export"],
                "default": "status",
            },
            "project_root": {"type": "string", "default": "."},
            "confirm": {"type": "boolean", "default": False},
            "session_id": {"type": "string", "default": "default"},
            "sequence": {"type": "integer"},
            "sequence_start": {"type": "integer"},
            "sequence_end": {"type": "integer"},
            "kind": {"type": "string", "default": "evidence"},
            "role": {"type": "string"},
            "source": {"type": "string", "default": "agent"},
            "summary": {"type": "string"},
            "body": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "paths": {"type": "array", "items": {"type": "string"}},
            "tools": {"type": "array", "items": {"type": "string"}},
            "importance": {"type": "integer", "default": 0},
            "turns": {"type": "array", "items": {"type": "object"}},
            "window_turns": {"type": "integer", "default": 8},
            "archive_all": {"type": "boolean", "default": False},
            "rolling_summary": {"type": "string"},
            "open_loops": {"type": "array", "items": {"type": "string"}},
            "decisions": {"type": "array", "items": {"type": "string"}},
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
            "item_id": {"type": "string"},
            "mode": {"type": "string", "enum": ["summary", "verbatim"], "default": "summary"},
            "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            "redact_paths": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    },
}


MUTATING_ACTIONS = {"init", "append", "archive_window", "export"}


def _needs_confirm(action: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    if action in MUTATING_ACTIONS and arguments.get("confirm") is not True:
        return tool_result(
            FILE_METADATA["tool_name"],
            arguments,
            {"approval_required": True, "reason": f"{action} requires confirm=true"},
            status="approval_required",
        )
    return None


def run(arguments: dict[str, Any]) -> dict[str, Any]:
    action = str(arguments.get("action", "status")).strip().lower()
    if action not in FILE_METADATA["input_schema"]["properties"]["action"]["enum"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, f"unsupported action: {action}")
    try:
        project_root = resolve_project_root(arguments.get("project_root"))
    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    confirmation = _needs_confirm(action, arguments)
    if confirmation is not None:
        return confirmation

    try:
        if action == "status":
            result = status(project_root)
        elif action == "init":
            result = init_store(project_root)
        elif action == "append":
            result = append_item(project_root, arguments)
        elif action == "archive_window":
            result = archive_window(project_root, arguments)
        elif action == "shelf":
            result = shelf(
                project_root,
                str(arguments.get("session_id", "default")),
                limit=int(arguments.get("limit", 25)),
                redact_paths=arguments.get("redact_paths", True) is not False,
            )
        elif action == "search":
            result = search(project_root, arguments)
        elif action == "get":
            result = get_item(project_root, arguments)
        else:
            result = export_store(project_root, arguments)
    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
