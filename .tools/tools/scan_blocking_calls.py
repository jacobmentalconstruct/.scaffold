"""
FILE: scan_blocking_calls.py
ROLE: AST scanner for blocking calls that can freeze a Tkinter UI.
WHAT IT DOES:
  - Scans Python files under a directory for calls to subprocess.run, time.sleep,
    os.system, urlopen, and similar blocking operations.
  - Reports file, line number, and call expression for every hit.
  - Useful for auditing which modules might block the main thread.
HOW TO USE:
  - Metadata: python src/tools/scan_blocking_calls.py metadata
  - Run:      python src/tools/scan_blocking_calls.py run --input-json '{"root": "src"}'
INPUT:
  - root: folder or single file to scan
  - extra_blocking: additional dotted call patterns to flag (e.g. ["requests.get", "requests.post"])
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import should_skip_dir, standard_main, tool_result, tool_error


FILE_METADATA = {
    "tool_name": "scan_blocking_calls",
    "version": "1.0.0",
    "entrypoint": "src/tools/scan_blocking_calls.py",
    "category": "analysis",
    "summary": "Scan Python files for blocking calls that can freeze a UI thread.",
    "mcp_name": "scan_blocking_calls",
    "input_schema": {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Folder or file to scan."},
            "extra_blocking": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional dotted call patterns to flag (e.g. 'requests.get').",
                "default": [],
            },
        },
        "required": ["root"],
        "additionalProperties": False,
    },
}


BLOCKING_DOTTED = {
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_output"),
    ("subprocess", "check_call"),
    ("subprocess", "Popen"),
    ("time", "sleep"),
    ("os", "system"),
    ("os", "popen"),
    ("urllib.request", "urlopen"),
}

BLOCKING_NAMES = {"urlopen", "sleep"}


def _scan_file(path: Path, extra: set[tuple[str, str]]) -> list[dict[str, Any]]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    all_blocking = BLOCKING_DOTTED | extra
    hits: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            pair = (func.value.id, func.attr)
            if pair in all_blocking:
                hits.append({
                    "line": node.lineno,
                    "call": f"{func.value.id}.{func.attr}()",
                    "kind": "dotted",
                })
        elif isinstance(func, ast.Name) and func.id in BLOCKING_NAMES:
            hits.append({
                "line": node.lineno,
                "call": f"{func.id}()",
                "kind": "name",
            })

    return hits


def run(arguments: dict) -> dict:
    root = Path(arguments["root"]).resolve()
    extra_patterns = arguments.get("extra_blocking", [])

    if not root.exists():
        return tool_error("scan_blocking_calls", arguments, f"Path not found: {root}")

    # Parse extra patterns like "requests.get" → ("requests", "get")
    extra: set[tuple[str, str]] = set()
    for pattern in extra_patterns:
        parts = str(pattern).rsplit(".", 1)
        if len(parts) == 2:
            extra.add((parts[0], parts[1]))

    py_files: list[Path] = []
    if root.is_file():
        py_files.append(root)
    else:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
            for f in filenames:
                if f.endswith(".py"):
                    py_files.append(Path(dirpath) / f)

    file_results: list[dict[str, Any]] = []
    total_hits = 0
    for pf in sorted(py_files):
        hits = _scan_file(pf, extra)
        if hits:
            file_results.append({"file": str(pf), "hits": hits, "hit_count": len(hits)})
            total_hits += len(hits)

    return tool_result("scan_blocking_calls", arguments, {
        "summary": {
            "files_scanned": len(py_files),
            "files_with_hits": len(file_results),
            "total_blocking_calls": total_hits,
        },
        "files": file_results,
    })


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
