"""
FILE: src/lib/bcc_constraint_map.py
ROLE: Deterministic compiler for the derived BCC constraint map.
WHAT IT DOES: Reads contracts/BCC.md, extracts a compact machine-usable
              decomposition surface by heading anchors, persists compiled maps
              as blob-backed derived state, and exposes drift facts for
              projections/bootstrap without rewriting runtime enforcement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.lib.common import gen_id, now_iso, safe_json_dumps, sha256_hex
from src.lib.contract_migration import PRIMARY_CONTRACT_REL, active_contract_path
from src.lib.doc_registry import doc_relpath
from src.schemas import contract_schema as runtime_contract_schema
from src.lib import common as runtime_common


COMPILER_VERSION = "1.0.0"
CURRENT_MAP_META_KEY = "current_bcc_constraint_map_id"
PROJECTION_REF = "projection://bcc_constraint_map"
REFRESH_COMMAND = "python -m src.app cli contract-constraint-map-refresh"

_REQUIRED_ANCHORS = (
    "Authority Levels and Approval Scope",
    "Initialization Protocol / Cold Start Rule",
    "Builder Workflow Discipline Amendment",
    "Document Authority Classes",
    "Required Project Documentation",
    "2. Root Boundary Rules",
    "6. Safe Sourcing / Extraction Rules",
    "7. Tooling Sidecar Rules",
    "10.8 Park Phase closure rule",
    "12. Prohibited Behaviors",
)

_CANONICAL_AUTHORITY_LEVELS = (
    "Observe",
    "Propose",
    "Project Apply",
    "Tooling Apply",
    "Workspace Apply",
    "Export",
)

_ARTIFACT_ZONES = (
    {
        "id": "project_root",
        "summary": "Active project build domain inside the current Project Root.",
        "origin": "derived_guidance",
        "source_sections": ["0.2 Project root", "2. Root Boundary Rules"],
    },
    {
        "id": "tooling_sidecar",
        "summary": "Project-attached but isolated Tooling Sidecar rooted inside the current Project Root.",
        "origin": "derived_guidance",
        "source_sections": ["0.27 Tooling Sidecar", "7. Tooling Sidecar Rules"],
    },
    {
        "id": "builder_memory",
        "summary": "Builder Memory Journal and Builder Memory Store continuity surfaces.",
        "origin": "derived_guidance",
        "source_sections": ["0.22 Builder memory", "Required Project Documentation"],
    },
    {
        "id": "project_workspace",
        "summary": "Broader Project Workspace outside the active Project Root.",
        "origin": "derived_guidance",
        "source_sections": ["0.1 Project Workspace root", "6.1 Project Workspace and sidecar model"],
    },
    {
        "id": "reference_reservoir",
        "summary": "Approved reference surface used for inspection and bounded extraction only.",
        "origin": "derived_guidance",
        "source_sections": ["0.28 Reference Reservoir", "6.2 Approved reference sources"],
    },
)

_REQUIRED_GATES = (
    {
        "id": "contract_doctrine_check",
        "summary": "Confirm the proposed action is authorized by BCC doctrine before acting.",
        "origin": "derived_guidance",
        "source_sections": ["Contract Use Preamble", "12.1 Contract-first prohibition rule"],
    },
    {
        "id": "authority_scope_check",
        "summary": "Match the intended action to the explicit authority floor and scope.",
        "origin": "derived_guidance",
        "source_sections": ["Authority Levels and Approval Scope"],
    },
    {
        "id": "artifact_zone_boundary_check",
        "summary": "Ensure the action stays within the allowed artifact zone boundary.",
        "origin": "derived_guidance",
        "source_sections": ["2. Root Boundary Rules", "6.1 Project Workspace and sidecar model"],
    },
    {
        "id": "approval_gate_check",
        "summary": "Pause and require explicit approval when contract coverage or scope is not already authorized.",
        "origin": "derived_guidance",
        "source_sections": ["12.3 Approval gate rule", "Authority Levels and Approval Scope"],
    },
    {
        "id": "provenance_recording_check",
        "summary": "Record sources, file changes, and phase evidence when meaningful work lands.",
        "origin": "derived_guidance",
        "source_sections": ["6.9 Provenance recording rule", "10. Reporting / Phase Output Rules"],
    },
    {
        "id": "park_review_gate_check",
        "summary": "Do not treat a tranche as complete until Park Phase and review/closure surfaces are consistent.",
        "origin": "derived_guidance",
        "source_sections": ["10.8 Park Phase closure rule", "5.13 Governed chat and projection surface rule"],
    },
)

_INTENT_CLASSES = (
    {
        "id": "inspect",
        "summary": "Read project, continuity, and approved reference surfaces without mutating state.",
        "canonical_authority_floor": "Observe",
        "artifact_zones": ["project_root", "builder_memory", "reference_reservoir"],
        "required_gates": ["contract_doctrine_check"],
        "source_sections": [
            "Authority Levels and Approval Scope",
            "Initialization Protocol / Cold Start Rule",
            "6. Safe Sourcing / Extraction Rules",
        ],
    },
    {
        "id": "propose",
        "summary": "Produce plans, drafts, and tranche framing without modifying project state.",
        "canonical_authority_floor": "Propose",
        "artifact_zones": ["project_root", "builder_memory"],
        "required_gates": ["contract_doctrine_check", "authority_scope_check"],
        "source_sections": [
            "Authority Levels and Approval Scope",
            "Builder Workflow Discipline Amendment",
        ],
    },
    {
        "id": "project_mutation",
        "summary": "Write or transform artifacts inside the active Project Root.",
        "canonical_authority_floor": "Project Apply",
        "artifact_zones": ["project_root"],
        "required_gates": [
            "contract_doctrine_check",
            "authority_scope_check",
            "artifact_zone_boundary_check",
            "approval_gate_check",
            "provenance_recording_check",
        ],
        "source_sections": [
            "Authority Levels and Approval Scope",
            "2. Root Boundary Rules",
            "10. Reporting / Phase Output Rules",
        ],
    },
    {
        "id": "tooling_sidecar_mutation",
        "summary": "Create or improve reusable sidecar/tooling surfaces inside the Tooling Sidecar.",
        "canonical_authority_floor": "Tooling Apply",
        "artifact_zones": ["tooling_sidecar"],
        "required_gates": [
            "contract_doctrine_check",
            "authority_scope_check",
            "artifact_zone_boundary_check",
            "approval_gate_check",
            "provenance_recording_check",
        ],
        "source_sections": [
            "Authority Levels and Approval Scope",
            "7. Tooling Sidecar Rules",
        ],
    },
    {
        "id": "workspace_mutation",
        "summary": "Write outside the current Project Root but within the broader Project Workspace.",
        "canonical_authority_floor": "Workspace Apply",
        "artifact_zones": ["project_workspace"],
        "required_gates": [
            "contract_doctrine_check",
            "authority_scope_check",
            "artifact_zone_boundary_check",
            "approval_gate_check",
            "provenance_recording_check",
        ],
        "source_sections": [
            "Authority Levels and Approval Scope",
            "6.1 Project Workspace and sidecar model",
        ],
    },
    {
        "id": "park_closeout",
        "summary": "Review, close, and seal a tranche with durable Park Phase records.",
        "canonical_authority_floor": "Propose",
        "artifact_zones": ["builder_memory", "project_root"],
        "required_gates": [
            "contract_doctrine_check",
            "authority_scope_check",
            "park_review_gate_check",
            "provenance_recording_check",
        ],
        "source_sections": [
            "10.8 Park Phase closure rule",
            "5.13 Governed chat and projection surface rule",
        ],
    },
    {
        "id": "export_handoff",
        "summary": "Emit bundles or handoff artifacts outside the active Project Root.",
        "canonical_authority_floor": "Export",
        "artifact_zones": ["project_workspace", "builder_memory"],
        "required_gates": [
            "contract_doctrine_check",
            "authority_scope_check",
            "approval_gate_check",
            "provenance_recording_check",
        ],
        "source_sections": [
            "Authority Levels and Approval Scope",
            "10.8 Park Phase closure rule",
        ],
    },
    {
        "id": "validate_verify",
        "summary": "Run smoke, validation, review, or structural checks appropriate to the artifact profile.",
        "canonical_authority_floor": "Observe",
        "artifact_zones": ["project_root", "builder_memory"],
        "required_gates": [
            "contract_doctrine_check",
            "authority_scope_check",
            "park_review_gate_check",
        ],
        "source_sections": [
            "9.4 Testing and task-checklist rule",
            "10.3 Testing report rule",
            "10.8 Park Phase closure rule",
        ],
    },
)

_DECOMPOSITION_HINTS = (
    {
        "intent_class": "inspect",
        "expected_next_step": "Read the relevant governing and continuity surfaces first, then summarize what is constrained and what is still unknown.",
        "expected_read_surfaces": ["contracts/BCC.md", "projection://agent_bootstrap", "projection://handoff"],
        "expected_write_surfaces": [],
        "approval_expectation": "No approval should be needed for pure inspection.",
        "park_requirement": "No Park requirement unless inspection is part of a larger tranche.",
        "compatibility_notes": [
            "Observe maps cleanly to the current runtime authority model.",
        ],
    },
    {
        "intent_class": "propose",
        "expected_next_step": "Frame scope, non-goals, completion criteria, or recommendations before any mutation path is chosen.",
        "expected_read_surfaces": ["contracts/BCC.md", "projection://agent_bootstrap", "projection://bcc_constraint_map"],
        "expected_write_surfaces": ["builder_memory"],
        "approval_expectation": "No extra approval unless the proposal hides a broader structural deviation.",
        "park_requirement": "Proposal-only work may stop without Park unless it becomes a meaningful tranche.",
        "compatibility_notes": [
            "Propose maps cleanly to the current runtime authority model.",
        ],
    },
    {
        "intent_class": "project_mutation",
        "expected_next_step": "Confirm the target stays inside the active Project Root and then use the governed mutation path.",
        "expected_read_surfaces": ["contracts/BCC.md", "projection://bcc_constraint_map", "projection://tranche_review_gate"],
        "expected_write_surfaces": ["project_root", "builder_memory"],
        "approval_expectation": "Requires explicit project-write authority when the actor does not already hold it.",
        "park_requirement": "Meaningful project mutation must be captured in tranche reporting and Park artifacts.",
        "compatibility_notes": [
            "Legacy runtime 'Apply' only aliases to 'Project Apply' when the touched zone is the main project artifact space.",
        ],
    },
    {
        "intent_class": "tooling_sidecar_mutation",
        "expected_next_step": "Treat Tooling Sidecar work as a separate authority path even though the sidecar lives inside the Project Root.",
        "expected_read_surfaces": ["contracts/BCC.md", "projection://bcc_constraint_map"],
        "expected_write_surfaces": ["tooling_sidecar", "builder_memory"],
        "approval_expectation": "Requires explicit Tooling Apply or broader explicit approval.",
        "park_requirement": "Meaningful tooling-sidecar work must still close through Park reporting.",
        "compatibility_notes": [
            "Legacy runtime 'Apply' can only be treated as a conditional compatibility alias here; BCC remains authoritative.",
        ],
    },
    {
        "intent_class": "workspace_mutation",
        "expected_next_step": "Stop unless the user has explicitly approved writes outside the active Project Root.",
        "expected_read_surfaces": ["contracts/BCC.md", "projection://bcc_constraint_map"],
        "expected_write_surfaces": ["project_workspace", "builder_memory"],
        "approval_expectation": "Explicit user approval is required.",
        "park_requirement": "Record the broader scope and approval in tranche closeout if the work becomes meaningful.",
        "compatibility_notes": [
            "Workspace Apply has no direct equivalent in the current runtime authority enum and must surface as drift.",
        ],
    },
    {
        "intent_class": "park_closeout",
        "expected_next_step": "Inspect tranche/review state, satisfy review gating, then seal through the Park path.",
        "expected_read_surfaces": ["projection://tranche_review_gate", "review://latest", "closeout://latest"],
        "expected_write_surfaces": ["builder_memory"],
        "approval_expectation": "Approval is embedded in the tranche review/park flow rather than in a generic grant.",
        "park_requirement": "Park artifacts are the required outcome for this class.",
        "compatibility_notes": [
            "Current runtime uses Propose/Apply semantics for review operations; the compiled map should remain BCC-first and treat this as guided decomposition only.",
        ],
    },
    {
        "intent_class": "export_handoff",
        "expected_next_step": "Verify the export scope and emit only through declared handoff/export surfaces.",
        "expected_read_surfaces": ["contracts/BCC.md", "projection://handoff", "projection://bcc_constraint_map"],
        "expected_write_surfaces": ["project_workspace", "builder_memory"],
        "approval_expectation": "Explicit Export authority is required.",
        "park_requirement": "Export work that closes a tranche should also be cited in Park reporting.",
        "compatibility_notes": [
            "Export maps cleanly to the current runtime authority model.",
        ],
    },
    {
        "intent_class": "validate_verify",
        "expected_next_step": "Run the narrowest verification surface that proves the intended state and report any remaining unverified assumptions.",
        "expected_read_surfaces": ["contracts/BCC.md", "projection://bcc_constraint_map", "projection://agent_bootstrap"],
        "expected_write_surfaces": ["builder_memory"],
        "approval_expectation": "Pure verification normally stays within Observe, but any side effects must follow the normal authority path.",
        "park_requirement": "Park requires explicit verification or an explicit statement of what remains unverified.",
        "compatibility_notes": [
            "Observe maps cleanly; any legacy runtime execution mode should not be confused with a BCC authority level.",
        ],
    },
)

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.*)$")
_ABSOLUTE_WINDOWS_RE = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass(frozen=True)
class CompiledMapRecord:
    map_id: str
    source_contract_path: str
    source_contract_hash: str
    compiler_version: str
    payload_ref: str
    summary: dict[str, Any]
    generated_at: str
    payload: dict[str, Any]


def ensure_current_bcc_constraint_map(state) -> CompiledMapRecord:
    current = current_bcc_constraint_map(state)
    if current is not None:
        return current
    return refresh_bcc_constraint_map(state)


def refresh_bcc_constraint_map(state) -> CompiledMapRecord:
    payload = compile_bcc_constraint_map(state.sidecar_root)
    summary = summarize_bcc_constraint_map(payload)
    payload_ref = state.blob_store.put_json(payload)
    record = {
        "map_id": gen_id("bcc_map_"),
        "source_contract_path": payload["source_contract_path"],
        "source_contract_hash": payload["source_contract_hash"],
        "compiler_version": payload["compiler_version"],
        "payload_ref": payload_ref,
        "summary_json": safe_json_dumps(summary),
        "generated_at": payload["generated_at"],
    }
    with state.store.transaction():
        state.store.execute(
            """
            INSERT INTO compiled_bcc_constraint_maps(
                map_id, source_contract_path, source_contract_hash,
                compiler_version, payload_ref, summary_json, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                record["map_id"],
                record["source_contract_path"],
                record["source_contract_hash"],
                record["compiler_version"],
                record["payload_ref"],
                record["summary_json"],
                record["generated_at"],
            ),
        )
        state.store.set_meta(CURRENT_MAP_META_KEY, record["map_id"])
    return current_bcc_constraint_map(state, record["map_id"])  # type: ignore[return-value]


def current_bcc_constraint_map(state, map_id: str = "") -> CompiledMapRecord | None:
    selected_id = map_id or (state.store.get_meta(CURRENT_MAP_META_KEY) or "")
    row = None
    if selected_id:
        row = state.store.query_one(
            "SELECT * FROM compiled_bcc_constraint_maps WHERE map_id = ? LIMIT 1;",
            (selected_id,),
        )
    if row is None and not selected_id:
        row = state.store.query_one(
            "SELECT * FROM compiled_bcc_constraint_maps ORDER BY generated_at DESC LIMIT 1;"
        )
    if row is None:
        return None
    payload = state.blob_store.get_json(row["payload_ref"])
    summary = _json_loads_dict(row["summary_json"])
    return CompiledMapRecord(
        map_id=str(row["map_id"]),
        source_contract_path=str(row["source_contract_path"]),
        source_contract_hash=str(row["source_contract_hash"]),
        compiler_version=str(row["compiler_version"]),
        payload_ref=str(row["payload_ref"]),
        summary=summary,
        generated_at=str(row["generated_at"]),
        payload=payload if isinstance(payload, dict) else {},
    )


def compile_bcc_constraint_map(sidecar_root: str | Path) -> dict[str, Any]:
    sidecar_root = Path(sidecar_root)
    contract_path = active_contract_path(sidecar_root)
    if not contract_path.is_file():
        raise FileNotFoundError(f"missing canonical contract file: {PRIMARY_CONTRACT_REL}")
    contract_bytes = contract_path.read_bytes()
    contract_text = contract_bytes.decode("utf-8")
    sections = _parse_sections(contract_text)
    missing = [anchor for anchor in _REQUIRED_ANCHORS if anchor not in sections]
    if missing:
        raise ValueError(f"required BCC anchors missing: {missing}")

    source_hash = f"sha256:{sha256_hex(contract_bytes)}"
    generated_at = now_iso()
    authority_model = _build_authority_model()
    document_authority_classes = _build_document_authority_classes(sections)
    cold_start_read_order = _build_cold_start_read_order()
    park_phase_requirements = _build_park_phase_requirements(sections)
    prohibited_patterns = _build_prohibited_patterns(sections)

    payload: dict[str, Any] = {
        "projection_type": "bcc_constraint_map",
        "status": "derived_non_authoritative",
        "compiler_version": COMPILER_VERSION,
        "source_contract_path": PRIMARY_CONTRACT_REL,
        "source_contract_hash": source_hash,
        "generated_at": generated_at,
        "conflict_rule": "BCC.md wins",
        "regeneration_required_if_hash_mismatch": True,
        "source_sections": list(_REQUIRED_ANCHORS),
        "authority_model": authority_model,
        "document_authority_classes": document_authority_classes,
        "cold_start_read_order": cold_start_read_order,
        "artifact_zones": list(_ARTIFACT_ZONES),
        "required_gates": list(_REQUIRED_GATES),
        "park_phase_requirements": park_phase_requirements,
        "prohibited_patterns": prohibited_patterns,
        "intent_classes": list(_INTENT_CLASSES),
        "decomposition_hints": list(_DECOMPOSITION_HINTS),
    }
    return payload


def summarize_bcc_constraint_map(payload: dict[str, Any]) -> dict[str, Any]:
    authority_model = payload.get("authority_model") or {}
    park = payload.get("park_phase_requirements") or {}
    return {
        "status": str(payload.get("status", "derived_non_authoritative")),
        "source_contract_path": str(payload.get("source_contract_path", PRIMARY_CONTRACT_REL)),
        "source_contract_hash": str(payload.get("source_contract_hash", "")),
        "compiler_version": str(payload.get("compiler_version", COMPILER_VERSION)),
        "canonical_authority_levels": list(authority_model.get("canonical_levels") or []),
        "runtime_authority_drift_detected": bool(authority_model.get("drift_detected", False)),
        "intent_classes": [item.get("id", "") for item in (payload.get("intent_classes") or []) if isinstance(item, dict)],
        "artifact_zones": [item.get("id", "") for item in (payload.get("artifact_zones") or []) if isinstance(item, dict)],
        "required_gates": [item.get("id", "") for item in (payload.get("required_gates") or []) if isinstance(item, dict)],
        "park_requirements_summary": {
            "required_preconditions": list(park.get("required_preconditions") or []),
            "required_outputs": list(park.get("required_outputs") or []),
        },
    }


def build_bcc_constraint_projection_row(state) -> dict[str, Any]:
    live_hash = _live_contract_hash(state.sidecar_root)
    contract_record_hash = f"sha256:{state.current_contract.get('text_hash', '')}" if (state.current_contract or {}).get("text_hash") else ""
    record = current_bcc_constraint_map(state)
    if record is None:
        drift = {
            "authority_model_mismatch": False,
            "contract_record_hash_mismatch": False,
            "absolute_path_leak_detected": False,
        }
        return {
            "status": "missing",
            "source_contract_path": PRIMARY_CONTRACT_REL,
            "live_contract_hash": live_hash,
            "contract_record_hash": contract_record_hash,
            "compiled_contract_hash": "",
            "hash_match": 0,
            "compiler_version": COMPILER_VERSION,
            "generated_at": "",
            "payload_json": safe_json_dumps({}),
            "summary_json": safe_json_dumps({}),
            "drift_json": safe_json_dumps(drift),
            "guidance_allowed": 0,
            "refresh_hint": REFRESH_COMMAND,
        }

    payload = record.payload
    compiled_hash = str(payload.get("source_contract_hash", record.source_contract_hash))
    authority_drift = bool((payload.get("authority_model") or {}).get("drift_detected", False))
    absolute_path_leak_detected = bool(_contains_absolute_path(payload))
    contract_record_hash_mismatch = bool(contract_record_hash and contract_record_hash != live_hash)
    hash_match = int(compiled_hash == live_hash)
    status = "ready"
    if compiled_hash != live_hash:
        status = "stale_contract_hash"
    if not isinstance(payload, dict):
        status = "error"
    drift = {
        "authority_model_mismatch": authority_drift,
        "contract_record_hash_mismatch": contract_record_hash_mismatch,
        "absolute_path_leak_detected": absolute_path_leak_detected,
    }
    guidance_allowed = int(status == "ready" and not absolute_path_leak_detected)
    return {
        "status": status,
        "source_contract_path": PRIMARY_CONTRACT_REL,
        "live_contract_hash": live_hash,
        "contract_record_hash": contract_record_hash,
        "compiled_contract_hash": compiled_hash,
        "hash_match": hash_match,
        "compiler_version": record.compiler_version,
        "generated_at": record.generated_at,
        "payload_json": safe_json_dumps(payload),
        "summary_json": safe_json_dumps(record.summary),
        "drift_json": safe_json_dumps(drift),
        "guidance_allowed": guidance_allowed,
        "refresh_hint": REFRESH_COMMAND,
    }


def build_bootstrap_constraint_summary(state) -> dict[str, Any]:
    row = build_bcc_constraint_projection_row(state)
    payload = _json_loads_dict(row["payload_json"])
    summary = _json_loads_dict(row["summary_json"])
    authority_model = payload.get("authority_model") or {}
    return {
        "status": row["status"],
        "guidance_allowed": bool(row["guidance_allowed"]),
        "source_contract_hash": row["live_contract_hash"],
        "compiled_contract_hash": row["compiled_contract_hash"],
        "canonical_authority_levels": list(authority_model.get("canonical_levels") or summary.get("canonical_authority_levels") or []),
        "runtime_authority_drift_detected": bool(authority_model.get("drift_detected", summary.get("runtime_authority_drift_detected", False))),
        "intent_classes": list(summary.get("intent_classes") or []),
        "artifact_zones": list(summary.get("artifact_zones") or []),
        "required_gates": list(summary.get("required_gates") or []),
        "park_requirements_summary": dict(summary.get("park_requirements_summary") or {}),
        "full_projection_ref": PROJECTION_REF,
        "refresh_command": REFRESH_COMMAND,
    }


def _build_authority_model() -> dict[str, Any]:
    runtime_levels_common = list(getattr(runtime_common, "AUTHORITY_LEVELS", ()))
    runtime_levels_contract_schema = list(getattr(runtime_contract_schema, "AUTHORITY_LEVELS", ()))
    runtime_defaults = {
        "agent": getattr(runtime_contract_schema, "DEFAULT_AGENT_AUTHORITY", ""),
        "human": getattr(runtime_contract_schema, "DEFAULT_HUMAN_AUTHORITY", ""),
        "system": getattr(runtime_contract_schema, "DEFAULT_SYSTEM_AUTHORITY", ""),
        "tool": getattr(runtime_contract_schema, "DEFAULT_TOOL_AUTHORITY", ""),
    }
    drift_bits: list[str] = []
    if runtime_levels_common != list(_CANONICAL_AUTHORITY_LEVELS):
        drift_bits.append("src.lib.common AUTHORITY_LEVELS does not match the canonical BCC authority ladder")
    if runtime_levels_contract_schema != list(_CANONICAL_AUTHORITY_LEVELS):
        drift_bits.append("src.schemas.contract_schema AUTHORITY_LEVELS does not match the canonical BCC authority ladder")
    if "Sandbox Execute" in runtime_levels_common or "Sandbox Execute" in runtime_levels_contract_schema:
        drift_bits.append("Sandbox Execute is present in the runtime authority model but has no canonical BCC equivalent")
    if "Workspace Apply" not in runtime_levels_common or "Workspace Apply" not in runtime_levels_contract_schema:
        drift_bits.append("Workspace Apply is not directly represented in the current runtime authority model")
    return {
        "canonical_levels": list(_CANONICAL_AUTHORITY_LEVELS),
        "runtime_levels_common": runtime_levels_common,
        "runtime_levels_contract_schema": runtime_levels_contract_schema,
        "runtime_default_authorities": runtime_defaults,
        "drift_detected": bool(drift_bits),
        "drift_summary": drift_bits,
        "aliases": [
            {
                "runtime_level": "Apply",
                "canonical_level": "Project Apply",
                "condition": "Only when the touched zone is the main project artifact space.",
                "origin": "derived_guidance",
            },
            {
                "runtime_level": "Apply",
                "canonical_level": "Tooling Apply",
                "condition": "Compatibility hint only when the touched zone is the Tooling Sidecar; BCC remains authoritative.",
                "origin": "derived_guidance",
            },
            {
                "runtime_level": "Sandbox Execute",
                "canonical_level": None,
                "condition": "Legacy runtime-only level with no canonical BCC equivalent.",
                "origin": "derived_guidance",
            },
        ],
        "resolution_status": "exposed_not_corrected",
    }


def _build_document_authority_classes(sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    mapping = (
        ("binding_doctrine", "A. Binding doctrine"),
        ("project_binding_artifact", "B. Project binding artifact"),
        ("target_state_and_architecture_doctrine", "C. Target-state and architecture doctrine"),
        ("current_state_continuity", "D. Current-state continuity"),
        ("historical_records", "E. Historical records"),
        ("generated_mirrors_and_projections", "F. Generated mirrors and projections"),
    )
    items: list[dict[str, Any]] = []
    for item_id, title in mapping:
        body = _normalized_excerpt(sections[title]["body"])
        items.append(
            {
                "id": item_id,
                "title": title,
                "summary": _first_sentence(body),
                "excerpt": body,
                "origin": "direct_extract",
                "source_section": title,
            }
        )
    return items


def _build_cold_start_read_order() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "surface": "contracts/BCC.md",
            "summary": "Read the binding doctrine first.",
            "origin": "derived_guidance",
            "source_sections": ["Contract Use Preamble", "Initialization Protocol / Cold Start Rule"],
        },
        {
            "order": 2,
            "surface": "project_binding_artifact",
            "summary": "Resolve local concrete bindings from the Project Binding Artifact.",
            "origin": "derived_guidance",
            "source_sections": ["Initialization Protocol / Cold Start Rule", "Appendix B. Project Binding Artifact"],
        },
        {
            "order": 3,
            "surface": "target_state_and_architecture",
            "summary": "Inspect architecture and target-state doctrine surfaces.",
            "origin": "derived_guidance",
            "source_sections": ["Initialization Protocol / Cold Start Rule", "Document Authority Classes"],
        },
        {
            "order": 4,
            "surface": "builder_memory_surfaces",
            "summary": "Inspect Builder Memory Journal and Builder Memory Store continuity surfaces.",
            "origin": "derived_guidance",
            "source_sections": ["Initialization Protocol / Cold Start Rule", "Required Project Documentation"],
        },
        {
            "order": 5,
            "surface": "provenance_surfaces",
            "summary": "Inspect provenance surfaces before broader public-facing summaries.",
            "origin": "derived_guidance",
            "source_sections": ["Initialization Protocol / Cold Start Rule"],
        },
        {
            "order": 6,
            "surface": "tool_manifest_surfaces",
            "summary": "Inspect tool and manifest surfaces before relying on convenience docs.",
            "origin": "derived_guidance",
            "source_sections": ["Initialization Protocol / Cold Start Rule", "Required Project Documentation"],
        },
        {
            "order": 7,
            "surface": "validation_surfaces",
            "summary": "Inspect validation and testing surfaces before declaring the next tranche path.",
            "origin": "derived_guidance",
            "source_sections": ["Initialization Protocol / Cold Start Rule", "10.8 Park Phase closure rule"],
        },
        {
            "order": 8,
            "surface": "README.md",
            "summary": "Read public-facing orientation only after the higher-authority surfaces above.",
            "origin": "derived_guidance",
            "source_sections": ["Initialization Protocol / Cold Start Rule", "Document Authority Classes"],
        },
    ]


def _build_park_phase_requirements(sections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    body = _normalized_excerpt(sections["10.8 Park Phase closure rule"]["body"])
    return {
        "origin": "direct_extract",
        "source_section": "10.8 Park Phase closure rule",
        "summary": _first_sentence(body),
        "required_preconditions": [
            "verification_or_explicit_unverified_statement",
            "durable_builder_memory_record",
            "mutually_consistent_closure_surfaces",
        ],
        "required_outputs": [
            "tranche_journal_entry",
            "sealed_park_notes_artifact",
            "updated_continuity_surfaces",
            "tranche_closing_event_trail",
            "final_closure_record",
        ],
        "excerpt": body,
    }


def _build_prohibited_patterns(sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    lines = [
        item.strip()[2:].strip()
        for item in sections["12.4 General prohibited examples"]["body"].splitlines()
        if item.strip().startswith("- ")
    ]
    patterns = [
        (
            "unauthorized_out_of_root_write",
            "Writing outside the current Project Root without explicit authorization.",
        ),
        (
            "hidden_reference_runtime_dependency",
            "Creating runtime dependency on the Reference Reservoir, Tooling Sidecar, or sibling projects.",
        ),
        (
            "silent_spine_bypass",
            "Silently bypassing the declared hierarchy and routing model.",
        ),
        (
            "imposed_application_scaffold",
            "Imposing an application scaffold on a non-application project without need or approval.",
        ),
    ]
    line_lookup = " ".join(lines)
    return [
        {
            "id": item_id,
            "summary": summary,
            "origin": "direct_extract",
            "source_section": "12.4 General prohibited examples",
            "excerpt_present": summary.lower().split()[0] in line_lookup.lower(),
        }
        for item_id, summary in patterns
    ]


def _parse_sections(text: str) -> dict[str, dict[str, Any]]:
    lines = text.splitlines()
    headings: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if not match:
            continue
        headings.append({"level": len(match.group(1)), "title": match.group(2).strip(), "line": index})
    sections: dict[str, dict[str, Any]] = {}
    for i, heading in enumerate(headings):
        start = heading["line"] + 1
        end = len(lines)
        for next_heading in headings[i + 1:]:
            if next_heading["level"] <= heading["level"]:
                end = next_heading["line"]
                break
        body = "\n".join(lines[start:end]).strip()
        sections[str(heading["title"])] = {
            "level": heading["level"],
            "body": body,
        }
    return sections


def _normalized_excerpt(body: str) -> str:
    return "\n".join(line.rstrip() for line in body.strip().splitlines() if line.strip())


def _first_sentence(text: str) -> str:
    normalized = text.replace("\n", " ").strip()
    if not normalized:
        return ""
    match = re.search(r"(?<=[.!?])\s", normalized)
    return normalized[:match.start()].strip() if match else normalized


def _contains_absolute_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    if isinstance(value, str):
        text = value.strip()
        if _ABSOLUTE_WINDOWS_RE.match(text):
            return True
        if text.startswith("\\\\"):
            return True
        if text.startswith("/") and not text.startswith("//"):
            return True
    return False


def _live_contract_hash(sidecar_root: str | Path) -> str:
    path = active_contract_path(Path(sidecar_root))
    return f"sha256:{sha256_hex(path.read_bytes())}" if path.is_file() else ""


def _json_loads_dict(raw: str) -> dict[str, Any]:
    try:
        value = __import__("json").loads(raw or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}
