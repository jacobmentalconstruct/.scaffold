"""
FILE: directory_scaffold.py
ROLE: Declarative directory/file scaffold tool for safe workspace operations.
WHAT IT DOES:
  - Applies a manifest of directories and text files under project_root
  - Defaults to dry-run and requires confirm:true to write
  - Skips existing files unless overwrite:true
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.text_workspace import protected_path_error, resolve_project_path, resolve_project_root, safe_relative, validate_text


FILE_METADATA = {
    "tool_name": "directory_scaffold",
    "version": "1.0.0",
    "entrypoint": "src/tools/directory_scaffold.py",
    "category": "scaffold",
    "summary": "Dry-run-first declarative directory and text-file scaffolding under project_root.",
    "mcp_name": "directory_scaffold",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "entries": {"type": "array", "items": {"type": "object"}},
            "dry_run": {"type": "boolean", "default": True},
            "confirm": {"type": "boolean", "default": False},
            "create_parents": {"type": "boolean", "default": True},
            "validate_files": {"type": "boolean", "default": False},
            "allow_toolbox": {"type": "boolean", "default": False},
            "protected_paths": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
}


def _entry_plan(
    project_root: Path,
    entry: dict[str, Any],
    allow_toolbox: bool,
    protected_paths: list[str],
    validate_files: bool,
    create_parents: bool,
) -> dict[str, Any]:
    entry_type = str(entry.get("type", entry.get("kind", "file"))).lower()
    if entry_type not in {"directory", "file"}:
        entry_type = "file"
    path, error = resolve_project_path(project_root, str(entry.get("path", "")), allow_toolbox=allow_toolbox, label="entry.path")
    item: dict[str, Any] = {
        "path": str(entry.get("path", "")),
        "type": entry_type,
        "status": "planned",
        "action": "",
    }
    if error:
        item.update({"status": "blocked", "reason": error})
        return item
    assert path is not None
    item["path"] = safe_relative(path, project_root)
    protection_error = protected_path_error(project_root, path, protected_paths, label="entry.path")
    if protection_error:
        item.update({"status": "blocked", "reason": protection_error, "recovery_class": "control_file_tamper"})
        return item

    if entry_type == "directory":
        if not path.parent.exists() and not create_parents:
            item.update({"status": "blocked", "reason": "parent directory does not exist"})
            return item
        if path.exists() and not path.is_dir():
            item.update({"status": "blocked", "reason": "path exists and is not a directory"})
        elif path.exists():
            item.update({"status": "exists", "action": "keep_directory"})
        else:
            item["action"] = "create_directory"
        return item

    overwrite = bool(entry.get("overwrite", False))
    if not path.parent.exists() and not create_parents:
        item.update({"status": "blocked", "reason": "parent directory does not exist"})
        return item
    if path.exists() and path.is_dir():
        item.update({"status": "blocked", "reason": "path exists and is a directory"})
        return item
    if path.exists() and not overwrite:
        item.update({"status": "skipped", "action": "skip_existing_file"})
        return item
    content = str(entry.get("content", ""))
    if validate_files:
        validation = validate_text(content, file_type=str(entry.get("file_type", "")), path=path)
        item["validation"] = validation
        if not validation["valid"]:
            item.update({"status": "blocked", "reason": "validation failed"})
            return item
    item["action"] = "overwrite_file" if path.exists() else "create_file"
    item["size_bytes"] = len(content.encode("utf-8"))
    return item


def run(arguments: dict) -> dict:
    project_root = resolve_project_root(arguments.get("project_root"))
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    entries = arguments.get("entries", [])
    if not isinstance(entries, list):
        return tool_error(FILE_METADATA["tool_name"], arguments, "entries must be a list")
    dry_run = bool(arguments.get("dry_run", True))
    confirm = bool(arguments.get("confirm", False))
    if not dry_run and not confirm:
        return tool_error(FILE_METADATA["tool_name"], arguments, "scaffold writes require confirm: true when dry_run is false")

    allow_toolbox = bool(arguments.get("allow_toolbox", False))
    protected_paths = arguments.get("protected_paths", [])
    if not isinstance(protected_paths, list):
        return tool_error(FILE_METADATA["tool_name"], arguments, "protected_paths must be a list")
    protected_paths = [str(item) for item in protected_paths]
    validate_files = bool(arguments.get("validate_files", False))
    create_parents = bool(arguments.get("create_parents", True))
    plans = [_entry_plan(project_root, dict(entry), allow_toolbox, protected_paths, validate_files, create_parents) for entry in entries]
    blocked = [item for item in plans if item["status"] == "blocked"]
    if blocked and not dry_run:
        recovery_class = "control_file_tamper" if any(item.get("recovery_class") == "control_file_tamper" for item in blocked) else "tool_schema_error"
        return tool_result(
            FILE_METADATA["tool_name"],
            arguments,
            {"message": f"blocked scaffold entries: {blocked}", "blocked": blocked, "recovery_class": recovery_class},
            status="error",
        )

    applied: list[dict[str, Any]] = []
    if not dry_run:
        for entry, plan in zip(entries, plans):
            if plan["status"] in {"blocked", "skipped", "exists"}:
                continue
            path, error = resolve_project_path(project_root, str(entry.get("path", "")), allow_toolbox=allow_toolbox, label="entry.path")
            if error:
                continue
            assert path is not None
            if plan["type"] == "directory":
                path.mkdir(parents=True, exist_ok=True)
            else:
                if create_parents:
                    path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(entry.get("content", "")), encoding="utf-8", newline="")
            applied.append(plan)

    result = {
        "project_root": str(project_root),
        "dry_run": dry_run,
        "entry_count": len(plans),
        "blocked_count": len(blocked),
        "applied_count": len(applied),
        "entries": plans,
        "applied": applied,
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
