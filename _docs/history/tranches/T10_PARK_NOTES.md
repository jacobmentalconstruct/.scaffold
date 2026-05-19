# Park Notes — T10 Tranche Review Gate + Horizon Semantics Hardening

> Generated: 2026-05-14T23:56:02.825Z | Status: sealed | tranche_id: tranche_18af73b084ee909c_c9522605
> Started: 2026-05-14T14:06:19.816Z

## Declared Scope
Add a mechanically generated pre-park review gate, require explicit human review approval before Park Phase, and fix latest parked tranche vs next horizon wording semantics across docs, projections, CLI, and Tk.

### Non-goals
Do not replace the existing Park Phase artifact set; do not introduce autonomous approval; do not spawn a new tranche on review return; do not broaden authority semantics outside this review gate path.

### Completion Criteria
A tranche can move active -> review_pending -> review_approved -> parked, review packets are generated mechanically and surfaced through CLI/Tk/projections, close_tranche is blocked before review approval, parked-state wording uses Next horizon instead of Active horizon, and smoke proves the new lifecycle and wording semantics.

## Decisions Recorded
_1 decision(s) captured during this tranche._

### Split tranche closure into Review Gate then Park Phase
**Impact area:** process

**Context:** T10 exposed a real process gap: Park Phase could seal before an explicit human checkpoint, and horizon wording could remain mechanically consistent but semantically ambiguous.

**Rationale:** Mechanically compiled review packets preserve reliable facts while keeping acceptance human-governed; returning the same tranche avoids ledger fragmentation and preserves continuity.

**Outcome:** Tranche lifecycle now becomes active -> review_pending -> review_approved -> parked, close_tranche is blocked before review approval, and current tranche vs next horizon semantics are surfaced distinctly in CLI/Tk/docs/projections.

_decision_id: decision_18af753639074840_77716cf2 | importance: 9_

## Files Changed
- `src/components/sqlite_store.py` (modified)
- `src/schemas/projection_schema.py` (modified)
- `src/schemas/contract_schema.py` (modified)
- `src/managers/tranche_manager.py` (modified)
- `src/orchestrators/closeout_orchestrator.py` (modified)
- `src/core/router.py` (modified)
- `src/core/projections.py` (modified)
- `src/interfaces/cli_interface.py` (modified)
- `src/ui/main_window.py` (modified)
- `src/ui/handoff_panel.py` (modified)
- `src/ui/tranche_review_panel.py` (added)
- `smoke_test.py` (modified)
- `contracts/builder_constraint_contract.md` (modified)
- `ARCHITECTURE.md` (modified)
- `ONBOARDING.md` (modified)
- `WE_ARE_HERE_NOW.md` (modified)
- `NORTHSTARS.md` (modified)

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-14T14:33:03.311Z)
- `smoke_test.py` → PASS (at 2026-05-14T14:34:13.541Z)

## Open Questions (carry forward)
- smoke review return for T10 gate coverage _(raised 2026-05-14T14:33:03.446Z)_

## Next Tranche
T10 broader post-baseline hardening horizon remains open after this slice

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-14T23:56:02.825Z._
_Source: tranche_id=tranche_18af73b084ee909c_c9522605_
