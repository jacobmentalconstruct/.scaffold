"""
FILE: text_file_writer.py
ROLE: Guarded text writer for safe workspace operations.
WHAT IT DOES:
  - Creates, overwrites, or appends text payloads under project_root
  - Requires confirm:true for mutation
  - Protects .dev-tools internals by default
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.text_workspace import (
    protected_path_error,
    read_text_bounded,
    resolve_project_path,
    resolve_project_root,
    safe_relative,
    validate_text,
)


FILE_METADATA = {
    "tool_name": "text_file_writer",
    "version": "1.0.0",
    "entrypoint": "src/tools/text_file_writer.py",
    "category": "write",
    "summary": "Confirmed create/overwrite/append text writes under project_root with optional validation.",
    "mcp_name": "text_file_writer",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "path": {"type": "string"},
            "content": {"type": "string", "default": ""},
            "action": {"type": "string", "enum": ["create", "overwrite", "append"], "default": "create"},
            "confirm": {"type": "boolean", "default": False},
            "overwrite": {"type": "boolean", "default": False},
            "create_dirs": {"type": "boolean", "default": False},
            "validate_after_write": {"type": "boolean", "default": False},
            "file_type": {"type": "string"},
            "allow_toolbox": {"type": "boolean", "default": False},
            "protected_paths": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    project_root = resolve_project_root(arguments.get("project_root"))
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    if not arguments.get("confirm", False):
        return tool_error(FILE_METADATA["tool_name"], arguments, "text writes require confirm: true")

    path, error = resolve_project_path(
        project_root,
        str(arguments.get("path", "")),
        allow_toolbox=bool(arguments.get("allow_toolbox", False)),
        label="path",
    )
    if error:
        return tool_error(FILE_METADATA["tool_name"], arguments, error)
    assert path is not None
    protected_paths = arguments.get("protected_paths", [])
    if not isinstance(protected_paths, list):
        return tool_error(FILE_METADATA["tool_name"], arguments, "protected_paths must be a list")
    protection_error = protected_path_error(project_root, path, [str(item) for item in protected_paths], label="path")
    if protection_error:
        return tool_result(
            FILE_METADATA["tool_name"],
            arguments,
            {"message": protection_error, "recovery_class": "control_file_tamper", "path": safe_relative(path, project_root)},
            status="error",
        )

    action = str(arguments.get("action", "create"))
    content = str(arguments.get("content", ""))
    exists = path.exists()
    overwrite = bool(arguments.get("overwrite", False))
    create_dirs = bool(arguments.get("create_dirs", False))

    if exists and path.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Target is a directory: {safe_relative(path, project_root)}")
    if action == "create" and exists and not overwrite:
        return tool_error(FILE_METADATA["tool_name"], arguments, "target exists; set overwrite: true or use action: append")
    if action == "overwrite" and not exists:
        return tool_error(FILE_METADATA["tool_name"], arguments, "overwrite target does not exist")
    if action == "overwrite" and not overwrite:
        return tool_error(FILE_METADATA["tool_name"], arguments, "replacement requires overwrite: true")
    if action == "append" and not exists:
        return tool_error(FILE_METADATA["tool_name"], arguments, "append target does not exist")
    if not path.parent.exists() and not create_dirs:
        return tool_error(FILE_METADATA["tool_name"], arguments, "parent directory does not exist; set create_dirs: true")

    final_content = content
    if action == "append" and exists:
        existing, _, read_error = read_text_bounded(path, max(path.stat().st_size + len(content.encode("utf-8")) + 1, 1))
        if read_error:
            return tool_error(FILE_METADATA["tool_name"], arguments, read_error)
        final_content = f"{existing}{content}"

    validation = None
    if arguments.get("validate_after_write", False):
        validation = validate_text(final_content, file_type=str(arguments.get("file_type", "")), path=path)
        if not validation["valid"]:
            return tool_error(FILE_METADATA["tool_name"], arguments, f"validation failed: {validation['errors']}")

    path.parent.mkdir(parents=True, exist_ok=True)
    if action == "append":
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(content)
    else:
        path.write_text(content, encoding="utf-8", newline="")

    result = {
        "project_root": str(project_root),
        "path": safe_relative(path, project_root),
        "action": action,
        "created": not exists,
        "overwrote": exists and action in {"create", "overwrite"},
        "appended": action == "append",
        "size_bytes": path.stat().st_size,
        "validation": validation,
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
