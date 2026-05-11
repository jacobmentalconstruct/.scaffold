"""
FILE: src/core/projections.py
ROLE: ProjectionManager — builds read models from events + state.
WHAT IT DOES: Registry of projection builders, refresh API used by the
              Router after event commit, read API used by UI/agent.
              T1 implements builders for current_sidecar_state and
              contract_status; the rest of the seven day-one projections
              have empty stub builders that just write last_refreshed_at.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

from src.lib.common import now_iso, safe_json_dumps
from src.lib.logging_setup import get_logger
from src.schemas.projection_schema import (
    PROJECTION_NAMES,
    affected_projections,
)


if TYPE_CHECKING:
    from src.components.sqlite_store import Store
    from src.core.envelope import SidecarEnvelope
    from src.core.events import EventStore
    from src.core.graph import Graph
    from src.core.state import SidecarState


log = get_logger("core.projections")


@dataclass
class ProjectionResult:
    name: str
    last_refreshed_at: str
    rows: list[dict]


class ProjectionManager:
    def __init__(self, state: "SidecarState", store: "Store",
                 events: "EventStore", graph: "Graph"):
        self._state = state
        self._store = store
        self._events = events
        self._graph = graph
        self._builders: dict[str, Callable[[], None]] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        self._builders["current_sidecar_state"] = self._build_current_state
        self._builders["contract_status"] = self._build_contract_status
        # Stub builders for other projections (just stamp the timestamp).
        for name in PROJECTION_NAMES:
            if name not in self._builders:
                self._builders[name] = self._stub_builder_for(name)

    # --- public API ---------------------------------------------------

    def list(self) -> list[str]:
        return list(PROJECTION_NAMES)

    def refresh(self, name: str) -> ProjectionResult:
        builder = self._builders.get(name)
        if builder is None:
            raise KeyError(f"unknown projection: {name}")
        builder()
        rows = self._read_rows(name)
        ts = self._read_last_refreshed(name)
        result = ProjectionResult(name=name, last_refreshed_at=ts, rows=rows)
        self._state.set_current_projection(name, {
            "last_refreshed_at": ts,
            "row_count": len(rows),
        })
        log.debug("projection refreshed: %s rows=%d", name, len(rows))
        return result

    def refresh_for(self, envelope: "SidecarEnvelope") -> list[str]:
        names = affected_projections(envelope.operation_intent)
        # Always refresh current_sidecar_state on every event (cheap).
        if "current_sidecar_state" not in names:
            names = names + ("current_sidecar_state",)
        refreshed: list[str] = []
        for name in names:
            try:
                self.refresh(name)
                refreshed.append(name)
            except Exception as e:
                log.error("projection refresh failed: %s -- %s", name, e)
        return refreshed

    def read(self, name: str, query: dict | None = None) -> ProjectionResult:
        rows = self._read_rows(name)
        ts = self._read_last_refreshed(name)
        return ProjectionResult(name=name, last_refreshed_at=ts, rows=rows)

    def refresh_all(self) -> list[str]:
        refreshed = []
        for name in PROJECTION_NAMES:
            try:
                self.refresh(name)
                refreshed.append(name)
            except Exception as e:
                log.error("initial projection refresh failed: %s -- %s", name, e)
        return refreshed

    # --- builders -----------------------------------------------------

    def _build_current_state(self) -> None:
        snap = self._state.snapshot()
        ts = now_iso()
        self._store.execute("DELETE FROM proj_current_sidecar_state;")
        self._store.execute(
            """
            INSERT INTO proj_current_sidecar_state(
                id, project_root, sidecar_root, sidecar_id,
                current_contract_hash, current_contract_acked,
                registered_object_count, registered_tool_count,
                active_task_id, event_log_position,
                agent_status_json, human_ui_status_json, last_refreshed_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                snap["sidecar_root"],
                snap["sidecar_root"],
                snap["sidecar_id"],
                snap.get("current_contract_hash"),
                1 if snap.get("current_contract_acked") else 0,
                snap["registered_object_count"],
                snap["registered_tool_count"],
                snap.get("active_task_id"),
                self._events.total_count(),
                safe_json_dumps(snap.get("agent_status", {})),
                safe_json_dumps(snap.get("human_ui_status", {})),
                ts,
            ),
        )

    def _build_contract_status(self) -> None:
        contract = self._state.current_contract or {}
        ts = now_iso()
        # Recent contract-related events (acknowledge_contract,
        # register_constraint, register_profile, seed_constraints).
        rows = self._store.query(
            """
            SELECT event_id, operation_intent, actor_id, created_at
            FROM events
            WHERE operation_intent IN
                ('acknowledge_contract', 'register_constraint',
                 'register_profile', 'seed_constraints')
            ORDER BY created_at DESC LIMIT 20;
            """
        )
        recent = [
            {
                "event_id": r["event_id"],
                "intent": r["operation_intent"],
                "actor_id": r["actor_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        ack_rows = self._store.query(
            "SELECT actor_id, actor_type, acknowledged_at FROM acknowledgments "
            "WHERE contract_id = ? AND contract_version = ?;",
            (contract.get("contract_id", ""), contract.get("version", "")),
        )
        acks = [
            {"actor_id": r["actor_id"], "actor_type": r["actor_type"],
             "acknowledged_at": r["acknowledged_at"]}
            for r in ack_rows
        ]
        grant_rows = self._store.query(
            "SELECT grant_id, actor_id, operation_intent, elevated_level, "
            "expires_at, single_use, consumed FROM grants WHERE consumed = 0;"
        )
        outstanding = [dict(r) for r in grant_rows]

        self._store.execute("DELETE FROM proj_contract_status;")
        self._store.execute(
            """
            INSERT INTO proj_contract_status(
                id, contract_id, version, text_hash,
                acks_json, outstanding_grants_json, recent_contract_events_json,
                last_refreshed_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                contract.get("contract_id", ""),
                contract.get("version", ""),
                contract.get("text_hash", ""),
                safe_json_dumps(acks),
                safe_json_dumps(outstanding),
                safe_json_dumps(recent),
                ts,
            ),
        )

    def _stub_builder_for(self, name: str) -> Callable[[], None]:
        """Stub: clear the table and stamp last_refreshed_at via meta key.

        Real builders for these projections land in T2+ (project_map,
        journal_timeline, evidence_bag, agent_bootstrap, human_dashboard).
        """
        def build() -> None:
            ts = now_iso()
            self._store.set_meta(f"proj_stub_refreshed_at:{name}", ts)
        return build

    # --- internals ----------------------------------------------------

    def _read_rows(self, name: str) -> list[dict]:
        try:
            rows = self._store.query(f"SELECT * FROM proj_{name};")
            return [dict(r) for r in rows]
        except Exception as e:
            log.warning("could not read projection %s: %s", name, e)
            return []

    def _read_last_refreshed(self, name: str) -> str:
        # Try the table's last_refreshed_at column for single-row projections.
        try:
            row = self._store.query_one(
                f"SELECT last_refreshed_at FROM proj_{name} LIMIT 1;"
            )
            if row and row["last_refreshed_at"]:
                return row["last_refreshed_at"]
        except Exception:
            pass
        # Fall back to the stub meta key.
        meta = self._store.get_meta(f"proj_stub_refreshed_at:{name}")
        return meta or ""
