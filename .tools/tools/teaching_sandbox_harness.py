"""
FILE: teaching_sandbox_harness.py
ROLE: Guarded teaching/evaluation harness for local-agent sandbox practice.
WHAT IT DOES: Creates ignored sandbox projects, runs sidecar teaching scenarios, verifies outputs, scores runs, and exports scorecards.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.teaching_sandbox_harness import (
    compare_runs,
    create_project,
    export_review,
    export_run,
    init_store,
    latest_status,
    list_scenarios,
    run_agent,
    run_scenario,
    scenario_plan,
    score_run,
    status,
    tail_events,
    verify_project,
)
from lib.text_workspace import resolve_project_root


FILE_METADATA = {
    "tool_name": "teaching_sandbox_harness",
    "version": "1.0.0",
    "entrypoint": "src/tools/teaching_sandbox_harness.py",
    "category": "evaluation",
    "summary": "Run ignored local-agent teaching sandboxes with guarded scaffolding, verification, evidence, traces, and scorecards.",
    "mcp_name": "teaching_sandbox_harness",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status",
                    "init",
                    "list_scenarios",
                    "plan",
                    "create_project",
                    "run_agent",
                    "verify_project",
                    "score",
                    "compare_runs",
                    "export_review",
                    "latest_status",
                    "tail_events",
                    "run_scenario",
                    "export",
                ],
                "default": "status",
            },
            "project_root": {"type": "string", "default": "."},
            "confirm": {"type": "boolean", "default": False},
            "scenario_id": {"type": "string", "default": "static_task_tracker"},
            "project_id": {"type": "string"},
            "run_id": {"type": "string"},
            "run_ids": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "default": 12},
            "session_id": {"type": "string"},
            "prompt": {"type": "string"},
            "ollama_base_url": {"type": "string", "default": "http://localhost:11434"},
            "planner_model": {"type": "string", "default": "qwen2.5-coder:7b"},
            "response_model": {"type": "string", "default": "qwen3.5:4b"},
            "timeout_seconds": {"type": "integer", "default": 60},
            "max_tool_rounds": {"type": "integer", "default": 4},
            "allowed_tools": {"type": "array", "items": {"type": "string"}},
            "confirm_checkpoint": {"type": "boolean", "default": False},
            "checkpoint": {"type": "boolean", "default": False},
            "window_turns": {"type": "integer", "default": 8},
            "use_evidence_shelf": {"type": "boolean", "default": True},
            "preflight": {"type": "boolean", "default": False},
            "run_mode": {"type": "string", "enum": ["mocked", "live"], "default": "mocked"},
            "mock_ollama_responses": {"type": "array", "items": {"type": "string"}},
            "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
        },
        "additionalProperties": False,
    },
}


MUTATING_ACTIONS = {"init", "create_project", "run_agent", "run_scenario", "export", "export_review"}


def _approval(action: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
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

    confirmation = _approval(action, arguments)
    if confirmation is not None:
        return confirmation

    try:
        if action == "status":
            result = status(project_root)
        elif action == "init":
            result = init_store(project_root)
        elif action == "list_scenarios":
            result = list_scenarios()
        elif action == "plan":
            result = scenario_plan(arguments)
        elif action == "create_project":
            result = create_project(project_root, arguments)
        elif action == "run_agent":
            result = run_agent(project_root, arguments)
        elif action == "verify_project":
            result = verify_project(project_root, arguments)
        elif action == "score":
            result = score_run(project_root, arguments)
        elif action == "compare_runs":
            result = compare_runs(project_root, arguments)
        elif action == "export_review":
            result = export_review(project_root, arguments)
        elif action == "latest_status":
            result = latest_status(project_root, arguments)
        elif action == "tail_events":
            result = tail_events(project_root, arguments)
        elif action == "run_scenario":
            result = run_scenario(project_root, arguments)
        else:
            result = export_run(project_root, arguments)
    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
