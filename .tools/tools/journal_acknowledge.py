"""
FILE: journal_acknowledge.py
ROLE: Contract acknowledgment tool for _app-journal v2.
WHAT IT DOES: Records that an agent or human has read and accepted the builder constraint contract.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import _connect, initialize_store
from lib.contract import acknowledge_contract, get_contract_summary


FILE_METADATA = {
    "tool_name": "journal_acknowledge",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_acknowledge.py",
    "category": "contract",
    "summary": "Acknowledge the builder constraint contract. Required before meaningful work.",
    "mcp_name": "journal_acknowledge",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "actor_id": {"type": "string"},
            "actor_type": {"type": "string", "default": "agent"},
        },
        "required": ["actor_id"],
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    paths = initialize_store(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
    )
    with _connect(paths["db_path"]) as connection:
        receipt = acknowledge_contract(
            connection,
            actor_id=arguments["actor_id"],
            actor_type=arguments.get("actor_type", "agent"),
        )
        summary = get_contract_summary(connection)
        connection.commit()
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "receipt": receipt,
        "contract_summary": summary,
    })


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
