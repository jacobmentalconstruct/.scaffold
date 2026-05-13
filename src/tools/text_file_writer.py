"""
FILE: src/tools/text_file_writer.py
ROLE: Guarded text writer for workspace-first mutation flows.
WHAT IT DOES: Writes text either to sidecar workspaces or, when explicitly
              enabled, to the host project tree. Validation stays bounded
              and all writes require human-approved authority.
"""

from __future__ import annotations

from pathlib import Path

from src.lib.text_workspace import (
    protected_path_error,
    read_text_bounded,
    resolve_bounded_path,
    safe_relative,
    validate_text,
)


FILE_METADATA = {
    "tool_name": "text_file_writer",
    "version": "1.0.0",
    "entrypoint": "src/tools/text_file_writer.py",
    "category": "write",
    "summary": "Confirmed text writes to sidecar workspaces or approved host-project paths.",
    "mcp_name": "text_file_writer",
    "required_authority": "Apply",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string", "default": ""},
            "body": {"type": "string"},
            "action": {"type": "string", "enum": ["create", "overwrite", "append"], "default": "create"},
            "confirm": {"type": "boolean", "default": False},
            "overwrite": {"type": "boolean", "default": False},
            "create_dirs": {"type": "boolean", "default": False},
            "validate_after_write": {"type": "boolean", "default": False},
            "file_type": {"type": "string"},
            "target_domain": {"type": "string", "enum": ["workspace", "project"], "default": "workspace"},
            "allow_host_project_write": {"type": "boolean", "default": False},
            "protected_paths": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


def run(arguments: dict, state) -> dict:
    if not arguments.get("confirm", False):
        return _error(arguments, "text writes require confirm=true")

    target_domain = str(arguments.get("target_domain", "workspace"))
    root = _resolve_root(state, target_domain, bool(arguments.get("allow_host_project_write", False)))
    if root is None:
        return _error(arguments, "host-project writes require allow_host_project_write=true")

    path, error = resolve_bounded_path(root, str(arguments.get("path", "")), label="path")
    if error:
        return _error(arguments, error)
    assert path is not None

    protected_paths = [str(item) for item in (arguments.get("protected_paths") or [])]
    protection = protected_path_error(root, path, protected_paths, label="path")
    if protection:
        return _error(arguments, protection, recovery_class="control_file_tamper")

    action = str(arguments.get("action", "create"))
    raw_content = arguments.get("content", arguments.get("body", ""))
    content = str(raw_content)
    overwrite = bool(arguments.get("overwrite", False))
    create_dirs = bool(arguments.get("create_dirs", False))
    exists = path.exists()

    if exists and path.is_dir():
        return _error(arguments, f"target is a directory: {safe_relative(path, root)}")
    if action == "create" and exists and not overwrite:
        return _error(arguments, "target exists; set overwrite=true or use append")
    if action == "overwrite" and not exists:
        return _error(arguments, "overwrite target does not exist")
    if action == "overwrite" and not overwrite:
        return _error(arguments, "overwrite requires overwrite=true")
    if action == "append" and not exists:
        return _error(arguments, "append target does not exist")
    if not path.parent.exists() and not create_dirs:
        return _error(arguments, "parent directory does not exist; set create_dirs=true")

    final_content = content
    if action == "append" and exists:
        current_text, _, read_error = read_text_bounded(path, max(path.stat().st_size + len(content.encode("utf-8")) + 32, 1))
        if read_error:
            return _error(arguments, read_error)
        final_content = f"{current_text}{content}"

    validation = None
    before_text = ""
    if exists and path.is_file():
        before_text, _, read_error = read_text_bounded(path, max(path.stat().st_size + 32, 1))
        if read_error:
            return _error(arguments, read_error)
    if bool(arguments.get("validate_after_write", False)):
        validation = validate_text(final_content, file_type=str(arguments.get("file_type", "")), path=path)
        if not validation["valid"]:
            return _error(arguments, f"validation failed: {validation['errors']}")

    path.parent.mkdir(parents=True, exist_ok=True)
    if action == "append":
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(content)
    else:
        path.write_text(content, encoding="utf-8", newline="")

    _record_memory_provenance(
        state,
        target_domain=target_domain,
        root=root,
        path=path,
        before_text=before_text,
        after_text=final_content,
    )

    return {
        "status": "ok",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {
            "target_domain": target_domain,
            "root": str(root),
            "path": safe_relative(path, root),
            "created": not exists,
            "overwrote": exists and action in {"create", "overwrite"},
            "appended": action == "append",
            "size_bytes": path.stat().st_size,
            "validation": validation,
        },
    }


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


def _record_memory_provenance(state, *, target_domain: str, root: Path, path: Path, before_text: str, after_text: str) -> None:
    memory_manager = getattr(state, "memory_manager", None)
    if memory_manager is None or before_text == after_text:
        return
    tool_context = getattr(state, "active_tool_context", {}) or {}
    actor_id = str(tool_context.get("actor_id") or (state.agent_status or {}).get("actor_id") or "human:unknown")
    session_id = str((state.agent_status or {}).get("session_id") or "")
    tranche = state.tranche_manager.get_active() if getattr(state, "tranche_manager", None) else None
    public = safe_relative(path, root)
    if target_domain == "workspace":
        public = f"workspaces/{public}"
    try:
        memory_manager.record_change_hunks(
            actor_id=actor_id,
            path=public,
            before_text=before_text,
            after_text=after_text,
            tranche_id=tranche.tranche_id if tranche else None,
            session_id=session_id or None,
            source_event_id=str(tool_context.get("object_id") or ""),
            summary_prefix=f"Bounded write to {public}",
        )
        if session_id:
            memory_manager.rebuild_shelf(session_id)
    except Exception:
        return
