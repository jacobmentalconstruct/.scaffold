# Park Notes — T10.4 HARD_BLOCK and Mutation-Path Trust-Gate Completion

> Generated: 2026-05-19T10:22:44.257Z | Status: sealed | tranche_id: tranche_18b0f0480cb283c0_ed32f51f
> Started: 2026-05-19T10:20:45.052Z

## Declared Scope
Finish the trust-gate floor so project-targeted text_file_writer and directory_scaffold mutations are mechanically enforced at the contract gate, tighten scaffold approval scope to exact manifest entry_paths, and block declare_tranche when authoritative Park/continuity drift exists.

### Non-goals
No derived BCC constraint-map work, no snapshot/migration harnesses, no concurrency soak work, and no broader chat expansion beyond the existing review cockpit.

### Completion Criteria
Project-targeted mutation paths fail early with concrete trust-gate reasons, scaffold approvals require exact entry_paths matches, declare_tranche fails fast on authoritative Park/continuity drift, and smoke covers the new gate behaviors without regressing existing review/installed-proof flows.

## Decisions Recorded
_2 decision(s) captured during this tranche._

### Centralize project-targeted mutation policy at the contract gate
**Impact area:** trust_gate

**Context:** T10.4 needed the trust decision for project-targeted writes and scaffolds to happen before tool execution rather than being split across tool-local validation and smoke expectations.

**Rationale:** One explicit gate path makes host-write intent, path-boundary checks, and runtime-subtree isolation mechanically inspectable and keeps failure reasons consistent across tools and MCP surfaces.

**Outcome:** ContractAuthority now evaluates shared mutation policy for project-targeted text_file_writer and directory_scaffold invocations, and scaffold grants match exact manifest entry_paths.

_decision_id: decision_18b0f0639a69d8c4_8ea5b35f | importance: 9_

### Use authoritative latest-closeout plus WE_ARE_HERE_NOW for tranche-declare drift blocking
**Impact area:** continuity

**Context:** The repo needed declare_tranche to fail fast when load-bearing Park/continuity drift exists, but the blocking set had to stay narrow enough to avoid turning every mirror-doc mismatch into a tranche gate failure.

**Rationale:** The latest closed tranche journal entry, generated closeout metadata, and WE_ARE_HERE_NOW form the minimal authoritative continuity set for safe tranche startup. README and TOOLS remain smoke-visible mirrors, not start-up blockers.

**Outcome:** A shared park drift helper now powers declare_tranche blocking while leaving broader status-header drift to smoke and continuity cleanup instead of the hard trust gate.

_decision_id: decision_18b0f063aff6f8c0_5a81d7e2 | importance: 8_

## Files Changed
- `src/core/contracts.py` (modified)
- `src/core/router.py` (modified)
- `src/managers/tranche_manager.py` (modified)
- `src/orchestrators/closeout_orchestrator.py` (modified)
- `src/runtime/local_agent_runtime.py` (modified)
- `smoke_test.py` (modified)
- `README.md` (modified)
- `_docs/continuity/WE_ARE_HERE_NOW.md` (modified)
- `_docs/reference/TOOLS.md` (modified)
- `_docs/planning/IMPLEMENTATION_ROADMAP.md` (modified)
- `_docs/planning/TARGET_STATE.md` (modified)
- `_docs/history/DEV_LOG.md` (modified)

## Tests Run
- `python smoke_test.py` → PASS (at 2026-05-19T10:22:44.117Z)

## Next Tranche
T10.5 Derived BCC Constraint-Map Slice for Intent Decomposition

## Additional Notes
This tranche intentionally stayed narrow. The trust-gate floor is now explicit enough that T10.5 can focus on deriving a machine-usable BCC constraint map for intent decomposition instead of mixing doctrine compilation with unfinished mutation-path enforcement.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-19T10:22:44.257Z._
_Source: tranche_id=tranche_18b0f0480cb283c0_ed32f51f_
