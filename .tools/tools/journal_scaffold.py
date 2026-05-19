"""
FILE: journal_scaffold.py
ROLE: Project scaffolding tool for _app-journal v2.
WHAT IT DOES: Unpacks standard project layout templates from the DB to disk.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import standard_main, tool_result
from lib.journal_store import _connect, initialize_store
from lib.scaffolds import list_templates, seed_templates, unpack_templates


FILE_METADATA = {
    "tool_name": "journal_scaffold",
    "version": "2.0.0",
    "entrypoint": "src/tools/journal_scaffold.py",
    "category": "scaffold",
    "summary": "Unpack standard project layout templates from the DB to disk.",
    "mcp_name": "journal_scaffold",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "db_path": {"type": "string"},
            "overwrite": {"type": "boolean", "default": False},
            "templates": {"type": "array", "items": {"type": "string"}},
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict) -> dict:
    paths = initialize_store(
        project_root=arguments.get("project_root"),
        db_path=arguments.get("db_path"),
    )
    project_root = Path(paths["project_root"])

    with _connect(paths["db_path"]) as connection:
        seeded = seed_templates(connection)
        files = unpack_templates(
            connection,
            project_root,
            overwrite=arguments.get("overwrite", False),
            template_ids=arguments.get("templates"),
        )
        available = list_templates(connection)
        connection.commit()

    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "templates_seeded": seeded,
        "templates_available": len(available),
        "files": files,
    })


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
