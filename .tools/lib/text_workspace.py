from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - Python <3.11 fallback
    tomllib = None


TEXT_EXTENSIONS = {
    ".bat", ".cfg", ".cmd", ".conf", ".css", ".csv", ".env", ".html",
    ".ini", ".js", ".json", ".jsx", ".md", ".mjs", ".ps1", ".py", ".sh",
    ".sql", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}

SPECIAL_TEXT_NAMES = {".dockerignore", ".gitignore", "Dockerfile", "Makefile", "README"}

VALIDATION_TYPES = {
    "batch", "css", "html", "json", "markdown", "python", "shell", "text",
    "toml", "yaml",
}


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def resolve_project_root(value: str | None = None) -> Path:
    return Path(value or ".").resolve()


def normalized_project_relative(path: Path, root: Path) -> str:
    return safe_relative(path.resolve(), root.resolve()).lower()


def protected_path_error(
    project_root: Path,
    path: Path,
    protected_paths: list[str] | tuple[str, ...],
    *,
    label: str = "path",
) -> str:
    if not protected_paths:
        return ""
    target = normalized_project_relative(path, project_root)
    for value in protected_paths:
        if not str(value).strip():
            continue
        protected = (project_root / str(value)).resolve()
        if target == normalized_project_relative(protected, project_root):
            return f"{label} targets protected control file: {target}"
    return ""


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def resolve_project_path(
    project_root: Path,
    value: str,
    *,
    allow_toolbox: bool = False,
    label: str = "path",
    forbid_root: bool = False,
) -> tuple[Path | None, str]:
    if not value:
        return None, f"{label} is required"
    path = (project_root / value).resolve()
    try:
        relative = path.relative_to(project_root)
    except ValueError:
        return None, f"{label} escapes project_root: {value}"
    if forbid_root and str(relative) == ".":
        return None, f"{label} must not be the project root"
    if not allow_toolbox and relative.parts and relative.parts[0] == ".dev-tools":
        return None, f"{label} targets .dev-tools internals; set allow_toolbox: true for explicit maintenance mode"
    return path, ""


def is_probably_binary(data: bytes) -> bool:
    if b"\x00" in data:
        return True
    if not data:
        return False
    sample = data[:4096]
    control = 0
    for byte in sample:
        if byte < 32 and byte not in {9, 10, 12, 13}:
            control += 1
    return control / max(1, len(sample)) > 0.08


def newline_style(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    styles = sum(1 for count in [crlf, lf, cr] if count > 0)
    if styles > 1:
        return "mixed"
    if crlf:
        return "crlf"
    if lf:
        return "lf"
    if cr:
        return "cr"
    return "none"


def line_count(text: str) -> int:
    if not text:
        return 0
    return len(text.splitlines())


def read_text_bounded(path: Path, max_bytes: int) -> tuple[str | None, dict[str, Any], str]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        return None, {}, str(exc)
    if size > max_bytes:
        return None, {"size_bytes": size}, f"file exceeds max_bytes: {size} > {max_bytes}"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return None, {"size_bytes": size}, str(exc)
    if is_probably_binary(data):
        return None, {"size_bytes": size}, "file appears to be binary"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return None, {"size_bytes": size}, f"file is not valid UTF-8 text: {exc}"
    metadata = {
        "size_bytes": size,
        "encoding": "utf-8-sig" if data.startswith(b"\xef\xbb\xbf") else "utf-8",
        "line_count": line_count(text),
        "newline_style": newline_style(text),
    }
    return text, metadata, ""


def infer_file_type(path: Path | None = None, explicit: str | None = None) -> str:
    if explicit:
        value = explicit.lower().strip().lstrip(".")
        aliases = {"md": "markdown", "py": "python", "yml": "yaml", "sh": "shell", "ps1": "shell", "cmd": "batch"}
        return aliases.get(value, value)
    suffix = (path.suffix.lower() if path else "")
    if suffix == ".py":
        return "python"
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".sh", ".ps1"}:
        return "shell"
    if suffix in {".bat", ".cmd"}:
        return "batch"
    if suffix == ".css":
        return "css"
    if suffix in {".html", ".htm", ".xml"}:
        return "html"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    return "text"


def validate_text(content: str, *, file_type: str = "", path: Path | None = None) -> dict[str, Any]:
    kind = infer_file_type(path, file_type)
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    checks: list[str] = []

    if "\x00" in content:
        errors.append({"kind": "null_byte", "message": "content contains a NUL byte"})

    if kind == "python":
        checks.append("ast.parse")
        try:
            ast.parse(content)
        except SyntaxError as exc:
            errors.append({
                "kind": "python_syntax",
                "message": exc.msg,
                "line": exc.lineno,
                "column": exc.offset,
            })
    elif kind == "json":
        checks.append("json.loads")
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            errors.append({
                "kind": "json_syntax",
                "message": exc.msg,
                "line": exc.lineno,
                "column": exc.colno,
            })
    elif kind == "toml":
        checks.append("tomllib.loads")
        if tomllib is None:
            warnings.append("tomllib is not available in this Python runtime")
        else:
            try:
                tomllib.loads(content)
            except tomllib.TOMLDecodeError as exc:
                errors.append({"kind": "toml_syntax", "message": str(exc)})
    else:
        checks.append("basic_text")
        if kind not in VALIDATION_TYPES:
            warnings.append(f"unknown file_type {kind!r}; basic text checks only")

    return {
        "valid": not errors,
        "file_type": kind,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "line_count": line_count(content),
        "newline_style": newline_style(content),
    }


def tracked_paths(project_root: Path, path: Path) -> list[str]:
    try:
        rel = safe_relative(path, project_root)
        pathspecs = [rel]
        if path.is_dir() and rel != ".":
            pathspecs.append(f"{rel}/**")
        completed = subprocess.run(
            ["git", "ls-files", "--"] + pathspecs,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            return []
        return [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return []


def runtime_root(project_root: Path) -> Path:
    if (project_root / "toolbox_manifest.json").exists() and (project_root / "src" / "mcp_server.py").exists():
        return project_root / "runtime"
    return project_root / ".dev-tools" / "runtime"


def sanitize_relpath(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.replace("\\", "/"))
    return sanitized.strip("._")[:120] or "target"


def quarantine_target(project_root: Path, source: Path, *, actor: str, reason: str, tracked: list[str]) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    bucket = runtime_root(project_root) / "trash" / f"{stamp}_{uuid.uuid4().hex[:8]}_{sanitize_relpath(safe_relative(source, project_root))}"
    payload_dir = bucket / "payload"
    payload_dir.mkdir(parents=True, exist_ok=False)
    destination = payload_dir / source.name
    shutil.move(str(source), str(destination))
    receipt = {
        "original_path": safe_relative(source, project_root),
        "quarantine_path": safe_relative(destination, project_root),
        "receipt_path": safe_relative(bucket / "receipt.json", project_root),
        "timestamp": stamp,
        "reason": reason,
        "actor": actor,
        "tracked": bool(tracked),
        "tracked_paths": tracked,
    }
    (bucket / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=False), encoding="utf-8")
    return receipt
