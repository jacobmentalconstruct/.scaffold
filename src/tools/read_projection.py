"""
FILE: src/tools/read_projection.py
ROLE: Generic projection reader. Returns the named projection's rows.
WHAT IT DOES: Wraps state.projections.read(name). Useful surface for an
              MCP agent that wants to ask "what's in projection X?"
              without knowing the table directly.
"""

from __future__ import annotations


FILE_METADATA = {
    "tool_name": "read_projection",
    "version": "1.0.0",
    "entrypoint": "src/tools/read_projection.py",
    "category": "query",
    "summary": "Read a named projection; returns its rows + last_refreshed_at.",
    "mcp_name": "read_projection",
    "required_authority": "Observe",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Projection name (e.g. 'project_map')"},
            "limit": {"type": "integer", "default": 200, "description": "Cap on rows returned"},
        },
        "required": ["name"],
    },
}


def run(arguments: dict, state) -> dict:
    name = arguments.get("name")
    if not name:
        return _err(arguments, "name is required")
    limit = int(arguments.get("limit", 200))

    available = state.projections.list()
    if name not in available:
        return _err(arguments, f"unknown projection: {name}; available: {available}")

    result = state.projections.read(name)
    rows = result.rows[:limit] if limit > 0 else result.rows
    return {
        "status": "ok",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {
            "name": result.name,
            "last_refreshed_at": result.last_refreshed_at,
            "row_count": len(rows),
            "total_rows": len(result.rows),
            "truncated": len(rows) < len(result.rows),
            "rows": rows,
        },
    }


def _err(arguments: dict, message: str) -> dict:
    return {
        "status": "error",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {"error": message},
    }
