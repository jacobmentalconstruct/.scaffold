"""
FILE: sqlite_schema_inspector.py
ROLE: Inspect SQLite database schema and structure.
WHAT IT DOES:
  - Reads a .sqlite3 file and returns structured schema information
  - Tables, columns, types, primary keys, indexes, foreign keys, row counts
  - Optionally returns sample rows for orientation
  - Zero write risk — purely read-only introspection
HOW TO USE:
  - python src/tools/sqlite_schema_inspector.py metadata
  - python src/tools/sqlite_schema_inspector.py run --input-json '{"db_path": "path/to/db.sqlite3"}'
  - python src/tools/sqlite_schema_inspector.py run --input-json '{"db_path": "...", "sample_rows": 3}'
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result, tool_error

FILE_METADATA = {
    "tool_name": "sqlite_schema_inspector",
    "version": "1.0.0",
    "entrypoint": "src/tools/sqlite_schema_inspector.py",
    "category": "introspection",
    "summary": "Inspect SQLite database schema: tables, columns, types, indexes, foreign keys, row counts, and optional sample rows.",
    "mcp_name": "sqlite_schema_inspector",
    "input_schema": {
        "type": "object",
        "required": ["db_path"],
        "properties": {
            "db_path": {
                "type": "string",
                "description": "Path to the SQLite database file."
            },
            "tables": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific tables to inspect. If omitted, inspects all tables."
            },
            "sample_rows": {
                "type": "integer",
                "default": 0,
                "description": "Number of sample rows to return per table (0 = none)."
            },
            "include_sql": {
                "type": "boolean",
                "default": False,
                "description": "If true, include the original CREATE TABLE SQL for each table."
            }
        }
    }
}


def _get_tables(conn: sqlite3.Connection) -> list[str]:
    """Get all user table names."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def _get_columns(conn: sqlite3.Connection, table: str) -> list[dict]:
    """Get column info for a table."""
    rows = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
    columns = []
    for row in rows:
        columns.append({
            "cid": row[0],
            "name": row[1],
            "type": row[2] or "ANY",
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": bool(row[5]),
        })
    return columns


def _get_indexes(conn: sqlite3.Connection, table: str) -> list[dict]:
    """Get indexes for a table."""
    rows = conn.execute(f"PRAGMA index_list([{table}])").fetchall()
    indexes = []
    for row in rows:
        idx_name = row[1]
        unique = bool(row[2])
        # Get columns in this index
        idx_cols = conn.execute(f"PRAGMA index_info([{idx_name}])").fetchall()
        col_names = [c[2] for c in idx_cols]
        indexes.append({
            "name": idx_name,
            "unique": unique,
            "columns": col_names,
        })
    return indexes


def _get_foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    """Get foreign key relationships for a table."""
    rows = conn.execute(f"PRAGMA foreign_key_list([{table}])").fetchall()
    fks = []
    for row in rows:
        fks.append({
            "id": row[0],
            "table": row[2],
            "from": row[3],
            "to": row[4],
            "on_update": row[5],
            "on_delete": row[6],
        })
    return fks


def _get_row_count(conn: sqlite3.Connection, table: str) -> int:
    """Get row count for a table."""
    try:
        return conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    except Exception:
        return -1


def _get_sample_rows(conn: sqlite3.Connection, table: str, limit: int) -> list[dict]:
    """Get sample rows as list of dicts."""
    if limit <= 0:
        return []
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(f"SELECT * FROM [{table}] LIMIT ?", (limit,)).fetchall()
        conn.row_factory = None
        result = []
        for row in rows:
            d = {}
            for key in row.keys():
                val = row[key]
                # Ensure JSON-serializable
                if isinstance(val, bytes):
                    d[key] = f"<blob {len(val)} bytes>"
                else:
                    d[key] = val
            result.append(d)
        return result
    except Exception:
        conn.row_factory = None
        return []


def _get_create_sql(conn: sqlite3.Connection, table: str) -> str:
    """Get the original CREATE TABLE statement."""
    try:
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return row[0] if row else ""
    except Exception:
        return ""


def _inspect_table(conn: sqlite3.Connection, table: str, sample_rows: int, include_sql: bool) -> dict:
    """Full inspection of a single table."""
    info: dict = {
        "name": table,
        "columns": _get_columns(conn, table),
        "row_count": _get_row_count(conn, table),
        "indexes": _get_indexes(conn, table),
        "foreign_keys": _get_foreign_keys(conn, table),
    }
    if include_sql:
        info["create_sql"] = _get_create_sql(conn, table)
    if sample_rows > 0:
        info["sample_rows"] = _get_sample_rows(conn, table, sample_rows)
    return info


def run(arguments: dict) -> dict:
    db_path = Path(arguments["db_path"])
    if not db_path.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Database not found: {db_path}")

    sample_rows = arguments.get("sample_rows", 0)
    include_sql = arguments.get("include_sql", False)
    requested_tables = arguments.get("tables")

    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        all_tables = _get_tables(conn)

        if requested_tables:
            missing = [t for t in requested_tables if t not in all_tables]
            tables_to_inspect = [t for t in requested_tables if t in all_tables]
        else:
            missing = []
            tables_to_inspect = all_tables

        # DB-level metadata
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]

        table_results = []
        for table in tables_to_inspect:
            table_results.append(_inspect_table(conn, table, sample_rows, include_sql))

        conn.close()

        result: dict = {
            "db_path": str(db_path),
            "db_size_bytes": db_path.stat().st_size,
            "user_version": user_version,
            "journal_mode": journal_mode,
            "page_size": page_size,
            "page_count": page_count,
            "table_count": len(all_tables),
            "all_tables": all_tables,
            "inspected": table_results,
        }
        if missing:
            result["missing_tables"] = missing

        return tool_result(FILE_METADATA["tool_name"], arguments, result)

    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
