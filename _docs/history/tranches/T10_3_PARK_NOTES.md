# Park Notes — T10.3 Explicit Authority Registration Hardening

> Generated: 2026-05-19T00:34:26.857Z | Status: sealed | tranche_id: tranche_18b0aa38ccddb648_7dcdb358
> Started: 2026-05-18T12:56:53.743Z

## Declared Scope
Reduce remaining reliance on default-by-prefix authority inference by persisting explicit authority rows for non-session actors as they first traverse the spine, and prove that behavior in smoke.

### Non-goals
No new second authority path, no broad grant-model redesign, and no incompatible identity migration yet.

### Completion Criteria
Non-session actors that route through the spine gain durable authority rows automatically, runtime/session behavior stays intact, and smoke proves the substrate no longer depends on implicit authority fallback for ordinary routed actors.

## Decisions Recorded
_1 decision(s) captured during this tranche._

### Seed explicit authority rows for ordinary routed actors at the contract gate
**Impact area:** architecture

**Context:** Session-backed local and MCP actors already gained durable authority rows, but non-session actors could still rely on default-by-prefix inference with no persisted authority record.

**Rationale:** The substrate becomes easier to audit and less dependent on implicit behavior if the first router-path encounter materializes a durable authority row instead of leaving actor identity purely inferred.

**Outcome:** ContractAuthority now seeds an explicit authorities row for actors as they first traverse the gate, and smoke proves a non-session routed actor receives a persisted Propose row with router-seed provenance.

_decision_id: decision_18b0aa51dc23bea4_50170b24 | importance: 8_

## Files Changed
- `src/core/contracts.py` (modified)
- `smoke_test.py` (modified)
- `README.md` (modified)
- `_docs/reference/TOOLS.md` (modified)
- `_docs/planning/IMPLEMENTATION_ROADMAP.md` (modified)
- `_docs/continuity/WE_ARE_HERE_NOW.md` (modified)
- `_docs/history/DEV_LOG.md` (modified)

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-18T13:01:34.822Z)

## Open Questions (carry forward)
- smoke review return for T10.2 MCP gate coverage _(raised 2026-05-18T13:01:35.044Z)_

## Next Tranche
T10.4 HARD_BLOCK and mutation-path trust-gate completion

## Additional Notes
Token-efficiency note: this tranche narrows the gap between inferred authority truth and mechanically materialized authority truth by ensuring ordinary routed actors gain durable authority rows. The intended effect is that later review and park packets can read explicit authority state directly from the spine instead of depending on operator recollection of prefix defaults.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-19T00:34:26.857Z._
_Source: tranche_id=tranche_18b0aa38ccddb648_7dcdb358_
