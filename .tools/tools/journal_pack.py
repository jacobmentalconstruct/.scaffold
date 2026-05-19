"""
FILE: journal_pack.py
ROLE: Tool packing/unpacking tool for _app-journal v2.
WHAT IT DOES: Packs tool source code into the DB or unpacks it to disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import _connect, initialize_store
from lib.tool_pack import list_packed_tools, pack_package, unpack_package, unpack_tool


FILE_METADATA = {
    "tool_name": "journal_pack",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_pack.py",
    "category": "packing",
    "summary": "Pack tool source code into the DB or unpack it to disk.",
    "mcp_name": "journal_pack",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "action": {"type": "string", "enum": ["pack", "unpack", "list"]},
            "package_root": {"type": "string"},
            "target_dir": {"type": "string"},
            "tool_id": {"type": "string"},
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
        if action == "pack":
            package_root = arguments.get("package_root")
            if not package_root:
                raise ValueError("package_root is required for pack action.")
            result = pack_package(connection, Path(package_root))
            connection.commit()
            return tool_result(FILE_METADATA["tool_name"], arguments, result)

        if action == "unpack":
            target_dir = arguments.get("target_dir")
            if not target_dir:
                raise ValueError("target_dir is required for unpack action.")
            tool_id = arguments.get("tool_id")
            if tool_id:
                result = unpack_tool(connection, tool_id, Path(target_dir))
            else:
                result = unpack_package(connection, Path(target_dir))
            return tool_result(FILE_METADATA["tool_name"], arguments, result)

        if action == "list":
            tools = list_packed_tools(connection)
            return tool_result(FILE_METADATA["tool_name"], arguments, {"tools": tools, "count": len(tools)})

        raise ValueError(f"Unsupported action: {action}")


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
