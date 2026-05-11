"""
FILE: src/managers/journal_manager.py
ROLE: Owner of the journal_entries domain. The single store for journal
      entries, per contract Pledge 2 (Single Store).
WHAT IT DOES (T2.1): create / update / close / archive / query journal
      entries via the standard envelope chain. Read API is direct (reads
      do not mutate state).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.lib.common import gen_id, now_iso, safe_json_dumps
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.blob_store import BlobStore
    from src.components.sqlite_store import Store
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState


log = get_logger("managers.journal")


# Valid kinds (per contract §"Journal Data Model").
VALID_KINDS = (
    "note", "decision", "todo", "issue", "log", "feedback",
    "contract", "specification", "work_log", "devlog", "guide",
    "design_record", "tranche",
)

VALID_STATUSES = ("open", "closed", "archived", "active")


@dataclass(frozen=True)
class JournalEntry:
    entry_uid: str
    created_at: str
    updated_at: str
    kind: str
    source: str
    author: str | None
    status: str
    importance: int
    title: str
    body: str
    body_hash: str
    tags: list
    related_path: str | None
    related_ref: str | None
    metadata: dict
    project_id: str | None
    superseded_by: str | None
    event_id: str


class JournalManager:
    def __init__(self, store: "Store", blob_store: "BlobStore"):
        self._store = store
        self._blob = blob_store

    # ===== envelope handlers (called by Router) =========================

    def handle_create(self, envelope: "SidecarEnvelope", state: "SidecarState") -> "SidecarEnvelope":
        """Handler for create_journal_entry.

        Reads the request payload from blob_store, writes the row with
        event_id='PENDING', creates a response blob with {entry_uid, ...},
        returns envelope with payload_ref pointing at the response blob.
        Router calls finalize_entry_event_id() after EventStore.append to
        resolve the PENDING marker.
        """
        request = self._read_request_payload(envelope)
        kind = request.get("kind", "note")
        if kind not in VALID_KINDS:
            raise ValueError(f"invalid journal kind: {kind!r}; must be one of {VALID_KINDS}")
        status = request.get("status", "open")
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid journal status: {status!r}; must be one of {VALID_STATUSES}")

        entry_uid = gen_id("journal_")
        now = now_iso()
        title = request.get("title", "(untitled)")
        body = request.get("body", "")
        body_hash = self._blob.put_text(body, content_type="text/markdown")
        source = request.get("source") or _source_for(envelope.actor_id)
        author = request.get("author") or envelope.actor_id
        importance = int(request.get("importance", 5))
        tags = request.get("tags") or []
        metadata = request.get("metadata") or {}
        related_path = request.get("related_path")
        related_ref = request.get("related_ref")

        self._store.execute(
            """
            INSERT INTO journal_entries(
                entry_uid, created_at, updated_at, kind, source, author,
                status, importance, title, body, body_hash, tags_json,
                related_path, related_ref, metadata_json, project_id,
                superseded_by, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'PENDING');
            """,
            (
                entry_uid, now, now, kind, source, author,
                status, importance, title, body, body_hash,
                safe_json_dumps(tags),
                related_path, related_ref,
                safe_json_dumps(metadata),
                envelope.project_id or None,
            ),
        )

        response = {
            "entry_uid": entry_uid,
            "body_hash": body_hash,
            "kind": kind,
            "title": title,
            "created_at": now,
        }
        response_ref = self._blob.put_json(response)
        log.info("journal entry created: uid=%s kind=%s title=%r", entry_uid, kind, title)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def handle_update(self, envelope: "SidecarEnvelope", state: "SidecarState") -> "SidecarEnvelope":
        """Handler for update_journal_entry.

        Request payload must include `entry_uid` and at least one updatable
        field (title, body, tags, importance, related_path, metadata, status).
        Writes a new revision row with the same entry_uid? No — entries
        are append-only at the row level. Updates produce a NEW entry that
        supersedes the old one.
        """
        request = self._read_request_payload(envelope)
        target_uid = request.get("entry_uid")
        if not target_uid:
            raise ValueError("update_journal_entry requires entry_uid in payload")
        old = self.get(target_uid)
        if old is None:
            raise KeyError(f"no such entry: {target_uid}")

        new_title = request.get("title", old.title)
        new_body = request.get("body", old.body)
        new_body_hash = self._blob.put_text(new_body, content_type="text/markdown")
        new_status = request.get("status", old.status)
        new_importance = int(request.get("importance", old.importance))
        new_tags = request.get("tags", old.tags)
        new_related_path = request.get("related_path", old.related_path)
        new_metadata = {**(old.metadata or {}), **(request.get("metadata") or {})}

        new_uid = gen_id("journal_")
        now = now_iso()

        with self._store.transaction():
            self._store.execute(
                """
                INSERT INTO journal_entries(
                    entry_uid, created_at, updated_at, kind, source, author,
                    status, importance, title, body, body_hash, tags_json,
                    related_path, related_ref, metadata_json, project_id,
                    superseded_by, event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'PENDING');
                """,
                (
                    new_uid, now, now, old.kind, old.source, old.author,
                    new_status, new_importance, new_title, new_body, new_body_hash,
                    safe_json_dumps(new_tags),
                    new_related_path, old.related_ref,
                    safe_json_dumps(new_metadata),
                    old.project_id,
                ),
            )
            self._store.execute(
                "UPDATE journal_entries SET superseded_by = ?, updated_at = ? "
                "WHERE entry_uid = ?;",
                (new_uid, now, target_uid),
            )

        response = {
            "entry_uid": new_uid,
            "supersedes": target_uid,
            "body_hash": new_body_hash,
            "created_at": now,
        }
        response_ref = self._blob.put_json(response)
        log.info("journal entry updated: %s -> %s", target_uid, new_uid)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def handle_close(self, envelope: "SidecarEnvelope", state: "SidecarState") -> "SidecarEnvelope":
        """Handler for close_journal_entry."""
        return self._set_status(envelope, "closed")

    def handle_archive(self, envelope: "SidecarEnvelope", state: "SidecarState") -> "SidecarEnvelope":
        """Handler for archive_journal_entry."""
        return self._set_status(envelope, "archived")

    def _set_status(self, envelope: "SidecarEnvelope", new_status: str) -> "SidecarEnvelope":
        request = self._read_request_payload(envelope)
        target_uid = request.get("entry_uid")
        if not target_uid:
            raise ValueError("requires entry_uid in payload")
        if not self.get(target_uid):
            raise KeyError(f"no such entry: {target_uid}")
        self._store.execute(
            "UPDATE journal_entries SET status = ?, updated_at = ? WHERE entry_uid = ?;",
            (new_status, now_iso(), target_uid),
        )
        response = {"entry_uid": target_uid, "status": new_status}
        response_ref = self._blob.put_json(response)
        log.info("journal entry %s -> status=%s", target_uid, new_status)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    # ===== Router post-commit finalization ==============================

    def finalize_entry_event_id(self, sealed_envelope: "SidecarEnvelope") -> None:
        """Called by Router after EventStore.append.

        The handler stored {entry_uid, ...} in the response blob; we use
        that entry_uid to set event_id on the row (replacing 'PENDING').
        """
        if not sealed_envelope.payload_ref:
            return
        try:
            response = self._blob.get_json(sealed_envelope.payload_ref)
        except Exception as e:
            log.error("could not read response blob for event %s: %s",
                      sealed_envelope.event_id, e)
            return
        entry_uid = response.get("entry_uid")
        if not entry_uid:
            return
        self._store.execute(
            "UPDATE journal_entries SET event_id = ? "
            "WHERE entry_uid = ? AND event_id = 'PENDING';",
            (sealed_envelope.event_id, entry_uid),
        )

    # ===== Read API (direct, not envelope-routed) =======================

    def get(self, entry_uid: str) -> JournalEntry | None:
        row = self._store.query_one(
            "SELECT * FROM journal_entries WHERE entry_uid = ?;", (entry_uid,)
        )
        return self._row_to_entry(row) if row else None

    def query(
        self,
        kind: str | None = None,
        status: str | None = None,
        min_importance: int | None = None,
        tag_contains: str | None = None,
        related_path: str | None = None,
        limit: int = 50,
        offset: int = 0,
        order_desc: bool = True,
        include_superseded: bool = False,
    ) -> list[JournalEntry]:
        sql = "SELECT * FROM journal_entries WHERE 1=1"
        params: list = []
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        if min_importance is not None:
            sql += " AND importance >= ?"
            params.append(min_importance)
        if related_path is not None:
            sql += " AND related_path = ?"
            params.append(related_path)
        if not include_superseded:
            sql += " AND superseded_by IS NULL"
        sql += f" ORDER BY created_at {'DESC' if order_desc else 'ASC'}"
        sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = self._store.query(sql + ";", params)
        out = [self._row_to_entry(r) for r in rows]
        if tag_contains:
            out = [e for e in out if any(tag_contains in t for t in (e.tags or []))]
        return out

    # ===== Direct write API (for orchestrators) =========================

    def create_direct(
        self,
        kind: str,
        title: str,
        body: str,
        actor_id: str,
        importance: int = 8,
        tags: list | None = None,
        evidence_refs: list | None = None,
        event_id: str = "DIRECT",
        metadata: dict | None = None,
    ) -> str:
        """Write a journal entry directly without an envelope.

        Intended for orchestrators (e.g. CloseoutOrchestrator) that coordinate
        multiple managers in sequence and cannot re-enter the Router.
        Returns entry_uid.
        """
        if kind not in VALID_KINDS:
            raise ValueError(f"invalid kind: {kind!r}")
        entry_uid = gen_id("journal_")
        now = now_iso()
        body_hash = self._blob.put_text(body, content_type="text/markdown")
        source = "agent" if actor_id.startswith("agent:") else "user"
        self._store.execute(
            """
            INSERT INTO journal_entries(
                entry_uid, created_at, updated_at, kind, source, author,
                status, importance, title, body, body_hash, tags_json,
                related_path, related_ref, metadata_json, project_id,
                superseded_by, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, ?);
            """,
            (
                entry_uid, now, now, kind, source, actor_id,
                importance, title, body, body_hash,
                safe_json_dumps(tags or []),
                safe_json_dumps(metadata or {}),
                event_id,
            ),
        )
        log.info("journal entry created (direct): uid=%s kind=%s title=%r", entry_uid, kind, title)
        return entry_uid

    def close_direct(self, entry_uid: str, event_id: str | None = None) -> None:
        """Close a journal entry directly without an envelope."""
        params: list = ["closed", now_iso(), entry_uid]
        sql = "UPDATE journal_entries SET status = ?, updated_at = ? WHERE entry_uid = ?;"
        self._store.execute(sql, params)
        if event_id:
            self._store.execute(
                "UPDATE journal_entries SET event_id = ? WHERE entry_uid = ? AND event_id = 'DIRECT';",
                (event_id, entry_uid),
            )
        log.info("journal entry closed (direct): uid=%s", entry_uid)

    def recent(self, limit: int = 20) -> list[JournalEntry]:
        return self.query(limit=limit, include_superseded=False)

    def count(self, kind: str | None = None) -> int:
        if kind is None:
            row = self._store.query_one("SELECT COUNT(*) AS n FROM journal_entries;")
        else:
            row = self._store.query_one(
                "SELECT COUNT(*) AS n FROM journal_entries WHERE kind = ?;",
                (kind,),
            )
        return int(row["n"]) if row else 0

    def stats(self) -> dict:
        rows = self._store.query(
            "SELECT kind, status, COUNT(*) AS n FROM journal_entries "
            "GROUP BY kind, status;"
        )
        by_kind: dict[str, dict[str, int]] = {}
        for r in rows:
            by_kind.setdefault(r["kind"], {})[r["status"]] = int(r["n"])
        return {
            "total": self.count(),
            "by_kind_status": by_kind,
        }

    # ===== internals ====================================================

    def _read_request_payload(self, envelope: "SidecarEnvelope") -> dict:
        if not envelope.payload_ref:
            return {}
        try:
            return self._blob.get_json(envelope.payload_ref)
        except Exception as e:
            raise ValueError(f"cannot read envelope payload from blob {envelope.payload_ref}: {e}")

    @staticmethod
    def _row_to_entry(row) -> JournalEntry:
        return JournalEntry(
            entry_uid=row["entry_uid"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            kind=row["kind"],
            source=row["source"],
            author=row["author"],
            status=row["status"],
            importance=int(row["importance"]),
            title=row["title"],
            body=row["body"],
            body_hash=row["body_hash"],
            tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
            related_path=row["related_path"],
            related_ref=row["related_ref"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            project_id=row["project_id"],
            superseded_by=row["superseded_by"],
            event_id=row["event_id"],
        )


def _source_for(actor_id: str) -> str:
    if actor_id.startswith("human:"):
        return "user"
    if actor_id.startswith("agent:"):
        return "agent"
    if actor_id.startswith("tool:"):
        return "tool"
    return "system"
