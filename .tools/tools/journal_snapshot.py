"""
FILE: journal_snapshot.py
ROLE: Snapshot management tool for _app-journal v2.
WHAT IT DOES: Creates, lists, inspects, and verifies merkle snapshots.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import _connect, initialize_store
from lib.snapshots import create_snapshot, get_snapshot, list_snapshots, verify_snapshot


FILE_METADATA = {
    "tool_name": "journal_snapshot",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_snapshot.py",
    "category": "snapshot",
    "summary": "Create, list, inspect, or verify merkle snapshots of the journal state.",
    "mcp_name": "journal_snapshot",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "action": {"type": "string", "enum": ["create", "list", "get", "verify"]},
            "snapshot_id": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    paths = initialize_store(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
    )
    action = arguments["action"]

    with _connect(paths["db_path"]) as connection:
        if action == "create":
            result = create_snapshot(connection, description=arguments.get("description", ""))
            connection.commit()
            return tool_result(FILE_METADATA["tool_name"], arguments, result)

        if action == "list":
            snaps = list_snapshots(connection)
            return tool_result(FILE_METADATA["tool_name"], arguments, {"snapshots": snaps, "count": len(snaps)})

        if action == "get":
            snapshot_id = arguments.get("snapshot_id")
            if not snapshot_id:
                raise ValueError("snapshot_id is required for get action.")
            result = get_snapshot(connection, snapshot_id)
            return tool_result(FILE_METADATA["tool_name"], arguments, result)

        if action == "verify":
            snapshot_id = arguments.get("snapshot_id")
            if not snapshot_id:
                raise ValueError("snapshot_id is required for verify action.")
            result = verify_snapshot(connection, snapshot_id)
            return tool_result(FILE_METADATA["tool_name"], arguments, result)

        raise ValueError(f"Unsupported action: {action}")


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
