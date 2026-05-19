"""
FILE: text_file_validator.py
ROLE: Stdlib text validation tool for safe workspace operations.
WHAT IT DOES:
  - Validates Python, JSON, TOML, and basic text-like surfaces
  - Accepts either a bounded project file path or an inline content payload
  - Never mutates the project
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.text_workspace import (
    read_text_bounded,
    resolve_project_path,
    resolve_project_root,
    safe_relative,
    validate_text,
)


FILE_METADATA = {
    "tool_name": "text_file_validator",
    "version": "1.0.0",
    "entrypoint": "src/tools/text_file_validator.py",
    "category": "testing",
    "summary": "Validate Python, JSON, TOML, and basic text-like files without third-party dependencies.",
    "mcp_name": "text_file_validator",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "path": {"type": "string"},
            "content": {"type": "string"},
            "file_type": {"type": "string"},
            "max_bytes": {"type": "integer", "default": 131072},
            "allow_toolbox": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    project_root = resolve_project_root(arguments.get("project_root"))
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    content = arguments.get("content")
    path_arg = arguments.get("path", "")
    path = None
    source = "content"

    if content is None:
        path, error = resolve_project_path(
            project_root,
            str(path_arg),
            allow_toolbox=bool(arguments.get("allow_toolbox", False)),
            label="path",
        )
        if error:
            return tool_error(FILE_METADATA["tool_name"], arguments, error)
        assert path is not None
        if not path.is_file():
            return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a file: {safe_relative(path, project_root)}")
        content, read_meta, error = read_text_bounded(path, max(1, int(arguments.get("max_bytes", 131072))))
        if error:
            return tool_error(FILE_METADATA["tool_name"], arguments, error)
        source = "file"
    else:
        read_meta = {
            "size_bytes": len(str(content).encode("utf-8")),
            "encoding": "inline",
        }

    validation = validate_text(str(content), file_type=str(arguments.get("file_type", "")), path=path)
    result = {
        "project_root": str(project_root),
        "path": safe_relative(path, project_root) if path else "",
        "source": source,
        "metadata": read_meta,
        "validation": validation,
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result, status="ok" if validation["valid"] else "error")


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
