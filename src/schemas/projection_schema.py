"""
FILE: src/schemas/projection_schema.py
ROLE: Declarative shape of projection tables and projection results.
WHAT IT DOES: Names the seven day-one projections, declares each one's
              columns, and maps operation_intent → affected projections.
              T1 implements builders only for current_sidecar_state and
              contract_status; the rest are reserved (table created, no
              builder yet).
"""

from __future__ import annotations


PROJECTION_SCHEMA_VERSION = "1.0.0"


# All projections.  Seven day-one projections (per ARCHITECTURE.md §9) plus
# tranche_checklist (added T2.5 — Active Tranche Ledger).
PROJECTION_NAMES = (
    "current_sidecar_state",
    "agent_bootstrap",
    "human_dashboard",
    "evidence_bag",
    "contract_status",
    "project_map",
    "journal_timeline",
    "tranche_checklist",
    "viewport_state",
    "handoff",
    "runtime_cockpit",
    "training_runway",
    "installed_project_proof",
    "tranche_review_gate",
    "contract_migration_overview",
    "contract_bundle_status",
    "continuity_translation_status",
    "legacy_reference_register",
    "doc_registry_status",
    "doc_cutover_readiness",
    "journal_translation_readiness",
    "bcc_constraint_map",
)


# Per-projection table column definitions (CREATE TABLE-style sketches).
PROJECTION_COLUMNS: dict[str, tuple[str, ...]] = {
    "current_sidecar_state": (
        # single-row enforced via PRIMARY KEY (id) CHECK (id = 1)
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "project_root TEXT",
        "sidecar_root TEXT",
        "sidecar_id TEXT",
        "current_contract_hash TEXT",
        "current_contract_acked INTEGER",
        "registered_object_count INTEGER",
        "registered_tool_count INTEGER",
        "active_task_id TEXT",
        "event_log_position INTEGER",
        "agent_status_json TEXT",
        "human_ui_status_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "agent_bootstrap": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        # PAST
        "recent_events_json TEXT",
        "recent_journal_json TEXT",
        "recent_decisions_json TEXT",
        # PRESENT
        "current_task_json TEXT",
        "authority_json TEXT",
        "contract_status_json TEXT",
        "tool_index_json TEXT",
        "projection_index_json TEXT",
        "stm_json TEXT",
        "bag_json TEXT",
        "evidence_shelf_json TEXT",
        # FUTURE
        "current_tranche_scope_json TEXT",
        "next_planned_steps_json TEXT",
        "active_goals_json TEXT",
        "open_questions_json TEXT",
        "runtime_summary_json TEXT",
        "constraint_map_summary_json TEXT",
        # META
        "source_plan_path TEXT",
        "source_plan_hash TEXT",
        "last_refreshed_at TEXT",
    ),
    "human_dashboard": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "pending_approvals_json TEXT",
        "recent_journal_json TEXT",
        "unresolved_issues_json TEXT",
        "current_tranche_scope_json TEXT",
        "last_scan_summary_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "evidence_bag": (
        "evidence_id TEXT PRIMARY KEY",
        "hash TEXT",
        "kind TEXT",
        "summary TEXT",
        "source_event TEXT",
        "attached_to_object TEXT",
        "status TEXT",
        "created_at TEXT",
    ),
    "contract_status": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "contract_id TEXT",
        "version TEXT",
        "text_hash TEXT",
        "acks_json TEXT",
        "outstanding_grants_json TEXT",
        "recent_contract_events_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "project_map": (
        "path TEXT PRIMARY KEY",
        "kind TEXT",
        "size_bytes INTEGER",
        "content_hash TEXT",
        "last_observed_at TEXT",
        "journal_cite_count INTEGER",
        "evidence_count INTEGER",
    ),
    "journal_timeline": (
        "entry_uid TEXT PRIMARY KEY",
        "kind TEXT",
        "source TEXT",
        "title TEXT",
        "body_excerpt TEXT",
        "created_at TEXT",
        "status TEXT",
        "importance INTEGER",
        "tags_json TEXT",
        "related_path TEXT",
        "evidence_refs_json TEXT",
    ),
    # Added T2.5 — Active Tranche Ledger
    "tranche_checklist": (
        "item_id TEXT PRIMARY KEY",
        "label TEXT NOT NULL",
        "category TEXT NOT NULL",
        # 'pass' | 'fail' | 'pending' | 'warn'
        "status TEXT NOT NULL",
        "detail TEXT",
        "checked_at TEXT",
        # 1 = required for close_tranche to proceed; 0 = informational only
        "required INTEGER NOT NULL DEFAULT 1",
    ),
    "viewport_state": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "topbar_json TEXT",
        "focus_json TEXT",
        "past_json TEXT",
        "present_json TEXT",
        "future_json TEXT",
        "log_json TEXT",
        "status_bar_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "handoff": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "latest_closed_tranche_json TEXT",
        "active_tranche_json TEXT",
        "active_horizon_json TEXT",
        "open_questions_json TEXT",
        "reading_order_json TEXT",
        "verification_commands_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "runtime_cockpit": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "active_run_json TEXT",
        "recent_runs_json TEXT",
        "recent_failures_json TEXT",
        "latest_recovery_summary_json TEXT",
        "run_heartbeat_json TEXT",
        "last_runtime_event_json TEXT",
        "touched_path_counts_json TEXT",
        "grounding_counts_json TEXT",
        "selected_run_ids_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "training_runway": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "scenario_inventory_json TEXT",
        "recent_runs_json TEXT",
        "recent_scorecards_json TEXT",
        "pass_fail_counts_json TEXT",
        "latest_live_proof_json TEXT",
        "reviewer_export_handles_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "installed_project_proof": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "fixture_summary_json TEXT",
        "latest_proof_json TEXT",
        "recent_proofs_json TEXT",
        "verification_result_json TEXT",
        "handoff_status_json TEXT",
        "supersession_status_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "tranche_review_gate": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "current_tranche_json TEXT",
        "latest_review_json TEXT",
        "history_json TEXT",
        "allowed_actions_json TEXT",
        "park_phase_allowed INTEGER",
        "last_refreshed_at TEXT",
    ),
    "contract_migration_overview": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "summary_json TEXT",
        "bundle_counts_json TEXT",
        "reference_counts_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "contract_bundle_status": (
        "bundle_id TEXT PRIMARY KEY",
        "title TEXT",
        "bcc_sections_json TEXT",
        "legacy_refs_json TEXT",
        "mapped_count INTEGER",
        "unresolved_count INTEGER",
        "status TEXT",
        "notes_json TEXT",
    ),
    "continuity_translation_status": (
        "surface_path TEXT PRIMARY KEY",
        "surface_class TEXT",
        "status TEXT",
        "legacy_ref_count INTEGER",
        "unresolved_count INTEGER",
        "notes_json TEXT",
        "last_seen_at TEXT",
    ),
    "legacy_reference_register": (
        "ref_id TEXT PRIMARY KEY",
        "source_path TEXT",
        "reference_kind TEXT",
        "legacy_ref TEXT",
        "translated_ref TEXT",
        "translation_status TEXT",
        "surface_class TEXT",
        "historical_preservation INTEGER",
    ),
    "doc_registry_status": (
        "doc_id TEXT PRIMARY KEY",
        "canonical_relpath TEXT",
        "resolved_relpath TEXT",
        "temporal_class TEXT",
        "surface_kind TEXT",
        "exists_flag INTEGER",
        "hash TEXT",
        "alias_count INTEGER",
        "drift_status TEXT",
    ),
    "doc_cutover_readiness": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "active_docs_total INTEGER",
        "ready_docs_count INTEGER",
        "unresolved_refs_count INTEGER",
        "compatibility_aliases_json TEXT",
        "last_refreshed_at TEXT",
    ),
    "journal_translation_readiness": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "tranche_entry_count INTEGER",
        "historical_artifact_count INTEGER",
        "translation_notes_count INTEGER",
        "unresolved_historical_refs_count INTEGER",
        "last_refreshed_at TEXT",
    ),
    "bcc_constraint_map": (
        "id INTEGER PRIMARY KEY CHECK (id = 1)",
        "status TEXT",
        "source_contract_path TEXT",
        "live_contract_hash TEXT",
        "contract_record_hash TEXT",
        "compiled_contract_hash TEXT",
        "hash_match INTEGER",
        "compiler_version TEXT",
        "generated_at TEXT",
        "payload_json TEXT",
        "summary_json TEXT",
        "drift_json TEXT",
        "guidance_allowed INTEGER",
        "refresh_hint TEXT",
        "last_refreshed_at TEXT",
    ),
}


# Mapping: operation_intent → list of projection names that should refresh
# after the event commits.
INTENT_AFFECTS_PROJECTIONS: dict[str, tuple[str, ...]] = {
    "acknowledge_contract": ("contract_status", "current_sidecar_state", "agent_bootstrap", "viewport_state", "contract_migration_overview", "contract_bundle_status", "continuity_translation_status", "legacy_reference_register", "doc_registry_status", "doc_cutover_readiness", "journal_translation_readiness", "bcc_constraint_map"),
    "install": ("current_sidecar_state", "contract_status", "agent_bootstrap", "viewport_state", "contract_migration_overview", "contract_bundle_status", "continuity_translation_status", "legacy_reference_register", "doc_registry_status", "doc_cutover_readiness", "journal_translation_readiness", "bcc_constraint_map"),
    "seed_constraints": ("contract_status",),

    "scan": ("project_map", "current_sidecar_state", "human_dashboard", "viewport_state", "contract_migration_overview", "contract_bundle_status", "continuity_translation_status", "legacy_reference_register", "doc_registry_status", "doc_cutover_readiness", "journal_translation_readiness", "bcc_constraint_map"),
    "rescan_path": ("project_map",),
    "observe_file": ("project_map",),
    "observe_git": ("human_dashboard", "viewport_state"),
    "record_observed_file": ("project_map",),

    "tool_invoked": ("current_sidecar_state", "viewport_state", "runtime_cockpit", "installed_project_proof", "contract_migration_overview", "continuity_translation_status", "doc_registry_status"),
    "tool_result": ("current_sidecar_state", "viewport_state", "runtime_cockpit", "installed_project_proof", "contract_migration_overview", "continuity_translation_status", "doc_registry_status"),
    "request_authority_elevation": ("human_dashboard", "contract_status", "viewport_state", "handoff", "runtime_cockpit", "installed_project_proof"),
    "approve_authority_request": ("human_dashboard", "contract_status", "viewport_state", "handoff", "runtime_cockpit", "installed_project_proof"),
    "reject_authority_request": ("human_dashboard", "contract_status", "viewport_state", "handoff", "runtime_cockpit", "installed_project_proof"),

    "create_journal_entry": ("journal_timeline", "human_dashboard", "agent_bootstrap", "viewport_state", "doc_registry_status", "journal_translation_readiness"),
    "update_journal_entry": ("journal_timeline", "viewport_state", "doc_registry_status", "journal_translation_readiness"),
    "close_journal_entry": ("journal_timeline", "viewport_state", "doc_registry_status", "journal_translation_readiness"),
    "archive_journal_entry": ("journal_timeline", "viewport_state", "doc_registry_status", "journal_translation_readiness"),

    "attach_evidence": ("evidence_bag", "human_dashboard", "viewport_state"),
    "verify_evidence": ("evidence_bag", "viewport_state"),

    "register_constraint": ("contract_status",),
    "register_profile": ("contract_status",),

    "register_tool": ("agent_bootstrap", "current_sidecar_state", "viewport_state"),
    "unregister_tool": ("agent_bootstrap", "current_sidecar_state", "viewport_state"),

    "accept_task": ("current_sidecar_state", "human_dashboard", "viewport_state"),
    "complete_task": ("current_sidecar_state", "human_dashboard", "viewport_state"),

    "declare_tranche": ("tranche_checklist", "human_dashboard", "agent_bootstrap", "viewport_state", "handoff", "runtime_cockpit", "training_runway", "installed_project_proof", "tranche_review_gate", "doc_registry_status", "journal_translation_readiness", "bcc_constraint_map"),
    "update_tranche":  ("tranche_checklist", "viewport_state", "handoff", "tranche_review_gate", "doc_registry_status", "journal_translation_readiness"),
    "record_decision": ("tranche_checklist", "agent_bootstrap", "viewport_state", "handoff", "runtime_cockpit", "training_runway", "installed_project_proof", "tranche_review_gate", "doc_registry_status", "journal_translation_readiness"),
    "smoke_pass":      ("tranche_checklist", "viewport_state", "tranche_review_gate"),
    "request_tranche_review": ("tranche_checklist", "viewport_state", "handoff", "tranche_review_gate"),
    "return_tranche_review": ("tranche_checklist", "viewport_state", "handoff", "tranche_review_gate", "agent_bootstrap"),
    "approve_tranche_review": ("tranche_checklist", "viewport_state", "handoff", "tranche_review_gate"),
    "close_tranche":   (
        "tranche_checklist", "human_dashboard", "agent_bootstrap", "journal_timeline", "viewport_state", "handoff", "runtime_cockpit", "training_runway", "installed_project_proof", "tranche_review_gate", "doc_registry_status", "journal_translation_readiness", "bcc_constraint_map",
    ),
}


def affected_projections(operation_intent: str) -> tuple[str, ...]:
    return INTENT_AFFECTS_PROJECTIONS.get(operation_intent, ())


def table_ddl(projection_name: str) -> str:
    """Return CREATE TABLE SQL for the named projection."""
    cols = PROJECTION_COLUMNS.get(projection_name)
    if not cols:
        raise KeyError(f"unknown projection: {projection_name}")
    body = ",\n  ".join(cols)
    return f"CREATE TABLE IF NOT EXISTS proj_{projection_name} (\n  {body}\n);"
