"""
FILE: schema_diff_tool.py
ROLE: Compare two SQLite database schemas and report differences.
WHAT IT DOES:
  - Reads schema from two .sqlite3 files (baseline and candidate)
  - Reports: added/dropped tables, added/dropped/changed columns,
    index changes, foreign key changes, row count deltas
  - Produces a structured migration-planning report
  - Zero write risk — purely read-only introspection
HOW TO USE:
  - python src/tools/schema_diff_tool.py metadata
  - python src/tools/schema_diff_tool.py run --input-json '{"baseline_db": "old.sqlite3", "candidate_db": "new.sqlite3"}'
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result, tool_error

FILE_METADATA = {
    "tool_name": "schema_diff_tool",
    "version": "1.0.0",
    "entrypoint": "src/tools/schema_diff_tool.py",
    "category": "introspection",
    "summary": "Compare two SQLite database schemas: added/dropped tables, column changes, index changes, and row count deltas.",
    "mcp_name": "schema_diff_tool",
    "input_schema": {
        "type": "object",
        "required": ["baseline_db", "candidate_db"],
        "properties": {
            "baseline_db": {
                "type": "string",
                "description": "Path to the baseline (old) SQLite database."
            },
            "candidate_db": {
                "type": "string",
                "description": "Path to the candidate (new) SQLite database."
            },
            "include_row_counts": {
                "type": "boolean",
                "default": True,
                "description": "If true, include row count comparison for common tables."
            }
        }
    }
}


def _get_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def _get_columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    rows = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
    columns = {}
    for row in rows:
        columns[row[1]] = {
            "type": row[2] or "ANY",
            "notnull": bool(row[3]),
            "default": row[4],
            "pk": bool(row[5]),
        }
    return columns


def _get_indexes(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    rows = conn.execute(f"PRAGMA index_list([{table}])").fetchall()
    indexes = {}
    for row in rows:
        idx_name = row[1]
        unique = bool(row[2])
        cols = [c[2] for c in conn.execute(f"PRAGMA index_info([{idx_name}])").fetchall()]
        indexes[idx_name] = {"unique": unique, "columns": cols}
    return indexes


def _get_foreign_keys(conn: sqlite3.Connection, table: str) -> list[dict]:
    rows = conn.execute(f"PRAGMA foreign_key_list([{table}])").fetchall()
    return [{"from": r[3], "table": r[2], "to": r[4]} for r in rows]


def _get_row_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
    except Exception:
        return -1


def _diff_columns(baseline: dict[str, dict], candidate: dict[str, dict]) -> dict[str, Any]:
    """Compare column sets between two versions of a table."""
    b_cols = set(baseline.keys())
    c_cols = set(candidate.keys())

    added = c_cols - b_cols
    dropped = b_cols - c_cols
    common = b_cols & c_cols

    changed = []
    for col in sorted(common):
        b = baseline[col]
        c = candidate[col]
        diffs = {}
        if b["type"] != c["type"]:
            diffs["type"] = {"from": b["type"], "to": c["type"]}
        if b["notnull"] != c["notnull"]:
            diffs["notnull"] = {"from": b["notnull"], "to": c["notnull"]}
        if b["default"] != c["default"]:
            diffs["default"] = {"from": b["default"], "to": c["default"]}
        if b["pk"] != c["pk"]:
            diffs["pk"] = {"from": b["pk"], "to": c["pk"]}
        if diffs:
            changed.append({"column": col, "changes": diffs})

    result: dict[str, Any] = {}
    if added:
        result["added"] = {c: candidate[c] for c in sorted(added)}
    if dropped:
        result["dropped"] = sorted(dropped)
    if changed:
        result["changed"] = changed
    return result


def _diff_indexes(baseline: dict[str, dict], candidate: dict[str, dict]) -> dict[str, Any]:
    """Compare indexes between two versions of a table."""
    b_idx = set(baseline.keys())
    c_idx = set(candidate.keys())

    result: dict[str, Any] = {}
    added = c_idx - b_idx
    dropped = b_idx - c_idx

    if added:
        result["added"] = {i: candidate[i] for i in sorted(added)}
    if dropped:
        result["dropped"] = {i: baseline[i] for i in sorted(dropped)}

    # Check for changed indexes (same name, different definition)
    for idx in sorted(b_idx & c_idx):
        if baseline[idx] != candidate[idx]:
            result.setdefault("changed", []).append({
                "index": idx,
                "from": baseline[idx],
                "to": candidate[idx],
            })

    return result


def run(arguments: dict) -> dict:
    baseline_path = Path(arguments["baseline_db"])
    candidate_path = Path(arguments["candidate_db"])
    include_row_counts = arguments.get("include_row_counts", True)

    if not baseline_path.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Baseline not found: {baseline_path}")
    if not candidate_path.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Candidate not found: {candidate_path}")

    try:
        b_conn = sqlite3.connect(str(baseline_path))
        c_conn = sqlite3.connect(str(candidate_path))

        b_tables = _get_tables(b_conn)
        c_tables = _get_tables(c_conn)

        added_tables = sorted(c_tables - b_tables)
        dropped_tables = sorted(b_tables - c_tables)
        common_tables = sorted(b_tables & c_tables)

        table_diffs: list[dict] = []
        row_count_diffs: list[dict] = []

        for table in common_tables:
            b_cols = _get_columns(b_conn, table)
            c_cols = _get_columns(c_conn, table)
            col_diff = _diff_columns(b_cols, c_cols)

            b_idx = _get_indexes(b_conn, table)
            c_idx = _get_indexes(c_conn, table)
            idx_diff = _diff_indexes(b_idx, c_idx)

            b_fk = _get_foreign_keys(b_conn, table)
            c_fk = _get_foreign_keys(c_conn, table)
            fk_changed = b_fk != c_fk

            if col_diff or idx_diff or fk_changed:
                diff_entry: dict[str, Any] = {"table": table}
                if col_diff:
                    diff_entry["columns"] = col_diff
                if idx_diff:
                    diff_entry["indexes"] = idx_diff
                if fk_changed:
                    diff_entry["foreign_keys"] = {"baseline": b_fk, "candidate": c_fk}
                table_diffs.append(diff_entry)

            if include_row_counts:
                b_count = _get_row_count(b_conn, table)
                c_count = _get_row_count(c_conn, table)
                if b_count != c_count:
                    row_count_diffs.append({
                        "table": table,
                        "baseline": b_count,
                        "candidate": c_count,
                        "delta": c_count - b_count,
                    })

        # Schema for added tables
        added_table_details = []
        for table in added_tables:
            cols = _get_columns(c_conn, table)
            added_table_details.append({
                "table": table,
                "columns": cols,
                "row_count": _get_row_count(c_conn, table) if include_row_counts else None,
            })

        b_conn.close()
        c_conn.close()

        # Build result
        has_changes = bool(added_tables or dropped_tables or table_diffs)

        result: dict[str, Any] = {
            "baseline": str(baseline_path),
            "candidate": str(candidate_path),
            "has_changes": has_changes,
            "tables_added": len(added_tables),
            "tables_dropped": len(dropped_tables),
            "tables_modified": len(table_diffs),
        }

        if added_tables:
            result["added_tables"] = added_table_details
        if dropped_tables:
            result["dropped_tables"] = dropped_tables
        if table_diffs:
            result["modified_tables"] = table_diffs
        if row_count_diffs:
            result["row_count_changes"] = row_count_diffs

        return tool_result(FILE_METADATA["tool_name"], arguments, result)

    except Exception as exc:
        return tool_error(FILE_METADATA["tool_name"], arguments, str(exc))


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
