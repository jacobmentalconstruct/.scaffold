"""
FILE: src/managers/run_trace_manager.py
ROLE: Durable runtime trace persistence for the local sidecar agent.
WHAT IT DOES: Stores run, round, event, touched-path, artifact-link, and
              claim-grounding records so local-agent execution becomes a
              first-class temporal object instead of an opaque process.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.lib.common import gen_id, now_iso, safe_json_dumps


RUN_STATUSES = (
    "created",
    "preflight_failed",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "stopped",
    "retrying",
    "superseded",
)
ROUND_STATUSES = (
    "started",
    "model_calling",
    "tool_calling",
    "waiting_approval",
    "completed",
    "failed",
    "stopped",
)
EVENT_STATUSES = ("started", "completed", "failed", "denied", "blocked", "skipped")
TOUCH_STATUSES = ("observed", "proposed", "applied", "failed", "rejected")


@dataclass(frozen=True)
class LocalAgentRun:
    run_id: str
    session_id: str | None
    actor_id: str
    model: str
    status: str
    authority_level: str
    task_summary: str
    started_at: str
    ended_at: str | None
    final_summary: str
    final_message: str
    recovery_class: str
    retryable: bool
    operator_hint: str
    retried_from_run_id: str | None
    last_round_index: int
    last_runtime_event_type: str
    journal_entry_uid: str | None
    approval_request_id: str | None
    approval_grant_id: str | None
    config_snapshot: dict
    metadata: dict


class RunTraceManager:
    def __init__(self, store, recovery_manager):
        self._store = store
        self._recovery = recovery_manager

    def start_run(
        self,
        *,
        run_id: str,
        session_id: str | None,
        actor_id: str,
        model: str,
        task_summary: str,
        authority_level: str,
        config_snapshot: dict,
        status: str = "created",
        retried_from_run_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        self._store.execute(
            """
            INSERT INTO local_agent_runs(
                run_id, session_id, actor_id, model, status, authority_level,
                task_summary, started_at, ended_at, final_summary, final_message,
                recovery_class, retryable, operator_hint, retried_from_run_id,
                last_round_index, last_runtime_event_type, journal_entry_uid,
                approval_request_id, approval_grant_id, config_snapshot_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, '', '', '', 0, '', ?, 0, '', NULL, NULL, NULL, ?, ?);
            """,
            (
                run_id, session_id, actor_id, model, status, authority_level,
                task_summary, now_iso(), retried_from_run_id,
                safe_json_dumps(config_snapshot),
                safe_json_dumps(metadata or {}),
            ),
        )

    def update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        final_summary: str | None = None,
        final_message: str | None = None,
        recovery_class: str | None = None,
        retryable: bool | None = None,
        operator_hint: str | None = None,
        last_round_index: int | None = None,
        last_runtime_event_type: str | None = None,
        journal_entry_uid: str | None = None,
        approval_request_id: str | None = None,
        approval_grant_id: str | None = None,
        ended: bool = False,
        metadata_patch: dict | None = None,
    ) -> None:
        row = self._store.query_one("SELECT metadata_json FROM local_agent_runs WHERE run_id = ?;", (run_id,))
        metadata = json.loads(row["metadata_json"] or "{}") if row else {}
        if metadata_patch:
            metadata.update(metadata_patch)
        self._store.execute(
            """
            UPDATE local_agent_runs
            SET status = COALESCE(?, status),
                final_summary = COALESCE(?, final_summary),
                final_message = COALESCE(?, final_message),
                recovery_class = COALESCE(?, recovery_class),
                retryable = COALESCE(?, retryable),
                operator_hint = COALESCE(?, operator_hint),
                last_round_index = COALESCE(?, last_round_index),
                last_runtime_event_type = COALESCE(?, last_runtime_event_type),
                journal_entry_uid = COALESCE(?, journal_entry_uid),
                approval_request_id = COALESCE(?, approval_request_id),
                approval_grant_id = COALESCE(?, approval_grant_id),
                ended_at = CASE WHEN ? = 1 THEN ? ELSE ended_at END,
                metadata_json = ?
            WHERE run_id = ?;
            """,
            (
                status, final_summary, final_message, recovery_class,
                1 if retryable else 0 if retryable is False else None,
                operator_hint, last_round_index, last_runtime_event_type,
                journal_entry_uid, approval_request_id, approval_grant_id,
                1 if ended else 0, now_iso(), safe_json_dumps(metadata), run_id,
            ),
        )

    def start_round(self, *, run_id: str, round_index: int, input_summary: str, status: str = "started", metadata: dict | None = None) -> str:
        round_id = gen_id("round_")
        self._store.execute(
            """
            INSERT INTO local_agent_run_rounds(
                round_id, run_id, round_index, status, input_summary, output_summary,
                started_at, ended_at, recovery_class, metadata_json
            ) VALUES (?, ?, ?, ?, ?, '', ?, NULL, '', ?);
            """,
            (round_id, run_id, round_index, status, input_summary, now_iso(), safe_json_dumps(metadata or {})),
        )
        self.update_run(run_id, last_round_index=round_index)
        return round_id

    def finish_round(self, round_id: str, *, status: str, output_summary: str = "", recovery_class: str = "", metadata_patch: dict | None = None) -> None:
        row = self._store.query_one("SELECT metadata_json FROM local_agent_run_rounds WHERE round_id = ?;", (round_id,))
        metadata = json.loads(row["metadata_json"] or "{}") if row else {}
        if metadata_patch:
            metadata.update(metadata_patch)
        self._store.execute(
            """
            UPDATE local_agent_run_rounds
            SET status = ?, output_summary = ?, ended_at = ?, recovery_class = ?, metadata_json = ?
            WHERE round_id = ?;
            """,
            (status, output_summary, now_iso(), recovery_class, safe_json_dumps(metadata), round_id),
        )

    def record_runtime_event(
        self,
        *,
        run_id: str,
        event_type: str,
        status: str,
        summary: str,
        round_id: str | None = None,
        recovery_class: str = "",
        linked_event_id: str | None = None,
        linked_tool_invocation_id: str | None = None,
        linked_approval_request_id: str | None = None,
        linked_approval_grant_id: str | None = None,
        metadata: dict | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> str:
        runtime_event_id = gen_id("rtev_")
        self._store.execute(
            """
            INSERT INTO local_agent_runtime_events(
                runtime_event_id, run_id, round_id, event_type, status, summary,
                recovery_class, started_at, ended_at, linked_event_id, linked_tool_invocation_id,
                linked_approval_request_id, linked_approval_grant_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                runtime_event_id, run_id, round_id, event_type, status, summary,
                recovery_class, started_at or now_iso(), ended_at,
                linked_event_id, linked_tool_invocation_id, linked_approval_request_id, linked_approval_grant_id,
                safe_json_dumps(metadata or {}),
            ),
        )
        self.update_run(run_id, last_runtime_event_type=event_type)
        return runtime_event_id

    def record_touched_path(
        self,
        *,
        run_id: str,
        path: str,
        touch_type: str,
        status: str,
        round_id: str | None = None,
        linked_hunk_id: str | None = None,
        linked_evidence_id: str | None = None,
        linked_tool_invocation_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        touch_id = gen_id("touch_")
        self._store.execute(
            """
            INSERT INTO local_agent_run_touched_paths(
                touch_id, run_id, round_id, path, touch_type, status,
                linked_hunk_id, linked_evidence_id, linked_tool_invocation_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                touch_id, run_id, round_id, path, touch_type, status,
                linked_hunk_id, linked_evidence_id, linked_tool_invocation_id,
                safe_json_dumps(metadata or {}), now_iso(),
            ),
        )
        return touch_id

    def link_artifact(
        self,
        *,
        run_id: str,
        link_kind: str,
        link_ref: str,
        relation: str,
        round_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        link_id = gen_id("lnk_")
        self._store.execute(
            """
            INSERT INTO local_agent_run_links(
                link_id, run_id, round_id, link_kind, link_ref, relation, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (link_id, run_id, round_id, link_kind, link_ref, relation, now_iso(), safe_json_dumps(metadata or {})),
        )
        return link_id

    def record_claim_grounding(
        self,
        *,
        run_id: str,
        claim_id: str,
        claim_text: str,
        grounding_kind: str,
        grounding_ref: str,
        grounding_role: str,
        round_id: str | None = None,
        runtime_event_id: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        claim_grounding_id = gen_id("cg_")
        self._store.execute(
            """
            INSERT INTO local_agent_claim_grounding(
                claim_grounding_id, run_id, claim_id, claim_text, grounding_kind,
                grounding_ref, grounding_role, round_id, runtime_event_id, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                claim_grounding_id, run_id, claim_id, claim_text, grounding_kind,
                grounding_ref, grounding_role, round_id, runtime_event_id, now_iso(), safe_json_dumps(metadata or {}),
            ),
        )
        return claim_grounding_id

    def get_run(self, run_id: str) -> LocalAgentRun | None:
        row = self._store.query_one("SELECT * FROM local_agent_runs WHERE run_id = ?;", (run_id,))
        return self._row_to_run(row) if row else None

    def list_runs(self, *, limit: int = 20) -> list[LocalAgentRun]:
        rows = self._store.query("SELECT * FROM local_agent_runs ORDER BY started_at DESC LIMIT ?;", (limit,))
        return [self._row_to_run(row) for row in rows]

    def get_run_rounds(self, run_id: str) -> list[dict]:
        rows = self._store.query(
            "SELECT * FROM local_agent_run_rounds WHERE run_id = ? ORDER BY round_index ASC, started_at ASC;",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def get_run_events(self, run_id: str, *, limit: int = 200) -> list[dict]:
        rows = self._store.query(
            """
            SELECT * FROM local_agent_runtime_events
            WHERE run_id = ?
            ORDER BY started_at ASC, runtime_event_id ASC
            LIMIT ?;
            """,
            (run_id, limit),
        )
        return [dict(row) for row in rows]

    def get_run_touched_paths(self, run_id: str) -> list[dict]:
        rows = self._store.query(
            "SELECT * FROM local_agent_run_touched_paths WHERE run_id = ? ORDER BY created_at ASC;",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def get_run_links(self, run_id: str) -> list[dict]:
        rows = self._store.query(
            "SELECT * FROM local_agent_run_links WHERE run_id = ? ORDER BY created_at ASC;",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def get_run_grounding(self, run_id: str) -> list[dict]:
        rows = self._store.query(
            "SELECT * FROM local_agent_claim_grounding WHERE run_id = ? ORDER BY created_at ASC;",
            (run_id,),
        )
        return [dict(row) for row in rows]

    def recovery_summary(self, *, limit: int = 10) -> list[dict]:
        rows = self._store.query(
            """
            SELECT run_id, status, recovery_class, retryable, operator_hint, started_at, ended_at
            FROM local_agent_runs
            WHERE recovery_class <> ''
            ORDER BY started_at DESC
            LIMIT ?;
            """,
            (limit,),
        )
        return [dict(row) for row in rows]

    def summary(self, *, limit: int = 8) -> dict:
        runs = self.list_runs(limit=limit)
        active = next((run for run in runs if run.status in {"created", "running", "waiting_approval", "retrying"}), None)
        focus_run = active or (runs[0] if runs else None)
        run_ids = [run.run_id for run in runs]
        recent_failures = [self._run_payload(run) for run in runs if run.status in {"failed", "stopped", "preflight_failed"}][:5]
        return {
            "active_run": self._run_payload(active) if active else {},
            "recent_runs": [self._run_payload(run) for run in runs],
            "recent_failures": recent_failures,
            "latest_recovery_summary": recent_failures[0] if recent_failures else {},
            "run_heartbeat": {
                "run_id": active.run_id,
                "status": active.status,
                "last_round_index": active.last_round_index,
                "last_runtime_event_type": active.last_runtime_event_type,
            } if active else {},
            "last_runtime_event": self._latest_event_payload(focus_run.run_id) if focus_run else {},
            "touched_path_counts": self._touch_counts(run_ids),
            "grounding_counts": self._grounding_counts(run_ids),
            "selected_run_ids": [run.run_id for run in runs],
        }

    def mark_retrying(self, run_id: str) -> None:
        self.update_run(run_id, status="retrying")

    def _latest_event_payload(self, run_id: str) -> dict:
        row = self._store.query_one(
            """
            SELECT event_type, status, summary, recovery_class, started_at, ended_at
            FROM local_agent_runtime_events
            WHERE run_id = ?
            ORDER BY started_at DESC LIMIT 1;
            """,
            (run_id,),
        )
        return dict(row) if row else {}

    def _touch_counts(self, run_ids: list[str]) -> dict:
        if not run_ids:
            return {}
        placeholders = ", ".join("?" for _ in run_ids)
        rows = self._store.query(
            f"""
            SELECT touch_type, COUNT(*) AS n
            FROM local_agent_run_touched_paths
            WHERE run_id IN ({placeholders})
            GROUP BY touch_type;
            """,
            tuple(run_ids),
        )
        return {row["touch_type"]: int(row["n"]) for row in rows}

    def _grounding_counts(self, run_ids: list[str]) -> dict:
        if not run_ids:
            return {}
        placeholders = ", ".join("?" for _ in run_ids)
        rows = self._store.query(
            f"""
            SELECT grounding_kind, COUNT(*) AS n
            FROM local_agent_claim_grounding
            WHERE run_id IN ({placeholders})
            GROUP BY grounding_kind;
            """,
            tuple(run_ids),
        )
        return {row["grounding_kind"]: int(row["n"]) for row in rows}

    def _row_to_run(self, row) -> LocalAgentRun:
        return LocalAgentRun(
            run_id=row["run_id"],
            session_id=row["session_id"],
            actor_id=row["actor_id"],
            model=row["model"],
            status=row["status"],
            authority_level=row["authority_level"],
            task_summary=row["task_summary"] or "",
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            final_summary=row["final_summary"] or "",
            final_message=row["final_message"] or "",
            recovery_class=row["recovery_class"] or "",
            retryable=bool(int(row["retryable"] or 0)),
            operator_hint=row["operator_hint"] or "",
            retried_from_run_id=row["retried_from_run_id"],
            last_round_index=int(row["last_round_index"] or 0),
            last_runtime_event_type=row["last_runtime_event_type"] or "",
            journal_entry_uid=row["journal_entry_uid"],
            approval_request_id=row["approval_request_id"],
            approval_grant_id=row["approval_grant_id"],
            config_snapshot=json.loads(row["config_snapshot_json"] or "{}"),
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def _run_payload(self, run: LocalAgentRun) -> dict:
        return {
            "run_id": run.run_id,
            "session_id": run.session_id,
            "actor_id": run.actor_id,
            "model": run.model,
            "status": run.status,
            "authority_level": run.authority_level,
            "task_summary": run.task_summary,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "final_summary": run.final_summary,
            "final_message": run.final_message,
            "recovery_class": run.recovery_class,
            "retryable": run.retryable,
            "operator_hint": run.operator_hint,
            "retried_from_run_id": run.retried_from_run_id,
            "last_round_index": run.last_round_index,
            "last_runtime_event_type": run.last_runtime_event_type,
            "journal_entry_uid": run.journal_entry_uid,
            "approval_request_id": run.approval_request_id,
            "approval_grant_id": run.approval_grant_id,
        }
