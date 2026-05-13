"""
FILE: src/managers/human_approval_manager.py
ROLE: Approval queue + grant issuance for authority elevation requests.
WHAT IT DOES: Records pending requests, approves/rejects them through the
              envelope chain, and creates narrow grants consumed by later
              tool invocations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.lib.common import gen_id, now_iso, safe_json_dumps
from src.lib.logging_setup import get_logger


log = get_logger("managers.human_approval")


@dataclass(frozen=True)
class ApprovalRequest:
    request_id: str
    actor_id: str
    session_id: str | None
    source_channel: str
    requested_level: str
    operation_intent: str
    scope_pattern: dict
    summary: str
    justification: str
    status: str
    requested_at: str
    decided_at: str | None
    decided_by: str | None
    decision_reason: str
    grant_id: str | None
    event_id: str


class HumanApprovalManager:
    def __init__(self, store, blob_store):
        self._store = store
        self._blob = blob_store

    def handle_request(self, envelope, state):
        request = self._read_payload(envelope)
        requested_level = str(request.get("requested_level", "")).strip()
        operation_intent = str(request.get("operation_intent", "tool_invoked")).strip() or "tool_invoked"
        summary = str(request.get("summary", "")).strip()
        justification = str(request.get("justification", "")).strip()
        scope_pattern = request.get("scope_pattern") or {}
        source_channel = str(request.get("source_channel", "unknown")).strip() or "unknown"
        session_id = request.get("session_id")

        if requested_level not in ("Sandbox Execute", "Apply", "Export"):
            raise ValueError("requested_level must be one of Sandbox Execute, Apply, Export")
        if not summary:
            raise ValueError("request_authority_elevation requires summary")
        if not justification:
            raise ValueError("request_authority_elevation requires justification")
        if not isinstance(scope_pattern, dict):
            raise ValueError("scope_pattern must be an object")

        request_id = gen_id("approval_")
        now = now_iso()
        self._store.execute(
            """
            INSERT INTO approval_requests(
                request_id, actor_id, session_id, source_channel,
                requested_level, operation_intent, scope_pattern_json,
                summary, justification, status, requested_at,
                decided_at, decided_by, decision_reason, grant_id, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, NULL, NULL, '', NULL, 'PENDING');
            """,
            (
                request_id,
                envelope.actor_id,
                session_id,
                source_channel,
                requested_level,
                operation_intent,
                safe_json_dumps(scope_pattern),
                summary,
                justification,
                now,
            ),
        )
        response_ref = self._blob.put_json(
            {
                "request_id": request_id,
                "status": "pending",
                "requested_level": requested_level,
                "operation_intent": operation_intent,
            }
        )
        log.info("approval request created: request_id=%s actor=%s", request_id, envelope.actor_id)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def handle_approve(self, envelope, state):
        request = self._read_payload(envelope)
        request_id = str(request.get("request_id", "")).strip()
        if not request_id:
            raise ValueError("approve_authority_request requires request_id")
        record = self.get(request_id)
        if record is None:
            raise KeyError(f"no such approval request: {request_id}")
        if record.status != "pending":
            raise RuntimeError(f"approval request {request_id} is already {record.status}")

        expires_minutes = int(request.get("expires_minutes", 60))
        single_use = bool(request.get("single_use", True))
        decision_reason = str(request.get("decision_reason", "")).strip()
        grant_id = gen_id("grant_")
        granted_at = now_iso()
        expires_at = _expires_at(granted_at, expires_minutes) if expires_minutes > 0 else None

        self._store.execute(
            """
            INSERT INTO grants(
                grant_id, actor_id, operation_intent, scope_pattern,
                elevated_level, granted_by, granted_at, expires_at,
                single_use, consumed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
            """,
            (
                grant_id,
                record.actor_id,
                record.operation_intent,
                safe_json_dumps(record.scope_pattern),
                record.requested_level,
                envelope.actor_id,
                granted_at,
                expires_at,
                1 if single_use else 0,
            ),
        )
        self._store.execute(
            """
            UPDATE approval_requests
            SET status = 'approved', decided_at = ?, decided_by = ?,
                decision_reason = ?, grant_id = ?
            WHERE request_id = ?;
            """,
            (granted_at, envelope.actor_id, decision_reason, grant_id, request_id),
        )
        response_ref = self._blob.put_json(
            {
                "request_id": request_id,
                "status": "approved",
                "grant_id": grant_id,
                "expires_at": expires_at,
                "single_use": single_use,
            }
        )
        log.info("approval request approved: request_id=%s grant_id=%s", request_id, grant_id)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def handle_reject(self, envelope, state):
        request = self._read_payload(envelope)
        request_id = str(request.get("request_id", "")).strip()
        if not request_id:
            raise ValueError("reject_authority_request requires request_id")
        record = self.get(request_id)
        if record is None:
            raise KeyError(f"no such approval request: {request_id}")
        if record.status != "pending":
            raise RuntimeError(f"approval request {request_id} is already {record.status}")

        decided_at = now_iso()
        decision_reason = str(request.get("decision_reason", "")).strip()
        self._store.execute(
            """
            UPDATE approval_requests
            SET status = 'rejected', decided_at = ?, decided_by = ?, decision_reason = ?
            WHERE request_id = ?;
            """,
            (decided_at, envelope.actor_id, decision_reason, request_id),
        )
        response_ref = self._blob.put_json(
            {"request_id": request_id, "status": "rejected", "decision_reason": decision_reason}
        )
        log.info("approval request rejected: request_id=%s", request_id)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def finalize_request_event_id(self, sealed) -> None:
        self._finalize_event_id_from_payload(sealed, "approval_requests", "request_id")

    def pending(self, limit: int = 100) -> list[ApprovalRequest]:
        rows = self._store.query(
            """
            SELECT * FROM approval_requests
            WHERE status = 'pending'
            ORDER BY requested_at ASC LIMIT ?;
            """,
            (limit,),
        )
        return [self._row_to_request(row) for row in rows]

    def recent(self, limit: int = 100) -> list[ApprovalRequest]:
        rows = self._store.query(
            "SELECT * FROM approval_requests ORDER BY requested_at DESC LIMIT ?;",
            (limit,),
        )
        return [self._row_to_request(row) for row in rows]

    def get(self, request_id: str) -> ApprovalRequest | None:
        row = self._store.query_one("SELECT * FROM approval_requests WHERE request_id = ?;", (request_id,))
        return self._row_to_request(row) if row else None

    def summary(self) -> dict:
        row = self._store.query_one(
            """
            SELECT
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved_count,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count
            FROM approval_requests;
            """
        )
        return {
            "pending_count": int(row["pending_count"] or 0) if row else 0,
            "approved_count": int(row["approved_count"] or 0) if row else 0,
            "rejected_count": int(row["rejected_count"] or 0) if row else 0,
        }

    def _finalize_event_id_from_payload(self, sealed, table: str, key_name: str) -> None:
        if not sealed.payload_ref:
            return
        try:
            response = self._blob.get_json(sealed.payload_ref)
        except Exception as exc:
            log.error("approval finalize failed: %s", exc)
            return
        key_value = response.get(key_name)
        if not key_value:
            return
        self._store.execute(
            f"UPDATE {table} SET event_id = ? WHERE {key_name} = ? AND event_id = 'PENDING';",
            (sealed.event_id, key_value),
        )

    def _read_payload(self, envelope) -> dict:
        if not envelope.payload_ref:
            return {}
        try:
            return self._blob.get_json(envelope.payload_ref)
        except Exception as exc:
            raise ValueError(f"cannot read payload from blob {envelope.payload_ref}: {exc}")

    @staticmethod
    def _row_to_request(row) -> ApprovalRequest:
        return ApprovalRequest(
            request_id=row["request_id"],
            actor_id=row["actor_id"],
            session_id=row["session_id"],
            source_channel=row["source_channel"] or "",
            requested_level=row["requested_level"],
            operation_intent=row["operation_intent"],
            scope_pattern=json.loads(row["scope_pattern_json"] or "{}"),
            summary=row["summary"] or "",
            justification=row["justification"] or "",
            status=row["status"],
            requested_at=row["requested_at"],
            decided_at=row["decided_at"],
            decided_by=row["decided_by"],
            decision_reason=row["decision_reason"] or "",
            grant_id=row["grant_id"],
            event_id=row["event_id"],
        )


def _expires_at(started_at: str, minutes: int) -> str | None:
    if minutes <= 0:
        return None
    from datetime import datetime, timedelta, timezone

    base = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    return (base + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
