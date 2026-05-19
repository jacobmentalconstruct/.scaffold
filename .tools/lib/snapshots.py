"""
FILE: snapshots.py
ROLE: Merkle snapshot management for _app-journal v2.
WHAT IT DOES: Creates point-in-time fingerprints of DB content,
    verifies integrity by recomputing merkle roots.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from common import now_stamp


def _compute_merkle_root(hashes: list[str]) -> str:
    """Sort hashes, concatenate, SHA-256 the result."""
    if not hashes:
        return hashlib.sha256(b"").hexdigest()
    combined = "".join(sorted(hashes))
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def create_snapshot(
    connection: sqlite3.Connection,
    *,
    description: str = "",
    include_entries: bool = True,
    include_templates: bool = True,
    include_tools: bool = True,
) -> dict:
    """Gather content hashes, compute merkle root, store snapshot."""
    snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
    now = now_stamp()
    items: list[tuple[str, str, str]] = []  # (content_hash, path, role)

    if include_entries:
        rows = connection.execute(
            "SELECT body_hash, entry_uid FROM journal_entries WHERE body_hash != ''"
        ).fetchall()
        for row in rows:
            items.append((row["body_hash"], row["entry_uid"], "entry"))

    if include_templates:
        rows = connection.execute(
            "SELECT body_hash, template_id FROM scaffold_templates WHERE body_hash != ''"
        ).fetchall()
        for row in rows:
            items.append((row["body_hash"], row["template_id"], "template"))

    if include_tools:
        rows = connection.execute(
            "SELECT body_hash, relative_path FROM packed_tools WHERE body_hash != ''"
        ).fetchall()
        for row in rows:
            items.append((row["body_hash"], row["relative_path"], "tool"))

    all_hashes = [item[0] for item in items]
    merkle_root = _compute_merkle_root(all_hashes)

    connection.execute(
        "INSERT INTO snapshots(snapshot_id, created_at, merkle_root, description, metadata_json) VALUES(?, ?, ?, ?, ?)",
        (snapshot_id, now, merkle_root, description, json.dumps({"item_count": len(items)})),
    )
    for content_hash, path, role in items:
        connection.execute(
            "INSERT OR IGNORE INTO snapshot_items(snapshot_id, content_hash, path, role) VALUES(?, ?, ?, ?)",
            (snapshot_id, content_hash, path, role),
        )

    return {
        "snapshot_id": snapshot_id,
        "created_at": now,
        "merkle_root": merkle_root,
        "item_count": len(items),
        "description": description,
    }


def list_snapshots(connection: sqlite3.Connection) -> list[dict]:
    """Return all snapshots ordered by creation time."""
    rows = connection.execute(
        "SELECT snapshot_id, created_at, merkle_root, description, metadata_json FROM snapshots ORDER BY created_at DESC"
    ).fetchall()
    return [
        {
            "snapshot_id": row["snapshot_id"],
            "created_at": row["created_at"],
            "merkle_root": row["merkle_root"],
            "description": row["description"],
            "metadata": json.loads(row["metadata_json"]),
        }
        for row in rows
    ]


def get_snapshot(connection: sqlite3.Connection, snapshot_id: str) -> dict:
    """Return a single snapshot with its items."""
    row = connection.execute(
        "SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Snapshot not found: {snapshot_id}")

    items = connection.execute(
        "SELECT content_hash, path, role FROM snapshot_items WHERE snapshot_id = ? ORDER BY path",
        (snapshot_id,),
    ).fetchall()

    return {
        "snapshot_id": row["snapshot_id"],
        "created_at": row["created_at"],
        "merkle_root": row["merkle_root"],
        "description": row["description"],
        "metadata": json.loads(row["metadata_json"]),
        "items": [{"content_hash": i["content_hash"], "path": i["path"], "role": i["role"]} for i in items],
    }


def verify_snapshot(connection: sqlite3.Connection, snapshot_id: str) -> dict:
    """Recompute merkle root from snapshot items, compare to stored."""
    snapshot = get_snapshot(connection, snapshot_id)
    recomputed = _compute_merkle_root([item["content_hash"] for item in snapshot["items"]])
    return {
        "snapshot_id": snapshot_id,
        "stored_root": snapshot["merkle_root"],
        "recomputed_root": recomputed,
        "valid": snapshot["merkle_root"] == recomputed,
        "item_count": len(snapshot["items"]),
    }
