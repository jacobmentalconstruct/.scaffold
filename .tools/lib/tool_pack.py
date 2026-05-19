"""
FILE: tool_pack.py
ROLE: Tool packing/unpacking for _app-journal v2.
WHAT IT DOES: Stores tool source code as blobs in the DB, extracts them to disk on demand.
    Enables the DB to be the portable package.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from common import now_stamp
from lib.journal_store import get_blob, store_blob


# Files/dirs to skip when packing
DEFAULT_EXCLUDE = {"__pycache__", ".pyc", ".pyo", ".git", ".venv", "_parts", "_docs"}


def _should_exclude(path: Path, exclude_patterns: set[str]) -> bool:
    for part in path.parts:
        if part in exclude_patterns:
            return True
    return any(path.name.endswith(ext) for ext in exclude_patterns if ext.startswith("."))


def pack_file(
    connection: sqlite3.Connection,
    *,
    tool_name: str,
    relative_path: str,
    source_text: str,
    tool_type: str = "python",
    metadata: dict | None = None,
) -> dict:
    """Store a single file in packed_tools + blob_store."""
    bh = store_blob(connection, source_text, f"text/{tool_type}")
    tool_id = f"tool_{uuid.uuid4().hex[:12]}"
    now = now_stamp()

    # Upsert by relative_path
    existing = connection.execute(
        "SELECT tool_id FROM packed_tools WHERE relative_path = ?", (relative_path,)
    ).fetchone()

    if existing:
        tool_id = existing["tool_id"]
        connection.execute(
            "UPDATE packed_tools SET tool_name = ?, body_hash = ?, tool_type = ?, metadata_json = ?, updated_at = ? WHERE tool_id = ?",
            (tool_name, bh, tool_type, json.dumps(metadata or {}), now, tool_id),
        )
    else:
        connection.execute(
            "INSERT INTO packed_tools(tool_id, tool_name, relative_path, body_hash, tool_type, metadata_json, created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (tool_id, tool_name, relative_path, bh, tool_type, json.dumps(metadata or {}), now, now),
        )

    return {"tool_id": tool_id, "relative_path": relative_path, "body_hash": bh}


def pack_package(
    connection: sqlite3.Connection,
    package_root: str | Path,
    *,
    exclude_patterns: set[str] | None = None,
) -> dict:
    """Walk package_root, pack every file into packed_tools. Returns summary."""
    package_root = Path(package_root)
    excludes = exclude_patterns or DEFAULT_EXCLUDE
    packed = []
    for file_path in sorted(package_root.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(package_root)
        if _should_exclude(rel, excludes):
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        suffix = file_path.suffix.lstrip(".")
        tool_type = {"py": "python", "json": "json", "md": "markdown", "bat": "batch", "sh": "shell"}.get(suffix, "text")
        result = pack_file(
            connection,
            tool_name=file_path.stem,
            relative_path=str(rel).replace("\\", "/"),
            source_text=content,
            tool_type=tool_type,
        )
        packed.append(result)

    return {"packed_count": len(packed), "files": packed}


def unpack_tool(connection: sqlite3.Connection, tool_id: str, target_dir: str | Path) -> dict:
    """Write a single packed tool to disk."""
    row = connection.execute(
        "SELECT * FROM packed_tools WHERE tool_id = ?", (tool_id,)
    ).fetchone()
    target_dir = Path(target_dir)
    if row is None:
        raise ValueError(f"Packed tool not found: {tool_id}")

    content = get_blob(connection, row["body_hash"])
    if content is None:
        raise ValueError(f"Blob not found for tool {tool_id}: {row['body_hash']}")

    target_path = target_dir / row["relative_path"]
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return {"path": str(target_path), "tool_id": tool_id, "relative_path": row["relative_path"]}


def unpack_package(connection: sqlite3.Connection, target_dir: str | Path) -> dict:
    """Unpack all packed tools to target_dir."""
    rows = connection.execute("SELECT tool_id FROM packed_tools ORDER BY relative_path").fetchall()
    unpacked = []
    for row in rows:
        result = unpack_tool(connection, row["tool_id"], target_dir)
        unpacked.append(result)
    return {"unpacked_count": len(unpacked), "files": unpacked}


def list_packed_tools(connection: sqlite3.Connection) -> list[dict]:
    """Return all packed tool records."""
    rows = connection.execute(
        "SELECT tool_id, tool_name, relative_path, body_hash, tool_type, metadata_json, created_at, updated_at FROM packed_tools ORDER BY relative_path"
    ).fetchall()
    return [
        {
            "tool_id": row["tool_id"],
            "tool_name": row["tool_name"],
            "relative_path": row["relative_path"],
            "body_hash": row["body_hash"],
            "tool_type": row["tool_type"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
