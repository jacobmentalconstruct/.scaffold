"""
FILE: src/core/envelope.py
ROLE: SidecarEnvelope — the unified message shape. The only currency through
      the spine.
WHAT IT DOES: Frozen dataclass with the 18 fields + factory + surface
              accessors + JSON round-trip + validation delegation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from src.lib.common import (
    ENVELOPE_VERSION_CURRENT,
    gen_correlation_id,
    gen_envelope_id,
    now_iso,
)
from src.schemas.envelope_schema import (
    ENVELOPE_FIELDS,
    SURFACE_NAMES,
    default_surface_manifest,
    validate as schema_validate,
)


@dataclass(frozen=True)
class SidecarEnvelope:
    envelope_version: str
    object_id: str
    object_type: str
    project_id: str
    sidecar_id: str
    actor_id: str
    created_at: str
    operation_intent: str
    status: str
    source_refs: list = field(default_factory=list)
    relation_refs: list = field(default_factory=list)
    contract_refs: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)
    event_id: str = ""
    correlation_id: str = ""
    causation_id: str = ""
    surface_manifest: dict = field(default_factory=dict)
    payload_ref: str = ""

    # ---- factory ------------------------------------------------------

    @classmethod
    def new(
        cls,
        *,
        object_type: str,
        actor_id: str,
        operation_intent: str,
        project_id: str = "",
        sidecar_id: str = "",
        source_refs: list | None = None,
        relation_refs: list | None = None,
        contract_refs: list | None = None,
        evidence_refs: list | None = None,
        causation_id: str = "",
        correlation_id: str = "",
        payload_ref: str = "",
        surface_manifest: dict | None = None,
        object_id: str = "",
        status: str = "submitted",
    ) -> "SidecarEnvelope":
        env = cls(
            envelope_version=ENVELOPE_VERSION_CURRENT,
            object_id=object_id or gen_envelope_id(),
            object_type=object_type,
            project_id=project_id,
            sidecar_id=sidecar_id,
            actor_id=actor_id,
            created_at=now_iso(),
            operation_intent=operation_intent,
            status=status,
            source_refs=list(source_refs or []),
            relation_refs=list(relation_refs or []),
            contract_refs=list(contract_refs or []),
            evidence_refs=list(evidence_refs or []),
            event_id="",
            correlation_id=correlation_id or gen_correlation_id(),
            causation_id=causation_id,
            surface_manifest=dict(surface_manifest or default_surface_manifest()),
            payload_ref=payload_ref,
        )
        return env

    # ---- mutators (return new instance) -------------------------------

    def with_event_id(self, event_id: str) -> "SidecarEnvelope":
        return replace(self, event_id=event_id)

    def with_status(self, status: str) -> "SidecarEnvelope":
        return replace(self, status=status)

    def with_payload_ref(self, payload_ref: str) -> "SidecarEnvelope":
        return replace(self, payload_ref=payload_ref)

    def with_relation_refs(self, relation_refs: list) -> "SidecarEnvelope":
        return replace(self, relation_refs=list(relation_refs))

    # ---- surface accessor ---------------------------------------------

    def surface(self, name: str) -> dict:
        """Return the named surface as a dict.

        Surfaces are NOT independent fields — they are slices of the
        envelope's data interpreted through the lens of one consumer.
        """
        if name not in SURFACE_NAMES:
            raise KeyError(f"unknown surface: {name}")
        if name == "routing":
            return {
                "object_id": self.object_id,
                "object_type": self.object_type,
                "operation_intent": self.operation_intent,
                "surface_manifest": dict(self.surface_manifest),
            }
        if name == "authority":
            return {
                "actor_id": self.actor_id,
                "contract_refs": list(self.contract_refs),
                "project_id": self.project_id,
                "sidecar_id": self.sidecar_id,
            }
        if name == "request":
            return {
                "operation_intent": self.operation_intent,
                "payload_ref": self.payload_ref,
            }
        if name == "scope":
            return {
                "object_id": self.object_id,
                "source_refs": list(self.source_refs),
                "relation_refs": list(self.relation_refs),
            }
        if name == "evidence":
            return {"evidence_refs": list(self.evidence_refs)}
        if name == "result":
            return {"status": self.status, "payload_ref": self.payload_ref}
        if name == "trace":
            return {
                "event_id": self.event_id,
                "correlation_id": self.correlation_id,
                "causation_id": self.causation_id,
                "created_at": self.created_at,
            }
        raise KeyError(name)  # unreachable

    # ---- (de)serialization --------------------------------------------

    def to_dict(self) -> dict:
        return {f: getattr(self, f) for f in ENVELOPE_FIELDS}

    @classmethod
    def from_dict(cls, d: dict) -> "SidecarEnvelope":
        kwargs = {f: d.get(f, "" if f not in ("source_refs", "relation_refs",
                                              "contract_refs", "evidence_refs",
                                              "surface_manifest") else None)
                  for f in ENVELOPE_FIELDS}
        # Default container types
        for k in ("source_refs", "relation_refs", "contract_refs", "evidence_refs"):
            if kwargs.get(k) is None:
                kwargs[k] = []
        if kwargs.get("surface_manifest") is None:
            kwargs["surface_manifest"] = {}
        return cls(**kwargs)

    def validate(self) -> list[str]:
        return schema_validate(self.to_dict())
