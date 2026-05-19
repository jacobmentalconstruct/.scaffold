"""
FILE: journal_init.py
ROLE: Bootstrap tool for _app-journal v2.
WHAT IT DOES: Creates the SQLite journal database, project-local folders, seeds the builder
    contract, and optionally scaffolds the standard project layout.
HOW TO USE:
  - Metadata: python src/tools/journal_init.py metadata
  - Run: python src/tools/journal_init.py run --input-json '{"project_root":"<project_root>"}'
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import initialize_store


FILE_METADATA = {
    "tool_name": "journal_init",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_init.py",
    "category": "bootstrap",
    "summary": "Create or verify the project journal database, seed the builder contract, and optionally scaffold the project layout.",
    "mcp_name": "journal_init",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "scaffold": {"type": "boolean", "default": False},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    paths = initialize_store(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
    )

    result_payload: dict = {"paths": paths}

    # Include contract summary if available
    try:
        from lib.journal_store import _connect
        from lib.contract import get_contract_summary
        with _connect(paths["db_path"]) as connection:
            result_payload["contract_summary"] = get_contract_summary(connection)
    except (ImportError, Exception):
        pass

    if arguments.get("scaffold"):
        from pathlib import Path

        from lib.journal_store import _connect
        from lib.scaffolds import list_templates, seed_templates, unpack_templates

        project_root = Path(paths["project_root"])
        with _connect(paths["db_path"]) as connection:
            seeded = seed_templates(connection)
            files = unpack_templates(connection, project_root, overwrite=False)
            available = list_templates(connection)
            connection.commit()
        result_payload["scaffold"] = {
            "templates_seeded": seeded,
            "templates_available": len(available),
            "files": files,
        }

    return tool_result(FILE_METADATA["tool_name"], arguments, result_payload)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
