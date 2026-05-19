"""
FILE: runtime_artifact_cleaner.py
ROLE: Dry-run-first cleanup tool for generated runtime artifacts.
WHAT IT DOES:
  - Finds allowlisted generated artifacts such as caches, logs, and runtime exports
  - Defaults to dry-run and never removes tracked files unless explicitly allowed
  - Requires confirm:true for deletion
HOW TO USE:
  - python src/tools/runtime_artifact_cleaner.py metadata
  - python src/tools/runtime_artifact_cleaner.py run --input-json '{"project_root": "."}'
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result


FILE_METADATA = {
    "tool_name": "runtime_artifact_cleaner",
    "version": "1.0.0",
    "entrypoint": "src/tools/runtime_artifact_cleaner.py",
    "category": "cleanup",
    "summary": "Dry-run-first cleanup of allowlisted generated runtime artifacts with tracked-file protection.",
    "mcp_name": "runtime_artifact_cleaner",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "dry_run": {"type": "boolean", "default": True},
            "confirm": {"type": "boolean", "default": False},
            "allow_tracked": {"type": "boolean", "default": False},
            "include_patterns": {"type": "array", "items": {"type": "string"}},
            "max_candidates": {"type": "integer", "default": 500},
        },
        "additionalProperties": False,
    },
}


DEFAULT_PATTERNS = [
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "runtime",
    "_logs",
    "*.log",
    "_docs/_AppJOURNAL/exports/*.md",
    "_docs/_AppJOURNAL/exports/*.json",
    "packages/_manifold-mcp/artifacts/smoke-store/smoke-corpus/bags/bag_*.json",
    "packages/_ollama-prompt-lab/artifacts/runs/*",
]


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _resolve_under(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def _git_tracked(root: Path, path: Path) -> bool:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(path.relative_to(root))],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def _candidate_paths(root: Path, patterns: list[str], max_candidates: int) -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            resolved = path.resolve()
            if resolved in seen or not _resolve_under(root, resolved):
                continue
            if not path.exists():
                continue
            seen.add(resolved)
            candidates.append(path)
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def _measure(path: Path) -> tuple[int, int]:
    if path.is_file():
        try:
            return path.stat().st_size, 1
        except OSError:
            return 0, 1
    total = 0
    count = 0
    for item in path.rglob("*"):
        if item.is_file():
            count += 1
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total, count


def _remove(path: Path) -> dict[str, Any]:
    try:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        return {"removed": True, "error": ""}
    except OSError as exc:
        return {"removed": False, "error": str(exc)}


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    dry_run = bool(arguments.get("dry_run", True))
    confirm = bool(arguments.get("confirm", False))
    allow_tracked = bool(arguments.get("allow_tracked", False))
    patterns = [str(item) for item in arguments.get("include_patterns", DEFAULT_PATTERNS)]
    max_candidates = max(1, int(arguments.get("max_candidates", 500)))
    if not dry_run and not confirm:
        return tool_error(FILE_METADATA["tool_name"], arguments, "cleanup requires confirm: true when dry_run is false")

    candidates = []
    removed = []
    blocked = []
    total_bytes = 0

    for path in _candidate_paths(project_root, patterns, max_candidates):
        tracked = _git_tracked(project_root, path)
        size_bytes, file_count = _measure(path)
        item = {
            "path": _safe_relative(path, project_root),
            "kind": "directory" if path.is_dir() else "file",
            "size_bytes": size_bytes,
            "file_count": file_count,
            "tracked": tracked,
            "allowed": not tracked or allow_tracked,
        }
        total_bytes += size_bytes
        if tracked and not allow_tracked:
            item["reason"] = "tracked_file_protected"
            blocked.append(item)
            candidates.append(item)
            continue
        if dry_run:
            candidates.append(item)
            continue
        result = _remove(path)
        item.update(result)
        removed.append(item)
        candidates.append(item)

    result = {
        "project_root": str(project_root),
        "dry_run": dry_run,
        "confirm": confirm,
        "allow_tracked": allow_tracked,
        "patterns": patterns,
        "candidate_count": len(candidates),
        "blocked_count": len(blocked),
        "removed_count": len(removed),
        "total_candidate_bytes": total_bytes,
        "candidates": candidates,
        "blocked": blocked,
        "removed": removed,
        "summary": {
            "defaulted_to_dry_run": dry_run,
            "tracked_files_protected": not allow_tracked,
            "truncated": len(candidates) >= max_candidates,
        },
        "warnings": ["Only allowlisted generated artifacts are considered; review dry-run output before cleanup."],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
