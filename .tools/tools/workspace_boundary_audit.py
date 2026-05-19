"""
FILE: workspace_boundary_audit.py
ROLE: Read-only workspace boundary auditor for local-agent operations.
WHAT IT DOES:
  - Resolves project root, sidecar root, git root, runtime/ignored paths, and size
  - Reports whether key operational surfaces exist
  - Avoids mutation; this is an orientation and safety-boundary tool only
HOW TO USE:
  - python src/tools/workspace_boundary_audit.py metadata
  - python src/tools/workspace_boundary_audit.py run --input-json '{"project_root": "."}'
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import should_skip_dir, standard_main, tool_error, tool_result


FILE_METADATA = {
    "tool_name": "workspace_boundary_audit",
    "version": "1.0.0",
    "entrypoint": "src/tools/workspace_boundary_audit.py",
    "category": "introspection",
    "summary": "Read-only audit of project root, sidecar root, git root, ignored/runtime paths, disk footprint, and write-boundary warnings.",
    "mcp_name": "workspace_boundary_audit",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "max_depth": {"type": "integer", "default": 8},
            "extra_ignore": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
}


RUNTIME_PATHS = [
    "_docs/_journalDB/app_journal.sqlite3",
    "_docs/_AppJOURNAL/journal_config.json",
    "_docs/_AppJOURNAL/db_manifest.json",
    "_docs/_AppJOURNAL/exports",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    "_logs",
    "runtime",
]


def _git_root(project_root: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if completed.returncode == 0:
            return {"available": True, "root": completed.stdout.strip()}
        return {"available": False, "root": "", "reason": completed.stderr.strip()[:300]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "root": "", "reason": str(exc)}


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _measure_tree(root: Path, max_depth: int, extra_ignore: set[str]) -> dict[str, Any]:
    file_count = 0
    dir_count = 0
    total_bytes = 0
    skipped_dirs: list[str] = []
    largest_files: list[dict[str, Any]] = []

    for path in root.rglob("*"):
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if len(rel_parts) > max_depth + 1:
            continue
        if any(should_skip_dir(part) or part in extra_ignore for part in rel_parts[:-1]):
            continue
        if path.is_dir():
            if should_skip_dir(path.name) or path.name in extra_ignore:
                skipped_dirs.append(_safe_relative(path, root))
                continue
            dir_count += 1
        elif path.is_file():
            try:
                size = path.stat().st_size
            except OSError:
                continue
            file_count += 1
            total_bytes += size
            largest_files.append({"path": _safe_relative(path, root), "size_bytes": size})

    largest_files.sort(key=lambda item: item["size_bytes"], reverse=True)
    return {
        "file_count": file_count,
        "dir_count": dir_count,
        "total_bytes": total_bytes,
        "largest_files": largest_files[:10],
        "skipped_dirs": skipped_dirs[:50],
    }


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    max_depth = int(arguments.get("max_depth", 8))
    extra_ignore = {str(item) for item in arguments.get("extra_ignore", [])}
    sidecar_root = project_root / ".dev-tools"
    if (project_root / "toolbox_manifest.json").exists() and (project_root / "src" / "mcp_server.py").exists():
        sidecar_root = project_root

    runtime = []
    for rel in RUNTIME_PATHS:
        path = project_root / rel
        runtime.append({
            "path": rel,
            "exists": path.exists(),
            "kind": "directory" if path.is_dir() else "file" if path.is_file() else "missing",
        })

    git = _git_root(project_root)
    warnings: list[str] = []
    if git["available"] and Path(git["root"]).resolve() != project_root:
        warnings.append("Project root is inside a larger git worktree; keep write scope explicit.")
    if not sidecar_root.exists():
        warnings.append("No .dev-tools sidecar was found at project root.")
    if project_root.parent == project_root:
        warnings.append("Project root resolved to filesystem root; unsafe for tool operations.")

    result = {
        "project_root": str(project_root),
        "sidecar_root": str(sidecar_root) if sidecar_root.exists() else "",
        "sidecar_present": sidecar_root.exists(),
        "git": git,
        "runtime_paths": runtime,
        "footprint": _measure_tree(project_root, max_depth, extra_ignore),
        "safe_write_boundary": str(project_root),
        "unsafe_write_targets": [
            str(project_root.parent),
            str(Path.home()),
        ],
        "warnings": warnings,
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
