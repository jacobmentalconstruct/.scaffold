# Park Notes — T10.1 Prototype Target Requirements Map + Chat-Centered Sidecar Alignment

> Generated: 2026-05-15T15:17:55.728Z | Status: sealed | tranche_id: tranche_18afc55d783658f4_62d171ee
> Started: 2026-05-15T15:03:03.074Z

## Declared Scope
Codify the chat-centered sidecar target state, separate prototype vs long-term targets, reclassify backlog truthfully, and update doctrine/continuity so future chat work stays over the spine rather than becoming a second brain.

### Non-goals
No chat workspace implementation, no runtime API expansion, no schema/tool additions, no silent todo cleanup, no new authority or memory layers.

### Completion Criteria
TARGET_STATE.md exists as a first-class doctrine artifact; continuity/docs/roadmap/contract reflect chat-first over-spine doctrine; backlog is reclassified honestly; smoke passes; review packet generates; tranche parks cleanly with T10.2 named as the next narrow implementation slice.

## Decisions Recorded
_2 decision(s) captured during this tranche._

### First chat slice is the Review Gate surface
**Impact area:** planning

**Context:** Need a narrow first proof of chat as cockpit that strengthens the exact failure mode we recently discovered without spawning a broad chat subsystem.

**Rationale:** Review, return, approval, park, and closeout inspection already exist as spine-backed surfaces and form the highest-value HITL loop.

**Outcome:** Locked T10.2 to the Chat Review Gate Surface and deferred broader chat planning/task initiation to later slices.

_decision_id: decision_18afc5d74865ee6c_2a800ef7 | importance: 5_

### Chat over spine, not second brain
**Impact area:** architecture

**Context:** Need to recenter the sidecar around a chat cockpit without violating single-store, truth-layer separation, or envelope discipline.

**Rationale:** User workflow and external review both require exports and verification bundles, so chat cannot become its own hidden memory or authority layer.

**Outcome:** Codified the governing rule that chat becomes the cockpit while the DB remains the memory and the spine remains the authority path.

_decision_id: decision_18afc5d98a1a1cdc_63d02996 | importance: 5_

## Files Changed
_No files explicitly tracked. Review git diff for actual changes._

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-15T15:14:34.362Z)
- `smoke_test.py` → PASS (at 2026-05-15T15:17:23.517Z)

## Open Questions (carry forward)
- smoke review return for T10 gate coverage _(raised 2026-05-15T15:14:34.503Z)_
- smoke review return for T10 gate coverage _(raised 2026-05-15T15:17:23.655Z)_

## Next Tranche
T10.2 Chat Review Gate Surface

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-15T15:17:55.728Z._
_Source: tranche_id=tranche_18afc55d783658f4_62d171ee_
