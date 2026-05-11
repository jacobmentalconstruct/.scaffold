"""
FILE: src/managers/evidence_manager.py
ROLE: Owner of the evidence table — CAS-backed evidence items attached to
      objects (journal entries, tasks, patch proposals, etc.).
WHAT IT DOES (T2.3): lightweight — handle_attach + handle_verify envelope
                     handlers. The Bag of Evidence / sliding-window
                     overflow logic is deferred until we run our own
                     local agent (DP1 deferred).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.lib.common import gen_id, now_iso
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.blob_store import BlobStore
    from src.components.sqlite_store import Store
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState


log = get_logger("managers.evidence")


VALID_KINDS = (
    "file_excerpt", "tool_output", "diff", "screenshot",
    "citation", "external", "scan_summary", "git_observation",
)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    hash: str
    kind: str
    summary: str
    source_event: str | None
    source_path: str | None
    source_line_range: str | None
    attached_to_object: str | None
    attached_to_type: str | None
    status: str
    created_at: str
    verified_at: str | None
    actor_id: str


class EvidenceManager:
    def __init__(self, store: "Store", blob_store: "BlobStore"):
        self._store = store
        self._blob = blob_store

    # ===== envelope handlers ===========================================

    def handle_attach(self, envelope: "SidecarEnvelope", state: "SidecarState") -> "SidecarEnvelope":
        """Handler for attach_evidence.

        Payload: {hash, kind, summary, source_path?, source_line_range?,
                  attached_to_object?, attached_to_type?, body_inline?}

        If body_inline is provided AND hash is empty, this method will hash
        the body and store it in blob_store. Otherwise we trust the provided
        hash references an existing blob (verified on first use).
        """
        if not envelope.payload_ref:
            raise ValueError("attach_evidence requires payload_ref")
        request = self._blob.get_json(envelope.payload_ref)

        kind = request.get("kind", "external")
        if kind not in VALID_KINDS:
            log.warning("evidence kind %r not in standard set; allowing", kind)

        body_inline = request.get("body_inline")
        body_hash = request.get("hash") or ""
        content_type = request.get("content_type", "text/plain")

        if body_inline is not None and not body_hash:
            if isinstance(body_inline, (dict, list)):
                body_hash = self._blob.put_json(body_inline)
            elif isinstance(body_inline, bytes):
                body_hash = self._blob.put(body_inline, content_type=content_type)
            else:
                body_hash = self._blob.put_text(str(body_inline), content_type=content_type)

        if not body_hash:
            raise ValueError("attach_evidence needs either 'hash' or 'body_inline'")

        # Confirm the hash exists in blob_store; if not, refuse.
        if not self._blob.exists(body_hash):
            raise ValueError(f"evidence hash {body_hash!r} not present in blob_store")

        evidence_id = gen_id("evd_")
        now = now_iso()

        self._store.execute(
            """
            INSERT INTO evidence(
                evidence_id, hash, kind, summary,
                source_event, source_path, source_line_range,
                attached_to_object, attached_to_type,
                status, created_at, verified_at, actor_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'attached', ?, NULL, ?);
            """,
            (
                evidence_id, body_hash, kind, request.get("summary", ""),
                None, request.get("source_path"),
                request.get("source_line_range"),
                request.get("attached_to_object"),
                request.get("attached_to_type"),
                now, envelope.actor_id,
            ),
        )

        response = {
            "evidence_id": evidence_id,
            "hash": body_hash,
            "kind": kind,
            "attached_to_object": request.get("attached_to_object"),
            "created_at": now,
        }
        response_ref = self._blob.put_json(response)
        log.info("evidence attached: id=%s kind=%s hash=%s...", evidence_id, kind, body_hash[:12])
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def handle_verify(self, envelope: "SidecarEnvelope", state: "SidecarState") -> "SidecarEnvelope":
        """Handler for verify_evidence. Payload: {evidence_id} → verifies the blob."""
        request = self._blob.get_json(envelope.payload_ref) if envelope.payload_ref else {}
        evidence_id = request.get("evidence_id")
        if not evidence_id:
            raise ValueError("verify_evidence requires evidence_id")
        record = self.get(evidence_id)
        if record is None:
            raise KeyError(f"no such evidence: {evidence_id}")
        ok = self._blob.verify(record.hash)
        now = now_iso()
        new_status = "verified" if ok else "corrupted"
        self._store.execute(
            "UPDATE evidence SET status = ?, verified_at = ? WHERE evidence_id = ?;",
            (new_status, now, evidence_id),
        )
        response = {
            "evidence_id": evidence_id,
            "hash": record.hash,
            "verified": ok,
            "status": new_status,
            "verified_at": now,
        }
        response_ref = self._blob.put_json(response)
        log.info("evidence verified: %s ok=%s", evidence_id, ok)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    # ===== reads =======================================================

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        row = self._store.query_one("SELECT * FROM evidence WHERE evidence_id = ?;", (evidence_id,))
        return _row_to_record(row) if row else None

    def for_object(self, object_id: str) -> list[EvidenceRecord]:
        rows = self._store.query(
            "SELECT * FROM evidence WHERE attached_to_object = ? ORDER BY created_at DESC;",
            (object_id,),
        )
        return [_row_to_record(r) for r in rows]

    def recent(self, limit: int = 50) -> list[EvidenceRecord]:
        rows = self._store.query(
            "SELECT * FROM evidence ORDER BY created_at DESC LIMIT ?;", (limit,)
        )
        return [_row_to_record(r) for r in rows]

    def count(self) -> int:
        row = self._store.query_one("SELECT COUNT(*) AS n FROM evidence;")
        return int(row["n"]) if row else 0


def _row_to_record(row) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=row["evidence_id"],
        hash=row["hash"],
        kind=row["kind"],
        summary=row["summary"] or "",
        source_event=row["source_event"],
        source_path=row["source_path"],
        source_line_range=row["source_line_range"],
        attached_to_object=row["attached_to_object"],
        attached_to_type=row["attached_to_type"],
        status=row["status"],
        created_at=row["created_at"],
        verified_at=row["verified_at"],
        actor_id=row["actor_id"],
    )
