"""
FILE: src/tools/text_file_reader.py
ROLE: Bounded text reads of project files. Read-only.
WHAT IT DOES: Reads a file from the host project tree with size + line
              caps. Refuses paths that escape project_root or fall into
              the sidecar's own subtree (the agent reads PROJECT files,
              not sidecar internals).
"""

from __future__ import annotations

from pathlib import Path

from src.lib.common import under


FILE_METADATA = {
    "tool_name": "text_file_reader",
    "version": "1.0.0",
    "entrypoint": "src/tools/text_file_reader.py",
    "category": "introspection",
    "summary": "Bounded text read of a host-project file.",
    "mcp_name": "text_file_reader",
    "required_authority": "Observe",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path relative to project_root."},
            "max_bytes": {"type": "integer", "default": 65536, "description": "Cap on bytes to read."},
            "encoding": {"type": "string", "default": "utf-8"},
            "line_start": {"type": "integer", "description": "Optional 1-based start line"},
            "line_end": {"type": "integer", "description": "Optional inclusive end line"},
        },
        "required": ["path"],
    },
}


# Forbidden subtrees within project_root that even Observe-level tools
# should refuse to expose. (.scaffold/ contains the sidecar's own data.)
_FORBIDDEN_SUBTREES = ("data", "logs", "cache", "exports", "workspaces", "snapshots")


def run(arguments: dict, state) -> dict:
    rel_path = arguments.get("path")
    if not rel_path:
        return _err(arguments, "path is required")
    max_bytes = int(arguments.get("max_bytes", 65536))
    encoding = arguments.get("encoding", "utf-8")
    line_start = arguments.get("line_start")
    line_end = arguments.get("line_end")

    project_root = Path(state.project_root).resolve()
    target = (project_root / rel_path).resolve()

    if not under(project_root, target):
        return _err(arguments, f"path escapes project_root: {rel_path}")
    # Refuse sidecar-runtime subtrees even though they're "inside" the project root
    # in dev scope. This keeps reads pointed at PROJECT content.
    rel = target.relative_to(project_root)
    parts = rel.parts
    if parts and parts[0] in _FORBIDDEN_SUBTREES:
        return _err(arguments, f"forbidden subtree: {parts[0]}/")
    if not target.is_file():
        return _err(arguments, f"not a file: {rel_path}")

    try:
        size = target.stat().st_size
    except OSError as e:
        return _err(arguments, f"stat failed: {e}")

    truncated = False
    try:
        with open(target, "rb") as f:
            raw = f.read(max_bytes + 1)
    except OSError as e:
        return _err(arguments, f"read failed: {e}")
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True

    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        return _err(arguments, f"unknown encoding: {encoding}")

    selected_text = text
    if line_start is not None or line_end is not None:
        lines = text.splitlines(keepends=True)
        s = max(0, int(line_start) - 1) if line_start else 0
        e = int(line_end) if line_end else len(lines)
        selected_text = "".join(lines[s:e])

    _record_trace_touch(state, rel_path, "read", "observed")

    return {
        "status": "ok",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {
            "path": rel_path,
            "size_bytes": size,
            "bytes_returned": len(selected_text.encode(encoding, errors="replace")),
            "truncated": truncated,
            "encoding": encoding,
            "content": selected_text,
        },
    }


def _err(arguments: dict, message: str) -> dict:
    return {
        "status": "error",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {"error": message},
    }


def _record_trace_touch(state, path: str, touch_type: str, status: str) -> None:
    run_trace = getattr(state, "run_trace_manager", None)
    run_context = getattr(state, "active_run_context", {}) or {}
    tool_context = getattr(state, "active_tool_context", {}) or {}
    run_id = str(run_context.get("run_id") or "")
    if not run_trace or not run_id:
        return
    try:
        run_trace.record_touched_path(
            run_id=run_id,
            round_id=str(run_context.get("round_id") or "") or None,
            path=str(path),
            touch_type=touch_type,
            status=status,
            linked_tool_invocation_id=str(tool_context.get("invocation_id") or "") or None,
            metadata={"tool_name": FILE_METADATA["tool_name"]},
        )
    except Exception:
        return
