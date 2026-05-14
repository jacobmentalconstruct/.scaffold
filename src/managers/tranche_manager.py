"""
FILE: src/managers/tranche_manager.py
ROLE: Active Tranche Ledger — owns decision_records and active_tranche tables.
WHAT IT DOES (T2.5): Handles declare_tranche, update_tranche, record_decision,
      and smoke_pass envelopes.  Provides read API used by the CloseoutOrchestrator
      and the tranche_checklist projection builder.

Design intent ("capture once, derive many"):
  - During a tranche, developers record typed DecisionRecords as decisions are made.
  - The active_tranche accumulates: files_changed, deviations, open_questions,
    tests_run, evidence_refs.
  - At close, CloseoutOrchestrator reads this structured data and compiles
    park notes programmatically — no reconstruction needed.
  - The tranche_checklist projection shows live readiness status.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.lib.common import gen_id, now_iso, safe_json_dumps
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.blob_store import BlobStore
    from src.components.sqlite_store import Store
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState


log = get_logger("managers.tranche")


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    tranche_id: str | None
    title: str
    context: str
    rationale: str
    outcome: str
    impact_area: str
    alternatives: list
    evidence_refs: list
    tags: list
    importance: int
    actor_id: str
    created_at: str
    event_id: str


@dataclass
class ActiveTranche:
    tranche_id: str
    title: str
    declared_scope: str
    declared_non_goals: str
    declared_completion_criteria: str
    status: str
    started_at: str
    closed_at: str | None
    files_changed: list
    decisions_count: int
    evidence_refs: list
    tests_run: list
    deviations: list
    open_questions: list
    next_tranche_candidate: str | None
    park_notes_blob_ref: str | None
    journal_entry_uid: str | None
    current_review_id: str | None
    last_review_status: str
    last_reviewed_at: str | None
    actor_id: str
    event_id: str


@dataclass(frozen=True)
class TrancheReviewPacket:
    review_id: str
    tranche_id: str
    status: str
    generated_at: str
    generated_by_actor: str
    review_packet_json_ref: str
    review_packet_markdown_ref: str
    smoke_snapshot: dict
    latest_decision_ids: list
    latest_test_records: list
    reviewed_by_actor: str | None
    reviewed_at: str | None
    return_reason: str
    approval_notes: str
    event_id: str
    metadata: dict


@dataclass
class ChecklistItem:
    item_id: str
    label: str
    category: str
    status: str          # 'pass' | 'fail' | 'pending' | 'warn'
    detail: str
    required: bool
    checked_at: str = field(default_factory=now_iso)


# ---------------------------------------------------------------------------
# Checklist item definitions
# Each tuple: (item_id, label, category, required)
# ---------------------------------------------------------------------------

_CHECKLIST_DEFS: tuple[tuple[str, str, str, bool], ...] = (
    ("contract_acked",      "Contract acknowledged by ≥1 actor",    "contract",   True),
    ("tranche_declared",    "Active tranche declared in DB",          "scope",      True),
    ("scope_declared",      "Declared scope is non-empty",            "scope",      True),
    ("smoke_test_passed",   "Smoke test recorded as PASS",            "testing",    True),
    ("review_approved",     "Human review approved before Park Phase", "review",    True),
    ("decisions_recorded",  "≥1 typed decision recorded this tranche","decisions",  False),
    ("evidence_attached",   "≥1 evidence item attached this tranche", "evidence",   False),
    ("no_open_tasks",       "No active task in progress",             "tasks",      False),
    ("park_notes_written",  "Park notes blob captured (at close)",    "park",       True),
    ("journal_entry_closed","Tranche journal entry exists + closed",  "park",       True),
)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class TrancheManager:
    def __init__(self, store: "Store", blob_store: "BlobStore"):
        self._store = store
        self._blob = blob_store

    # ===== envelope handlers (called by Router) =========================

    def handle_declare_tranche(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        """Handler for declare_tranche.

        Payload keys:
          title (str, required)
          scope (str)
          non_goals (str)
          completion_criteria (str)
          next_tranche_candidate (str, optional)
        """
        request = self._read_payload(envelope)
        title = request.get("title", "").strip()
        if not title:
            raise ValueError("declare_tranche requires non-empty 'title' in payload")

        # Only one active tranche at a time.
        existing = self.get_current()
        if existing:
            raise RuntimeError(
                f"Cannot declare a new tranche — '{existing.title}' "
                f"(id={existing.tranche_id}) is still open with status={existing.status!r}. "
                "Finish or return the current tranche before declaring a new one."
            )

        tranche_id = gen_id("tranche_")
        now = now_iso()

        self._store.execute(
            """
            INSERT INTO active_tranche(
                tranche_id, title, declared_scope, declared_non_goals,
                declared_completion_criteria, status, started_at,
                files_changed_json, decisions_count, evidence_refs_json,
                tests_run_json, deviations_json, open_questions_json,
                next_tranche_candidate, actor_id, event_id
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, '[]', 0, '[]', '[]', '[]', '[]', ?, ?, 'PENDING');
            """,
            (
                tranche_id,
                title,
                request.get("scope", ""),
                request.get("non_goals", ""),
                request.get("completion_criteria", ""),
                now,
                request.get("next_tranche_candidate"),
                envelope.actor_id,
            ),
        )

        # Stash current_tranche_scope in journal_meta so human_dashboard
        # can pick it up without hitting active_tranche directly.
        self._store.set_meta("current_tranche_scope", safe_json_dumps({
            "tranche_id": tranche_id,
            "title": title,
            "scope": request.get("scope", ""),
            "started_at": now,
        }))

        response = {"tranche_id": tranche_id, "title": title, "started_at": now}
        response_ref = self._blob.put_json(response)
        log.info("tranche declared: id=%s title=%r actor=%s", tranche_id, title, envelope.actor_id)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def finalize_declare_event_id(self, sealed: "SidecarEnvelope") -> None:
        """Called by Router after EventStore.append — replaces PENDING event_id."""
        if not sealed.payload_ref:
            return
        try:
            response = self._blob.get_json(sealed.payload_ref)
        except Exception as e:
            log.error("finalize_declare_event_id: cannot read blob: %s", e)
            return
        tranche_id = response.get("tranche_id")
        if tranche_id:
            self._store.execute(
                "UPDATE active_tranche SET event_id = ? "
                "WHERE tranche_id = ? AND event_id = 'PENDING';",
                (sealed.event_id, tranche_id),
            )

    def handle_update_tranche(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        """Handler for update_tranche.

        Payload keys (all optional, each list is APPENDED to existing data):
          files_changed:   list[{path, change_type}]
          deviations:      list[{description, reason, impact}]
          open_questions:  list[{question, raised_at}]
          tests_run:       list[{test_name, passed, ran_at, details}]
          evidence_refs:   list[{hash, kind, summary}]
        """
        request = self._read_payload(envelope)
        tranche = self.get_active()
        if not tranche:
            raise RuntimeError("No active tranche — call declare_tranche first")

        def _append(existing_json: str, new_items: list) -> str:
            existing = json.loads(existing_json or "[]")
            existing.extend(new_items)
            return safe_json_dumps(existing)

        updates: dict[str, str] = {}
        if request.get("files_changed"):
            updates["files_changed_json"] = _append(
                safe_json_dumps(tranche.files_changed), request["files_changed"]
            )
        if request.get("deviations"):
            updates["deviations_json"] = _append(
                safe_json_dumps(tranche.deviations), request["deviations"]
            )
        if request.get("open_questions"):
            updates["open_questions_json"] = _append(
                safe_json_dumps(tranche.open_questions), request["open_questions"]
            )
        if request.get("tests_run"):
            updates["tests_run_json"] = _append(
                safe_json_dumps(tranche.tests_run), request["tests_run"]
            )
        if request.get("evidence_refs"):
            updates["evidence_refs_json"] = _append(
                safe_json_dumps(tranche.evidence_refs), request["evidence_refs"]
            )

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            params = list(updates.values()) + [tranche.tranche_id]
            self._store.execute(
                f"UPDATE active_tranche SET {set_clause} WHERE tranche_id = ?;",
                params,
            )

        response = {"tranche_id": tranche.tranche_id, "updated_fields": list(updates.keys())}
        response_ref = self._blob.put_json(response)
        log.info("tranche updated: id=%s fields=%s", tranche.tranche_id, list(updates.keys()))
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def handle_record_decision(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        """Handler for record_decision.

        Payload keys:
          title (str, required)
          context (str) — what problem were we solving?
          rationale (str) — why this choice over alternatives?
          outcome (str) — what exactly did we decide?
          impact_area (str) — e.g. 'schema', 'architecture', 'tools', 'process'
          alternatives (list[{option, reason_rejected}])
          evidence_refs (list[{hash, kind}])
          tags (list[str])
          importance (int, 0–10, default 5)
        """
        request = self._read_payload(envelope)
        title = request.get("title", "").strip()
        if not title:
            raise ValueError("record_decision requires non-empty 'title' in payload")

        tranche = self.get_active()
        tranche_id = tranche.tranche_id if tranche else None

        decision_id = gen_id("decision_")
        now = now_iso()

        self._store.execute(
            """
            INSERT INTO decision_records(
                decision_id, tranche_id, title, context, rationale, outcome,
                impact_area, alternatives_json, evidence_refs_json, tags_json,
                importance, actor_id, created_at, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING');
            """,
            (
                decision_id,
                tranche_id,
                title,
                request.get("context", ""),
                request.get("rationale", ""),
                request.get("outcome", ""),
                request.get("impact_area", ""),
                safe_json_dumps(request.get("alternatives") or []),
                safe_json_dumps(request.get("evidence_refs") or []),
                safe_json_dumps(request.get("tags") or []),
                int(request.get("importance", 5)),
                envelope.actor_id,
                now,
            ),
        )

        # Increment denormalized counter on active_tranche.
        if tranche_id:
            self._store.execute(
                "UPDATE active_tranche SET decisions_count = decisions_count + 1 "
                "WHERE tranche_id = ?;",
                (tranche_id,),
            )

        response = {
            "decision_id": decision_id,
            "tranche_id": tranche_id,
            "title": title,
            "created_at": now,
        }
        response_ref = self._blob.put_json(response)
        log.info("decision recorded: id=%s title=%r tranche=%s", decision_id, title, tranche_id)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def finalize_decision_event_id(self, sealed: "SidecarEnvelope") -> None:
        """Called by Router after EventStore.append — replaces PENDING event_id."""
        if not sealed.payload_ref:
            return
        try:
            response = self._blob.get_json(sealed.payload_ref)
        except Exception as e:
            log.error("finalize_decision_event_id: cannot read blob: %s", e)
            return
        decision_id = response.get("decision_id")
        if decision_id:
            self._store.execute(
                "UPDATE decision_records SET event_id = ? "
                "WHERE decision_id = ? AND event_id = 'PENDING';",
                (sealed.event_id, decision_id),
            )

    def handle_smoke_pass(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        """Handler for smoke_pass.

        Records a smoke test result in the active tranche's tests_run list.
        Payload keys:
          test_name (str, default 'smoke_test.py')
          passed (bool, default True)
          details (str, optional)
        """
        request = self._read_payload(envelope)
        tranche = self.get_active()
        if not tranche:
            # No active tranche; record the pass but don't fail.
            log.info("smoke_pass: no active tranche — pass noted but not attached")
            response = {"recorded": False, "reason": "no active tranche"}
            return envelope.with_status("completed").with_payload_ref(
                self._blob.put_json(response)
            )

        now = now_iso()
        test_record = {
            "test_name": request.get("test_name", "smoke_test.py"),
            "passed": bool(request.get("passed", True)),
            "ran_at": now,
            "details": request.get("details", ""),
        }
        existing = json.loads(tranche.tests_run_json if hasattr(tranche, "tests_run_json")
                              else safe_json_dumps(tranche.tests_run))
        # Re-read fresh from DB to avoid stale in-memory object.
        row = self._store.query_one(
            "SELECT tests_run_json FROM active_tranche WHERE tranche_id = ?;",
            (tranche.tranche_id,),
        )
        existing = json.loads(row["tests_run_json"] if row else "[]")
        existing.append(test_record)
        self._store.execute(
            "UPDATE active_tranche SET tests_run_json = ? WHERE tranche_id = ?;",
            (safe_json_dumps(existing), tranche.tranche_id),
        )

        response = {
            "tranche_id": tranche.tranche_id,
            "test_name": test_record["test_name"],
            "passed": test_record["passed"],
            "ran_at": now,
        }
        response_ref = self._blob.put_json(response)
        log.info("smoke_pass recorded: tranche=%s passed=%s", tranche.tranche_id,
                 test_record["passed"])
        return envelope.with_status("completed").with_payload_ref(response_ref)

    # ===== Read API ====================================================

    def get_active(self) -> ActiveTranche | None:
        """Return the current active tranche, or None if none declared."""
        row = self._store.query_one(
            "SELECT * FROM active_tranche WHERE status = 'active' "
            "ORDER BY started_at DESC LIMIT 1;"
        )
        return self._row_to_tranche(row) if row else None

    def get_current(self) -> ActiveTranche | None:
        row = self._store.query_one(
            """
            SELECT * FROM active_tranche
            WHERE status IN ('active', 'review_pending', 'review_approved')
            ORDER BY started_at DESC LIMIT 1;
            """
        )
        return self._row_to_tranche(row) if row else None

    def get_by_id(self, tranche_id: str) -> ActiveTranche | None:
        row = self._store.query_one(
            "SELECT * FROM active_tranche WHERE tranche_id = ?;", (tranche_id,)
        )
        return self._row_to_tranche(row) if row else None

    def get_decisions(self, tranche_id: str | None = None) -> list[DecisionRecord]:
        """Return decision records, optionally filtered by tranche_id."""
        if tranche_id is not None:
            rows = self._store.query(
                "SELECT * FROM decision_records WHERE tranche_id = ? "
                "ORDER BY created_at ASC;",
                (tranche_id,),
            )
        else:
            rows = self._store.query(
                "SELECT * FROM decision_records ORDER BY created_at DESC LIMIT 50;"
        )
        return [self._row_to_decision(r) for r in rows]

    def create_review_packet(
        self,
        *,
        tranche_id: str,
        actor_id: str,
        review_packet_json_ref: str,
        review_packet_markdown_ref: str,
        smoke_snapshot: dict,
        latest_decision_ids: list[str],
        latest_test_records: list[dict],
        metadata: dict | None = None,
    ) -> str:
        review_id = gen_id("review_")
        now = now_iso()
        self._store.execute(
            """
            UPDATE tranche_review_packets
            SET status = 'superseded'
            WHERE tranche_id = ? AND status IN ('pending', 'returned');
            """,
            (tranche_id,),
        )
        self._store.execute(
            """
            INSERT INTO tranche_review_packets(
                review_id, tranche_id, status, generated_at, generated_by_actor,
                review_packet_json_ref, review_packet_markdown_ref,
                smoke_snapshot_json, latest_decision_ids_json, latest_test_records_json,
                reviewed_by_actor, reviewed_at, return_reason, approval_notes,
                event_id, metadata_json
            ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, NULL, NULL, '', '', 'PENDING', ?);
            """,
            (
                review_id,
                tranche_id,
                now,
                actor_id,
                review_packet_json_ref,
                review_packet_markdown_ref,
                safe_json_dumps(smoke_snapshot),
                safe_json_dumps(latest_decision_ids),
                safe_json_dumps(latest_test_records),
                safe_json_dumps(metadata or {}),
            ),
        )
        self._store.execute(
            """
            UPDATE active_tranche
            SET status = 'review_pending',
                current_review_id = ?,
                last_review_status = 'pending',
                last_reviewed_at = ?
            WHERE tranche_id = ?;
            """,
            (review_id, now, tranche_id),
        )
        return review_id

    def finalize_review_event_id(self, review_id: str, event_id: str) -> None:
        self._store.execute(
            """
            UPDATE tranche_review_packets
            SET event_id = ?
            WHERE review_id = ? AND event_id = 'PENDING';
            """,
            (event_id, review_id),
        )

    def get_latest_review(self, tranche_id: str) -> TrancheReviewPacket | None:
        row = self._store.query_one(
            """
            SELECT * FROM tranche_review_packets
            WHERE tranche_id = ?
            ORDER BY generated_at DESC
            LIMIT 1;
            """,
            (tranche_id,),
        )
        return self._row_to_review(row) if row else None

    def list_reviews(self, tranche_id: str, *, limit: int = 10) -> list[TrancheReviewPacket]:
        rows = self._store.query(
            """
            SELECT * FROM tranche_review_packets
            WHERE tranche_id = ?
            ORDER BY generated_at DESC
            LIMIT ?;
            """,
            (tranche_id, limit),
        )
        return [self._row_to_review(row) for row in rows]

    def return_review(self, *, tranche_id: str, review_id: str, reviewed_by_actor: str, reason: str) -> None:
        now = now_iso()
        self._store.execute(
            """
            UPDATE tranche_review_packets
            SET status = 'returned',
                reviewed_by_actor = ?,
                reviewed_at = ?,
                return_reason = ?
            WHERE review_id = ? AND tranche_id = ?;
            """,
            (reviewed_by_actor, now, reason, review_id, tranche_id),
        )
        row = self._store.query_one(
            "SELECT open_questions_json FROM active_tranche WHERE tranche_id = ?;",
            (tranche_id,),
        )
        open_questions = json.loads(row["open_questions_json"] if row else "[]")
        open_questions.append(
            {
                "question": reason,
                "raised_at": now,
                "source": "human_review_return",
                "review_id": review_id,
                "reviewed_by_actor": reviewed_by_actor,
            }
        )
        self._store.execute(
            """
            UPDATE active_tranche
            SET status = 'active',
                last_review_status = 'returned',
                last_reviewed_at = ?,
                open_questions_json = ?
            WHERE tranche_id = ?;
            """,
            (now, safe_json_dumps(open_questions), tranche_id),
        )

    def approve_review(self, *, tranche_id: str, review_id: str, reviewed_by_actor: str, notes: str) -> None:
        now = now_iso()
        self._store.execute(
            """
            UPDATE tranche_review_packets
            SET status = 'approved',
                reviewed_by_actor = ?,
                reviewed_at = ?,
                approval_notes = ?
            WHERE review_id = ? AND tranche_id = ?;
            """,
            (reviewed_by_actor, now, notes, review_id, tranche_id),
        )
        self._store.execute(
            """
            UPDATE active_tranche
            SET status = 'review_approved',
                last_review_status = 'approved',
                last_reviewed_at = ?
            WHERE tranche_id = ?;
            """,
            (now, tranche_id),
        )

    def build_checklist(self, state: "SidecarState") -> list[ChecklistItem]:
        """Evaluate all checklist items against current DB state.

        Returns a list[ChecklistItem] used both by the projection builder
        and by CloseoutOrchestrator to gate close_tranche.
        """
        now = now_iso()
        tranche = self.get_active()
        items: list[ChecklistItem] = []

        for item_id, label, category, required in _CHECKLIST_DEFS:
            status, detail = self._evaluate_item(item_id, tranche, state)
            items.append(ChecklistItem(
                item_id=item_id,
                label=label,
                category=category,
                status=status,
                detail=detail,
                required=required,
                checked_at=now,
            ))

        return items

    def seal(
        self,
        tranche_id: str,
        park_notes_blob_ref: str,
        journal_entry_uid: str,
    ) -> None:
        """Mark the active tranche as 'parked' (called by CloseoutOrchestrator)."""
        self._store.execute(
            """
            UPDATE active_tranche
            SET status = 'parked', closed_at = ?, park_notes_blob_ref = ?,
                journal_entry_uid = ?, current_review_id = current_review_id
            WHERE tranche_id = ?;
            """,
            (now_iso(), park_notes_blob_ref, journal_entry_uid, tranche_id),
        )
        # Clear the current_tranche_scope meta so human_dashboard shows empty.
        self._store.set_meta("current_tranche_scope", "{}")
        log.info("tranche sealed: id=%s", tranche_id)

    # ===== Internals ===================================================

    def _evaluate_item(
        self, item_id: str, tranche: ActiveTranche | None, state: "SidecarState"
    ) -> tuple[str, str]:
        """Return (status, detail) for a single checklist item."""
        try:
            return self._check(item_id, tranche, state)
        except Exception as e:
            log.warning("checklist item %s raised: %s", item_id, e)
            return ("fail", f"check error: {e}")

    def _check(
        self, item_id: str, tranche: ActiveTranche | None, state: "SidecarState"
    ) -> tuple[str, str]:
        if item_id == "contract_acked":
            row = self._store.query_one("SELECT COUNT(*) AS n FROM acknowledgments;")
            n = int(row["n"]) if row else 0
            if n > 0:
                return ("pass", f"{n} actor(s) acknowledged")
            return ("fail", "no contract acknowledgments found")

        if item_id == "tranche_declared":
            if tranche:
                return ("pass", f"'{tranche.title}' (id={tranche.tranche_id})")
            return ("fail", "no active tranche — run tranche-declare")

        if item_id == "scope_declared":
            if tranche and tranche.declared_scope.strip():
                preview = tranche.declared_scope[:80]
                return ("pass", preview + ("..." if len(tranche.declared_scope) > 80 else ""))
            return ("fail", "declared_scope is empty — re-declare or update tranche")

        if item_id == "smoke_test_passed":
            if not tranche:
                return ("pending", "no active tranche")
            row = self._store.query_one(
                "SELECT tests_run_json FROM active_tranche WHERE tranche_id = ?;",
                (tranche.tranche_id,),
            )
            tests = json.loads(row["tests_run_json"] if row else "[]")
            passes = [t for t in tests if t.get("passed")]
            if passes:
                last = passes[-1]
                return ("pass", f"last PASS at {last.get('ran_at', '?')}")
            if tests:
                return ("fail", f"{len(tests)} test run(s), none PASS")
            return ("fail", "no smoke tests recorded — run smoke_test.py then tranche-smoke-pass")

        if item_id == "review_approved":
            if not tranche:
                return ("pending", "no current tranche")
            if tranche.status == "review_approved":
                return ("pass", f"review approved at {tranche.last_reviewed_at or '?'}")
            if tranche.status == "review_pending":
                return ("fail", "review packet is pending human approval")
            if tranche.last_review_status == "returned":
                return ("fail", "latest review was returned to the agent")
            return ("fail", "review has not been approved yet — run tranche-review-request")

        if item_id == "decisions_recorded":
            if not tranche:
                return ("pending", "no active tranche")
            row = self._store.query_one(
                "SELECT decisions_count FROM active_tranche WHERE tranche_id = ?;",
                (tranche.tranche_id,),
            )
            n = int(row["decisions_count"]) if row else 0
            if n > 0:
                return ("pass", f"{n} decision(s) recorded")
            return ("warn", "no decisions recorded — consider running decision-record")

        if item_id == "evidence_attached":
            if not tranche:
                return ("pending", "no active tranche")
            row = self._store.query_one(
                "SELECT evidence_refs_json FROM active_tranche WHERE tranche_id = ?;",
                (tranche.tranche_id,),
            )
            refs = json.loads(row["evidence_refs_json"] if row else "[]")
            if refs:
                return ("pass", f"{len(refs)} evidence ref(s) attached")
            return ("warn", "no evidence attached this tranche")

        if item_id == "no_open_tasks":
            try:
                if state.active_task:
                    task_title = state.active_task.get("title", "?")
                    return ("warn", f"active task: '{task_title}'")
            except AttributeError:
                pass
            return ("pass", "no active task")

        if item_id == "park_notes_written":
            if tranche and tranche.park_notes_blob_ref:
                return ("pass", f"blob_ref={tranche.park_notes_blob_ref[:16]}...")
            return ("fail", "park notes not yet captured — run tranche-close")

        if item_id == "journal_entry_closed":
            if not tranche:
                return ("fail", "no active tranche")
            if tranche.journal_entry_uid:
                # Check if the entry is actually closed.
                row = self._store.query_one(
                    "SELECT status FROM journal_entries WHERE entry_uid = ?;",
                    (tranche.journal_entry_uid,),
                )
                if row and row["status"] == "closed":
                    return ("pass", f"entry {tranche.journal_entry_uid} is closed")
                elif row:
                    return ("fail", f"entry {tranche.journal_entry_uid} status={row['status']!r}")
            return ("fail", "tranche journal entry not yet created — run tranche-close")

        return ("pending", "unknown item")

    def _read_payload(self, envelope: "SidecarEnvelope") -> dict:
        if not envelope.payload_ref:
            return {}
        try:
            return self._blob.get_json(envelope.payload_ref)
        except Exception as e:
            raise ValueError(f"cannot read payload from blob {envelope.payload_ref}: {e}")

    @staticmethod
    def _row_to_tranche(row) -> ActiveTranche:
        return ActiveTranche(
            tranche_id=row["tranche_id"],
            title=row["title"],
            declared_scope=row["declared_scope"] or "",
            declared_non_goals=row["declared_non_goals"] or "",
            declared_completion_criteria=row["declared_completion_criteria"] or "",
            status=row["status"],
            started_at=row["started_at"],
            closed_at=row["closed_at"],
            files_changed=json.loads(row["files_changed_json"] or "[]"),
            decisions_count=int(row["decisions_count"] or 0),
            evidence_refs=json.loads(row["evidence_refs_json"] or "[]"),
            tests_run=json.loads(row["tests_run_json"] or "[]"),
            deviations=json.loads(row["deviations_json"] or "[]"),
            open_questions=json.loads(row["open_questions_json"] or "[]"),
            next_tranche_candidate=row["next_tranche_candidate"],
            park_notes_blob_ref=row["park_notes_blob_ref"],
            journal_entry_uid=row["journal_entry_uid"],
            current_review_id=row["current_review_id"] if "current_review_id" in row.keys() else None,
            last_review_status=row["last_review_status"] if "last_review_status" in row.keys() else "",
            last_reviewed_at=row["last_reviewed_at"] if "last_reviewed_at" in row.keys() else None,
            actor_id=row["actor_id"],
            event_id=row["event_id"],
        )

    @staticmethod
    def _row_to_decision(row) -> DecisionRecord:
        return DecisionRecord(
            decision_id=row["decision_id"],
            tranche_id=row["tranche_id"],
            title=row["title"],
            context=row["context"] or "",
            rationale=row["rationale"] or "",
            outcome=row["outcome"] or "",
            impact_area=row["impact_area"] or "",
            alternatives=json.loads(row["alternatives_json"] or "[]"),
            evidence_refs=json.loads(row["evidence_refs_json"] or "[]"),
            tags=json.loads(row["tags_json"] or "[]"),
            importance=int(row["importance"] or 5),
            actor_id=row["actor_id"],
            created_at=row["created_at"],
            event_id=row["event_id"],
        )

    @staticmethod
    def _row_to_review(row) -> TrancheReviewPacket:
        return TrancheReviewPacket(
            review_id=row["review_id"],
            tranche_id=row["tranche_id"],
            status=row["status"],
            generated_at=row["generated_at"],
            generated_by_actor=row["generated_by_actor"],
            review_packet_json_ref=row["review_packet_json_ref"],
            review_packet_markdown_ref=row["review_packet_markdown_ref"],
            smoke_snapshot=json.loads(row["smoke_snapshot_json"] or "{}"),
            latest_decision_ids=json.loads(row["latest_decision_ids_json"] or "[]"),
            latest_test_records=json.loads(row["latest_test_records_json"] or "[]"),
            reviewed_by_actor=row["reviewed_by_actor"],
            reviewed_at=row["reviewed_at"],
            return_reason=row["return_reason"] or "",
            approval_notes=row["approval_notes"] or "",
            event_id=row["event_id"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )
