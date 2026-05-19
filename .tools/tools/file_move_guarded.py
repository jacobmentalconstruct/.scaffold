"""
FILE: file_move_guarded.py
ROLE: Guarded move/rename tool for safe workspace operations.
WHAT IT DOES:
  - Moves files or directories under project_root
  - Requires confirm:true and a non-empty reason
  - Protects .dev-tools internals and tracked files by default
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.text_workspace import resolve_project_path, resolve_project_root, safe_relative, tracked_paths


FILE_METADATA = {
    "tool_name": "file_move_guarded",
    "version": "1.0.0",
    "entrypoint": "src/tools/file_move_guarded.py",
    "category": "editing",
    "summary": "Confirmed move/rename of files or directories under project_root with tracked-file protection.",
    "mcp_name": "file_move_guarded",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "source": {"type": "string"},
            "destination": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
            "reason": {"type": "string"},
            "overwrite": {"type": "boolean", "default": False},
            "create_dirs": {"type": "boolean", "default": False},
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
        return tool_error(FILE_METADATA["tool_name"], arguments, "move requires confirm: true")
    reason = str(arguments.get("reason", "")).strip()
    if not reason:
        return tool_error(FILE_METADATA["tool_name"], arguments, "move requires a non-empty reason")

    allow_toolbox = bool(arguments.get("allow_toolbox", False))
    source, error = resolve_project_path(project_root, str(arguments.get("source", "")), allow_toolbox=allow_toolbox, label="source", forbid_root=True)
    if error:
        return tool_error(FILE_METADATA["tool_name"], arguments, error)
    destination, error = resolve_project_path(project_root, str(arguments.get("destination", "")), allow_toolbox=allow_toolbox, label="destination", forbid_root=True)
    if error:
        return tool_error(FILE_METADATA["tool_name"], arguments, error)
    assert source is not None and destination is not None
    if not source.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"source does not exist: {safe_relative(source, project_root)}")

    source_tracked = tracked_paths(project_root, source)
    destination_tracked = tracked_paths(project_root, destination) if destination.exists() else []
    if (source_tracked or destination_tracked) and not arguments.get("allow_tracked", False):
        return tool_error(FILE_METADATA["tool_name"], arguments, "tracked files are protected; set allow_tracked: true to move tracked paths")

    if destination.exists():
        if not arguments.get("overwrite", False):
            return tool_error(FILE_METADATA["tool_name"], arguments, "destination exists; set overwrite: true")
        if destination.is_dir():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    elif not destination.parent.exists():
        if not arguments.get("create_dirs", False):
            return tool_error(FILE_METADATA["tool_name"], arguments, "destination parent does not exist; set create_dirs: true")
        destination.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(str(source), str(destination))
    result = {
        "project_root": str(project_root),
        "source": safe_relative(source, project_root),
        "destination": safe_relative(destination, project_root),
        "reason": reason,
        "tracked": bool(source_tracked or destination_tracked),
        "tracked_paths": sorted(set(source_tracked + destination_tracked)),
        "moved": True,
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
