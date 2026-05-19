# Park Notes — T3 Tk Monitoring UI

> Generated: 2026-05-13T00:46:26.057Z | Status: sealed | tranche_id: tranche_18aef88dee7b4b48_fc6c4123
> Started: 2026-05-13T00:29:51.333Z

## Declared Scope
Implement a Tkinter-native observational monitoring console using the Unified Tri-Temporal mock as reference, preserving broad visibility across sidecar state, events, tools, evidence, tranche status, contract status, and planning state.

### Non-goals
No state-changing UI actions, no approval workflow, no browser runtime, no external dependencies, no host-project mutation from the UI.

### Completion Criteria
python -m src.app ui opens a Tk monitoring window; the home view surfaces past/present/future monitoring data from real projections; journal/evidence/project/tool/contract/tranche visibility is reachable; smoke_test.py passes; T3 is properly parked.

## Decisions Recorded
_2 decision(s) captured during this tranche._

### Use viewport_state as the aggregated Tk dashboard read model
**Impact area:** architecture

**Context:** The Tk monitoring console needs broad observability without each widget directly reconstructing state from many tables and projections.

**Rationale:** A single aggregated projection keeps the dashboard declarative while detailed tabs can still read the existing projections directly. This preserves spine discipline and avoids a parallel ad hoc UI data model.

**Outcome:** Add a real viewport_state projection for topbar, focus counts, tri-temporal dashboard content, drift status, and log summaries. Keep detailed tabs backed by current_sidecar_state, journal_timeline, evidence_bag, project_map, and contract_status.

_decision_id: decision_18aef8a5b4490768_535d7e5a | importance: 9_

### Keep T3 Tk UI observational-only
**Impact area:** scope

**Context:** The immediate user need is rich monitoring and drill-down into everything the sidecar can see, while avoiding premature workflow controls in the UI.

**Rationale:** An observational-only T3 keeps the UI aligned with the contract, reduces risk, and maximizes visibility first. State-changing controls can be introduced later with explicit approval workflows.

**Outcome:** T3 ships navigation, filtering, selection-linked detail panes, and polling-based monitoring only. No UI-triggered scan, journal write, approval, Apply, Export, or host-project actions land in this tranche.

_decision_id: decision_18aef8a73700686c_dd8cd070 | importance: 9_

## Files Changed
- `src/schemas/projection_schema.py` (modified)
- `src/core/state.py` (modified)
- `src/core/projections.py` (modified)
- `src/components/sqlite_store.py` (modified)
- `src/app.py` (modified)
- `src/ui/main_window.py` (modified)
- `src/ui/state_panel.py` (modified)
- `src/ui/journal_panel.py` (modified)
- `src/ui/evidence_panel.py` (modified)
- `src/ui/project_map_panel.py` (modified)
- `src/ui/contracts_panel.py` (modified)
- `smoke_test.py` (modified)
- `README.md` (modified)
- `ONBOARDING.md` (modified)
- `IMPLEMENTATION_ROADMAP.md` (modified)
- `ARCHITECTURE.md` (modified)
- `SOURCE_PROVENANCE.md` (modified)

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-13T00:46:21.410Z)

## Additional Notes
T3 preserved Tkinter as the product identity, used .parts/UI_Concept as a visual/layout reference only, and intentionally shipped as an observational monitoring console with no UI-triggered mutation path.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-13T00:46:26.057Z._
_Source: tranche_id=tranche_18aef88dee7b4b48_fc6c4123_
