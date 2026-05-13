"""
FILE: src/managers/memory_manager.py
ROLE: Session-scoped STM / Bag / Shelf memory manager for the local sidecar.
WHAT IT DOES: Persists short-term memory, overflows older working context into
              a Bag of Evidence, derives a compact Evidence Shelf, and records
              per-hunk diff provenance for bounded writes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from src.components.diff_builder import DiffBuilder
from src.lib.common import gen_id, now_iso, public_path, safe_json_dumps


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str
    session_id: str
    actor_id: str
    layer: str
    role: str
    summary: str
    content_ref: str | None
    source_kind: str
    source_id: str
    metadata: dict
    ordinal: int
    promoted_to_journal_uid: str | None
    created_at: str
    last_accessed_at: str


@dataclass(frozen=True)
class ChangeHunkRecord:
    hunk_id: str
    tranche_id: str | None
    session_id: str | None
    actor_id: str
    path: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    added_lines: int
    removed_lines: int
    diff_text_ref: str
    context_hash: str
    summary: str
    decision_id: str | None
    source_event_id: str | None
    created_at: str


class MemoryManager:
    STM_KEEP_LATEST = 8
    SHELF_ITEM_LIMIT = 8

    def __init__(self, store, blob_store):
        self._store = store
        self._blob = blob_store

    # ------------------------------------------------------------------
    # Session memory
    # ------------------------------------------------------------------

    def append_stm(
        self,
        *,
        session_id: str,
        actor_id: str,
        role: str,
        content: str,
        summary: str = "",
        source_kind: str = "",
        source_id: str = "",
        metadata: dict | None = None,
    ) -> MemoryItem:
        ordinal = self._next_ordinal(session_id, "stm")
        return self._insert_item(
            session_id=session_id,
            actor_id=actor_id,
            layer="stm",
            role=role,
            summary=summary or _excerpt(content, 180),
            content=content,
            source_kind=source_kind,
            source_id=source_id,
            metadata=metadata or {},
            ordinal=ordinal,
        )

    def overflow_stm_to_bag(self, session_id: str, *, keep_latest: int | None = None) -> int:
        keep_latest = keep_latest if keep_latest is not None else self.STM_KEEP_LATEST
        rows = self._store.query(
            """
            SELECT memory_id FROM session_memory_items
            WHERE session_id = ? AND layer = 'stm'
            ORDER BY ordinal DESC;
            """,
            (session_id,),
        )
        if len(rows) <= keep_latest:
            self.rebuild_shelf(session_id)
            return 0
        move_ids = [row["memory_id"] for row in rows[keep_latest:]]
        now = now_iso()
        for memory_id in move_ids:
            self._store.execute(
                """
                UPDATE session_memory_items
                SET layer = 'bag', last_accessed_at = ?
                WHERE memory_id = ?;
                """,
                (now, memory_id),
            )
        self.rebuild_shelf(session_id)
        return len(move_ids)

    def list_layer(self, session_id: str, layer: str, *, limit: int = 20) -> list[MemoryItem]:
        rows = self._store.query(
            """
            SELECT * FROM session_memory_items
            WHERE session_id = ? AND layer = ?
            ORDER BY ordinal DESC, created_at DESC
            LIMIT ?;
            """,
            (session_id, layer, limit),
        )
        return [self._row_to_item(row) for row in rows]

    def rebuild_shelf(self, session_id: str) -> list[MemoryItem]:
        row = self._store.query_one(
            """
            SELECT actor_id FROM session_memory_items
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (session_id,),
        )
        actor_id = row["actor_id"] if row else ""
        self._store.execute(
            "DELETE FROM session_memory_items WHERE session_id = ? AND layer = 'shelf';",
            (session_id,),
        )
        created: list[MemoryItem] = []
        if not actor_id:
            return created

        stm_items = self.list_layer(session_id, "stm", limit=4)
        bag_items = self.list_layer(session_id, "bag", limit=4)
        latest_hunks = self.list_change_hunks(session_id=session_id, limit=4)
        pending = self._store.query(
            """
            SELECT request_id, summary, requested_level, requested_at
            FROM approval_requests
            WHERE session_id = ? AND status = 'pending'
            ORDER BY requested_at DESC LIMIT 4;
            """,
            (session_id,),
        )

        ordinal = 1
        if pending:
            content = safe_json_dumps([dict(row) for row in pending], indent=2)
            created.append(
                self._insert_item(
                    session_id=session_id,
                    actor_id=actor_id,
                    layer="shelf",
                    role="open_loops",
                    summary=f"{len(pending)} pending approval loop(s)",
                    content=content,
                    source_kind="approval_requests",
                    source_id=session_id,
                    metadata={"count": len(pending)},
                    ordinal=ordinal,
                )
            )
            ordinal += 1

        if stm_items:
            content = safe_json_dumps([self._item_to_payload(item) for item in stm_items], indent=2)
            created.append(
                self._insert_item(
                    session_id=session_id,
                    actor_id=actor_id,
                    layer="shelf",
                    role="working_set",
                    summary=f"{len(stm_items)} live STM item(s)",
                    content=content,
                    source_kind="stm",
                    source_id=session_id,
                    metadata={"count": len(stm_items)},
                    ordinal=ordinal,
                )
            )
            ordinal += 1

        if bag_items:
            content = safe_json_dumps([self._item_to_payload(item) for item in bag_items], indent=2)
            created.append(
                self._insert_item(
                    session_id=session_id,
                    actor_id=actor_id,
                    layer="shelf",
                    role="overflow_archive",
                    summary=f"{len(bag_items)} bag item(s) available for recall",
                    content=content,
                    source_kind="bag",
                    source_id=session_id,
                    metadata={"count": len(bag_items)},
                    ordinal=ordinal,
                )
            )
            ordinal += 1

        if latest_hunks:
            content = safe_json_dumps([self._hunk_to_payload(hunk) for hunk in latest_hunks], indent=2)
            created.append(
                self._insert_item(
                    session_id=session_id,
                    actor_id=actor_id,
                    layer="shelf",
                    role="change_provenance",
                    summary=f"{len(latest_hunks)} recent change hunk(s)",
                    content=content,
                    source_kind="change_hunks",
                    source_id=session_id,
                    metadata={"count": len(latest_hunks)},
                    ordinal=ordinal,
                )
            )
        return created

    def session_summary(self, session_id: str) -> dict:
        def _count(layer: str) -> int:
            row = self._store.query_one(
                "SELECT COUNT(*) AS n FROM session_memory_items WHERE session_id = ? AND layer = ?;",
                (session_id, layer),
            )
            return int(row["n"]) if row else 0

        return {
            "session_id": session_id,
            "stm_count": _count("stm"),
            "bag_count": _count("bag"),
            "shelf_count": _count("shelf"),
            "recent_stm": [self._item_to_payload(item) for item in self.list_layer(session_id, "stm", limit=4)],
            "recent_bag": [self._item_to_payload(item) for item in self.list_layer(session_id, "bag", limit=4)],
            "evidence_shelf": [self._item_to_payload(item) for item in self.list_layer(session_id, "shelf", limit=self.SHELF_ITEM_LIMIT)],
            "recent_change_hunks": [self._hunk_to_payload(hunk) for hunk in self.list_change_hunks(session_id=session_id, limit=6)],
        }

    def promote_bag_item_to_journal(self, *, memory_id: str, journal_entry_uid: str) -> None:
        self._store.execute(
            """
            UPDATE session_memory_items
            SET promoted_to_journal_uid = ?, last_accessed_at = ?
            WHERE memory_id = ? AND layer = 'bag';
            """,
            (journal_entry_uid, now_iso(), memory_id),
        )

    # ------------------------------------------------------------------
    # Change hunks
    # ------------------------------------------------------------------

    def record_change_hunks(
        self,
        *,
        actor_id: str,
        path: str,
        before_text: str,
        after_text: str,
        tranche_id: str | None = None,
        session_id: str | None = None,
        decision_id: str | None = None,
        source_event_id: str | None = None,
        summary_prefix: str = "",
    ) -> list[ChangeHunkRecord]:
        diff = DiffBuilder.from_strings(path=path, before=before_text, after=after_text)
        created: list[ChangeHunkRecord] = []
        for hunk in diff.hunks:
            diff_text_ref = self._blob.put_text(hunk["diff_text"], content_type="text/x-diff")
            summary = summary_prefix.strip() or f"{path} lines {hunk['new_start']}..{hunk['new_start'] + max(hunk['new_count'] - 1, 0)}"
            hunk_id = gen_id("hunk_")
            created_at = now_iso()
            self._store.execute(
                """
                INSERT INTO change_hunks(
                    hunk_id, tranche_id, session_id, actor_id, path,
                    old_start, old_count, new_start, new_count,
                    added_lines, removed_lines, diff_text_ref, context_hash,
                    summary, decision_id, source_event_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    hunk_id, tranche_id, session_id, actor_id, path,
                    hunk["old_start"], hunk["old_count"], hunk["new_start"], hunk["new_count"],
                    hunk["added_lines"], hunk["removed_lines"], diff_text_ref, diff.context_hash,
                    summary, decision_id, source_event_id, created_at,
                ),
            )
            created.append(
                ChangeHunkRecord(
                    hunk_id=hunk_id,
                    tranche_id=tranche_id,
                    session_id=session_id,
                    actor_id=actor_id,
                    path=path,
                    old_start=hunk["old_start"],
                    old_count=hunk["old_count"],
                    new_start=hunk["new_start"],
                    new_count=hunk["new_count"],
                    added_lines=hunk["added_lines"],
                    removed_lines=hunk["removed_lines"],
                    diff_text_ref=diff_text_ref,
                    context_hash=diff.context_hash,
                    summary=summary,
                    decision_id=decision_id,
                    source_event_id=source_event_id,
                    created_at=created_at,
                )
            )
        return created

    def list_change_hunks(
        self,
        *,
        session_id: str | None = None,
        tranche_id: str | None = None,
        path: str | None = None,
        limit: int = 20,
    ) -> list[ChangeHunkRecord]:
        sql = "SELECT * FROM change_hunks WHERE 1=1"
        params: list[object] = []
        if session_id:
            sql += " AND session_id = ?"
            params.append(session_id)
        if tranche_id:
            sql += " AND tranche_id = ?"
            params.append(tranche_id)
        if path:
            sql += " AND path = ?"
            params.append(path)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._store.query(sql + ";", params)
        return [self._row_to_hunk(row) for row in rows]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _insert_item(
        self,
        *,
        session_id: str,
        actor_id: str,
        layer: str,
        role: str,
        summary: str,
        content: str,
        source_kind: str,
        source_id: str,
        metadata: dict,
        ordinal: int,
    ) -> MemoryItem:
        memory_id = gen_id("mem_")
        now = now_iso()
        content_ref = self._blob.put_text(content, content_type="application/json" if _looks_like_json(content) else "text/plain")
        self._store.execute(
            """
            INSERT INTO session_memory_items(
                memory_id, session_id, actor_id, layer, role, summary,
                content_ref, source_kind, source_id, metadata_json,
                ordinal, promoted_to_journal_uid, created_at, last_accessed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?);
            """,
            (
                memory_id, session_id, actor_id, layer, role, summary,
                content_ref, source_kind, source_id, safe_json_dumps(metadata),
                ordinal, now, now,
            ),
        )
        return MemoryItem(
            memory_id=memory_id,
            session_id=session_id,
            actor_id=actor_id,
            layer=layer,
            role=role,
            summary=summary,
            content_ref=content_ref,
            source_kind=source_kind,
            source_id=source_id,
            metadata=metadata,
            ordinal=ordinal,
            promoted_to_journal_uid=None,
            created_at=now,
            last_accessed_at=now,
        )

    def _next_ordinal(self, session_id: str, layer: str) -> int:
        row = self._store.query_one(
            "SELECT COALESCE(MAX(ordinal), 0) AS n FROM session_memory_items WHERE session_id = ? AND layer = ?;",
            (session_id, layer),
        )
        return int(row["n"]) + 1 if row else 1

    @staticmethod
    def _row_to_item(row) -> MemoryItem:
        return MemoryItem(
            memory_id=row["memory_id"],
            session_id=row["session_id"],
            actor_id=row["actor_id"],
            layer=row["layer"],
            role=row["role"] or "",
            summary=row["summary"] or "",
            content_ref=row["content_ref"],
            source_kind=row["source_kind"] or "",
            source_id=row["source_id"] or "",
            metadata=json.loads(row["metadata_json"] or "{}"),
            ordinal=int(row["ordinal"] or 0),
            promoted_to_journal_uid=row["promoted_to_journal_uid"],
            created_at=row["created_at"],
            last_accessed_at=row["last_accessed_at"],
        )

    @staticmethod
    def _row_to_hunk(row) -> ChangeHunkRecord:
        return ChangeHunkRecord(
            hunk_id=row["hunk_id"],
            tranche_id=row["tranche_id"],
            session_id=row["session_id"],
            actor_id=row["actor_id"],
            path=row["path"],
            old_start=int(row["old_start"]),
            old_count=int(row["old_count"]),
            new_start=int(row["new_start"]),
            new_count=int(row["new_count"]),
            added_lines=int(row["added_lines"]),
            removed_lines=int(row["removed_lines"]),
            diff_text_ref=row["diff_text_ref"],
            context_hash=row["context_hash"] or "",
            summary=row["summary"] or "",
            decision_id=row["decision_id"],
            source_event_id=row["source_event_id"],
            created_at=row["created_at"],
        )

    def _item_to_payload(self, item: MemoryItem) -> dict:
        payload = {
            "memory_id": item.memory_id,
            "layer": item.layer,
            "role": item.role,
            "summary": item.summary,
            "source_kind": item.source_kind,
            "source_id": item.source_id,
            "metadata": item.metadata,
            "ordinal": item.ordinal,
            "created_at": item.created_at,
            "promoted_to_journal_uid": item.promoted_to_journal_uid,
        }
        if item.content_ref:
            try:
                payload["content"] = self._blob.get_text(item.content_ref)
            except Exception:
                payload["content"] = ""
        return payload

    def _hunk_to_payload(self, hunk: ChangeHunkRecord) -> dict:
        payload = {
            "hunk_id": hunk.hunk_id,
            "path": hunk.path,
            "summary": hunk.summary,
            "old_start": hunk.old_start,
            "old_count": hunk.old_count,
            "new_start": hunk.new_start,
            "new_count": hunk.new_count,
            "added_lines": hunk.added_lines,
            "removed_lines": hunk.removed_lines,
            "created_at": hunk.created_at,
        }
        try:
            payload["diff_text"] = self._blob.get_text(hunk.diff_text_ref)
        except Exception:
            payload["diff_text"] = ""
        return payload


def _excerpt(text: str, limit: int) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[:limit] + ("..." if len(cleaned) > limit else "")


def _looks_like_json(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[")
