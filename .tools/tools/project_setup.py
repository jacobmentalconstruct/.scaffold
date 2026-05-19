from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.project_setup import apply_project_setup, audit_project_setup, verify_project_setup


FILE_METADATA = {
    "tool_name": "project_setup",
    "version": "1.0.0",
    "entrypoint": "src/tools/project_setup.py",
    "category": "bootstrap",
    "summary": "Audit, apply, or verify the project setup doctrine from inside a sidecar-equipped project.",
    "mcp_name": "project_setup",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["audit", "apply", "verify"]
            },
            "project_root": {"type": "string"},
            "sidecar_root": {"type": "string"},
            "actor_id": {"type": "string"},
            "actor_type": {"type": "string", "default": "agent"},
            "overwrite": {"type": "boolean", "default": False}
        },
        "required": ["action", "project_root"],
        "additionalProperties": False
    }
}


def run(arguments: dict) -> dict:
    action = arguments["action"]
    if action == "audit":
        result = audit_project_setup(
            arguments["project_root"],
            sidecar_root=arguments.get("sidecar_root"),
        )
    elif action == "apply":
        result = apply_project_setup(
            arguments["project_root"],
            actor_id=arguments.get("actor_id"),
            actor_type=arguments.get("actor_type", "agent"),
            overwrite=arguments.get("overwrite", False),
        )
    elif action == "verify":
        result = verify_project_setup(
            arguments["project_root"],
            sidecar_root=arguments.get("sidecar_root"),
        )
    else:
        raise ValueError(f"Unsupported action: {action}")
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
