"""
FILE: src/schemas/event_schema.py
ROLE: Declarative shape of an event row + the operation_intent → stream
      dispatch table.
WHAT IT DOES: Defines event row columns (including reserved nullable
              fields per Tranche B Q4) and the canonical INTENT_STREAM
              mapping.
"""

from __future__ import annotations


EVENT_SCHEMA_VERSION = "1.0.0"


# Core event row columns (always present on every event).
EVENT_CORE_FIELDS = (
    "event_id",
    "stream",
    "stream_key",
    "sequence",
    "envelope_version",
    "operation_intent",
    "actor_id",
    "project_id",
    "sidecar_id",
    "correlation_id",
    "causation_id",
    "contract_refs",
    "payload_ref",
    "evidence_refs",
    "relation_refs",
    "status",
    "created_at",
    "envelope_blob",
)


# Reserved nullable fields (Tranche B Q4).
RESERVED_RECOVERY_FIELDS = (
    "recovery_class",
    "recovery_decision",
    "evidence_id",
)

RESERVED_SESSION_TRAINING_FIELDS = (
    "session_id",
    "run_id",
    "scenario_id",
    "run_mode",
    "timeout_seconds",
    "max_tool_rounds",
    "score_result",
    "pass_fail_state",
    "touched_paths",
)

RESERVED_JOURNAL_FIELDS = (
    "journal_entry_id",
    "is_durable",
    "append_only",
)


VALID_STREAMS = ("project", "task", "object", "tool")


# Canonical mapping of operation_intent → stream.
# An intent not present here defaults to "object" with a logged warning.
INTENT_STREAM: dict[str, str] = {
    # project stream
    "install": "project",
    "scan": "project",
    "snapshot": "project",
    "project_map_updated": "project",
    "rescan_path": "project",

    # task stream
    "task_created": "task",
    "task_superseded": "task",
    "task_completed": "task",
    "accept_task": "task",
    "complete_task": "task",
    "supersede_task": "task",
    "request_authority_elevation": "task",

    # object stream
    "create_journal_entry": "object",
    "update_journal_entry": "object",
    "close_journal_entry": "object",
    "archive_journal_entry": "object",
    "acknowledge_contract": "object",
    "observe_file": "object",
    "observe_git": "object",
    "record_observed_file": "object",
    "attach_evidence": "object",
    "verify_evidence": "object",
    "register_constraint": "object",
    "register_profile": "object",
    "seed_constraints": "object",
    "register_project": "object",

    # tool stream
    "tool_invoked": "tool",
    "tool_result": "tool",
    "tool_failed": "tool",
    "register_tool": "tool",
    "unregister_tool": "tool",
}


def stream_for(operation_intent: str) -> str:
    return INTENT_STREAM.get(operation_intent, "object")


def stream_key_for(envelope_dict: dict) -> str:
    """Derive a stream partition key from an envelope.

    Heuristic: project events partition by project_id; task events partition
    by correlation_id (a workflow's events share one); object events
    partition by object_id; tool events partition by operation_intent
    so failures cluster.
    """
    stream = stream_for(envelope_dict.get("operation_intent", ""))
    if stream == "project":
        return envelope_dict.get("project_id", "") or "self"
    if stream == "task":
        return envelope_dict.get("correlation_id", "") or "default"
    if stream == "tool":
        return envelope_dict.get("operation_intent", "tool")
    return envelope_dict.get("object_id", "") or "default"


def validate_event_row(row: dict) -> list[str]:
    """Return validation errors for an event row dict."""
    errors: list[str] = []
    for field in EVENT_CORE_FIELDS:
        if field not in row:
            errors.append(f"missing core field: {field}")
    if row.get("stream") not in VALID_STREAMS:
        errors.append(f"invalid stream: {row.get('stream')!r}")
    if row.get("status") != "accepted":
        errors.append(f"events must have status='accepted', got {row.get('status')!r}")
    return errors
