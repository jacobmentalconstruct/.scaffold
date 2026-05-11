"""
FILE: src/components/sqlite_store.py
ROLE: The single code path to the SQLite spine. All DB access flows through here.
WHAT IT DOES: Opens the DB with WAL mode + FK enforcement, runs additive
              migrations, exposes execute/query/transaction primitives,
              owns the canonical schema DDL.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from src.lib.common import now_iso
from src.lib.logging_setup import get_logger
from src.schemas.projection_schema import PROJECTION_NAMES, table_ddl


log = get_logger("components.sqlite_store")


# ----------------------------------------------------------------------------
# Schema DDL — additive only. Each migration appends; never destructive
# without a separate documented plan.
# ----------------------------------------------------------------------------

_CORE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS journal_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS journal_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL,
        description TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS blob_store (
        hash TEXT PRIMARY KEY,
        size_bytes INTEGER NOT NULL,
        content_type TEXT NOT NULL,
        body BLOB NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        stream TEXT NOT NULL,
        stream_key TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        envelope_version TEXT NOT NULL,
        operation_intent TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        sidecar_id TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        causation_id TEXT,
        contract_refs TEXT,
        payload_ref TEXT,
        evidence_refs TEXT,
        relation_refs TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        envelope_blob BLOB,
        recovery_class TEXT,
        recovery_decision TEXT,
        evidence_id TEXT,
        session_id TEXT,
        run_id TEXT,
        scenario_id TEXT,
        run_mode TEXT,
        timeout_seconds INTEGER,
        max_tool_rounds INTEGER,
        score_result TEXT,
        pass_fail_state TEXT,
        touched_paths TEXT,
        journal_entry_id TEXT,
        is_durable INTEGER,
        append_only INTEGER,
        UNIQUE (stream, stream_key, sequence)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_stream ON events(stream, stream_key, sequence);",
    "CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_intent ON events(operation_intent);",
    "CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id);",
    """
    CREATE TABLE IF NOT EXISTS relations (
        relation_id TEXT PRIMARY KEY,
        subject_id TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        predicate TEXT NOT NULL,
        object_id TEXT NOT NULL,
        object_type TEXT NOT NULL,
        metadata_json TEXT,
        emitted_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations(subject_id, predicate);",
    "CREATE INDEX IF NOT EXISTS idx_relations_object ON relations(object_id, predicate);",
    "CREATE INDEX IF NOT EXISTS idx_relations_predicate ON relations(predicate);",
    "CREATE INDEX IF NOT EXISTS idx_relations_emitted_by ON relations(emitted_by);",
    """
    CREATE TABLE IF NOT EXISTS constraint_units (
        constraint_uid TEXT PRIMARY KEY,
        section TEXT,
        title TEXT NOT NULL,
        domain_tags TEXT,
        severity TEXT NOT NULL,
        tier TEXT NOT NULL,
        instruction TEXT NOT NULL,
        full_text TEXT,
        contract_id TEXT NOT NULL,
        contract_version TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_constraint_severity ON constraint_units(severity);",
    "CREATE INDEX IF NOT EXISTS idx_constraint_tier ON constraint_units(tier);",
    """
    CREATE TABLE IF NOT EXISTS task_profiles (
        profile_id TEXT PRIMARY KEY,
        description TEXT,
        constraint_uids TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS contracts (
        contract_id TEXT PRIMARY KEY,
        version TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        text_blob_ref TEXT NOT NULL,
        section_index_json TEXT,
        introduced_at TEXT NOT NULL,
        superseded_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS acknowledgments (
        ack_id TEXT PRIMARY KEY,
        contract_id TEXT NOT NULL,
        contract_version TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        actor_type TEXT NOT NULL,
        acknowledged_at TEXT NOT NULL,
        event_id TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_acks_actor ON acknowledgments(actor_id);",
    """
    CREATE TABLE IF NOT EXISTS authorities (
        actor_id TEXT PRIMARY KEY,
        base_level TEXT NOT NULL,
        granted_by TEXT NOT NULL,
        effective_from TEXT NOT NULL,
        effective_until TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS grants (
        grant_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        operation_intent TEXT NOT NULL,
        scope_pattern TEXT,
        elevated_level TEXT NOT NULL,
        granted_by TEXT NOT NULL,
        granted_at TEXT NOT NULL,
        expires_at TEXT,
        single_use INTEGER NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS project_registry (
        project_id TEXT PRIMARY KEY,
        project_root TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        last_seen_at TEXT,
        metadata_json TEXT
    );
    """,
)


# Migration registry: version → (description, list of statements).
# Migrations run in version order, idempotent.
_MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "T1 spine boot — core tables + projection tables", _CORE_DDL),
)


# ----------------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------------


class Store:
    """Single SQLite connection wrapper. T1 = single-threaded use."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path),
            isolation_level=None,  # autocommit; we use explicit transactions
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_pragmas()

    def _configure_pragmas(self) -> None:
        c = self._conn
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA foreign_keys=ON;")
        c.execute("PRAGMA busy_timeout=10000;")
        c.execute("PRAGMA synchronous=NORMAL;")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- DML -------------------------------------------------------------

    def execute(self, sql: str, params: Iterable[Any] | dict | None = None) -> sqlite3.Cursor:
        return self._conn.execute(sql, params or ())

    def executemany(self, sql: str, seq_params: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        return self._conn.executemany(sql, seq_params)

    def query(self, sql: str, params: Iterable[Any] | dict | None = None) -> list[sqlite3.Row]:
        cur = self._conn.execute(sql, params or ())
        return cur.fetchall()

    def query_one(self, sql: str, params: Iterable[Any] | dict | None = None) -> sqlite3.Row | None:
        cur = self._conn.execute(sql, params or ())
        return cur.fetchone()

    def executescript(self, sql: str) -> None:
        self._conn.executescript(sql)

    @contextmanager
    def transaction(self):
        try:
            self._conn.execute("BEGIN")
            yield self
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # --- Meta ------------------------------------------------------------

    def schema_version(self) -> int:
        row = self.query_one("SELECT MAX(version) AS v FROM journal_migrations;")
        return int(row["v"]) if row and row["v"] is not None else 0

    def get_meta(self, key: str) -> str | None:
        row = self.query_one("SELECT value FROM journal_meta WHERE key = ?;", (key,))
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO journal_meta(key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;",
            (key, value, now_iso()),
        )


# ----------------------------------------------------------------------------
# Migrations
# ----------------------------------------------------------------------------


def _bootstrap_meta_table(store: Store) -> None:
    """Ensure journal_migrations exists before we look at schema_version."""
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS journal_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT
        );
        """
    )


def migrate(store: Store) -> list[int]:
    """Apply pending migrations in version order; return applied versions."""
    _bootstrap_meta_table(store)
    current = store.schema_version()
    applied: list[int] = []

    for version, description, statements in _MIGRATIONS:
        if version <= current:
            continue
        log.info("applying migration %s: %s", version, description)
        with store.transaction():
            for stmt in statements:
                store.execute(stmt)
            for projection in PROJECTION_NAMES:
                store.execute(table_ddl(projection))
            store.execute(
                "INSERT INTO journal_migrations(version, applied_at, description) VALUES (?, ?, ?);",
                (version, now_iso(), description),
            )
        applied.append(version)

    return applied


def open_store(path: Path) -> Store:
    """Open the SQLite spine and apply pending migrations."""
    store = Store(path)
    migrate(store)
    return store
