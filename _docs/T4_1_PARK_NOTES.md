# Park Notes — T4.1 Deferred Backlog Normalization

> Generated: 2026-05-13T03:37:18.969Z | Status: sealed | tranche_id: tranche_18af02a6da1d7284_9429a3f5
> Started: 2026-05-13T03:34:53.481Z

## Declared Scope
Normalize all explicitly deferred work into tranche-owned roadmap entries and open journal todos so carry-forward work lives in project state, not only in prose.

### Non-goals
Do not begin T5 runtime implementation; do not resolve the deferred items themselves.

### Completion Criteria
Every explicit deferred item is mapped to a tranche or horizon in the roadmap and mirrored as open todo journal entries visible through projections/UI.

## Decisions Recorded
_1 decision(s) captured during this tranche._

### Deferred work must live in roadmap plus open todo journal entries
**Impact area:** continuity

**Context:** Several deferred items were still scattered across architecture notes, roadmap prose, and park artifacts, which made carry-forward work easy to miss during onboarding or resumption.

**Rationale:** The contract and architecture already say deferred work belongs in durable project state rather than chat memory. Mapping every deferred item to an owner tranche and mirroring it into open todos makes the backlog visible to humans, agents, UI surfaces, and projections.

**Outcome:** Normalize deferred work into a tranche-owned backlog in IMPLEMENTATION_ROADMAP.md and seed matching open journal todo entries until each item is resolved or superseded.

_decision_id: decision_18af02a85dfbfb4c_d56aaaf2 | importance: 5_

## Files Changed
- `IMPLEMENTATION_ROADMAP.md` (modified)
- `ARCHITECTURE.md` (modified)
- `WE_ARE_HERE_NOW.md` (modified)
- `NORTHSTARS.md` (modified)
- `ONBOARDING.md` (modified)
- `SOURCE_PROVENANCE.md` (modified)
- `DEV_LOG.md` (modified)
- `src/core/projections.py` (modified)

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-13T03:37:13.282Z)

## Next Tranche
T5 Local Sidecar Agent Reintegration

## Additional Notes
Normalized the deferred backlog into a tranche-owned roadmap table and 12 open todo journal entries. Future surfaces now expose the carry-forward list directly via journal-query, viewport_state, and the handoff flow. This tranche intentionally did not begin T5 runtime work; it prepared the substrate so deferred work is durable, queryable, and visible to a cold team.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-13T03:37:18.969Z._
_Source: tranche_id=tranche_18af02a6da1d7284_9429a3f5_
