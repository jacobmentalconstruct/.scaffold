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

from src.lib.common import now_iso, safe_json_dumps
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
    log.info("wrote %s (%d tools)", target, len(tools))
    return target


def generate_toolbox_manifest(state: "SidecarState", config_dir: Path) -> Path:
    """Write config/toolbox_manifest.json — zero-context agent entry descriptor."""
    contract = state.current_contract or {}
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "sidecar_name": SIDECAR_NAME,
        "sidecar_version": SIDECAR_VERSION,
        "sidecar_id": state.sidecar_id,
        "generated_at": now_iso(),
        "sidecar_root_marker": ".scaffold",
        "host_invariant": "the host project does not import from .scaffold/",

        "zero_context_entry_protocol": {
            "step_1": "Read ONBOARDING.md at the sidecar root.",
            "step_2": "Read this manifest in full.",
            "step_3": "Read contracts/builder_constrant_contract.md and acknowledge it.",
            "step_4": "Call read_projection(name='agent_bootstrap') for the live PAST/PRESENT/FUTURE summary.",
            "step_5": "Begin meaningful work under Observe or Propose authority.",
            "linked_contract": "contracts/builder_constrant_contract.md",
            "linked_architecture": "ARCHITECTURE.md",
            "linked_roadmap": "IMPLEMENTATION_ROADMAP.md",
            "linked_onboarding": "ONBOARDING.md",
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
                {"name": "ONBOARDING.md", "purpose": "explicit reading order for a cold agent or human"},
                {"name": "ARCHITECTURE.md", "purpose": "design truth"},
                {"name": "IMPLEMENTATION_ROADMAP.md", "purpose": "tranche-by-tranche build plan and current status"},
                {"name": "TOOLS.md", "purpose": "human-readable tool index"},
                {"name": "SOURCE_PROVENANCE.md", "purpose": "what was original code vs structurally borrowed"},
                {"name": "_docs/INCORPORATION_INVENTORY.md", "purpose": "precursor review and triage"},
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
            "Every tranche closes per contract §D / ARCHITECTURE.md §12.2. Five artifacts required: "
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
            "contract": "contracts/builder_constrant_contract.md",
            "architecture": "ARCHITECTURE.md",
            "roadmap": "IMPLEMENTATION_ROADMAP.md",
            "onboarding": "ONBOARDING.md",
            "source_provenance": "SOURCE_PROVENANCE.md",
        },
    }
    target = Path(config_dir) / "toolbox_manifest.json"
    target.write_text(safe_json_dumps(payload, indent=2), encoding="utf-8")
    log.info("wrote %s", target)
    return target


def generate_all(state: "SidecarState", config_dir: Path) -> dict[str, Path]:
    """Generate both manifests; return paths."""
    return {
        "tool_manifest": generate_tool_manifest(state, config_dir),
        "toolbox_manifest": generate_toolbox_manifest(state, config_dir),
    }
