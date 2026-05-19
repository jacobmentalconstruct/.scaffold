"""
FILE: file_tree_snapshot.py
ROLE: Snapshot the file tree of a project for agent orientation.
WHAT IT DOES:
  - Walks a project directory and produces a structured JSON tree
  - Reports file sizes, line counts, and last-modified timestamps
  - Optionally extracts the first docstring from each .py file
  - Respects standard ignore patterns (.venv, node_modules, __pycache__, etc.)
  - Zero write risk — purely read-only introspection
HOW TO USE:
  - python src/tools/file_tree_snapshot.py metadata
  - python src/tools/file_tree_snapshot.py run --input-json '{"project_root": "path/to/project"}'
  - python src/tools/file_tree_snapshot.py run --input-json '{"project_root": ".", "include_docstrings": true, "max_depth": 4}'
"""

from __future__ import annotations

import ast
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result, tool_error, should_skip_dir

FILE_METADATA = {
    "tool_name": "file_tree_snapshot",
    "version": "1.0.0",
    "entrypoint": "src/tools/file_tree_snapshot.py",
    "category": "introspection",
    "summary": "Snapshot a project's file tree: paths, sizes, line counts, timestamps, and optional Python docstrings for fast agent orientation.",
    "mcp_name": "file_tree_snapshot",
    "input_schema": {
        "type": "object",
        "required": ["project_root"],
        "properties": {
            "project_root": {
                "type": "string",
                "description": "Path to the project root directory."
            },
            "max_depth": {
                "type": "integer",
                "default": 8,
                "description": "Maximum directory depth to walk (0 = root only)."
            },
            "include_docstrings": {
                "type": "boolean",
                "default": False,
                "description": "If true, extract the module-level docstring from each .py file."
            },
            "include_line_counts": {
                "type": "boolean",
                "default": True,
                "description": "If true, count lines in text files."
            },
            "extensions_filter": {
                "type": "array",
                "items": {"type": "string"},
                "description": "If set, only include files with these extensions (e.g. ['.py', '.json', '.md']). Empty = all files."
            },
            "extra_ignore": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional directory names to skip."
            }
        }
    }
}


def _extract_docstring(filepath: Path) -> str | None:
    """Extract the module-level docstring from a Python file."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
        ds = ast.get_docstring(tree)
        if ds and len(ds) > 500:
            return ds[:500] + "..."
        return ds
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return None


def _count_lines(filepath: Path) -> int:
    """Count lines in a text file. Returns -1 if binary or unreadable."""
    try:
        return sum(1 for _ in filepath.open("r", encoding="utf-8", errors="replace"))
    except Exception:
        return -1


def _is_text_extension(ext: str) -> bool:
    """Heuristic: is this extension likely a text file?"""
    text_exts = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".md", ".txt",
        ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".sql",
        ".html", ".css", ".xml", ".sh", ".bat", ".ps1", ".r", ".rs",
        ".go", ".java", ".c", ".cpp", ".h", ".hpp", ".rb", ".lua",
        ".gitignore", ".env", ".editorconfig",
    }
    return ext.lower() in text_exts


def _walk_tree(
    root: Path,
    base: Path,
    depth: int,
    max_depth: int,
    include_docstrings: bool,
    include_line_counts: bool,
    extensions_filter: set[str] | None,
    extra_ignore: set[str],
) -> dict[str, Any]:
    """Recursively walk and build the tree structure."""
    node: dict[str, Any] = {
        "name": root.name or str(root),
        "type": "directory",
        "path": str(root.relative_to(base)),
    }

    if depth > max_depth:
        node["truncated"] = True
        return node

    children_dirs: list[dict] = []
    children_files: list[dict] = []
    total_files = 0
    total_size = 0

    try:
        entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        node["error"] = "permission denied"
        return node

    for entry in entries:
        if entry.is_dir():
            if should_skip_dir(entry.name) or entry.name in extra_ignore:
                continue
            child = _walk_tree(
                entry, base, depth + 1, max_depth,
                include_docstrings, include_line_counts,
                extensions_filter, extra_ignore,
            )
            children_dirs.append(child)
            total_files += child.get("total_files", 0)
            total_size += child.get("total_size", 0)

        elif entry.is_file():
            ext = entry.suffix.lower()
            if extensions_filter and ext not in extensions_filter:
                continue

            try:
                stat = entry.stat()
            except (PermissionError, OSError):
                continue

            file_info: dict[str, Any] = {
                "name": entry.name,
                "type": "file",
                "path": str(entry.relative_to(base)),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M"),
            }

            if include_line_counts and _is_text_extension(ext):
                lines = _count_lines(entry)
                if lines >= 0:
                    file_info["lines"] = lines

            if include_docstrings and ext == ".py":
                ds = _extract_docstring(entry)
                if ds:
                    file_info["docstring"] = ds

            children_files.append(file_info)
            total_files += 1
            total_size += stat.st_size

    node["children"] = children_dirs + children_files
    node["total_files"] = total_files
    node["total_size"] = total_size
    node["dir_count"] = len(children_dirs)
    node["file_count"] = len(children_files)

    return node


def run(arguments: dict) -> dict:
    project_root = Path(arguments["project_root"]).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    max_depth = arguments.get("max_depth", 8)
    include_docstrings = arguments.get("include_docstrings", False)
    include_line_counts = arguments.get("include_line_counts", True)
    extensions_filter = arguments.get("extensions_filter")
    extra_ignore = set(arguments.get("extra_ignore", []))

    ext_set = {e if e.startswith(".") else f".{e}" for e in extensions_filter} if extensions_filter else None

    try:
        tree = _walk_tree(
            project_root, project_root, 0, max_depth,
            include_docstrings, include_line_counts,
            ext_set, extra_ignore,
        )

        result = {
            "project_root": str(project_root),
            "total_files": tree.get("total_files", 0),
            "total_size_bytes": tree.get("total_size", 0),
            "tree": tree,
        }

        return tool_result(FILE_METADATA["tool_name"], arguments, result)

    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
