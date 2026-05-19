# Park Notes — T10.5 Derived BCC Constraint-Map Slice for Intent Decomposition

> Generated: 2026-05-19T12:18:59.822Z | Status: sealed | tranche_id: tranche_18b0f6ac7dedb3d8_669177a0
> Started: 2026-05-19T12:17:53.518Z

## Declared Scope
Derive the first machine-usable bcc_constraint_map from contracts/BCC.md, persist and project it as derived non-authoritative truth, and summarize it in agent_bootstrap so agents can classify intent before mutation without rewriting runtime enforcement.

### Non-goals
No runtime authority enum rewrite, no full contract execution engine, no broad trust-gate rewrite, no new MCP constraint resource, and no widening of mutation authority.

### Completion Criteria
A durable compiled BCC constraint map exists, projection://bcc_constraint_map and CLI refresh/read surfaces work, agent_bootstrap exposes compact constraint guidance, contract-hash drift disables guidance until explicit refresh, authority drift is surfaced rather than corrected, no absolute path leakage is present, and smoke passes without regressing T10.4 trust enforcement.

## Decisions Recorded
_3 decision(s) captured during this tranche._

### Compile BCC by anchors into a derived constraint map
**Impact area:** architecture

**Context:** T10.5 needed a machine-usable decomposition surface without turning contracts/BCC.md into a second executable doctrine source.

**Rationale:** Anchor/template extraction is deterministic, cheaper than broad prose parsing, and narrow enough to prove the shape safely in one tranche.

**Outcome:** Added a dedicated compiler that reads contracts/BCC.md, validates required headings, computes the live contract hash, and emits a derived non-authoritative bcc_constraint_map payload.

_decision_id: decision_18b0f6b2446b4368_b80d092d | importance: 8_

### Require explicit refresh on contract-hash drift
**Impact area:** process

**Context:** A compiled constraint surface is only safe if agents can tell when it no longer matches the live contract.

**Rationale:** Auto-regenerating on every contract change would hide drift and make it harder to inspect what was previously compiled and trusted.

**Outcome:** Compiled maps are now stored durably, stale hashes disable guidance in projection://bcc_constraint_map and agent_bootstrap, and operators refresh explicitly with python -m src.app cli contract-constraint-map-refresh.

_decision_id: decision_18b0f6b24f6d94dc_1f244a87 | importance: 8_

### Expose authority drift instead of correcting runtime enums in T10.5
**Impact area:** architecture

**Context:** The current runtime authority model still differs from the six-level BCC ladder, but this tranche was explicitly decomposition-only.

**Rationale:** Surfacing the mismatch preserves truthful doctrine, avoids hidden normalization, and keeps T10.5 from becoming a stealth runtime-enforcement rewrite.

**Outcome:** The compiled map now shows canonical BCC levels, runtime legacy levels, conditional aliases, and resolution_status=exposed_not_corrected without changing src/lib/common.py or src/schemas/contract_schema.py.

_decision_id: decision_18b0f6b250105550_10d8b747 | importance: 9_

## Files Changed
- `src/lib/bcc_constraint_map.py` (added)
- `src/components/sqlite_store.py` (modified)
- `src/schemas/projection_schema.py` (modified)
- `src/core/projections.py` (modified)
- `src/app.py` (modified)
- `src/interfaces/cli_interface.py` (modified)
- `smoke_test.py` (modified)
- `README.md` (modified)
- `_docs/continuity/ONBOARDING.md` (modified)
- `_docs/continuity/WE_ARE_HERE_NOW.md` (modified)
- `_docs/planning/IMPLEMENTATION_ROADMAP.md` (modified)
- `_docs/planning/TARGET_STATE.md` (modified)
- `_docs/reference/ARCHITECTURE.md` (modified)
- `_docs/history/DEV_LOG.md` (modified)

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-19T12:18:27.276Z)

## Next Tranche
T10.6 Snapshot Cadence + Schema-Migration Harnesses

## Additional Notes
T10.5 parked after verifying the durable compiled-map store, projection://bcc_constraint_map, agent_bootstrap constraint summary, stale-contract guidance disablement, explicit refresh recovery, runtime authority drift exposure, and relative-path hygiene. Next candidate remains T10.6 Snapshot Cadence + Schema-Migration Harnesses.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-19T12:18:59.822Z._
_Source: tranche_id=tranche_18b0f6ac7dedb3d8_669177a0_
