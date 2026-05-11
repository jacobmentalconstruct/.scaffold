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

from src.lib.common import now_iso, safe_json_dumps  # noqa: F401
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
        self._builders["journal_timeline"] = self._build_journal_timeline
        self._builders["project_map"] = self._build_project_map
        self._builders["human_dashboard"] = self._build_human_dashboard
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

    def _build_journal_timeline(self) -> None:
        """Rebuild proj_journal_timeline from journal_entries.

        Excludes superseded entries (those are still in journal_entries
        but considered prior revisions, not current timeline items).
        """
        ts = now_iso()
        # Check journal_entries exists (T2.1 migration adds it).
        try:
            rows = self._store.query(
                """
                SELECT entry_uid, kind, source, title, body, created_at,
                       status, importance, tags_json, related_path,
                       superseded_by, event_id
                FROM journal_entries
                WHERE superseded_by IS NULL
                ORDER BY created_at DESC;
                """
            )
        except Exception as e:
            log.warning("journal_timeline builder: journal_entries not available yet (%s); skipping", e)
            return

        with self._store.transaction():
            self._store.execute("DELETE FROM proj_journal_timeline;")
            for r in rows:
                body = r["body"] or ""
                excerpt = body[:280] + ("..." if len(body) > 280 else "")
                # Collect any evidence_refs from the creating event.
                evidence_refs_json = "[]"
                if r["event_id"] and r["event_id"] != "PENDING":
                    ev_row = self._store.query_one(
                        "SELECT evidence_refs FROM events WHERE event_id = ?;",
                        (r["event_id"],),
                    )
                    if ev_row and ev_row["evidence_refs"]:
                        evidence_refs_json = ev_row["evidence_refs"]
                self._store.execute(
                    """
                    INSERT INTO proj_journal_timeline(
                        entry_uid, kind, source, title, body_excerpt,
                        created_at, status, importance, tags_json,
                        related_path, evidence_refs_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        r["entry_uid"], r["kind"], r["source"], r["title"],
                        excerpt, r["created_at"], r["status"],
                        int(r["importance"]), r["tags_json"] or "[]",
                        r["related_path"], evidence_refs_json,
                    ),
                )
        # Stamp a meta key so _read_last_refreshed can find it (multi-row
        # tables don't have a single last_refreshed_at column).
        self._store.set_meta(f"proj_stub_refreshed_at:journal_timeline", ts)

    def _build_project_map(self) -> None:
        """Rebuild proj_project_map from project_index.

        Joins journal_entries (citing files via related_path) and the
        events table (for last observation) to produce annotated rows.
        """
        ts = now_iso()
        try:
            rows = self._store.query(
                """
                SELECT path, kind, size_bytes, content_hash, last_observed_at
                FROM project_index
                ORDER BY path;
                """
            )
        except Exception as e:
            log.warning("project_map builder: project_index not available yet (%s); skipping", e)
            return

        with self._store.transaction():
            self._store.execute("DELETE FROM proj_project_map;")
            for r in rows:
                cite_row = self._store.query_one(
                    "SELECT COUNT(*) AS n FROM journal_entries "
                    "WHERE related_path = ? AND superseded_by IS NULL;",
                    (r["path"],),
                )
                cite_count = int(cite_row["n"]) if cite_row else 0
                # Evidence count placeholder: how many events touched this path
                # via evidence_refs? T2.3 will wire this through evidence_manager.
                evidence_count = 0
                self._store.execute(
                    """
                    INSERT INTO proj_project_map(
                        path, kind, size_bytes, content_hash,
                        last_observed_at, journal_cite_count, evidence_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        r["path"], r["kind"], r["size_bytes"], r["content_hash"],
                        r["last_observed_at"], cite_count, evidence_count,
                    ),
                )
        self._store.set_meta("proj_stub_refreshed_at:project_map", ts)

    def _build_human_dashboard(self) -> None:
        """Rebuild proj_human_dashboard.

        T2.2 fills: pending_approvals (empty until T4), recent_journal,
        unresolved_issues, current_tranche_scope (placeholder until we have
        a current-tranche notion in journal_meta), last_scan_summary.
        """
        ts = now_iso()

        # Recent journal: last 10 non-superseded entries.
        recent_rows = []
        try:
            recent_rows = self._store.query(
                """
                SELECT entry_uid, kind, title, status, importance, created_at
                FROM journal_entries
                WHERE superseded_by IS NULL
                ORDER BY created_at DESC LIMIT 10;
                """
            )
        except Exception:
            recent_rows = []
        recent_journal = [dict(r) for r in recent_rows]

        unresolved_rows = []
        try:
            unresolved_rows = self._store.query(
                """
                SELECT entry_uid, kind, title, importance, created_at
                FROM journal_entries
                WHERE superseded_by IS NULL AND kind IN ('issue', 'todo') AND status = 'open'
                ORDER BY importance DESC, created_at DESC LIMIT 20;
                """
            )
        except Exception:
            unresolved_rows = []
        unresolved_issues = [dict(r) for r in unresolved_rows]

        # Last scan summary: most recent scan row.
        last_scan = {}
        try:
            row = self._store.query_one(
                "SELECT scan_id, started_at, finished_at, file_count, "
                "directory_count, added_count, modified_count, removed_count, "
                "unchanged_count, status, event_id "
                "FROM scans ORDER BY started_at DESC LIMIT 1;"
            )
            if row:
                last_scan = dict(row)
        except Exception:
            last_scan = {}

        # Current tranche scope: read from meta if set; otherwise empty.
        tranche_scope = {}
        scope_meta = self._store.get_meta("current_tranche_scope")
        if scope_meta:
            try:
                tranche_scope = json.loads(scope_meta)
            except Exception:
                tranche_scope = {"raw": scope_meta}

        self._store.execute("DELETE FROM proj_human_dashboard;")
        self._store.execute(
            """
            INSERT INTO proj_human_dashboard(
                id, pending_approvals_json, recent_journal_json,
                unresolved_issues_json, current_tranche_scope_json,
                last_scan_summary_json, last_refreshed_at
            ) VALUES (1, ?, ?, ?, ?, ?, ?);
            """,
            (
                safe_json_dumps([]),  # pending approvals — T4
                safe_json_dumps(recent_journal),
                safe_json_dumps(unresolved_issues),
                safe_json_dumps(tranche_scope),
                safe_json_dumps(last_scan),
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
