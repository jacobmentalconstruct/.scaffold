"""
FILE: src/components/manifest_generator.py
ROLE: Generates config/toolbox_manifest.json and config/tool_manifest.json
      from current runtime state (tool registry, projections, etc.).
WHAT IT DOES: Called by app.boot() after tool discovery. Both manifests
              are *derived state* — regeneratable from the DB; they live
              in config/ for human inspection and external-tool consumption
              (zero-context agent entry).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.lib.contract_migration import PRIMARY_CONTRACT_REL
from src.lib.common import now_iso, public_path, safe_json_dumps
from src.lib.doc_registry import doc_relpath
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.core.state import SidecarState


log = get_logger("components.manifest_generator")


MANIFEST_VERSION = "1.0.0"
SIDECAR_NAME = "scaffold-sidecar"
SIDECAR_VERSION = "0.1.0"


def generate_tool_manifest(state: "SidecarState", config_dir: Path) -> Path:
    """Write config/tool_manifest.json — auto-generated per-tool index."""
    tools = state.tool_registry_manager.list_tools()
    categories: dict[str, list[str]] = {}
    for t in tools:
        categories.setdefault(t.category, []).append(t.tool_name)
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": now_iso(),
        "sidecar_id": state.sidecar_id,
        "tool_count": len(tools),
        "tools": [
            {
                "tool_name": t.tool_name,
                "version": t.version,
                "entrypoint": t.entrypoint,
                "category": t.category,
                "summary": t.summary,
                "mcp_name": t.mcp_name,
                "required_authority": t.required_authority,
                "input_schema": t.input_schema,
                "result_envelope_keys": ["status", "tool", "input", "result"],
                "source_hash": t.source_hash,
                "registered_at": t.registered_at,
            }
            for t in sorted(tools, key=lambda x: x.tool_name)
        ],
        "categories": {k: sorted(v) for k, v in sorted(categories.items())},
    }
    target = Path(config_dir) / "tool_manifest.json"
    target.write_text(safe_json_dumps(payload, indent=2), encoding="utf-8")
    log.info("wrote %s (%d tools)", public_path(target, config_dir.parent, "."), len(tools))
    return target


def generate_toolbox_manifest(state: "SidecarState", config_dir: Path) -> Path:
    """Write config/toolbox_manifest.json — zero-context agent entry descriptor."""
    contract = state.current_contract or {}
    sidecar_root = state.sidecar_root
    onboarding_rel = doc_relpath(sidecar_root, "onboarding")
    project_bindings_rel = doc_relpath(sidecar_root, "project_bindings")
    architecture_rel = doc_relpath(sidecar_root, "architecture")
    roadmap_rel = doc_relpath(sidecar_root, "implementation_roadmap")
    tools_rel = doc_relpath(sidecar_root, "tools_index")
    provenance_rel = doc_relpath(sidecar_root, "source_provenance")
    migration_inventory_rel = doc_relpath(sidecar_root, "incorporation_inventory")
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "sidecar_name": SIDECAR_NAME,
        "sidecar_version": SIDECAR_VERSION,
        "sidecar_id": state.sidecar_id,
        "generated_at": now_iso(),
        "sidecar_root_marker": ".scaffold",
        "host_invariant": "the host project does not import from .scaffold/",

        "zero_context_entry_protocol": {
            "step_1": "Read contracts/BCC.md first.",
            "step_2": f"Inspect {project_bindings_rel} as the local Project Binding Artifact defined by BCC Appendix B.",
            "step_3": f"Use {onboarding_rel} only as a convenience orientation surface derived from the contract and the local binding artifact.",
            "step_4": "Read this manifest in full.",
            "step_5": "Call read_projection(name='agent_bootstrap') for the live PAST/PRESENT/FUTURE summary.",
            "step_6": "Acknowledge the contract before meaningful work and begin under Observe or Propose authority.",
            "linked_contract": PRIMARY_CONTRACT_REL,
            "linked_project_bindings": project_bindings_rel,
            "linked_architecture": architecture_rel,
            "linked_roadmap": roadmap_rel,
            "linked_onboarding": onboarding_rel,
        },

        "current_contract": {
            "contract_id": contract.get("contract_id"),
            "version": contract.get("version"),
            "text_hash": contract.get("text_hash"),
            "ack_count": len(contract.get("acked_by") or []),
        },

        "tiers": {
            "builder_tools": "src/tools/ — see config/tool_manifest.json for per-tool details",
            "vendable_packages": [],
            "vendable_documents": [
                {"name": "README.md", "purpose": "human-facing introduction"},
                {"name": project_bindings_rel, "purpose": "repo-local path and surface bindings"},
                {"name": onboarding_rel, "purpose": "explicit reading order for a cold agent or human"},
                {"name": architecture_rel, "purpose": "design truth"},
                {"name": roadmap_rel, "purpose": "tranche-by-tranche build plan and current status"},
                {"name": tools_rel, "purpose": "human-readable tool index"},
                {"name": provenance_rel, "purpose": "what was original code vs structurally borrowed"},
                {"name": migration_inventory_rel, "purpose": "precursor review and triage"},
            ],
        },

        "authority_levels": ["Observe", "Propose", "Sandbox Execute", "Apply", "Export"],
        "default_agent_authority": "Propose",

        "projections": sorted(state.projections.list()),
        "event_streams": ["project", "task", "object", "tool"],

        "memory_model": {
            "ltm": "Everything persistent on disk: journal, logs, projections, project code, sidecar code, contract.",
            "stm": "Sliding window in agent context (managed by the agent's runtime, not the sidecar).",
            "bag_of_evidence": "Bridge layer between STM overflow and LTM. Reserved schema; deferred implementation (DP1).",
            "temporal_directions": "agent_bootstrap projection carries PAST + PRESENT + FUTURE — see ARCHITECTURE.md §3.6.",
        },

        "spine_rule": (
            "Interface -> Envelope -> Router -> ContractCheck -> Orchestrator -> Manager "
            "-> Event -> derived views. No sideways calls. The envelope is the only currency."
        ),

        "park_phase_discipline": (
            "Every tranche closes per BCC §10.8 / ARCHITECTURE.md §12.2. Five artifacts required: "
            "(a) tranche journal entry, (b) park-notes blob, (c) continuity docs updated, "
            "(d) accept_task + complete_task events, (e) close_journal_entry. "
            "smoke_test.py enforces drift detection."
        ),

        "verification_commands": [
            "python -m src.app cli version",
            "python -m src.app cli list-projections",
            "python -m src.app cli tool-list",
            "python -m src.app cli journal-query --kind tranche",
            "python smoke_test.py",
        ],

        "schema_version": state.store.schema_version(),
        "event_count": state.events.total_count(),
        "tool_count": state.tool_registry_manager.count(),
        "journal_count": state.journal_manager.count(),

        "linked_resources": {
            "tool_manifest": "config/tool_manifest.json",
            "sidecar_db": "data/sidecar.db",
            "contract": PRIMARY_CONTRACT_REL,
            "project_bindings": project_bindings_rel,
            "architecture": architecture_rel,
            "roadmap": roadmap_rel,
            "onboarding": onboarding_rel,
            "source_provenance": provenance_rel,
        },
    }
    target = Path(config_dir) / "toolbox_manifest.json"
    target.write_text(safe_json_dumps(payload, indent=2), encoding="utf-8")
    log.info("wrote %s", public_path(target, config_dir.parent, "."))
    return target


def generate_all(state: "SidecarState", config_dir: Path) -> dict[str, Path]:
    """Generate both manifests; return paths."""
    return {
        "tool_manifest": generate_tool_manifest(state, config_dir),
        "toolbox_manifest": generate_toolbox_manifest(state, config_dir),
    }
