"""
FILE: text_file_reader.py
ROLE: Bounded text reader for safe workspace operations.
WHAT IT DOES:
  - Resolves paths under project_root
  - Rejects outside-root, protected .dev-tools, oversized, and binary files
  - Reports basic text metadata with optional content/excerpt
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.text_workspace import read_text_bounded, resolve_project_path, resolve_project_root, safe_relative


FILE_METADATA = {
    "tool_name": "text_file_reader",
    "version": "1.0.0",
    "entrypoint": "src/tools/text_file_reader.py",
    "category": "introspection",
    "summary": "Bounded text reads under project_root with binary, size, and .dev-tools protections.",
    "mcp_name": "text_file_reader",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "path": {"type": "string"},
            "max_bytes": {"type": "integer", "default": 65536},
            "include_content": {"type": "boolean", "default": True},
            "excerpt_lines": {"type": "integer", "default": 40},
            "allow_toolbox": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    project_root = resolve_project_root(arguments.get("project_root"))
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    path, error = resolve_project_path(
        project_root,
        str(arguments.get("path", "")),
        allow_toolbox=bool(arguments.get("allow_toolbox", False)),
        label="path",
    )
    if error:
        return tool_error(FILE_METADATA["tool_name"], arguments, error)
    assert path is not None
    if not path.is_file():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a file: {safe_relative(path, project_root)}")

    content, metadata, error = read_text_bounded(path, max(1, int(arguments.get("max_bytes", 65536))))
    if error:
        return tool_error(FILE_METADATA["tool_name"], arguments, error)
    assert content is not None

    excerpt_lines = max(0, int(arguments.get("excerpt_lines", 40)))
    lines = content.splitlines()
    excerpt = "\n".join(lines[:excerpt_lines]) if excerpt_lines else ""
    result = {
        "project_root": str(project_root),
        "path": safe_relative(path, project_root),
        **metadata,
        "include_content": bool(arguments.get("include_content", True)),
        "excerpt": excerpt,
        "excerpt_line_count": len(lines[:excerpt_lines]) if excerpt_lines else 0,
        "truncated_excerpt": excerpt_lines > 0 and len(lines) > excerpt_lines,
    }
    if arguments.get("include_content", True):
        result["content"] = content
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
