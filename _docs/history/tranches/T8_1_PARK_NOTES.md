# Park Notes — T8.1 Post-Park Training Handoff Alignment

> Generated: 2026-05-14T00:47:55.983Z | Status: sealed | tranche_id: tranche_18af47f0614da9d4_9bd53ca6
> Started: 2026-05-14T00:44:35.584Z

## Declared Scope
Small continuity follow-up after T8 close to reconcile roadmap parsing and parked handoff/bootstrap surfaces so T9 outcome-driven planning remains visible to smoke, agents, and cold-team onboarding.

### Completion Criteria
- agent_bootstrap.next_planned_steps_json is non-empty with T9 parked as next horizon.\n- python smoke_test.py passes after the parser fix.\n- continuity surfaces remain aligned and the branch ends with no active tranche open.

## Decisions Recorded
_1 decision(s) captured during this tranche._

### Fall back from roadmap file lists to completion criteria for next-step parsing
**Impact area:** architecture

**Context:** T8 closed cleanly, but smoke exposed that agent_bootstrap.next_planned_steps_json became empty because T9 is described by proof-oriented completion criteria rather than target files.

**Rationale:** Cold-start handoff surfaces must survive roadmap sections that are outcome-first instead of file-first, especially late in the program when vendability proof matters more than file inventory.

**Outcome:** Update roadmap parsing to derive next planned steps from file/surface lists first, then completion criteria, then scope sentences as a final fallback.

_decision_id: decision_18af481cf2dbd2a0_a68ad4c8 | importance: 7_

## Files Changed
- `src/core/projections.py` (modified)
- `README.md` (modified)
- `WE_ARE_HERE_NOW.md` (modified)
- `DEV_LOG.md` (modified)
- `IMPLEMENTATION_ROADMAP.md` (modified)
- `ARCHITECTURE.md` (modified)
- `SOURCE_PROVENANCE.md` (modified)

## Tests Run
- `python smoke_test.py` → PASS (at 2026-05-14T00:47:51.211Z)

## Additional Notes
T8.1 exists solely to seal the post-T8 continuity bug uncovered by smoke: the roadmap parser previously emitted an empty next_planned_steps_json when the next tranche was described by completion criteria rather than target files. The fix keeps T9 visible to agent_bootstrap, handoff, and cold-team onboarding without widening T8 scope.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-14T00:47:55.983Z._
_Source: tranche_id=tranche_18af47f0614da9d4_9bd53ca6_
