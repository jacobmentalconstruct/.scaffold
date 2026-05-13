"""
FILE: src/core/state.py
ROLE: SidecarState — central in-memory registry of "what is true right now."
WHAT IT DOES: Holds the live references and small set of volatile facts the
              spine needs without round-tripping to disk on every envelope.
              Construction is wholesale (in app.py); mutation is via narrow
              setters used by the boot sequence and by event commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.lib.common import public_root_labels


@dataclass
class SidecarState:
    sidecar_root: Path
    project_root: Path
    sidecar_id: str
    project_id: str = ""

    # Filled in during app.py wiring (after construction).
    store: Any = None
    blob_store: Any = None
    events: Any = None
    graph: Any = None
    constraint_manager: Any = None
    contract_authority: Any = None
    projections: Any = None
    journal_manager: Any = None
    project_index_manager: Any = None
    evidence_manager: Any = None
    git_state_manager: Any = None
    tool_registry_manager: Any = None
    tranche_manager: Any = None
    file_scanner: Any = None
    install_orchestrator: Any = None
    scan_orchestrator: Any = None
    agent_task_orchestrator: Any = None
    closeout_orchestrator: Any = None
    router: Any = None

    # Live registries (read-mostly; updated by event commit).
    registered_objects: dict = field(default_factory=dict)
    registered_tools: dict = field(default_factory=dict)
    active_task: dict | None = None
    current_projections: dict = field(default_factory=dict)
    event_log_position: int = 0

    # Status snapshots refreshed by managers.
    journal_state: dict = field(default_factory=dict)
    evidence_bag_state: dict = field(default_factory=dict)
    ontology_state: dict = field(default_factory=dict)
    agent_status: dict = field(default_factory=dict)
    human_ui_status: dict = field(default_factory=dict)

    # Contract record (loaded by ContractAuthority).
    current_contract: dict | None = None

    @classmethod
    def bootstrap(
        cls,
        sidecar_root: Path,
        project_root: Path,
        store,
        sidecar_id: str | None = None,
        project_id: str = "",
    ) -> "SidecarState":
        sidecar_id = sidecar_id or _resolve_or_create_sidecar_id(store)
        return cls(
            sidecar_root=Path(sidecar_root),
            project_root=Path(project_root),
            sidecar_id=sidecar_id,
            project_id=project_id,
            store=store,
        )

    def snapshot(self) -> dict:
        """Serializable view, for projections."""
        project_root_label, sidecar_root_label = public_root_labels(
            self.sidecar_root, self.project_root
        )
        return {
            "sidecar_root": sidecar_root_label,
            "project_root": project_root_label,
            "sidecar_id": self.sidecar_id,
            "project_id": self.project_id,
            "registered_object_count": len(self.registered_objects),
            "registered_tool_count": len(self.registered_tools),
            "active_task_id": (self.active_task or {}).get("task_id"),
            "event_log_position": self.event_log_position,
            "current_contract_hash": (self.current_contract or {}).get("text_hash"),
            "current_contract_acked": bool((self.current_contract or {}).get("acked_by")),
            "agent_status": dict(self.agent_status),
            "human_ui_status": dict(self.human_ui_status),
        }

    # --- narrow mutators (called by event commit) ----------------------

    def advance_event_position(self, by: int = 1) -> None:
        self.event_log_position += by

    def set_current_projection(self, name: str, snapshot: dict) -> None:
        self.current_projections[name] = snapshot

    def set_current_contract(self, contract: dict) -> None:
        self.current_contract = contract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_or_create_sidecar_id(store) -> str:
    """Read sidecar_id from journal_meta; if absent, generate and persist."""
    from src.lib.common import gen_id

    existing = store.get_meta("sidecar_id")
    if existing:
        return existing
    new_id = gen_id("sc_")
    store.set_meta("sidecar_id", new_id)
    return new_id
