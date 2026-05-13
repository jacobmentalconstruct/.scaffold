"""
FILE: src/tools/directory_scaffold.py
ROLE: Declarative scaffold tool for workspace-first operations.
WHAT IT DOES: Applies a manifest of directories and text files under the
              sidecar workspaces area or an explicitly-approved project path.
"""

from __future__ import annotations

from pathlib import Path

from src.lib.text_workspace import protected_path_error, resolve_bounded_path, safe_relative, validate_text


FILE_METADATA = {
    "tool_name": "directory_scaffold",
    "version": "1.0.0",
    "entrypoint": "src/tools/directory_scaffold.py",
    "category": "scaffold",
    "summary": "Dry-run-first declarative scaffolding under workspaces or approved project paths.",
    "mcp_name": "directory_scaffold",
    "required_authority": "Apply",
    "input_schema": {
        "type": "object",
        "properties": {
            "entries": {"type": "array", "items": {"type": "object"}},
            "dry_run": {"type": "boolean", "default": True},
            "confirm": {"type": "boolean", "default": False},
            "create_parents": {"type": "boolean", "default": True},
            "validate_files": {"type": "boolean", "default": False},
            "target_domain": {"type": "string", "enum": ["workspace", "project"], "default": "workspace"},
            "allow_host_project_write": {"type": "boolean", "default": False},
            "protected_paths": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict, state) -> dict:
    dry_run = bool(arguments.get("dry_run", True))
    confirm = bool(arguments.get("confirm", False))
    if not dry_run and not confirm:
        return _error(arguments, "scaffold writes require confirm=true when dry_run=false")

    target_domain = str(arguments.get("target_domain", "workspace"))
    root = _resolve_root(state, target_domain, bool(arguments.get("allow_host_project_write", False)))
    if root is None:
        return _error(arguments, "host-project scaffolds require allow_host_project_write=true")
    entries = arguments.get("entries") or []
    if not isinstance(entries, list):
        return _error(arguments, "entries must be a list")

    protected_paths = [str(item) for item in (arguments.get("protected_paths") or [])]
    create_parents = bool(arguments.get("create_parents", True))
    validate_files = bool(arguments.get("validate_files", False))

    plans = [
        _plan_entry(root, dict(entry), protected_paths, validate_files, create_parents)
        for entry in entries
    ]
    blocked = [plan for plan in plans if plan["status"] == "blocked"]
    if blocked and not dry_run:
        recovery_class = "control_file_tamper" if any(plan.get("recovery_class") == "control_file_tamper" for plan in blocked) else "tool_schema_error"
        return _error(arguments, f"blocked scaffold entries: {blocked}", recovery_class=recovery_class)

    applied: list[dict] = []
    if not dry_run:
        for entry, plan in zip(entries, plans):
            if plan["status"] in {"blocked", "exists", "skipped"}:
                continue
            target, error = resolve_bounded_path(root, str(entry.get("path", "")), label="entry.path")
            if error:
                continue
            assert target is not None
            if plan["type"] == "directory":
                target.mkdir(parents=True, exist_ok=True)
            else:
                if create_parents:
                    target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(entry.get("content", "")), encoding="utf-8", newline="")
            applied.append(plan)

    return {
        "status": "ok",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {
            "target_domain": target_domain,
            "root": str(root),
            "dry_run": dry_run,
            "entry_count": len(plans),
            "blocked_count": len(blocked),
            "applied_count": len(applied),
            "entries": plans,
            "applied": applied,
        },
    }


def _plan_entry(root: Path, entry: dict, protected_paths: list[str], validate_files: bool, create_parents: bool) -> dict:
    entry_type = str(entry.get("type", entry.get("kind", "file"))).lower()
    if entry_type not in {"directory", "file"}:
        entry_type = "file"
    target, error = resolve_bounded_path(root, str(entry.get("path", "")), label="entry.path")
    plan = {"path": str(entry.get("path", "")), "type": entry_type, "status": "planned", "action": ""}
    if error:
        plan.update({"status": "blocked", "reason": error})
        return plan
    assert target is not None
    plan["path"] = safe_relative(target, root)
    protection = protected_path_error(root, target, protected_paths, label="entry.path")
    if protection:
        plan.update({"status": "blocked", "reason": protection, "recovery_class": "control_file_tamper"})
        return plan
    if entry_type == "directory":
        if not target.parent.exists() and not create_parents:
            plan.update({"status": "blocked", "reason": "parent directory does not exist"})
        elif target.exists() and not target.is_dir():
            plan.update({"status": "blocked", "reason": "path exists and is not a directory"})
        elif target.exists():
            plan.update({"status": "exists", "action": "keep_directory"})
        else:
            plan["action"] = "create_directory"
        return plan

    overwrite = bool(entry.get("overwrite", False))
    if not target.parent.exists() and not create_parents:
        plan.update({"status": "blocked", "reason": "parent directory does not exist"})
        return plan
    if target.exists() and target.is_dir():
        plan.update({"status": "blocked", "reason": "path exists and is a directory"})
        return plan
    if target.exists() and not overwrite:
        plan.update({"status": "skipped", "action": "skip_existing_file"})
        return plan
    content = str(entry.get("content", ""))
    if validate_files:
        validation = validate_text(content, file_type=str(entry.get("file_type", "")), path=target)
        plan["validation"] = validation
        if not validation["valid"]:
            plan.update({"status": "blocked", "reason": "validation failed"})
            return plan
    plan["action"] = "overwrite_file" if target.exists() else "create_file"
    plan["size_bytes"] = len(content.encode("utf-8"))
    return plan


def _resolve_root(state, target_domain: str, allow_host_project_write: bool) -> Path | None:
    if target_domain == "workspace":
        return Path(state.sidecar_root).resolve() / "workspaces"
    if target_domain == "project" and allow_host_project_write:
        return Path(state.project_root).resolve()
    return None


def _error(arguments: dict, message: str, recovery_class: str = "tool_schema_error") -> dict:
    return {
        "status": "error",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {"error": message, "recovery_class": recovery_class},
    }
