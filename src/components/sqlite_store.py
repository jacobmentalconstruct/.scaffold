"""
FILE: src/components/sqlite_store.py
ROLE: The single code path to the SQLite spine. All DB access flows through here.
WHAT IT DOES: Opens the DB with WAL mode + FK enforcement, runs additive
              migrations, exposes execute/query/transaction primitives,
              owns the canonical schema DDL.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from src.lib.common import now_iso
from src.lib.logging_setup import get_logger
from src.schemas.projection_schema import PROJECTION_NAMES, table_ddl


log = get_logger("components.sqlite_store")


# ----------------------------------------------------------------------------
# Schema DDL — additive only. Each migration appends; never destructive
# without a separate documented plan.
# ----------------------------------------------------------------------------

_CORE_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS journal_meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS journal_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL,
        description TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS blob_store (
        hash TEXT PRIMARY KEY,
        size_bytes INTEGER NOT NULL,
        content_type TEXT NOT NULL,
        body BLOB NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        stream TEXT NOT NULL,
        stream_key TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        envelope_version TEXT NOT NULL,
        operation_intent TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        sidecar_id TEXT NOT NULL,
        correlation_id TEXT NOT NULL,
        causation_id TEXT,
        contract_refs TEXT,
        payload_ref TEXT,
        evidence_refs TEXT,
        relation_refs TEXT,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        envelope_blob BLOB,
        recovery_class TEXT,
        recovery_decision TEXT,
        evidence_id TEXT,
        session_id TEXT,
        run_id TEXT,
        scenario_id TEXT,
        run_mode TEXT,
        timeout_seconds INTEGER,
        max_tool_rounds INTEGER,
        score_result TEXT,
        pass_fail_state TEXT,
        touched_paths TEXT,
        journal_entry_id TEXT,
        is_durable INTEGER,
        append_only INTEGER,
        UNIQUE (stream, stream_key, sequence)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_stream ON events(stream, stream_key, sequence);",
    "CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);",
    "CREATE INDEX IF NOT EXISTS idx_events_intent ON events(operation_intent);",
    "CREATE INDEX IF NOT EXISTS idx_events_actor ON events(actor_id);",
    """
    CREATE TABLE IF NOT EXISTS relations (
        relation_id TEXT PRIMARY KEY,
        subject_id TEXT NOT NULL,
        subject_type TEXT NOT NULL,
        predicate TEXT NOT NULL,
        object_id TEXT NOT NULL,
        object_type TEXT NOT NULL,
        metadata_json TEXT,
        emitted_by TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations(subject_id, predicate);",
    "CREATE INDEX IF NOT EXISTS idx_relations_object ON relations(object_id, predicate);",
    "CREATE INDEX IF NOT EXISTS idx_relations_predicate ON relations(predicate);",
    "CREATE INDEX IF NOT EXISTS idx_relations_emitted_by ON relations(emitted_by);",
    """
    CREATE TABLE IF NOT EXISTS constraint_units (
        constraint_uid TEXT PRIMARY KEY,
        section TEXT,
        title TEXT NOT NULL,
        domain_tags TEXT,
        severity TEXT NOT NULL,
        tier TEXT NOT NULL,
        instruction TEXT NOT NULL,
        full_text TEXT,
        contract_id TEXT NOT NULL,
        contract_version TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_constraint_severity ON constraint_units(severity);",
    "CREATE INDEX IF NOT EXISTS idx_constraint_tier ON constraint_units(tier);",
    """
    CREATE TABLE IF NOT EXISTS task_profiles (
        profile_id TEXT PRIMARY KEY,
        description TEXT,
        constraint_uids TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS contracts (
        contract_id TEXT PRIMARY KEY,
        version TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        text_blob_ref TEXT NOT NULL,
        section_index_json TEXT,
        introduced_at TEXT NOT NULL,
        superseded_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS acknowledgments (
        ack_id TEXT PRIMARY KEY,
        contract_id TEXT NOT NULL,
        contract_version TEXT NOT NULL,
        text_hash TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        actor_type TEXT NOT NULL,
        acknowledged_at TEXT NOT NULL,
        event_id TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_acks_actor ON acknowledgments(actor_id);",
    """
    CREATE TABLE IF NOT EXISTS authorities (
        actor_id TEXT PRIMARY KEY,
        base_level TEXT NOT NULL,
        granted_by TEXT NOT NULL,
        effective_from TEXT NOT NULL,
        effective_until TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS grants (
        grant_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        operation_intent TEXT NOT NULL,
        scope_pattern TEXT,
        elevated_level TEXT NOT NULL,
        granted_by TEXT NOT NULL,
        granted_at TEXT NOT NULL,
        expires_at TEXT,
        single_use INTEGER NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS project_registry (
        project_id TEXT PRIMARY KEY,
        project_root TEXT NOT NULL,
        registered_at TEXT NOT NULL,
        last_seen_at TEXT,
        metadata_json TEXT
    );
    """,
)


# ----------------------------------------------------------------------------
# Migration v2 — T2.1: journal_entries (LTM activation)
# ----------------------------------------------------------------------------

_T2_1_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS journal_entries (
        entry_uid TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        kind TEXT NOT NULL,
        source TEXT NOT NULL,
        author TEXT,
        status TEXT NOT NULL DEFAULT 'open',
        importance INTEGER NOT NULL DEFAULT 5,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        body_hash TEXT NOT NULL,
        tags_json TEXT,
        related_path TEXT,
        related_ref TEXT,
        metadata_json TEXT,
        project_id TEXT,
        superseded_by TEXT,
        event_id TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_journal_kind ON journal_entries(kind);",
    "CREATE INDEX IF NOT EXISTS idx_journal_status ON journal_entries(status);",
    "CREATE INDEX IF NOT EXISTS idx_journal_created ON journal_entries(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_journal_event ON journal_entries(event_id);",
    "CREATE INDEX IF NOT EXISTS idx_journal_importance ON journal_entries(importance);",
)


# ----------------------------------------------------------------------------
# Migration v3 — T2.2: project_index + scans (Install + Scan)
# ----------------------------------------------------------------------------

_T2_2_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS project_index (
        path TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        size_bytes INTEGER,
        content_hash TEXT,
        ext TEXT,
        mtime TEXT,
        last_observed_at TEXT NOT NULL,
        last_observed_event TEXT,
        last_observed_scan TEXT,
        observe_count INTEGER NOT NULL DEFAULT 1,
        annotation_json TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_project_index_kind ON project_index(kind);",
    "CREATE INDEX IF NOT EXISTS idx_project_index_hash ON project_index(content_hash);",
    "CREATE INDEX IF NOT EXISTS idx_project_index_ext ON project_index(ext);",
    "CREATE INDEX IF NOT EXISTS idx_project_index_scan ON project_index(last_observed_scan);",
    """
    CREATE TABLE IF NOT EXISTS scans (
        scan_id TEXT PRIMARY KEY,
        project_root TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        file_count INTEGER NOT NULL DEFAULT 0,
        directory_count INTEGER NOT NULL DEFAULT 0,
        added_count INTEGER NOT NULL DEFAULT 0,
        modified_count INTEGER NOT NULL DEFAULT 0,
        removed_count INTEGER NOT NULL DEFAULT 0,
        unchanged_count INTEGER NOT NULL DEFAULT 0,
        actor_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'in_progress',
        event_id TEXT,
        summary_blob_ref TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_scans_started ON scans(started_at);",
    "CREATE INDEX IF NOT EXISTS idx_scans_status ON scans(status);",
)


# ----------------------------------------------------------------------------
# Migration v4 — T2.3: git observation + evidence + tool_registry
# ----------------------------------------------------------------------------

_T2_3_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS git_observations (
        observation_id TEXT PRIMARY KEY,
        observed_at TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        is_repo INTEGER NOT NULL,
        branch TEXT,
        head_sha TEXT,
        detached INTEGER,
        dirty_count INTEGER,
        ahead INTEGER,
        behind INTEGER,
        remote TEXT,
        remote_url TEXT,
        event_id TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_git_obs_at ON git_observations(observed_at);",
    "CREATE INDEX IF NOT EXISTS idx_git_obs_event ON git_observations(event_id);",
    """
    CREATE TABLE IF NOT EXISTS git_dirty_paths (
        observation_id TEXT NOT NULL,
        path TEXT NOT NULL,
        status TEXT NOT NULL,
        PRIMARY KEY (observation_id, path)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_git_dirty_obs ON git_dirty_paths(observation_id);",
    """
    CREATE TABLE IF NOT EXISTS evidence (
        evidence_id TEXT PRIMARY KEY,
        hash TEXT NOT NULL,
        kind TEXT NOT NULL,
        summary TEXT,
        source_event TEXT,
        source_path TEXT,
        source_line_range TEXT,
        attached_to_object TEXT,
        attached_to_type TEXT,
        status TEXT NOT NULL DEFAULT 'attached',
        created_at TEXT NOT NULL,
        verified_at TEXT,
        actor_id TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_evidence_hash ON evidence(hash);",
    "CREATE INDEX IF NOT EXISTS idx_evidence_kind ON evidence(kind);",
    "CREATE INDEX IF NOT EXISTS idx_evidence_attached ON evidence(attached_to_object);",
    """
    CREATE TABLE IF NOT EXISTS tool_registry (
        tool_name TEXT PRIMARY KEY,
        version TEXT NOT NULL,
        entrypoint TEXT NOT NULL,
        category TEXT NOT NULL,
        summary TEXT,
        mcp_name TEXT NOT NULL,
        required_authority TEXT NOT NULL,
        input_schema_json TEXT,
        source_hash TEXT,
        registered_at TEXT NOT NULL,
        last_invoked_at TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_tool_category ON tool_registry(category);",
    "CREATE INDEX IF NOT EXISTS idx_tool_mcp ON tool_registry(mcp_name);",
    """
    CREATE TABLE IF NOT EXISTS tool_invocations (
        invocation_id TEXT PRIMARY KEY,
        tool_name TEXT NOT NULL,
        envelope_id TEXT,
        event_id TEXT,
        actor_id TEXT NOT NULL,
        arguments_ref TEXT,
        result_ref TEXT,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        error_summary TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_tool_inv_name ON tool_invocations(tool_name);",
    "CREATE INDEX IF NOT EXISTS idx_tool_inv_status ON tool_invocations(status);",
    "CREATE INDEX IF NOT EXISTS idx_tool_inv_event ON tool_invocations(event_id);",
)


# ----------------------------------------------------------------------------
# Migration v5 — T2.5: Active Tranche Ledger (pre-T3 enhancement)
# Adds decision_records (typed decisions captured during work) and
# active_tranche (live accumulating object for the current tranche).
# These power the tranche_checklist projection and close_tranche orchestrator.
# ----------------------------------------------------------------------------

_T2_5_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS decision_records (
        decision_id TEXT PRIMARY KEY,
        tranche_id TEXT,
        title TEXT NOT NULL,
        context TEXT NOT NULL DEFAULT '',
        rationale TEXT NOT NULL DEFAULT '',
        outcome TEXT NOT NULL DEFAULT '',
        impact_area TEXT NOT NULL DEFAULT '',
        alternatives_json TEXT NOT NULL DEFAULT '[]',
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        tags_json TEXT NOT NULL DEFAULT '[]',
        importance INTEGER NOT NULL DEFAULT 5,
        actor_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        event_id TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_decision_tranche ON decision_records(tranche_id);",
    "CREATE INDEX IF NOT EXISTS idx_decision_actor ON decision_records(actor_id);",
    "CREATE INDEX IF NOT EXISTS idx_decision_created ON decision_records(created_at);",
    """
    CREATE TABLE IF NOT EXISTS active_tranche (
        tranche_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        declared_scope TEXT NOT NULL DEFAULT '',
        declared_non_goals TEXT NOT NULL DEFAULT '',
        declared_completion_criteria TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        started_at TEXT NOT NULL,
        closed_at TEXT,
        files_changed_json TEXT NOT NULL DEFAULT '[]',
        decisions_count INTEGER NOT NULL DEFAULT 0,
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        tests_run_json TEXT NOT NULL DEFAULT '[]',
        deviations_json TEXT NOT NULL DEFAULT '[]',
        open_questions_json TEXT NOT NULL DEFAULT '[]',
        next_tranche_candidate TEXT,
        park_notes_blob_ref TEXT,
        journal_entry_uid TEXT,
        actor_id TEXT NOT NULL,
        event_id TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_active_tranche_status ON active_tranche(status);",
)


# ----------------------------------------------------------------------------
# Migration v7 — T4: approval loop + handoff doctrine uplift
# ----------------------------------------------------------------------------

_T4_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS agent_sessions (
        session_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        channel TEXT NOT NULL,
        client_name TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        authority_level TEXT NOT NULL DEFAULT 'Propose',
        started_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        last_envelope_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_agent_sessions_actor ON agent_sessions(actor_id);",
    "CREATE INDEX IF NOT EXISTS idx_agent_sessions_seen ON agent_sessions(last_seen_at);",
    """
    CREATE TABLE IF NOT EXISTS approval_requests (
        request_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        session_id TEXT,
        source_channel TEXT NOT NULL DEFAULT '',
        requested_level TEXT NOT NULL,
        operation_intent TEXT NOT NULL,
        scope_pattern_json TEXT NOT NULL DEFAULT '{}',
        summary TEXT NOT NULL DEFAULT '',
        justification TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        requested_at TEXT NOT NULL,
        decided_at TEXT,
        decided_by TEXT,
        decision_reason TEXT NOT NULL DEFAULT '',
        grant_id TEXT,
        event_id TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_requests(status);",
    "CREATE INDEX IF NOT EXISTS idx_approval_actor ON approval_requests(actor_id);",
    "CREATE INDEX IF NOT EXISTS idx_approval_requested ON approval_requests(requested_at);",
)


# ----------------------------------------------------------------------------
# Migration v8 — T6: STM + Bag of Evidence + Evidence Shelf
# ----------------------------------------------------------------------------

_T6_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS session_memory_items (
        memory_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        layer TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        content_ref TEXT,
        source_kind TEXT NOT NULL DEFAULT '',
        source_id TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        ordinal INTEGER NOT NULL DEFAULT 0,
        promoted_to_journal_uid TEXT,
        created_at TEXT NOT NULL,
        last_accessed_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_session_memory_session_layer ON session_memory_items(session_id, layer, ordinal);",
    "CREATE INDEX IF NOT EXISTS idx_session_memory_actor ON session_memory_items(actor_id, created_at);",
    """
    CREATE TABLE IF NOT EXISTS change_hunks (
        hunk_id TEXT PRIMARY KEY,
        tranche_id TEXT,
        session_id TEXT,
        actor_id TEXT NOT NULL,
        path TEXT NOT NULL,
        old_start INTEGER NOT NULL,
        old_count INTEGER NOT NULL,
        new_start INTEGER NOT NULL,
        new_count INTEGER NOT NULL,
        added_lines INTEGER NOT NULL DEFAULT 0,
        removed_lines INTEGER NOT NULL DEFAULT 0,
        diff_text_ref TEXT NOT NULL,
        context_hash TEXT NOT NULL DEFAULT '',
        summary TEXT NOT NULL DEFAULT '',
        decision_id TEXT,
        source_event_id TEXT,
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_change_hunks_tranche ON change_hunks(tranche_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_change_hunks_session ON change_hunks(session_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_change_hunks_path ON change_hunks(path, created_at);",
    """
    ALTER TABLE proj_agent_bootstrap
    ADD COLUMN stm_json TEXT;
    """,
    """
    ALTER TABLE proj_agent_bootstrap
    ADD COLUMN bag_json TEXT;
    """,
    """
    ALTER TABLE proj_agent_bootstrap
    ADD COLUMN evidence_shelf_json TEXT;
    """,
)


# ----------------------------------------------------------------------------
# Migration v9 — T7: Run Trace, Recovery, and Operator Cockpit
# ----------------------------------------------------------------------------

_T7_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS local_agent_runs (
        run_id TEXT PRIMARY KEY,
        session_id TEXT,
        actor_id TEXT NOT NULL,
        model TEXT NOT NULL,
        status TEXT NOT NULL,
        authority_level TEXT NOT NULL DEFAULT 'Propose',
        task_summary TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL,
        ended_at TEXT,
        final_summary TEXT NOT NULL DEFAULT '',
        final_message TEXT NOT NULL DEFAULT '',
        recovery_class TEXT NOT NULL DEFAULT '',
        retryable INTEGER NOT NULL DEFAULT 0,
        operator_hint TEXT NOT NULL DEFAULT '',
        retried_from_run_id TEXT,
        last_round_index INTEGER NOT NULL DEFAULT 0,
        last_runtime_event_type TEXT NOT NULL DEFAULT '',
        journal_entry_uid TEXT,
        approval_request_id TEXT,
        approval_grant_id TEXT,
        config_snapshot_json TEXT NOT NULL DEFAULT '{}',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_local_agent_runs_started ON local_agent_runs(started_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_local_agent_runs_status ON local_agent_runs(status, started_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_local_agent_runs_session ON local_agent_runs(session_id, started_at DESC);",
    """
    CREATE TABLE IF NOT EXISTS local_agent_run_rounds (
        round_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        round_index INTEGER NOT NULL,
        status TEXT NOT NULL,
        input_summary TEXT NOT NULL DEFAULT '',
        output_summary TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL,
        ended_at TEXT,
        recovery_class TEXT NOT NULL DEFAULT '',
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_local_agent_rounds_run ON local_agent_run_rounds(run_id, round_index);",
    """
    CREATE TABLE IF NOT EXISTS local_agent_runtime_events (
        runtime_event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        round_id TEXT,
        event_type TEXT NOT NULL,
        status TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        recovery_class TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL,
        ended_at TEXT,
        linked_event_id TEXT,
        linked_tool_invocation_id TEXT,
        linked_approval_request_id TEXT,
        linked_approval_grant_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_local_agent_runtime_events_run ON local_agent_runtime_events(run_id, started_at);",
    """
    CREATE TABLE IF NOT EXISTS local_agent_run_touched_paths (
        touch_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        round_id TEXT,
        path TEXT NOT NULL,
        touch_type TEXT NOT NULL,
        status TEXT NOT NULL,
        linked_hunk_id TEXT,
        linked_evidence_id TEXT,
        linked_tool_invocation_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_local_agent_touch_run ON local_agent_run_touched_paths(run_id, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_local_agent_touch_path ON local_agent_run_touched_paths(path, created_at);",
    """
    CREATE TABLE IF NOT EXISTS local_agent_run_links (
        link_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        round_id TEXT,
        link_kind TEXT NOT NULL,
        link_ref TEXT NOT NULL,
        relation TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_local_agent_links_run ON local_agent_run_links(run_id, created_at);",
    """
    CREATE TABLE IF NOT EXISTS local_agent_claim_grounding (
        claim_grounding_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        claim_id TEXT NOT NULL,
        claim_text TEXT NOT NULL DEFAULT '',
        grounding_kind TEXT NOT NULL,
        grounding_ref TEXT NOT NULL,
        grounding_role TEXT NOT NULL DEFAULT '',
        round_id TEXT,
        runtime_event_id TEXT,
        created_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_local_agent_claim_grounding_run ON local_agent_claim_grounding(run_id, created_at);",
    """
    ALTER TABLE proj_agent_bootstrap
    ADD COLUMN runtime_summary_json TEXT;
    """,
)


# ----------------------------------------------------------------------------
# Migration v10 — T8: Teaching Sandbox + Training Runway
# ----------------------------------------------------------------------------

_T8_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS teaching_scenario_runs (
        scenario_run_id TEXT PRIMARY KEY,
        scenario_id TEXT NOT NULL,
        scenario_version TEXT NOT NULL,
        scenario_hash TEXT NOT NULL,
        run_mode TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        model TEXT NOT NULL DEFAULT '',
        sandbox_root TEXT NOT NULL,
        run_status TEXT NOT NULL,
        input_snapshot_json TEXT NOT NULL DEFAULT '{}',
        linked_run_ids_json TEXT NOT NULL DEFAULT '[]',
        scorecard_id TEXT,
        journal_entry_uid TEXT,
        reviewer_export_ref TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_teaching_scenario_runs_started ON teaching_scenario_runs(started_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_teaching_scenario_runs_scenario ON teaching_scenario_runs(scenario_id, started_at DESC);",
    """
    CREATE TABLE IF NOT EXISTS teaching_scenario_run_trace_links (
        scenario_run_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        relation TEXT NOT NULL DEFAULT 'primary_attempt',
        created_at TEXT NOT NULL,
        PRIMARY KEY (scenario_run_id, run_id, relation)
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_teaching_scenario_run_trace_links_run ON teaching_scenario_run_trace_links(run_id, created_at);",
    """
    CREATE TABLE IF NOT EXISTS teaching_scorecards (
        scorecard_id TEXT PRIMARY KEY,
        scenario_run_id TEXT NOT NULL,
        scenario_id TEXT NOT NULL,
        run_mode TEXT NOT NULL,
        aggregate_result TEXT NOT NULL,
        pass_fail_state TEXT NOT NULL,
        total_score INTEGER NOT NULL DEFAULT 0,
        max_score INTEGER NOT NULL DEFAULT 100,
        linked_run_ids_json TEXT NOT NULL DEFAULT '[]',
        dimension_scores_json TEXT NOT NULL DEFAULT '{}',
        checks_json TEXT NOT NULL DEFAULT '[]',
        failure_classes_json TEXT NOT NULL DEFAULT '[]',
        touched_path_summary_json TEXT NOT NULL DEFAULT '{}',
        evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        journal_entry_uid TEXT,
        reviewer_export_ref TEXT,
        created_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_teaching_scorecards_created ON teaching_scorecards(created_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_teaching_scorecards_result ON teaching_scorecards(aggregate_result, created_at DESC);",
    """
    CREATE TABLE IF NOT EXISTS teaching_reviewer_exports (
        export_id TEXT PRIMARY KEY,
        scenario_run_id TEXT NOT NULL,
        scorecard_id TEXT NOT NULL,
        format TEXT NOT NULL,
        blob_ref TEXT NOT NULL,
        export_path TEXT NOT NULL,
        created_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_teaching_reviewer_exports_run ON teaching_reviewer_exports(scenario_run_id, created_at DESC);",
)


# ----------------------------------------------------------------------------
# Migration v11 — T9: Installed-Project Proof + Vendability Seal
# ----------------------------------------------------------------------------

_T9_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS installed_project_proofs (
        proof_run_id TEXT PRIMARY KEY,
        fixture_id TEXT NOT NULL,
        fixture_version TEXT NOT NULL,
        host_root TEXT NOT NULL,
        installed_sidecar_root TEXT NOT NULL,
        status TEXT NOT NULL,
        install_state_json TEXT NOT NULL DEFAULT '{}',
        verification_summary_json TEXT NOT NULL DEFAULT '{}',
        proposal_summary_json TEXT NOT NULL DEFAULT '{}',
        linked_run_ids_json TEXT NOT NULL DEFAULT '[]',
        linked_scorecard_ids_json TEXT NOT NULL DEFAULT '[]',
        linked_evidence_refs_json TEXT NOT NULL DEFAULT '[]',
        linked_journal_uids_json TEXT NOT NULL DEFAULT '[]',
        approval_request_id TEXT,
        approval_grant_id TEXT,
        touched_paths_json TEXT NOT NULL DEFAULT '[]',
        hunk_refs_json TEXT NOT NULL DEFAULT '[]',
        handoff_packet_ref TEXT NOT NULL DEFAULT '',
        supersession_status TEXT NOT NULL DEFAULT '',
        started_at TEXT NOT NULL,
        ended_at TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_installed_project_proofs_started ON installed_project_proofs(started_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_installed_project_proofs_status ON installed_project_proofs(status, started_at DESC);",
)


# ----------------------------------------------------------------------------
# Migration v12 — T10: Tranche Review Gate + Horizon Semantics Hardening
# ----------------------------------------------------------------------------

_T10_DDL: tuple[str, ...] = (
    """
    ALTER TABLE active_tranche
    ADD COLUMN current_review_id TEXT;
    """,
    """
    ALTER TABLE active_tranche
    ADD COLUMN last_review_status TEXT NOT NULL DEFAULT '';
    """,
    """
    ALTER TABLE active_tranche
    ADD COLUMN last_reviewed_at TEXT;
    """,
    """
    CREATE TABLE IF NOT EXISTS tranche_review_packets (
        review_id TEXT PRIMARY KEY,
        tranche_id TEXT NOT NULL,
        status TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        generated_by_actor TEXT NOT NULL,
        review_packet_json_ref TEXT NOT NULL,
        review_packet_markdown_ref TEXT NOT NULL,
        smoke_snapshot_json TEXT NOT NULL DEFAULT '{}',
        latest_decision_ids_json TEXT NOT NULL DEFAULT '[]',
        latest_test_records_json TEXT NOT NULL DEFAULT '[]',
        reviewed_by_actor TEXT,
        reviewed_at TEXT,
        return_reason TEXT NOT NULL DEFAULT '',
        approval_notes TEXT NOT NULL DEFAULT '',
        event_id TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_tranche_review_packets_tranche ON tranche_review_packets(tranche_id, generated_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_tranche_review_packets_status ON tranche_review_packets(status, generated_at DESC);",
)


# ----------------------------------------------------------------------------
# Migration v13 — T10.2: BCC migration inventory + continuity ledger
# ----------------------------------------------------------------------------

_T10_2_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS contract_migration_nodes (
        node_id TEXT PRIMARY KEY,
        node_type TEXT NOT NULL,
        title TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_contract_migration_nodes_type ON contract_migration_nodes(node_type);",
    """
    CREATE TABLE IF NOT EXISTS contract_migration_edges (
        edge_id TEXT PRIMARY KEY,
        subject_id TEXT NOT NULL,
        predicate TEXT NOT NULL,
        object_id TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_contract_migration_edges_subject ON contract_migration_edges(subject_id, predicate);",
    "CREATE INDEX IF NOT EXISTS idx_contract_migration_edges_object ON contract_migration_edges(object_id, predicate);",
    """
    CREATE TABLE IF NOT EXISTS legacy_contract_references (
        ref_id TEXT PRIMARY KEY,
        source_path TEXT NOT NULL,
        reference_kind TEXT NOT NULL,
        legacy_ref TEXT NOT NULL,
        translated_ref TEXT NOT NULL DEFAULT '',
        translation_status TEXT NOT NULL DEFAULT 'unmapped',
        surface_class TEXT NOT NULL DEFAULT '',
        historical_preservation INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_legacy_contract_references_source ON legacy_contract_references(source_path);",
    "CREATE INDEX IF NOT EXISTS idx_legacy_contract_references_status ON legacy_contract_references(translation_status, surface_class);",
)


# ----------------------------------------------------------------------------
# Migration v14 — T10.3: documentation registry cutover
# ----------------------------------------------------------------------------

_T10_3_DDL: tuple[str, ...] = ()


# ----------------------------------------------------------------------------
# Migration v15 — T10.5: compiled BCC constraint map + bootstrap summary
# ----------------------------------------------------------------------------

_T10_5_DDL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS compiled_bcc_constraint_maps (
        map_id TEXT PRIMARY KEY,
        source_contract_path TEXT NOT NULL,
        source_contract_hash TEXT NOT NULL,
        compiler_version TEXT NOT NULL,
        payload_ref TEXT NOT NULL,
        summary_json TEXT NOT NULL DEFAULT '{}',
        generated_at TEXT NOT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_compiled_bcc_constraint_maps_hash ON compiled_bcc_constraint_maps(source_contract_hash, generated_at DESC);",
    """
    ALTER TABLE proj_agent_bootstrap
    ADD COLUMN constraint_map_summary_json TEXT;
    """,
)


# Migration registry: version → (description, list of statements).
# Migrations run in version order, idempotent.
_MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (1, "T1 spine boot — core tables + projection tables", _CORE_DDL),
    (2, "T2.1 LTM activation — journal_entries table + indices", _T2_1_DDL),
    (3, "T2.2 Install + Scan — project_index + scans tables", _T2_2_DDL),
    (4, "T2.3 Git + Evidence + Tool Registry", _T2_3_DDL),
    (5, "T2.5 Active Tranche Ledger — decision_records + active_tranche", _T2_5_DDL),
    (6, "T3 Tk monitoring UI — viewport_state projection table", ()),
    (7, "T4 Approval loop + handoff doctrine uplift", _T4_DDL),
    (8, "T6 STM + Bag of Evidence + Evidence Shelf", _T6_DDL),
    (9, "T7 Run Trace, Recovery, and Operator Cockpit", _T7_DDL),
    (10, "T8 Teaching Sandbox + Training Runway", _T8_DDL),
    (11, "T9 Installed-Project Proof + Vendability Seal", _T9_DDL),
    (12, "T10 Tranche Review Gate + Horizon Semantics Hardening", _T10_DDL),
    (13, "T10.2 BCC migration inventory + continuity ledger", _T10_2_DDL),
    (14, "T10.3 documentation registry cutover", _T10_3_DDL),
    (15, "T10.5 compiled BCC constraint map + bootstrap summary", _T10_5_DDL),
)


# ----------------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------------


class Store:
    """Single SQLite connection wrapper. T1 = single-threaded use."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self.path),
            isolation_level=None,  # autocommit; we use explicit transactions
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_pragmas()

    def _configure_pragmas(self) -> None:
        c = self._conn
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA foreign_keys=ON;")
        c.execute("PRAGMA busy_timeout=10000;")
        c.execute("PRAGMA synchronous=NORMAL;")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- DML -------------------------------------------------------------

    def execute(self, sql: str, params: Iterable[Any] | dict | None = None) -> sqlite3.Cursor:
        return self._conn.execute(sql, params or ())

    def executemany(self, sql: str, seq_params: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        return self._conn.executemany(sql, seq_params)

    def query(self, sql: str, params: Iterable[Any] | dict | None = None) -> list[sqlite3.Row]:
        cur = self._conn.execute(sql, params or ())
        return cur.fetchall()

    def query_one(self, sql: str, params: Iterable[Any] | dict | None = None) -> sqlite3.Row | None:
        cur = self._conn.execute(sql, params or ())
        return cur.fetchone()

    def executescript(self, sql: str) -> None:
        self._conn.executescript(sql)

    @contextmanager
    def transaction(self):
        try:
            self._conn.execute("BEGIN")
            yield self
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # --- Meta ------------------------------------------------------------

    def schema_version(self) -> int:
        row = self.query_one("SELECT MAX(version) AS v FROM journal_migrations;")
        return int(row["v"]) if row and row["v"] is not None else 0

    def get_meta(self, key: str) -> str | None:
        row = self.query_one("SELECT value FROM journal_meta WHERE key = ?;", (key,))
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO journal_meta(key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;",
            (key, value, now_iso()),
        )


# ----------------------------------------------------------------------------
# Migrations
# ----------------------------------------------------------------------------


def _bootstrap_meta_table(store: Store) -> None:
    """Ensure journal_migrations exists before we look at schema_version."""
    store.execute(
        """
        CREATE TABLE IF NOT EXISTS journal_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL,
            description TEXT
        );
        """
    )


def migrate(store: Store) -> list[int]:
    """Apply pending migrations in version order; return applied versions."""
    _bootstrap_meta_table(store)
    current = store.schema_version()
    applied: list[int] = []

    for version, description, statements in _MIGRATIONS:
        if version <= current:
            continue
        log.info("applying migration %s: %s", version, description)
        with store.transaction():
            for stmt in statements:
                try:
                    store.execute(stmt)
                except sqlite3.OperationalError as exc:
                    if _is_safe_duplicate_column(stmt, exc):
                        log.info("ignoring additive duplicate during migration %s: %s", version, exc)
                        continue
                    raise
            for projection in PROJECTION_NAMES:
                store.execute(table_ddl(projection))
            store.execute(
                "INSERT OR IGNORE INTO journal_migrations(version, applied_at, description) VALUES (?, ?, ?);",
                (version, now_iso(), description),
            )
        applied.append(version)

    return applied


def open_store(path: Path) -> Store:
    """Open the SQLite spine and apply pending migrations."""
    store = Store(path)
    migrate(store)
    return store


def _is_safe_duplicate_column(statement: str, exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return "duplicate column name" in message and "alter table" in statement.lower()
