"""
FILE: src/core/events.py
ROLE: EventStore — appends every accepted envelope as an event row.
WHAT IT DOES: Validates, assigns event_id and (stream, stream_key, sequence),
              writes the row in a transaction, returns the envelope with
              event_id populated.
"""

from __future__ import annotations

import json
from typing import Iterable

from src.components.sqlite_store import Store
from src.core.envelope import SidecarEnvelope
from src.lib.common import gen_event_id, now_iso, safe_json_dumps
from src.lib.logging_setup import get_logger
from src.schemas.event_schema import (
    stream_for,
    stream_key_for,
    validate_event_row,
)


log = get_logger("core.events")


class EventStore:
    def __init__(self, store: Store):
        self._store = store

    # --- write ---------------------------------------------------------

    def append(self, envelope: SidecarEnvelope) -> SidecarEnvelope:
        """Append an accepted envelope to the event log; return updated envelope."""
        env_dict = envelope.to_dict()
        stream = stream_for(env_dict["operation_intent"])
        key = stream_key_for(env_dict)
        event_id = gen_event_id()

        sealed = envelope.with_event_id(event_id).with_status("accepted")
        sealed_dict = sealed.to_dict()

        with self._store.transaction():
            sequence = self._next_sequence(stream, key)
            row = {
                "event_id": event_id,
                "stream": stream,
                "stream_key": key,
                "sequence": sequence,
                "envelope_version": sealed_dict["envelope_version"],
                "operation_intent": sealed_dict["operation_intent"],
                "actor_id": sealed_dict["actor_id"],
                "project_id": sealed_dict["project_id"],
                "sidecar_id": sealed_dict["sidecar_id"],
                "correlation_id": sealed_dict["correlation_id"],
                "causation_id": sealed_dict["causation_id"] or None,
                "contract_refs": safe_json_dumps(sealed_dict["contract_refs"]),
                "payload_ref": sealed_dict["payload_ref"] or None,
                "evidence_refs": safe_json_dumps(sealed_dict["evidence_refs"]),
                "relation_refs": safe_json_dumps(sealed_dict["relation_refs"]),
                "status": "accepted",
                "created_at": now_iso(),
                "envelope_blob": safe_json_dumps(sealed_dict).encode("utf-8"),
            }
            errors = validate_event_row(row)
            if errors:
                raise ValueError(f"event row invalid: {errors}")
            self._store.execute(
                """
                INSERT INTO events(
                    event_id, stream, stream_key, sequence,
                    envelope_version, operation_intent, actor_id,
                    project_id, sidecar_id, correlation_id, causation_id,
                    contract_refs, payload_ref, evidence_refs, relation_refs,
                    status, created_at, envelope_blob
                ) VALUES (
                    :event_id, :stream, :stream_key, :sequence,
                    :envelope_version, :operation_intent, :actor_id,
                    :project_id, :sidecar_id, :correlation_id, :causation_id,
                    :contract_refs, :payload_ref, :evidence_refs, :relation_refs,
                    :status, :created_at, :envelope_blob
                );
                """,
                row,
            )
        log.info(
            "event appended: %s stream=%s key=%s seq=%d intent=%s actor=%s",
            event_id, stream, key, sequence,
            sealed_dict["operation_intent"], sealed_dict["actor_id"],
        )
        return sealed

    # --- read ----------------------------------------------------------

    def read(self, event_id: str) -> SidecarEnvelope | None:
        row = self._store.query_one(
            "SELECT envelope_blob FROM events WHERE event_id = ?;", (event_id,)
        )
        if row is None:
            return None
        body = bytes(row["envelope_blob"]) if row["envelope_blob"] is not None else b"{}"
        return SidecarEnvelope.from_dict(json.loads(body.decode("utf-8")))

    def iter(
        self,
        stream: str | None = None,
        stream_key: str | None = None,
        since_sequence: int | None = None,
        limit: int | None = None,
    ) -> Iterable[SidecarEnvelope]:
        sql = "SELECT envelope_blob FROM events"
        clauses: list[str] = []
        params: list = []
        if stream is not None:
            clauses.append("stream = ?")
            params.append(stream)
        if stream_key is not None:
            clauses.append("stream_key = ?")
            params.append(stream_key)
        if since_sequence is not None:
            clauses.append("sequence > ?")
            params.append(since_sequence)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC, sequence ASC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self._store.query(sql + ";", params)
        return [
            SidecarEnvelope.from_dict(json.loads(bytes(r["envelope_blob"]).decode("utf-8")))
            for r in rows
            if r["envelope_blob"] is not None
        ]

    def head(self, stream: str, stream_key: str | None = None) -> int:
        if stream_key is None:
            row = self._store.query_one(
                "SELECT MAX(sequence) AS s FROM events WHERE stream = ?;",
                (stream,),
            )
        else:
            row = self._store.query_one(
                "SELECT MAX(sequence) AS s FROM events WHERE stream = ? AND stream_key = ?;",
                (stream, stream_key),
            )
        return int(row["s"]) if row and row["s"] is not None else 0

    def total_count(self) -> int:
        row = self._store.query_one("SELECT COUNT(*) AS n FROM events;")
        return int(row["n"]) if row else 0

    def recent(self, limit: int = 20) -> list[SidecarEnvelope]:
        rows = self._store.query(
            "SELECT envelope_blob FROM events ORDER BY created_at DESC, sequence DESC LIMIT ?;",
            (limit,),
        )
        return [
            SidecarEnvelope.from_dict(json.loads(bytes(r["envelope_blob"]).decode("utf-8")))
            for r in rows
            if r["envelope_blob"] is not None
        ]

    # --- internals -----------------------------------------------------

    def _next_sequence(self, stream: str, stream_key: str) -> int:
        row = self._store.query_one(
            "SELECT MAX(sequence) AS s FROM events WHERE stream = ? AND stream_key = ?;",
            (stream, stream_key),
        )
        last = int(row["s"]) if row and row["s"] is not None else 0
        return last + 1
