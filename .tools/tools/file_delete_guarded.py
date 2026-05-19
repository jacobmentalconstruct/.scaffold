"""
FILE: file_delete_guarded.py
ROLE: Guarded quarantine-delete tool for safe workspace operations.
WHAT IT DOES:
  - Requires confirm:true and a non-empty reason
  - Moves targets into ignored runtime trash instead of permanent deletion
  - Protects .dev-tools internals and tracked files by default
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.text_workspace import quarantine_target, resolve_project_path, resolve_project_root, safe_relative, tracked_paths


FILE_METADATA = {
    "tool_name": "file_delete_guarded",
    "version": "1.0.0",
    "entrypoint": "src/tools/file_delete_guarded.py",
    "category": "editing",
    "summary": "Confirmed quarantine-delete under project_root with receipts and tracked-file protection.",
    "mcp_name": "file_delete_guarded",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "path": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
            "reason": {"type": "string"},
            "actor": {"type": "string", "default": "agent"},
            "allow_tracked": {"type": "boolean", "default": False},
            "allow_toolbox": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    project_root = resolve_project_root(arguments.get("project_root"))
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    if not arguments.get("confirm", False):
        return tool_error(FILE_METADATA["tool_name"], arguments, "delete requires confirm: true")
    reason = str(arguments.get("reason", "")).strip()
    if not reason:
        return tool_error(FILE_METADATA["tool_name"], arguments, "delete requires a non-empty reason")

    path, error = resolve_project_path(
        project_root,
        str(arguments.get("path", "")),
        allow_toolbox=bool(arguments.get("allow_toolbox", False)),
        label="path",
        forbid_root=True,
    )
    if error:
        return tool_error(FILE_METADATA["tool_name"], arguments, error)
    assert path is not None
    if not path.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"path does not exist: {safe_relative(path, project_root)}")

    tracked = tracked_paths(project_root, path)
    if tracked and not arguments.get("allow_tracked", False):
        return tool_error(FILE_METADATA["tool_name"], arguments, "tracked files are protected; set allow_tracked: true to quarantine tracked paths")

    receipt = quarantine_target(
        project_root,
        path,
        actor=str(arguments.get("actor", "agent")),
        reason=reason,
        tracked=tracked,
    )
    result = {
        "project_root": str(project_root),
        "path": receipt["original_path"],
        "quarantined": True,
        "receipt": receipt,
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
