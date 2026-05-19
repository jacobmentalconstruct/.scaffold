"""
FILE: journal_store.py
ROLE: Shared SQLite store for _app-journal v2.
WHAT IT DOES: Content-addressed storage, journal entries, action ledger,
    scaffold templates, tool packing, snapshots, and project registry.
HOW TO USE:
  - Import from tools/ or ui/
  - Call `initialize_store(...)` before using the database
  - All content flows through blob_store via SHA-256 hashes
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

import sys
_SRC_ROOT = Path(__file__).resolve().parents[1]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from common import ensure_dir, now_stamp, read_json, write_json


# ═══════════════════════════════════════════════════════════════════
# Schema v2 DDL
# ═══════════════════════════════════════════════════════════════════

SCHEMA = """
-- Metadata and migrations
CREATE TABLE IF NOT EXISTS journal_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_migrations (
    schema_version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    notes TEXT NOT NULL
);

-- Content-addressed blob store
CREATE TABLE IF NOT EXISTS blob_store (
    content_hash TEXT PRIMARY KEY,
    content_text TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT 'text/plain',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

-- Journal entries (body + body_hash dual-write)
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_uid TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    body_hash TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL,
    related_path TEXT NOT NULL,
    related_ref TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT ''
);

-- Scaffold templates
CREATE TABLE IF NOT EXISTS scaffold_templates (
    template_id TEXT PRIMARY KEY,
    path_pattern TEXT NOT NULL,
    body_hash TEXT NOT NULL DEFAULT '',
    file_type TEXT NOT NULL DEFAULT 'text',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

-- Packed tools
CREATE TABLE IF NOT EXISTS packed_tools (
    tool_id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    body_hash TEXT NOT NULL DEFAULT '',
    tool_type TEXT NOT NULL DEFAULT 'python',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Action ledger
CREATE TABLE IF NOT EXISTS action_log (
    action_id TEXT PRIMARY KEY,
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    body_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete'
);

-- Snapshots
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    merkle_root TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS snapshot_items (
    snapshot_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    path TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'entry',
    PRIMARY KEY (snapshot_id, content_hash, path)
);

-- Project registry (mother app)
CREATE TABLE IF NOT EXISTS project_registry (
    project_id TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    project_root TEXT NOT NULL DEFAULT '',
    vended_at TEXT NOT NULL,
    last_ingested TEXT NOT NULL DEFAULT '',
    tool_hash TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

-- Indexes (excluding journal_entries columns that may need ALTER TABLE first)
CREATE INDEX IF NOT EXISTS idx_journal_entries_updated_at ON journal_entries(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_journal_entries_kind ON journal_entries(kind);
CREATE INDEX IF NOT EXISTS idx_journal_entries_source ON journal_entries(source);
CREATE INDEX IF NOT EXISTS idx_journal_entries_status ON journal_entries(status);
CREATE INDEX IF NOT EXISTS idx_blob_store_created_at ON blob_store(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_log_created_at ON action_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_log_actor_type ON action_log(actor_type);
CREATE INDEX IF NOT EXISTS idx_packed_tools_tool_name ON packed_tools(tool_name);
"""

# Indexes that depend on columns added by migration (created after _migrate_to_v2)
POST_MIGRATION_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_journal_entries_project_id ON journal_entries(project_id);
"""

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_MANIFEST_PATH = PACKAGE_ROOT / "tool_manifest.json"
SCHEMA_VERSION = "2.0.0"
SQLITE_USER_VERSION = 2


# ═══════════════════════════════════════════════════════════════════
# Content-Addressed Storage helpers
# ═══════════════════════════════════════════════════════════════════

def _content_hash(text: str) -> str:
    """SHA-256 hex digest of the UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def store_blob(connection: sqlite3.Connection, content_text: str, content_type: str = "text/plain") -> str:
    """Insert into blob_store if not exists. Returns content_hash."""
    ch = _content_hash(content_text)
    connection.execute(
        "INSERT OR IGNORE INTO blob_store(content_hash, content_text, content_type, size_bytes, created_at) VALUES(?, ?, ?, ?, ?)",
        (ch, content_text, content_type, len(content_text.encode("utf-8")), now_stamp()),
    )
    return ch


def get_blob(connection: sqlite3.Connection, content_hash: str) -> str | None:
    """Retrieve content_text from blob_store by hash."""
    row = connection.execute("SELECT content_text FROM blob_store WHERE content_hash = ?", (content_hash,)).fetchone()
    return row["content_text"] if row else None


# ═══════════════════════════════════════════════════════════════════
# Path resolution
# ═══════════════════════════════════════════════════════════════════

def _sanitize_path_arg(value: str | Path | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    normalized = normalized.replace("\"", "").replace("'", "")
    return normalized or None


def _resolve_project_root(project_root: str | Path | None) -> Path:
    normalized = _sanitize_path_arg(project_root)
    if normalized:
        return Path(normalized).resolve()
    return Path.cwd().resolve()


def resolve_paths(project_root: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, str]:
    normalized_db_path = _sanitize_path_arg(db_path)
    if normalized_db_path:
        resolved_db_path = Path(normalized_db_path).resolve()
        docs_dir = resolved_db_path.parent.parent if resolved_db_path.parent.name == "_journalDB" else resolved_db_path.parent
        project_root_path = docs_dir.parent if docs_dir.name == "_docs" else resolved_db_path.parent
    else:
        project_root_path = _resolve_project_root(project_root)
        resolved_db_path = project_root_path / "_docs" / "_journalDB" / "app_journal.sqlite3"

    docs_root = project_root_path / "_docs"
    db_dir = docs_root / "_journalDB"
    app_dir = docs_root / "_AppJOURNAL"
    exports_dir = app_dir / "exports"
    config_path = app_dir / "journal_config.json"

    return {
        "project_root": str(project_root_path),
        "docs_root": str(docs_root),
        "db_dir": str(db_dir),
        "db_path": str(resolved_db_path),
        "app_dir": str(app_dir),
        "exports_dir": str(exports_dir),
        "config_path": str(config_path),
    }


# ═══════════════════════════════════════════════════════════════════
# Connection and schema
# ═══════════════════════════════════════════════════════════════════

def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def _package_manifest() -> dict[str, Any]:
    if PACKAGE_MANIFEST_PATH.exists():
        return read_json(PACKAGE_MANIFEST_PATH)
    return {"name": "project-authority-kit", "manifest_version": "2.0", "status": "active"}


def _db_manifest(paths: dict[str, str]) -> dict[str, Any]:
    package_manifest = _package_manifest()
    return {
        "db_manifest_version": "2.0",
        "schema_version": SCHEMA_VERSION,
        "sqlite_user_version": SQLITE_USER_VERSION,
        "package_name": package_manifest.get("name", "app-journal"),
        "package_manifest_version": package_manifest.get("manifest_version", "2.0"),
        "package_status": package_manifest.get("status", "active"),
        "package_description": package_manifest.get("description", ""),
        "db_schema": {
            "table_names": [
                "journal_meta", "journal_migrations", "journal_entries",
                "blob_store", "scaffold_templates", "packed_tools",
                "action_log", "snapshots", "snapshot_items", "project_registry",
            ],
            "entry_primary_id": "entry_uid",
            "metadata_store": "journal_meta",
            "migration_store": "journal_migrations",
            "content_store": "blob_store",
            "schema_version": SCHEMA_VERSION,
        },
        "project_convention": {
            "project_root": paths["project_root"],
            "db_path": paths["db_path"],
            "app_dir": paths["app_dir"],
            "exports_dir": paths["exports_dir"],
        },
        "agent_entrypoints": {
            "mcp": "src/mcp_server.py",
            "cli_tools": [
                "src/tools/journal_init.py",
                "src/tools/journal_write.py",
                "src/tools/journal_query.py",
                "src/tools/journal_export.py",
                "src/tools/journal_manifest.py",
                "src/tools/journal_acknowledge.py",
                "src/tools/journal_actions.py",
                "src/tools/journal_scaffold.py",
                "src/tools/journal_pack.py",
                "src/tools/journal_snapshot.py",
            ],
        },
    }


# ═══════════════════════════════════════════════════════════════════
# Migration
# ═══════════════════════════════════════════════════════════════════

def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    """Migrate an existing v1 database to v2. Idempotent."""
    user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    if user_version >= SQLITE_USER_VERSION:
        return

    # Add body_hash column if missing (v1 → v2)
    columns = [row[1] for row in connection.execute("PRAGMA table_info(journal_entries)").fetchall()]
    if "body_hash" not in columns:
        connection.execute("ALTER TABLE journal_entries ADD COLUMN body_hash TEXT NOT NULL DEFAULT ''")
    if "project_id" not in columns:
        connection.execute("ALTER TABLE journal_entries ADD COLUMN project_id TEXT NOT NULL DEFAULT ''")

    # Backfill body_hash from existing entries
    rows = connection.execute("SELECT id, body FROM journal_entries WHERE body_hash = '' OR body_hash IS NULL").fetchall()
    for row in rows:
        ch = store_blob(connection, row["body"], "text/plain")
        connection.execute("UPDATE journal_entries SET body_hash = ? WHERE id = ?", (ch, row["id"]))

    # Record migration
    connection.execute(
        "INSERT OR IGNORE INTO journal_migrations(schema_version, applied_at, notes) VALUES(?, ?, ?)",
        (SCHEMA_VERSION, now_stamp(), "Migration to v2: CAS blob_store, action_log, scaffold_templates, packed_tools, snapshots, project_registry."),
    )

    connection.execute(f"PRAGMA user_version = {SQLITE_USER_VERSION}")


# ═══════════════════════════════════════════════════════════════════
# Initialize
# ═══════════════════════════════════════════════════════════════════

def initialize_store(project_root: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, str]:
    paths = resolve_paths(project_root=project_root, db_path=db_path)
    ensure_dir(Path(paths["db_dir"]))
    ensure_dir(Path(paths["app_dir"]))
    ensure_dir(Path(paths["exports_dir"]))
    package_manifest = _package_manifest()
    db_manifest = _db_manifest(paths)

    with closing(_connect(paths["db_path"])) as connection:
        connection.executescript(SCHEMA)
        _migrate_to_v2(connection)
        connection.executescript(POST_MIGRATION_INDEXES)

        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("project_root", paths["project_root"]),
        )
        connection.execute(
            "INSERT OR IGNORE INTO journal_meta(key, value) VALUES(?, ?)",
            ("initialized_at", now_stamp()),
        )
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("package_manifest_json", json.dumps(package_manifest, sort_keys=True)),
        )
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("db_manifest_json", json.dumps(db_manifest, sort_keys=True)),
        )
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        connection.execute(
            "INSERT OR REPLACE INTO journal_meta(key, value) VALUES(?, ?)",
            ("sqlite_user_version", str(SQLITE_USER_VERSION)),
        )
        connection.execute(
            "INSERT OR IGNORE INTO journal_migrations(schema_version, applied_at, notes) VALUES(?, ?, ?)",
            (SCHEMA_VERSION, now_stamp(), "Schema v2 initialized."),
        )
        connection.commit()

    write_json(
        Path(paths["config_path"]),
        {
            "project_root": paths["project_root"],
            "db_path": paths["db_path"],
            "schema_version": SCHEMA_VERSION,
            "installer_hint": "python install.py",
            "mcp_hint": "python src/mcp_server.py",
        },
    )
    write_json(Path(paths["app_dir"]) / "db_manifest.json", db_manifest)

    # Seed builder constraint contract (Phase 3)
    try:
        from lib.contract import seed_contract
        with closing(_connect(paths["db_path"])) as connection:
            seed_contract(connection, paths)
            connection.commit()
    except (ImportError, FileNotFoundError):
        pass  # Contract module or file not yet available

    return paths


# ═══════════════════════════════════════════════════════════════════
# Manifest
# ═══════════════════════════════════════════════════════════════════

def get_manifest(*, project_root: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root, db_path=db_path)
    with closing(_connect(paths["db_path"])) as connection:
        rows = connection.execute(
            "SELECT key, value FROM journal_meta WHERE key IN ('project_root', 'initialized_at', 'package_manifest_json', 'db_manifest_json', 'schema_version', 'sqlite_user_version', 'contract_version', 'contract_hash')"
        ).fetchall()
        entry_count_row = connection.execute("SELECT COUNT(*) AS count FROM journal_entries").fetchone()
        blob_count_row = connection.execute("SELECT COUNT(*) AS count FROM blob_store").fetchone()
        migration_rows = connection.execute(
            "SELECT schema_version, applied_at, notes FROM journal_migrations ORDER BY applied_at ASC"
        ).fetchall()

    meta = {row["key"]: row["value"] for row in rows}
    package_manifest = json.loads(meta.get("package_manifest_json", "{}"))
    db_manifest = json.loads(meta.get("db_manifest_json", "{}"))
    return {
        "paths": paths,
        "package_manifest_path": str(PACKAGE_MANIFEST_PATH),
        "package_manifest": package_manifest,
        "db_manifest": db_manifest,
        "db_summary": {
            "initialized_at": meta.get("initialized_at", ""),
            "schema_version": meta.get("schema_version", ""),
            "sqlite_user_version": int(meta.get("sqlite_user_version", "0") or 0),
            "entry_count": int(entry_count_row["count"]) if entry_count_row else 0,
            "blob_count": int(blob_count_row["count"]) if blob_count_row else 0,
            "contract_version": meta.get("contract_version", ""),
            "contract_hash": meta.get("contract_hash", ""),
        },
        "migrations": [
            {"schema_version": row["schema_version"], "applied_at": row["applied_at"], "notes": row["notes"]}
            for row in migration_rows
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# Tags
# ═══════════════════════════════════════════════════════════════════

def _normalize_tags(tags: list[str] | None) -> list[str]:
    values = []
    seen = set()
    for raw in tags or []:
        tag = str(raw).strip()
        if tag and tag not in seen:
            values.append(tag)
            seen.add(tag)
    return values


def parse_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return _normalize_tags([str(item) for item in value])
    if isinstance(value, str):
        return _normalize_tags([part.strip() for part in value.split(",")])
    raise ValueError("tags must be a list of strings or a comma-separated string")


# ═══════════════════════════════════════════════════════════════════
# Row conversion
# ═══════════════════════════════════════════════════════════════════

def _row_to_entry(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "entry_uid": row["entry_uid"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "kind": row["kind"],
        "source": row["source"],
        "author": row["author"],
        "status": row["status"],
        "importance": row["importance"],
        "title": row["title"],
        "body": row["body"],
        "body_hash": row["body_hash"] if "body_hash" in row.keys() else "",
        "tags": json.loads(row["tags_json"]),
        "related_path": row["related_path"],
        "related_ref": row["related_ref"],
        "metadata": json.loads(row["metadata_json"]),
        "project_id": row["project_id"] if "project_id" in row.keys() else "",
    }


# ═══════════════════════════════════════════════════════════════════
# Write / Get / Query / Export entries
# ═══════════════════════════════════════════════════════════════════

def write_entry(
    *,
    project_root: str | Path | None = None,
    db_path: str | Path | None = None,
    action: str = "create",
    entry_uid: str | None = None,
    title: str = "",
    body: str = "",
    kind: str = "note",
    source: str | None = None,
    author: str | None = None,
    tags: list[str] | None = None,
    status: str | None = None,
    importance: int | None = None,
    related_path: str | None = None,
    related_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
    append_text: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root, db_path=db_path)
    now = now_stamp()
    normalized_tags = _normalize_tags(tags)
    payload_metadata = metadata or {}

    with closing(_connect(paths["db_path"])) as connection:
        if action == "create":
            if not title.strip() and not body.strip():
                raise ValueError("Provide at least a title or body for a new journal entry.")
            new_uid = entry_uid or f"journal_{uuid.uuid4().hex[:12]}"
            body_text = body.strip()
            bh = store_blob(connection, body_text) if body_text else ""
            connection.execute(
                """
                INSERT INTO journal_entries(
                    entry_uid, created_at, updated_at, kind, source, author, status,
                    importance, title, body, body_hash, tags_json, related_path, related_ref,
                    metadata_json, project_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_uid, now, now, kind,
                    source or "agent", author or "",
                    status or "open", int(importance or 0),
                    title.strip() or "(untitled)", body_text, bh,
                    json.dumps(normalized_tags),
                    related_path or "", related_ref or "",
                    json.dumps(payload_metadata), project_id,
                ),
            )
            connection.commit()
            return get_entry(entry_uid=new_uid, db_path=paths["db_path"])

        if not entry_uid:
            raise ValueError("entry_uid is required for update or append.")

        if action == "append":
            existing = get_entry(entry_uid=entry_uid, db_path=paths["db_path"])
            joiner = "\n\n" if existing["body"].strip() and append_text.strip() else ""
            updated_body = f"{existing['body']}{joiner}{append_text.strip()}".strip()
            bh = store_blob(connection, updated_body) if updated_body else ""
            connection.execute(
                "UPDATE journal_entries SET body = ?, body_hash = ?, updated_at = ?, status = ?, importance = ? WHERE entry_uid = ?",
                (updated_body, bh, now, status or existing["status"], int(importance if importance is not None else existing["importance"]), entry_uid),
            )
            connection.commit()
            return get_entry(entry_uid=entry_uid, db_path=paths["db_path"])

        if action == "update":
            existing = get_entry(entry_uid=entry_uid, db_path=paths["db_path"])
            final_body = body if body != "" else existing["body"]
            bh = store_blob(connection, final_body) if final_body else ""
            connection.execute(
                """
                UPDATE journal_entries
                SET title = ?, body = ?, body_hash = ?, kind = ?, source = ?, author = ?, status = ?,
                    importance = ?, tags_json = ?, related_path = ?, related_ref = ?,
                    metadata_json = ?, updated_at = ?
                WHERE entry_uid = ?
                """,
                (
                    title.strip() or existing["title"],
                    final_body, bh,
                    kind or existing["kind"],
                    source if source is not None else existing["source"],
                    author if author is not None else existing["author"],
                    status if status is not None else existing["status"],
                    int(importance if importance is not None else existing["importance"]),
                    json.dumps(normalized_tags or existing["tags"]),
                    related_path if related_path is not None else existing["related_path"],
                    related_ref if related_ref is not None else existing["related_ref"],
                    json.dumps(payload_metadata or existing["metadata"]),
                    now, entry_uid,
                ),
            )
            connection.commit()
            return get_entry(entry_uid=entry_uid, db_path=paths["db_path"])

        raise ValueError(f"Unsupported action: {action}")


def get_entry(*, entry_uid: str, project_root: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root, db_path=db_path)
    with closing(_connect(paths["db_path"])) as connection:
        row = connection.execute("SELECT * FROM journal_entries WHERE entry_uid = ?", (entry_uid,)).fetchone()
    if row is None:
        raise ValueError(f"Journal entry not found: {entry_uid}")
    return _row_to_entry(row)


def query_entries(
    *,
    project_root: str | Path | None = None,
    db_path: str | Path | None = None,
    query: str = "",
    kind: str = "",
    source: str = "",
    status: str = "",
    tags: list[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root, db_path=db_path)
    conditions: list[str] = []
    values: list[Any] = []

    if query.strip():
        needle = f"%{query.strip().lower()}%"
        conditions.append("(LOWER(title) LIKE ? OR LOWER(body) LIKE ? OR LOWER(tags_json) LIKE ?)")
        values.extend([needle, needle, needle])
    if kind.strip():
        conditions.append("kind = ?")
        values.append(kind.strip())
    if source.strip():
        conditions.append("source = ?")
        values.append(source.strip())
    if status.strip():
        conditions.append("status = ?")
        values.append(status.strip())

    for tag in _normalize_tags(tags):
        conditions.append("tags_json LIKE ?")
        values.append(f'%"{tag}"%')

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT * FROM journal_entries {where_clause} ORDER BY updated_at DESC, created_at DESC, id DESC LIMIT ?"
    values.append(max(1, int(limit)))

    with closing(_connect(paths["db_path"])) as connection:
        rows = connection.execute(sql, values).fetchall()
        count_row = connection.execute("SELECT COUNT(*) AS count FROM journal_entries").fetchone()

    entries = [_row_to_entry(row) for row in rows]
    return {
        "paths": paths,
        "summary": {
            "entry_count": len(entries),
            "total_entries": int(count_row["count"]) if count_row else 0,
        },
        "entries": entries,
    }


def export_entries(
    *,
    project_root: str | Path | None = None,
    db_path: str | Path | None = None,
    query: str = "",
    kind: str = "",
    source: str = "",
    status: str = "",
    tags: list[str] | None = None,
    limit: int = 200,
    format_name: str = "markdown",
) -> dict[str, Any]:
    result = query_entries(
        project_root=project_root, db_path=db_path,
        query=query, kind=kind, source=source, status=status, tags=tags, limit=limit,
    )
    paths = result["paths"]
    exports_dir = Path(paths["exports_dir"])
    stamp = now_stamp().replace(":", "").replace("-", "")

    if format_name == "json":
        export_path = exports_dir / f"journal_export_{stamp}.json"
        write_json(export_path, result)
        return {"export_path": str(export_path), "format": format_name, "entry_count": len(result["entries"])}

    lines = ["# App Journal Export", ""]
    for entry in result["entries"]:
        lines.extend([
            f"## {entry['title']}",
            f"- entry_uid: `{entry['entry_uid']}`",
            f"- kind: `{entry['kind']}`",
            f"- source: `{entry['source']}`",
            f"- status: `{entry['status']}`",
            f"- updated_at: `{entry['updated_at']}`",
            f"- tags: `{', '.join(entry['tags'])}`",
            "",
            entry["body"],
            "",
        ])
    export_path = exports_dir / f"journal_export_{stamp}.md"
    export_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {"export_path": str(export_path), "format": "markdown", "entry_count": len(result["entries"])}


# ═══════════════════════════════════════════════════════════════════
# Action Ledger
# ═══════════════════════════════════════════════════════════════════

def log_action(
    connection: sqlite3.Connection,
    *,
    actor_type: str,
    actor_id: str,
    action_type: str,
    target: str = "",
    summary: str = "",
    body_text: str | None = None,
    status: str = "complete",
) -> dict[str, Any]:
    """Log an action to the shared action ledger."""
    action_id = f"action_{uuid.uuid4().hex[:12]}"
    bh = store_blob(connection, body_text, "text/plain") if body_text else ""
    now = now_stamp()
    connection.execute(
        "INSERT INTO action_log(action_id, actor_type, actor_id, action_type, target, summary, body_hash, created_at, status) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (action_id, actor_type, actor_id, action_type, target, summary, bh, now, status),
    )
    return {
        "action_id": action_id, "actor_type": actor_type, "actor_id": actor_id,
        "action_type": action_type, "target": target, "summary": summary,
        "body_hash": bh, "created_at": now, "status": status,
    }


def query_actions(
    *,
    project_root: str | Path | None = None,
    db_path: str | Path | None = None,
    actor_type: str = "",
    action_type: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Query the action log with optional filters."""
    paths = initialize_store(project_root=project_root, db_path=db_path)
    conditions: list[str] = []
    values: list[Any] = []

    if actor_type.strip():
        conditions.append("actor_type = ?")
        values.append(actor_type.strip())
    if action_type.strip():
        conditions.append("action_type = ?")
        values.append(action_type.strip())

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"SELECT * FROM action_log {where_clause} ORDER BY created_at DESC LIMIT ?"
    values.append(max(1, int(limit)))

    with closing(_connect(paths["db_path"])) as connection:
        rows = connection.execute(sql, values).fetchall()

    return {
        "paths": paths,
        "actions": [
            {
                "action_id": row["action_id"], "actor_type": row["actor_type"],
                "actor_id": row["actor_id"], "action_type": row["action_type"],
                "target": row["target"], "summary": row["summary"],
                "body_hash": row["body_hash"], "created_at": row["created_at"],
                "status": row["status"],
            }
            for row in rows
        ],
    }
