"""
FILE: contract.py
ROLE: Contract authority for _app-journal v2.
WHAT IT DOES: Seeds the builder constraint contract into the journal DB,
    serves it during onboarding, and tracks acknowledgment.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from common import now_stamp
from lib.journal_store import _connect, initialize_store, log_action, store_blob, write_entry


BUILTIN_CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "BCC.md"
BUILTIN_CONTRACT_VERSION = "2.0.0"


def get_builtin_contract_text() -> str:
    """Returns the builder constraint contract text from the bundled file."""
    if BUILTIN_CONTRACT_PATH.is_file():
        return BUILTIN_CONTRACT_PATH.read_text(encoding="utf-8")
    fallback_path = Path(__file__).resolve().parent / "builtin_contract.md"
    return fallback_path.read_text(encoding="utf-8")


def seed_contract(connection: sqlite3.Connection, paths: dict[str, str]) -> dict:
    """
    Idempotent. Checks journal_meta for contract_version.
    If missing or older, stores the contract in blob_store and creates
    a kind='contract' journal entry.
    """
    row = connection.execute(
        "SELECT value FROM journal_meta WHERE key = 'contract_version'"
    ).fetchone()
    current_version = row["value"] if row else ""

    if current_version == BUILTIN_CONTRACT_VERSION:
        # Already seeded at this version
        contract_row = connection.execute(
            "SELECT entry_uid, title, body_hash FROM journal_entries WHERE kind = 'contract' ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if contract_row:
            return {
                "action": "already_seeded",
                "contract_version": BUILTIN_CONTRACT_VERSION,
                "entry_uid": contract_row["entry_uid"],
                "body_hash": contract_row["body_hash"],
            }

    contract_text = get_builtin_contract_text()
    content_hash = store_blob(connection, contract_text, "text/markdown")

    # Check if a contract entry already exists
    existing = connection.execute(
        "SELECT entry_uid FROM journal_entries WHERE kind = 'contract' LIMIT 1"
    ).fetchone()

    if existing:
        # Update existing contract entry
        connection.execute(
            "UPDATE journal_entries SET body = ?, body_hash = ?, updated_at = ?, status = 'active' WHERE entry_uid = ?",
            (contract_text, content_hash, now_stamp(), existing["entry_uid"]),
        )
        entry_uid = existing["entry_uid"]
    else:
        # Create new contract entry
        import uuid
        entry_uid = f"contract_{uuid.uuid4().hex[:12]}"
        connection.execute(
            """
            INSERT INTO journal_entries(
                entry_uid, created_at, updated_at, kind, source, author, status,
                importance, title, body, body_hash, tags_json, related_path,
                related_ref, metadata_json, project_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_uid, now_stamp(), now_stamp(), "contract", "system", "project-authority-kit",
                "active", 10, "Builder Constraint Contract",
                contract_text, content_hash, json.dumps(["contract", "builder", "authority"]),
                "", "", json.dumps({"contract_version": BUILTIN_CONTRACT_VERSION}), "",
            ),
        )

    # Update meta keys
    for key, value in [
        ("contract_version", BUILTIN_CONTRACT_VERSION),
        ("contract_hash", content_hash),
        ("contract_seeded_at", now_stamp()),
    ]:
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)", (key, value)
        )

    return {
        "action": "seeded",
        "contract_version": BUILTIN_CONTRACT_VERSION,
        "entry_uid": entry_uid,
        "body_hash": content_hash,
    }


def get_contract(connection: sqlite3.Connection) -> dict | None:
    """Fetch the current contract entry."""
    row = connection.execute(
        "SELECT * FROM journal_entries WHERE kind = 'contract' ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    from lib.journal_store import _row_to_entry
    return _row_to_entry(row)


def get_contract_summary(connection: sqlite3.Connection) -> dict:
    """Return a compact contract summary (for init responses)."""
    contract = get_contract(connection)
    if contract is None:
        return {"contract_seeded": False}

    meta_row = connection.execute(
        "SELECT value FROM journal_meta WHERE key = 'contract_version'"
    ).fetchone()
    ack_row = connection.execute(
        "SELECT value FROM journal_meta WHERE key = 'contract_acknowledged_at'"
    ).fetchone()

    return {
        "contract_seeded": True,
        "contract_version": meta_row["value"] if meta_row else "",
        "entry_uid": contract["entry_uid"],
        "title": contract["title"],
        "body_hash": contract["body_hash"],
        "preview": contract["body"][:500] + ("..." if len(contract["body"]) > 500 else ""),
        "acknowledged": ack_row is not None,
        "acknowledged_at": ack_row["value"] if ack_row else "",
    }


def acknowledge_contract(
    connection: sqlite3.Connection,
    *,
    actor_id: str,
    actor_type: str = "agent",
) -> dict:
    """Record contract acknowledgment in journal_meta and action_log."""
    now = now_stamp()
    connection.execute(
        "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
        ("contract_acknowledged_at", now),
    )
    connection.execute(
        "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
        ("contract_acknowledged_by", f"{actor_type}:{actor_id}"),
    )

    log_action(
        connection,
        actor_type=actor_type,
        actor_id=actor_id,
        action_type="acknowledge_contract",
        target="builder_constraint_contract",
        summary=f"Contract acknowledged by {actor_type}:{actor_id}",
    )

    return {
        "acknowledged": True,
        "acknowledged_at": now,
        "actor_type": actor_type,
        "actor_id": actor_id,
    }
