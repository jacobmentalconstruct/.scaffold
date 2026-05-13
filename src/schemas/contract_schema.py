"""
FILE: src/schemas/contract_schema.py
ROLE: Declarative shapes for contract records, acknowledgments, authorities,
      grants, plus the operation_intent → required-authority mapping.
WHAT IT DOES: Names the fields and provides required_authority(intent).
"""

from __future__ import annotations


# Authority levels in ascending order.
AUTHORITY_LEVELS = (
    "Observe",
    "Propose",
    "Sandbox Execute",
    "Apply",
    "Export",
)


SEVERITY_LEVELS = ("HARD_BLOCK", "PUSHBACK", "ADVISORY")
TIER_LEVELS = ("spirit", "letter", "gate")


CONTRACT_RECORD_FIELDS = (
    "contract_id",
    "version",
    "text_hash",
    "text_blob_ref",
    "section_index_json",
    "introduced_at",
    "superseded_at",
)


ACKNOWLEDGMENT_FIELDS = (
    "ack_id",
    "contract_id",
    "contract_version",
    "text_hash",
    "actor_id",
    "actor_type",
    "acknowledged_at",
    "event_id",
)


AUTHORITY_RECORD_FIELDS = (
    "actor_id",
    "base_level",
    "granted_by",
    "effective_from",
    "effective_until",
)


GRANT_FIELDS = (
    "grant_id",
    "actor_id",
    "operation_intent",
    "scope_pattern",
    "elevated_level",
    "granted_by",
    "granted_at",
    "expires_at",
    "single_use",
    "consumed",
)


CONSTRAINT_UNIT_FIELDS = (
    "constraint_uid",
    "section",
    "title",
    "domain_tags",
    "severity",
    "tier",
    "instruction",
    "full_text",
    "contract_id",
    "contract_version",
    "created_at",
)


TASK_PROFILE_FIELDS = (
    "profile_id",
    "description",
    "constraint_uids",
    "created_at",
)


# Default actor authority assignments.
DEFAULT_AGENT_AUTHORITY = "Propose"
DEFAULT_HUMAN_AUTHORITY = "Apply"
DEFAULT_SYSTEM_AUTHORITY = "Apply"
DEFAULT_TOOL_AUTHORITY = "Observe"


# Canonical mapping: operation_intent → required authority level.
INTENT_REQUIRED_AUTHORITY: dict[str, str] = {
    # bootstrap / contract — Observe gate, but acknowledgment is special-cased.
    "acknowledge_contract": "Observe",
    "install": "Observe",
    "seed_constraints": "Observe",

    # observe / scan
    "scan": "Observe",
    "rescan_path": "Observe",
    "observe_file": "Observe",
    "observe_git": "Observe",
    "record_observed_file": "Observe",
    "snapshot": "Apply",
    "project_map_updated": "Observe",

    # tool registry
    "register_tool": "Apply",
    "unregister_tool": "Apply",
    "tool_invoked": "Observe",
    "tool_result": "Observe",
    "tool_failed": "Observe",

    # journal
    "create_journal_entry": "Propose",
    "update_journal_entry": "Propose",
    "close_journal_entry": "Propose",
    "archive_journal_entry": "Propose",

    # evidence
    "attach_evidence": "Propose",
    "verify_evidence": "Observe",

    # tasks
    "accept_task": "Propose",
    "complete_task": "Propose",
    "supersede_task": "Propose",
    "request_authority_elevation": "Propose",
    "approve_authority_request": "Apply",
    "reject_authority_request": "Apply",

    # constraint registry
    "register_constraint": "Apply",
    "register_profile": "Apply",

    # project registry
    "register_project": "Apply",

    # mutating
    "apply_patch": "Apply",
    "scaffold_into_project": "Apply",
    "export_bundle": "Export",
    "export_journal_bundle": "Export",
}


def required_authority(operation_intent: str) -> str:
    """Return the required authority level for an intent.

    Default for unknown intents is 'Apply' (fail-closed)."""
    return INTENT_REQUIRED_AUTHORITY.get(operation_intent, "Apply")


# Operation intents that are exempt from contract acknowledgment requirement
# (the bootstrap exception — see contracts.py and ARCHITECTURE.md §5).
BOOTSTRAP_EXEMPT_INTENTS = (
    "acknowledge_contract",
    "install",
    "seed_constraints",
)
