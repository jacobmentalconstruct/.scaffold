"""
FILE: intake.py
ROLE: Project DB ingestion for _app-journal v2 (mother app).
WHAT IT DOES: Ingests returned project databases, importing journal entries
    with project namespacing, detecting tool diffs, and managing the project registry.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from common import now_stamp
from lib.journal_store import _connect, _content_hash, _row_to_entry, store_blob


def register_project(
    connection: sqlite3.Connection,
    *,
    project_name: str,
    project_root: str = "",
    tool_hash: str = "",
    metadata: dict | None = None,
) -> dict:
    """Register a new vendored project in the mother app's registry."""
    project_id = f"proj_{uuid.uuid4().hex[:12]}"
    now = now_stamp()
    connection.execute(
        "INSERT INTO project_registry(project_id, project_name, project_root, vended_at, tool_hash, metadata_json) VALUES(?, ?, ?, ?, ?, ?)",
        (project_id, project_name, project_root, now, tool_hash, json.dumps(metadata or {})),
    )
    return {
        "project_id": project_id,
        "project_name": project_name,
        "project_root": project_root,
        "vended_at": now,
        "tool_hash": tool_hash,
    }


def list_projects(connection: sqlite3.Connection) -> list[dict]:
    """List all registered projects."""
    rows = connection.execute(
        "SELECT project_id, project_name, project_root, vended_at, last_ingested, tool_hash, status, metadata_json FROM project_registry ORDER BY vended_at DESC"
    ).fetchall()
    return [
        {
            "project_id": row["project_id"],
            "project_name": row["project_name"],
            "project_root": row["project_root"],
            "vended_at": row["vended_at"],
            "last_ingested": row["last_ingested"],
            "tool_hash": row["tool_hash"],
            "status": row["status"],
            "metadata": json.loads(row["metadata_json"]),
        }
        for row in rows
    ]


def ingest_project_db(
    mother_connection: sqlite3.Connection,
    source_db_path: str | Path,
    project_id: str,
) -> dict:
    """
    Import journal entries from a returned project DB into the mother app.
    Entries are tagged with project_id to keep histories separate.
    Blobs are copied to the mother's blob_store (deduped by hash).
    """
    source_conn = _connect(str(source_db_path))
    source_conn.row_factory = sqlite3.Row

    # Import blobs first (dedup by hash)
    blob_rows = source_conn.execute("SELECT content_hash, content_text, content_type FROM blob_store").fetchall()
    blob_count = 0
    for row in blob_rows:
        mother_connection.execute(
            "INSERT OR IGNORE INTO blob_store(content_hash, content_text, content_type, size_bytes, created_at) VALUES(?, ?, ?, ?, ?)",
            (row["content_hash"], row["content_text"], row["content_type"], len(row["content_text"].encode("utf-8")), now_stamp()),
        )
        blob_count += 1

    # Import journal entries (tagged with project_id)
    entry_rows = source_conn.execute("SELECT * FROM journal_entries ORDER BY created_at ASC").fetchall()
    entry_count = 0
    for row in entry_rows:
        # Check if entry already exists (by entry_uid)
        existing = mother_connection.execute(
            "SELECT id FROM journal_entries WHERE entry_uid = ?", (row["entry_uid"],)
        ).fetchone()
        if existing:
            continue

        mother_connection.execute(
            """
            INSERT INTO journal_entries(
                entry_uid, created_at, updated_at, kind, source, author, status,
                importance, title, body, body_hash, tags_json, related_path,
                related_ref, metadata_json, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["entry_uid"], row["created_at"], row["updated_at"],
                row["kind"], row["source"], row["author"], row["status"],
                row["importance"], row["title"], row["body"],
                row["body_hash"] if "body_hash" in row.keys() else "",
                row["tags_json"], row["related_path"], row["related_ref"],
                row["metadata_json"], project_id,
            ),
        )
        entry_count += 1

    # Update registry
    mother_connection.execute(
        "UPDATE project_registry SET last_ingested = ? WHERE project_id = ?",
        (now_stamp(), project_id),
    )

    source_conn.close()

    return {
        "project_id": project_id,
        "blobs_imported": blob_count,
        "entries_imported": entry_count,
    }


def review_tool_diffs(
    mother_connection: sqlite3.Connection,
    source_db_path: str | Path,
) -> list[dict]:
    """
    Compare packed tools in a returned project DB against the mother's canonical versions.
    Returns a list of diffs.
    """
    source_conn = _connect(str(source_db_path))
    source_conn.row_factory = sqlite3.Row

    diffs = []
    source_tools = source_conn.execute(
        "SELECT tool_id, tool_name, relative_path, body_hash FROM packed_tools"
    ).fetchall()

    for tool in source_tools:
        canonical = mother_connection.execute(
            "SELECT body_hash FROM packed_tools WHERE relative_path = ?",
            (tool["relative_path"],),
        ).fetchone()

        if canonical is None:
            diffs.append({
                "relative_path": tool["relative_path"],
                "tool_name": tool["tool_name"],
                "status": "new_in_project",
                "project_hash": tool["body_hash"],
                "canonical_hash": "",
            })
        elif canonical["body_hash"] != tool["body_hash"]:
            diffs.append({
                "relative_path": tool["relative_path"],
                "tool_name": tool["tool_name"],
                "status": "modified",
                "project_hash": tool["body_hash"],
                "canonical_hash": canonical["body_hash"],
            })
        # If hashes match, no diff — skip

    source_conn.close()
    return diffs


def promote_tool(
    mother_connection: sqlite3.Connection,
    source_db_path: str | Path,
    relative_path: str,
) -> dict:
    """Accept a tool change from a project DB as the new canonical head."""
    source_conn = _connect(str(source_db_path))
    source_conn.row_factory = sqlite3.Row

    source_tool = source_conn.execute(
        "SELECT * FROM packed_tools WHERE relative_path = ?", (relative_path,)
    ).fetchone()
    if source_tool is None:
        source_conn.close()
        raise ValueError(f"Tool not found in source DB: {relative_path}")

    # Copy blob if needed
    source_blob = source_conn.execute(
        "SELECT content_text, content_type FROM blob_store WHERE content_hash = ?",
        (source_tool["body_hash"],),
    ).fetchone()
    if source_blob:
        store_blob(mother_connection, source_blob["content_text"], source_blob["content_type"])

    # Upsert in mother's packed_tools
    existing = mother_connection.execute(
        "SELECT tool_id FROM packed_tools WHERE relative_path = ?", (relative_path,)
    ).fetchone()

    now = now_stamp()
    if existing:
        mother_connection.execute(
            "UPDATE packed_tools SET body_hash = ?, updated_at = ? WHERE tool_id = ?",
            (source_tool["body_hash"], now, existing["tool_id"]),
        )
        tool_id = existing["tool_id"]
    else:
        tool_id = f"tool_{uuid.uuid4().hex[:12]}"
        mother_connection.execute(
            "INSERT INTO packed_tools(tool_id, tool_name, relative_path, body_hash, tool_type, metadata_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (tool_id, source_tool["tool_name"], relative_path, source_tool["body_hash"], source_tool["tool_type"], source_tool["metadata_json"], now, now),
        )

    source_conn.close()
    return {"tool_id": tool_id, "relative_path": relative_path, "new_hash": source_tool["body_hash"], "promoted_at": now}
