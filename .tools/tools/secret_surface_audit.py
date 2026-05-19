"""
FILE: secret_surface_audit.py
ROLE: Read-only secret and risky env surface auditor.
WHAT IT DOES:
  - Scans text files for obvious committed secrets and risky env exposure
  - Redacts discovered values in every finding
  - Skips common generated/dependency directories by default
HOW TO USE:
  - python src/tools/secret_surface_audit.py metadata
  - python src/tools/secret_surface_audit.py run --input-json '{"project_root": "."}'
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import should_skip_dir, standard_main, tool_error, tool_result


FILE_METADATA = {
    "tool_name": "secret_surface_audit",
    "version": "1.0.0",
    "entrypoint": "src/tools/secret_surface_audit.py",
    "category": "security",
    "summary": "Read-only scan for obvious committed secrets and risky env exposure with redacted output.",
    "mcp_name": "secret_surface_audit",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "max_files": {"type": "integer", "default": 2000},
            "max_findings": {"type": "integer", "default": 100},
            "extensions": {"type": "array", "items": {"type": "string"}},
            "extra_ignore": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
}


TEXT_EXTENSIONS = {
    ".bat", ".cfg", ".cmd", ".conf", ".css", ".csv", ".env", ".html", ".ini",
    ".js", ".json", ".jsx", ".md", ".mjs", ".ps1", ".py", ".sh", ".sql",
    ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}

RISKY_ENV_NAMES = {".env", ".env.local", ".env.production", ".env.development", ".env.test"}

SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "high"),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"), "high"),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "high"),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "critical"),
    ("assignment_secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd|client[_-]?secret)\b\s*[:=]\s*['\"]?([^'\"\s#]{8,})"
    ), "medium"),
]


def _normalize_extensions(raw: Any) -> set[str] | None:
    if not raw:
        return None
    return {str(item).lower() if str(item).startswith(".") else f".{str(item).lower()}" for item in raw}


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _is_text_file(path: Path, allowed: set[str] | None) -> bool:
    if allowed is not None:
        return path.suffix.lower() in allowed or path.name in allowed
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in {".gitignore", ".dockerignore", "Dockerfile", "Makefile"} or path.name.startswith(".env")


def _redact(value: str) -> str:
    text = value.strip().strip("'\"")
    if len(text) <= 8:
        return "***REDACTED***"
    return f"{text[:3]}...{text[-3:]} ({len(text)} chars)"


def _line_preview(line: str, secret_value: str = "") -> str:
    text = line.strip()
    if secret_value:
        text = text.replace(secret_value, "***REDACTED***")
    return text[:240]


def _scan_file(path: Path, root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [{
            "path": _safe_relative(path, root),
            "line_number": 0,
            "kind": "read_error",
            "severity": "low",
            "redacted_value": "",
            "line_preview": "",
            "message": str(exc),
        }]
    for line_number, line in enumerate(lines, start=1):
        for kind, pattern, severity in SECRET_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            secret_value = match.group(2) if kind == "assignment_secret" and match.lastindex and match.lastindex >= 2 else match.group(0)
            findings.append({
                "path": _safe_relative(path, root),
                "line_number": line_number,
                "kind": kind,
                "severity": severity,
                "redacted_value": _redact(secret_value),
                "line_preview": _line_preview(line, secret_value),
                "message": "Potential secret-like value detected; verify before sharing or packaging.",
            })
    return findings


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    max_files = max(1, int(arguments.get("max_files", 2000)))
    max_findings = max(1, int(arguments.get("max_findings", 100)))
    allowed_extensions = _normalize_extensions(arguments.get("extensions"))
    extra_ignore = {str(item) for item in arguments.get("extra_ignore", [])}

    findings: list[dict[str, Any]] = []
    risky_env_files: list[dict[str, Any]] = []
    files_scanned = 0
    files_skipped = 0

    for path in project_root.rglob("*"):
        if len(findings) >= max_findings or files_scanned >= max_files:
            break
        if not path.is_file():
            continue
        rel_parts = path.relative_to(project_root).parts
        if any(should_skip_dir(part) or part in extra_ignore for part in rel_parts[:-1]):
            files_skipped += 1
            continue
        if path.name in RISKY_ENV_NAMES or path.name.startswith(".env."):
            risky_env_files.append({
                "path": _safe_relative(path, project_root),
                "message": "Environment file is present in the project tree; confirm it is gitignored and safe before packaging.",
            })
        if not _is_text_file(path, allowed_extensions):
            files_skipped += 1
            continue
        files_scanned += 1
        findings.extend(_scan_file(path, project_root))

    findings = findings[:max_findings]
    severities: dict[str, int] = {}
    for finding in findings:
        severity = str(finding.get("severity", "unknown"))
        severities[severity] = severities.get(severity, 0) + 1

    result = {
        "project_root": str(project_root),
        "files_scanned": files_scanned,
        "files_skipped": files_skipped,
        "finding_count": len(findings),
        "risky_env_file_count": len(risky_env_files),
        "risky_env_files": risky_env_files[:50],
        "findings": findings,
        "summary": {
            "severity_counts": severities,
            "redacted": True,
            "truncated": len(findings) >= max_findings or files_scanned >= max_files,
        },
        "warnings": ["Findings are heuristic and redacted; manually verify before rotating credentials or deleting files."],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
