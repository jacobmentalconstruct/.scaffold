"""
FILE: src/lib/text_workspace.py
ROLE: Shared text-workspace safety helpers for write-capable tools.
WHAT IT DOES: Resolves bounded targets, validates text payloads, and
              keeps workspace/project writes inside approved roots.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


_TEXT_EXTENSIONS = {
    ".bat", ".cfg", ".cmd", ".conf", ".css", ".csv", ".env", ".html",
    ".ini", ".js", ".json", ".jsx", ".md", ".mjs", ".ps1", ".py", ".sh",
    ".sql", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}


def safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def resolve_bounded_path(root: Path, value: str, *, label: str = "path") -> tuple[Path | None, str]:
    if not value or not str(value).strip():
        return None, f"{label} is required"
    target = (root / str(value)).resolve()
    if not is_inside(target, root):
        return None, f"{label} escapes its allowed root: {value}"
    return target, ""


def protected_path_error(root: Path, path: Path, protected_paths: list[str], *, label: str = "path") -> str:
    if not protected_paths:
        return ""
    rel_target = safe_relative(path, root).lower()
    for protected in protected_paths:
        if not protected or not str(protected).strip():
            continue
        protected_target = (root / str(protected)).resolve()
        if rel_target == safe_relative(protected_target, root).lower():
            return f"{label} targets protected path: {rel_target}"
    return ""


def infer_file_type(path: Path | None = None, explicit: str | None = None) -> str:
    if explicit:
        value = explicit.lower().strip().lstrip(".")
        aliases = {
            "md": "markdown",
            "py": "python",
            "yml": "yaml",
            "ps1": "shell",
            "cmd": "batch",
        }
        return aliases.get(value, value)
    suffix = (path.suffix.lower() if path else "")
    if suffix == ".py":
        return "python"
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".sh", ".ps1"}:
        return "shell"
    return "text"


def validate_text(content: str, *, file_type: str = "", path: Path | None = None) -> dict[str, Any]:
    kind = infer_file_type(path, file_type)
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []

    if "\x00" in content:
        errors.append({"kind": "null_byte", "message": "content contains a NUL byte"})

    if kind == "python":
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
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            errors.append({
                "kind": "json_syntax",
                "message": exc.msg,
                "line": exc.lineno,
                "column": exc.colno,
            })
    elif kind == "text":
        if path and path.suffix.lower() and path.suffix.lower() not in _TEXT_EXTENSIONS:
            warnings.append(f"unrecognized text extension: {path.suffix.lower()}")

    return {
        "valid": not errors,
        "file_type": kind,
        "errors": errors,
        "warnings": warnings,
        "line_count": len(content.splitlines()) if content else 0,
    }


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
    if b"\x00" in data:
        return None, {"size_bytes": size}, "file appears to be binary"
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        return None, {"size_bytes": size}, f"file is not valid UTF-8 text: {exc}"
    return text, {"size_bytes": size, "line_count": len(text.splitlines())}, ""
