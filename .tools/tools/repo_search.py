"""
FILE: repo_search.py
ROLE: Search a repository with rg when healthy and a safe native fallback when not.
WHAT IT DOES:
  - Searches text files under a project root for a query string or regex
  - Tries ripgrep first for speed when available
  - Falls back to a Python-native recursive search when rg is unavailable or fails
  - Avoids shell invocation so Windows app-bundle/PowerShell permission snags do not
    turn into security-bypass attempts
HOW TO USE:
  - python src/tools/repo_search.py metadata
  - python src/tools/repo_search.py run --input-json '{"project_root": ".", "query": "TODO"}'
  - python src/tools/repo_search.py run --input-json '{"query": "tool_result", "extensions": [".py"]}'
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import should_skip_dir, standard_main, tool_error, tool_result

FILE_METADATA = {
    "tool_name": "repo_search",
    "version": "1.0.0",
    "entrypoint": "src/tools/repo_search.py",
    "category": "introspection",
    "summary": "Search a repository with rg when available, then fall back to a safe native text search without shell/security bypass behavior.",
    "mcp_name": "repo_search",
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "project_root": {
                "type": "string",
                "default": ".",
                "description": "Directory to search. Defaults to the current working directory.",
            },
            "query": {
                "type": "string",
                "description": "Text or regex pattern to search for.",
            },
            "regex": {
                "type": "boolean",
                "default": False,
                "description": "Treat query as a regular expression. Default uses literal text matching.",
            },
            "case_sensitive": {
                "type": "boolean",
                "default": False,
                "description": "Use case-sensitive matching.",
            },
            "extensions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional file extensions to include, such as ['.py', '.md'].",
            },
            "max_results": {
                "type": "integer",
                "default": 100,
                "description": "Maximum matching lines to return.",
            },
            "context_chars": {
                "type": "integer",
                "default": 160,
                "description": "Maximum characters of each matched line to return.",
            },
            "force_fallback": {
                "type": "boolean",
                "default": False,
                "description": "Skip rg and use the native fallback. Useful for testing and locked-down Windows shells.",
            },
            "extra_ignore": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional directory names to skip during fallback search.",
            },
        },
    },
}

TEXT_EXTENSIONS = {
    ".bat", ".c", ".cfg", ".cmd", ".cpp", ".css", ".csv", ".editorconfig",
    ".env", ".go", ".h", ".hpp", ".html", ".ini", ".java", ".js", ".json",
    ".jsx", ".lua", ".md", ".mjs", ".ps1", ".py", ".rb", ".rs", ".sh",
    ".sql", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}


def _normalize_extensions(raw: Any) -> set[str] | None:
    if not raw:
        return None
    return {str(item).lower() if str(item).startswith(".") else f".{str(item).lower()}" for item in raw}


def _line_excerpt(line: str, max_chars: int) -> str:
    text = line.rstrip("\r\n")
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _compile_pattern(query: str, *, regex: bool, case_sensitive: bool) -> re.Pattern[str]:
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = query if regex else re.escape(query)
    return re.compile(pattern, flags)


def _is_probably_text(path: Path, allowed_extensions: set[str] | None) -> bool:
    if allowed_extensions is not None:
        return path.suffix.lower() in allowed_extensions
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    return path.name in {".gitignore", ".dockerignore", "Dockerfile", "Makefile"}


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _search_with_rg(
    root: Path,
    query: str,
    *,
    regex: bool,
    case_sensitive: bool,
    allowed_extensions: set[str] | None,
    max_results: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rg_path = shutil.which("rg")
    if not rg_path:
        return [], {"attempted": False, "reason": "rg_not_found"}

    command = [
        rg_path,
        "--json",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
        "--max-count",
        str(max_results),
    ]
    if not regex:
        command.append("--fixed-strings")
    if not case_sensitive:
        command.append("--ignore-case")
    if allowed_extensions:
        for ext in sorted(allowed_extensions):
            command.extend(["--glob", f"*{ext}"])
    command.extend(["--", query, str(root)])

    completed = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode == 1:
        return [], {"attempted": True, "returncode": 1, "reason": "no_matches"}
    if completed.returncode != 0:
        return [], {
            "attempted": True,
            "returncode": completed.returncode,
            "reason": "rg_failed",
            "stderr": completed.stderr.strip()[:500],
        }

    matches: list[dict[str, Any]] = []
    for raw_line in completed.stdout.splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue
        data = event.get("data", {})
        path = Path(data.get("path", {}).get("text", ""))
        lines = data.get("lines", {}).get("text", "")
        matches.append({
            "path": _safe_relative(path, root),
            "line_number": data.get("line_number"),
            "line": _line_excerpt(lines, 1000),
            "source": "rg",
        })
        if len(matches) >= max_results:
            break

    return matches, {"attempted": True, "returncode": 0, "reason": "ok"}


def _search_native(
    root: Path,
    pattern: re.Pattern[str],
    *,
    allowed_extensions: set[str] | None,
    max_results: int,
    context_chars: int,
    extra_ignore: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    files_scanned = 0
    files_skipped = 0
    read_errors: list[dict[str, str]] = []

    for path in root.rglob("*"):
        if len(matches) >= max_results:
            break
        if path.is_dir():
            continue
        if any(should_skip_dir(part) or part in extra_ignore for part in path.relative_to(root).parts[:-1]):
            files_skipped += 1
            continue
        if not _is_probably_text(path, allowed_extensions):
            files_skipped += 1
            continue

        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                files_scanned += 1
                for line_number, line in enumerate(handle, start=1):
                    if pattern.search(line):
                        matches.append({
                            "path": _safe_relative(path, root),
                            "line_number": line_number,
                            "line": _line_excerpt(line, context_chars),
                            "source": "native_fallback",
                        })
                        if len(matches) >= max_results:
                            break
        except (OSError, UnicodeError) as exc:
            read_errors.append({"path": _safe_relative(path, root), "error": str(exc)})

    stats = {
        "files_scanned": files_scanned,
        "files_skipped": files_skipped,
        "read_error_count": len(read_errors),
        "read_errors": read_errors[:10],
    }
    return matches, stats


def run(arguments: dict) -> dict:
    query = str(arguments.get("query", ""))
    if not query:
        return tool_error(FILE_METADATA["tool_name"], arguments, "query is required")

    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    regex = bool(arguments.get("regex", False))
    case_sensitive = bool(arguments.get("case_sensitive", False))
    max_results = max(1, int(arguments.get("max_results", 100)))
    context_chars = max(20, int(arguments.get("context_chars", 160)))
    force_fallback = bool(arguments.get("force_fallback", False))
    allowed_extensions = _normalize_extensions(arguments.get("extensions"))
    extra_ignore = {str(item) for item in arguments.get("extra_ignore", [])}

    try:
        pattern = _compile_pattern(query, regex=regex, case_sensitive=case_sensitive)
    except re.error as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Invalid regex: {exc}")

    rg_info: dict[str, Any] = {"attempted": False, "reason": "force_fallback" if force_fallback else "not_attempted"}
    matches: list[dict[str, Any]] = []
    search_engine = "native_fallback"

    if not force_fallback:
        matches, rg_info = _search_with_rg(
            project_root,
            query,
            regex=regex,
            case_sensitive=case_sensitive,
            allowed_extensions=allowed_extensions,
            max_results=max_results,
        )
        if rg_info.get("reason") in {"ok", "no_matches"}:
            search_engine = "rg"

    fallback_info: dict[str, Any] = {"used": False}
    if search_engine != "rg":
        matches, native_stats = _search_native(
            project_root,
            pattern,
            allowed_extensions=allowed_extensions,
            max_results=max_results,
            context_chars=context_chars,
            extra_ignore=extra_ignore,
        )
        fallback_info = {
            "used": True,
            "reason": rg_info.get("reason", "rg_not_used"),
            **native_stats,
        }

    result = {
        "project_root": str(project_root),
        "query": query,
        "regex": regex,
        "case_sensitive": case_sensitive,
        "search_engine": search_engine,
        "fallback_used": fallback_info["used"],
        "rg": rg_info,
        "fallback": fallback_info,
        "match_count": len(matches),
        "max_results": max_results,
        "matches": matches,
        "warnings": [],
    }
    if fallback_info["used"]:
        result["warnings"].append(
            "Used native fallback search instead of rg; no shell or PowerShell bypass behavior was attempted."
        )

    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
