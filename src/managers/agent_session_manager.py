"""
FILE: src/managers/agent_session_manager.py
ROLE: Durable MCP/local agent session bookkeeping.
WHAT IT DOES: Tracks actor identity, channel, and last-seen status so the
              human UI and handoff surfaces can show who is connected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.lib.common import gen_id, now_iso, safe_json_dumps
from src.lib.logging_setup import get_logger


log = get_logger("managers.agent_sessions")


@dataclass(frozen=True)
class AgentSession:
    session_id: str
    actor_id: str
    channel: str
    client_name: str
    status: str
    authority_level: str
    started_at: str
    last_seen_at: str
    last_envelope_id: str | None
    metadata: dict


class AgentSessionManager:
    def __init__(self, store):
        self._store = store

    def touch(
        self,
        *,
        actor_id: str,
        channel: str,
        client_name: str = "",
        authority_level: str = "Propose",
        last_envelope_id: str | None = None,
        metadata: dict | None = None,
    ) -> AgentSession:
        self._ensure_actor_authority_row(actor_id, authority_level)
        row = self._store.query_one(
            """
            SELECT * FROM agent_sessions
            WHERE actor_id = ? AND channel = ? AND client_name = ? AND status = 'active'
            ORDER BY started_at DESC LIMIT 1;
            """,
            (actor_id, channel, client_name),
        )
        now = now_iso()
        payload = safe_json_dumps(metadata or {})
        if row:
            self._store.execute(
                """
                UPDATE agent_sessions
                SET last_seen_at = ?, authority_level = ?, last_envelope_id = ?, metadata_json = ?
                WHERE session_id = ?;
                """,
                (now, authority_level, last_envelope_id, payload, row["session_id"]),
            )
            return self.get(row["session_id"])

        session_id = gen_id("session_")
        self._store.execute(
            """
            INSERT INTO agent_sessions(
                session_id, actor_id, channel, client_name, status,
                authority_level, started_at, last_seen_at, last_envelope_id, metadata_json
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?);
            """,
            (session_id, actor_id, channel, client_name, authority_level, now, now, last_envelope_id, payload),
        )
        log.info("agent session touched: actor=%s channel=%s client=%s", actor_id, channel, client_name)
        return self.get(session_id)

    def _ensure_actor_authority_row(self, actor_id: str, authority_level: str) -> None:
        row = self._store.query_one(
            """
            SELECT actor_id FROM authorities
            WHERE actor_id = ? AND (effective_until IS NULL OR effective_until > ?)
            LIMIT 1;
            """,
            (actor_id, now_iso()),
        )
        if row:
            return
        self._store.execute(
            """
            INSERT INTO authorities(actor_id, base_level, granted_by, effective_from, effective_until)
            VALUES (?, ?, ?, ?, NULL);
            """,
            (actor_id, authority_level, "system:session_bootstrap", now_iso()),
        )
        log.info("authority row ensured for actor=%s level=%s", actor_id, authority_level)

    def get(self, session_id: str) -> AgentSession | None:
        row = self._store.query_one("SELECT * FROM agent_sessions WHERE session_id = ?;", (session_id,))
        return self._row_to_session(row) if row else None

    def active(self, limit: int = 20) -> list[AgentSession]:
        rows = self._store.query(
            """
            SELECT * FROM agent_sessions
            WHERE status = 'active'
            ORDER BY last_seen_at DESC LIMIT ?;
            """,
            (limit,),
        )
        return [self._row_to_session(row) for row in rows]

    def list_recent(self, limit: int = 50) -> list[AgentSession]:
        rows = self._store.query(
            "SELECT * FROM agent_sessions ORDER BY last_seen_at DESC LIMIT ?;",
            (limit,),
        )
        return [self._row_to_session(row) for row in rows]

    @staticmethod
    def _row_to_session(row) -> AgentSession:
        return AgentSession(
            session_id=row["session_id"],
            actor_id=row["actor_id"],
            channel=row["channel"],
            client_name=row["client_name"] or "",
            status=row["status"],
            authority_level=row["authority_level"] or "Propose",
            started_at=row["started_at"],
            last_seen_at=row["last_seen_at"],
            last_envelope_id=row["last_envelope_id"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
