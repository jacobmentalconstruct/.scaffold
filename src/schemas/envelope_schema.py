"""
FILE: src/schemas/envelope_schema.py
ROLE: Declarative shape of SidecarEnvelope.
WHAT IT DOES: Names the eighteen frozen fields, declares required vs
              system-populated, and provides validate() for envelope dicts.
"""

from __future__ import annotations

from typing import Any


ENVELOPE_SCHEMA_VERSION = "1.0.0"


# The eighteen frozen fields, in canonical order.
ENVELOPE_FIELDS = (
    "envelope_version",
    "object_id",
    "object_type",
    "project_id",
    "sidecar_id",
    "actor_id",
    "created_at",
    "operation_intent",
    "status",
    "source_refs",
    "relation_refs",
    "contract_refs",
    "evidence_refs",
    "event_id",
    "correlation_id",
    "causation_id",
    "surface_manifest",
    "payload_ref",
)


# Fields the caller must supply when constructing a new envelope.
REQUIRED_AT_CONSTRUCTION = (
    "object_type",
    "actor_id",
    "operation_intent",
)


# Fields the system populates if the caller leaves them empty.
SYSTEM_POPULATED = (
    "envelope_version",
    "object_id",
    "project_id",
    "sidecar_id",
    "created_at",
    "status",
    "correlation_id",
    "surface_manifest",
)


# Fields the EventStore writes (caller and gate leave empty).
SET_BY_EVENT_STORE = ("event_id",)


VALID_STATUSES = (
    "draft",
    "submitted",
    "accepted",
    "rejected",
    "completed",
    "failed",
)


# Field types for shallow validation (str | list | dict).
_FIELD_TYPES = {
    "envelope_version": str,
    "object_id": str,
    "object_type": str,
    "project_id": str,
    "sidecar_id": str,
    "actor_id": str,
    "created_at": str,
    "operation_intent": str,
    "status": str,
    "source_refs": list,
    "relation_refs": list,
    "contract_refs": list,
    "evidence_refs": list,
    "event_id": str,
    "correlation_id": str,
    "causation_id": str,
    "surface_manifest": dict,
    "payload_ref": str,
}


def validate(envelope_dict: dict) -> list[str]:
    """Return a list of validation errors (empty if valid)."""
    errors: list[str] = []

    for field in ENVELOPE_FIELDS:
        if field not in envelope_dict:
            errors.append(f"missing field: {field}")

    if errors:
        return errors

    for field, expected_type in _FIELD_TYPES.items():
        value = envelope_dict.get(field)
        if value is None:
            errors.append(f"field {field}: cannot be None (use empty string/list/dict)")
            continue
        if not isinstance(value, expected_type):
            errors.append(
                f"field {field}: expected {expected_type.__name__}, got {type(value).__name__}"
            )

    status = envelope_dict.get("status")
    if status and status not in VALID_STATUSES:
        errors.append(f"field status: invalid value {status!r}; must be one of {VALID_STATUSES}")

    if not envelope_dict.get("object_type"):
        errors.append("field object_type: must be non-empty")
    if not envelope_dict.get("operation_intent"):
        errors.append("field operation_intent: must be non-empty")
    if not envelope_dict.get("actor_id"):
        errors.append("field actor_id: must be non-empty")

    relation_refs = envelope_dict.get("relation_refs", [])
    for i, rel in enumerate(relation_refs):
        if not isinstance(rel, dict):
            errors.append(f"relation_refs[{i}]: must be a dict, got {type(rel).__name__}")
            continue
        if "predicate" not in rel:
            errors.append(f"relation_refs[{i}]: missing 'predicate'")

    return errors


SURFACE_NAMES = ("routing", "authority", "request", "scope", "evidence", "result", "trace")


def default_surface_manifest() -> dict:
    return {
        "routing": True,
        "authority": True,
        "request": True,
        "scope": True,
        "evidence": False,
        "result": False,
        "trace": True,
    }
