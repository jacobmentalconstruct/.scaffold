# Park Notes — T4 Approval Loop + Handoff Doctrine Uplift

> Generated: 2026-05-13T02:44:40.422Z | Status: sealed | tranche_id: tranche_18aefe95dc5220dc_2b56d961
> Started: 2026-05-13T02:20:22.457Z

## Declared Scope
Implement proposal approval mutation flow, add codified cold-team handoff continuity docs and surfaces, and restore the first bounded mutation path through the sidecar spine.

### Non-goals
No full local-agent runtime yet unless only narrow substrate foundations fit cleanly inside T4; no training harness reincorporation in this tranche; no broad host-project filesystem authority.

### Completion Criteria
Connected agents can submit proposals through MCP, proposals appear in Tk for human approval, approved bounded text mutations execute through the spine, new continuity docs are codified and smoke-enforced, and the tranche parks cleanly.

## Decisions Recorded
_3 decision(s) captured during this tranche._

### Treat T4 as the first strangler parity tranche
**Impact area:** scope

**Context:** The full supersession program is multi-tranche, but implementation must start with the smallest sequential step that makes the sidecar materially more complete without skipping Park Phase discipline.

**Rationale:** Approval loop plus handoff doctrine uplift is the narrowest tranche that unlocks real human-agent work while preserving the current architecture and leaving the local-agent/runtime/training reintegration for subsequent tranches.

**Outcome:** T4 will implement proposal approval mutation flow, codified continuity docs, and derived handoff surfaces first. Later tranches will pull the old local-agent system back in on top of that substrate.

_decision_id: decision_18aefe95ddc62e90_6634eb80 | importance: 5_

### Keep T4 mutation flow workspace-first
**Impact area:** architecture

**Context:** T4 needed a real approval-gated write path, but the substrate is not ready to normalize broad host-project writes as the default proof path.

**Rationale:** Using sidecar workspaces for the first approved mutation proves the approval loop and grant model while preserving the contract boundary and leaving host-project promotion as a later explicit decision.

**Outcome:** text_file_writer and directory_scaffold default to target_domain=workspace; host-project writes require explicit opt-in and remain a later expansion concern.

_decision_id: decision_18aeffe4c66ed544_3113884c | importance: 8_

### Keep T4 mutation flow workspace-first
**Impact area:** architecture

**Context:** T4 needed a real approval-gated write path, but the substrate is not ready to normalize broad host-project writes as the default proof path.

**Rationale:** Using sidecar workspaces for the first approved mutation proves the approval loop and grant model while preserving the contract boundary and leaving host-project promotion as a later explicit decision.

**Outcome:** text_file_writer and directory_scaffold default to target_domain=workspace; host-project writes require explicit opt-in and remain a later expansion concern.

_decision_id: decision_18aeffe6954cf430_830778a9 | importance: 8_

## Files Changed
- `src/lib/text_workspace.py` (added)
- `src/managers/agent_session_manager.py` (added)
- `src/managers/human_approval_manager.py` (added)
- `src/tools/text_file_writer.py` (added)
- `src/tools/directory_scaffold.py` (added)
- `src/interfaces/mcp_interface.py` (modified)
- `src/interfaces/cli_interface.py` (modified)
- `src/core/contracts.py` (modified)
- `src/core/projections.py` (modified)
- `src/ui/contracts_panel.py` (modified)
- `src/ui/main_window.py` (modified)
- `src/ui/handoff_panel.py` (added)
- `src/components/sqlite_store.py` (modified)
- `src/schemas/projection_schema.py` (modified)
- `src/schemas/contract_schema.py` (modified)
- `README.md` (modified)
- `ONBOARDING.md` (modified)
- `IMPLEMENTATION_ROADMAP.md` (modified)
- `ARCHITECTURE.md` (modified)
- `SOURCE_PROVENANCE.md` (modified)
- `TOOLS.md` (modified)
- `contracts/builder_constraint_contract.md` (modified)
- `DEV_LOG.md` (added)
- `WE_ARE_HERE_NOW.md` (added)
- `NORTHSTARS.md` (added)

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-13T02:44:20.900Z)

## Additional Notes
T4 establishes the first full proposal-approval-bounded-mutation loop and codifies cold-team handoff as first-class project state. T5 should focus on reincorporating the local Ollama sidecar agent on top of this substrate.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-13T02:44:40.422Z._
_Source: tranche_id=tranche_18aefe95dc5220dc_2b56d961_
