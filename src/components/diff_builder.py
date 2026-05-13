"""
FILE: src/components/diff_builder.py
ROLE: Constructs unified diffs and hunk metadata for provenance capture.
WHAT IT DOES: Builds deterministic unified diff text from before/after text,
              computes per-hunk line ranges, and exposes a short preview for
              evidence surfaces.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


@dataclass(frozen=True)
class DiffResult:
    path: str
    unified_diff_text: str
    hunks: list[dict]
    hunk_count: int
    added_lines: int
    removed_lines: int
    context_hash: str
    kind: str = "text"


class DiffBuilder:
    @staticmethod
    def from_strings(*, path: str, before: str, after: str, context_lines: int = 3) -> DiffResult:
        before_lines = before.splitlines(keepends=True)
        after_lines = after.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=path,
                tofile=path,
                n=context_lines,
                lineterm="",
            )
        )
        unified = "\n".join(diff_lines)
        hunks = _parse_hunks(diff_lines)
        return DiffResult(
            path=path,
            unified_diff_text=unified,
            hunks=hunks,
            hunk_count=len(hunks),
            added_lines=sum(item["added_lines"] for item in hunks),
            removed_lines=sum(item["removed_lines"] for item in hunks),
            context_hash=hashlib.sha256(f"{path}\n{before}\n{after}".encode("utf-8")).hexdigest(),
        )

    @staticmethod
    def from_files(*, project_root: Path, path: str, after_text: str, context_lines: int = 3) -> DiffResult:
        target = (Path(project_root).resolve() / path).resolve()
        before_text = target.read_text(encoding="utf-8") if target.is_file() else ""
        return DiffBuilder.from_strings(path=path, before=before_text, after=after_text, context_lines=context_lines)

    @staticmethod
    def preview(diff_result: DiffResult, max_lines: int = 80) -> str:
        lines = diff_result.unified_diff_text.splitlines()
        if len(lines) <= max_lines:
            return diff_result.unified_diff_text
        return "\n".join(lines[:max_lines] + ["", f"... truncated {len(lines) - max_lines} more line(s)"])


def _parse_hunks(diff_lines: list[str]) -> list[dict]:
    hunks: list[dict] = []
    current: dict | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        nonlocal current, current_lines
        if current is None:
            return
        diff_text = "\n".join(current_lines)
        added = 0
        removed = 0
        for line in current_lines[1:]:
            if line.startswith("+") and not line.startswith("+++"):
                added += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed += 1
        current["diff_text"] = diff_text
        current["added_lines"] = added
        current["removed_lines"] = removed
        hunks.append(current)
        current = None
        current_lines = []

    for line in diff_lines:
        if line.startswith("@@ "):
            _flush()
            match = _HUNK_HEADER.match(line)
            if not match:
                continue
            current = {
                "old_start": int(match.group("old_start")),
                "old_count": int(match.group("old_count") or "1"),
                "new_start": int(match.group("new_start")),
                "new_count": int(match.group("new_count") or "1"),
            }
            current_lines = [line]
            continue
        if current is not None:
            current_lines.append(line)
    _flush()
    return hunks
