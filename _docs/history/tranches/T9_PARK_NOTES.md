# Park Notes — T9 Installed-Project Proof + Vendability Seal

> Generated: 2026-05-14T11:56:53.773Z | Status: sealed | tranche_id: tranche_18af48de3d38b1f8_234b2628
> Started: 2026-05-14T01:01:37.181Z

## Declared Scope
Vendability proof tranche: create one tiny installed-project fixture, install a clean .scaffold into it, prove first boot plus governed proposal-approval-bounded-mutation in the installed context, surface the result through CLI/projections/Tk, and seal formal supersession with only trust-gate hardening.

### Non-goals
No new major substrate layers, no broad curriculum expansion, no large real-world host migration, no full load suite, no unbounded autonomous mutation.

### Completion Criteria
- One fresh installed-project proving loop completes end to end.\n- A cold operator can inspect the installed proof using docs, DB, UI, projections, and verification commands alone.\n- Formal supersession of the old experiment is recorded and the branch parks with no active tranche open.

## Decisions Recorded
_1 decision(s) captured during this tranche._

### Keep T9 as a vendability proof tranche
**Impact area:** process

**Context:** T9 could have expanded into broad post-baseline hardening work instead of a crisp fresh-host proof.

**Rationale:** The substrate needed one inspectable installed-project proof more than another feature expansion tranche.

**Outcome:** T9 centers on one tiny fresh-host install, governed mutation proof, cold-team handoff packet, and only trust-gate hardening required to make that proof credible.

_decision_id: decision_18af6c556f2a7ee0_fbad50cf | importance: 9_

## Files Changed
- `src/managers/installed_project_proof_manager.py` (added)
- `src/ui/installed_project_proof_panel.py` (added)
- `src/components/sqlite_store.py` (modified)
- `src/core/contracts.py` (modified)
- `src/core/projections.py` (modified)
- `src/interfaces/cli_interface.py` (modified)
- `src/app.py` (modified)
- `smoke_test.py` (modified)
- `README.md` (modified)
- `ONBOARDING.md` (modified)
- `WE_ARE_HERE_NOW.md` (modified)
- `IMPLEMENTATION_ROADMAP.md` (modified)
- `ARCHITECTURE.md` (modified)
- `NORTHSTARS.md` (modified)
- `DEV_LOG.md` (modified)
- `SOURCE_PROVENANCE.md` (modified)
- `TOOLS.md` (modified)

## Tests Run
- `python smoke_test.py` → PASS (at 2026-05-14T11:56:53.764Z)

## Additional Notes
Installed-project proof fixture: workspaces/installed_project_proof/tiny_notes_app/. Successful proof run ids include proof_run_18af6bba61f19740_953e88c4 and subsequent smoke-backed proof runs. T9 establishes the vendable baseline and formal supersession of the older experiment.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-14T11:56:53.773Z._
_Source: tranche_id=tranche_18af48de3d38b1f8_234b2628_
