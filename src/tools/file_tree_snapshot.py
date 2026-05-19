"""
FILE: src/tools/file_tree_snapshot.py
ROLE: Read the project_index and return a snapshot of the file tree.
WHAT IT DOES: Reads project_index_manager.query(), groups by directory,
              returns a tree-shaped JSON. Pure Observe authority.
"""

from __future__ import annotations

from src.lib.common import public_root_labels


FILE_METADATA = {
    "tool_name": "file_tree_snapshot",
    "version": "1.0.0",
    "entrypoint": "src/tools/file_tree_snapshot.py",
    "category": "introspection",
    "summary": "Snapshot the host project's file tree from project_index.",
    "mcp_name": "file_tree_snapshot",
    "required_authority": "Observe",
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["file", "directory", "symlink"],
                "description": "Optional filter by kind",
            },
            "ext": {
                "type": "string",
                "description": "Optional file extension filter (e.g. '.py')",
            },
            "limit": {"type": "integer", "default": 1000, "description": "Max rows to return"},
        },
    },
}


def run(arguments: dict, state) -> dict:
    kind = arguments.get("kind")
    ext = arguments.get("ext")
    limit = int(arguments.get("limit", 1000))

    entries = state.project_index_manager.query(kind=kind, ext=ext, limit=limit)
    by_kind: dict[str, int] = {}
    rows = []
    for entry in entries:
        by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
        rows.append({
            "path": entry.path,
            "kind": entry.kind,
            "size_bytes": entry.size_bytes,
            "content_hash": entry.content_hash,
            "ext": entry.ext,
            "last_observed_at": entry.last_observed_at,
        })

    latest_scan = state.project_index_manager.latest_scan()
    project_root_label, _ = public_root_labels(state.sidecar_root, state.project_root)
    return {
        "status": "ok",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {
            "project_root": project_root_label,
            "total_returned": len(rows),
            "by_kind": by_kind,
            "latest_scan_id": latest_scan.scan_id if latest_scan else None,
            "rows": rows,
        },
    }
