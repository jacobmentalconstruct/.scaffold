"""
FILE: agent_run_trace.py
ROLE: Local-agent run trace and tuning-data spine tool.
WHAT IT DOES: Stores, queries, retrieves, and exports structured local-agent run traces under ignored runtime state.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.agent_run_trace import (
    append_trace,
    export_traces,
    get_trace,
    init_store,
    query_traces,
    status,
)
from lib.text_workspace import resolve_project_root


FILE_METADATA = {
    "tool_name": "agent_run_trace",
    "version": "1.0.0",
    "entrypoint": "src/tools/agent_run_trace.py",
    "category": "memory",
    "summary": "Manage project-scoped local-agent run traces for recovery, evidence, and future tuning/eval data.",
    "mcp_name": "agent_run_trace",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "init", "append", "query", "get", "export"], "default": "status"},
            "project_root": {"type": "string", "default": "."},
            "confirm": {"type": "boolean", "default": False},
            "run_id": {"type": "string"},
            "session_id": {"type": "string"},
            "status": {"type": "string"},
            "recovery_class": {"type": "string"},
            "recovery_message": {"type": "string"},
            "prompt": {"type": "string"},
            "summary": {"type": "string"},
            "selected_models": {"type": "object"},
            "allowed_tools": {"type": "array", "items": {"type": "string"}},
            "tool_calls": {"type": "array", "items": {"type": "object"}},
            "tool_results": {"type": "array", "items": {"type": "object"}},
            "approvals": {"type": "object"},
            "touched_paths": {"type": "array", "items": {"type": "string"}},
            "evidence_ids": {"type": "array", "items": {"type": "string"}},
            "verification": {"type": "object"},
            "journal_entry_uid": {"type": "string"},
            "duration_ms": {"type": "integer"},
            "operator_outcome": {"type": "string"},
            "trace": {"type": "object"},
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
            "mode": {"type": "string", "enum": ["summary", "full"], "default": "summary"},
            "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
        },
        "additionalProperties": False,
    },
}


MUTATING_ACTIONS = {"init", "append", "export"}


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
            result = append_trace(project_root, arguments)
        elif action == "query":
            result = query_traces(project_root, arguments)
        elif action == "get":
            result = get_trace(project_root, arguments)
        else:
            result = export_traces(project_root, arguments)
    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
