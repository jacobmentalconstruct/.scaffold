# Park Notes — T10.2 Chat Review Gate Surface

> Generated: 2026-05-18T12:56:44.943Z | Status: sealed | tranche_id: tranche_18b0a9cc2d5d3830_2ecda529
> Started: 2026-05-18T12:49:07.210Z

## Declared Scope
Expose tranche review and closeout artifacts as MCP-readable chat-cockpit resources, route review/approval/park actions through sidecar/submit, and document the governed chat review flow without adding a second memory or authority path.

### Non-goals
No general chat workspace, no chat-driven tranche declaration, no broader self-modification surface, and no second authority or memory layer.

### Completion Criteria
MCP clients can inspect tranche/review state, inspect review packets and closeout metadata, return or approve review, trigger close only after approval, and the docs/smoke surfaces reflect the chat-over-spine review flow.

## Decisions Recorded
_2 decision(s) captured during this tranche._

### Expose review and closeout artifacts as first-class MCP resources
**Impact area:** architecture

**Context:** Chat clients could inspect tranche_review_gate state, but not the full mechanical review packet or generated closeout metadata directly through MCP.

**Rationale:** Chat has to operate as a cockpit over the existing spine, so review and closeout inspection needed to come from the same truth surfaces rather than a second transcript-owned memory layer.

**Outcome:** Added review://latest, review://<review_id>, closeout://latest, and closeout://<journal_entry_uid> resource reads that surface both JSON and Markdown forms from existing packet blobs and generated closeout metadata.

_decision_id: decision_18b0a9d0de290924_57c72dc1 | importance: 8_

### Keep chat mutation on sidecar/submit with explicit review then park sequencing
**Impact area:** process

**Context:** The new chat cockpit slice needed review return, approval, and park actions without creating a hidden fast path around the spine or combining human approval with Park Phase implicitly.

**Rationale:** The authority boundary stays understandable only if chat follows the same review gate as Tk and CLI: inspect state, request or inspect review, approve or return explicitly, then close in a separate step once allowed.

**Outcome:** Mapped tranche review intents onto MCP defaults, documented the inspect -> approve -> inspect gate -> close flow, and expanded smoke so close remains blocked before approval but succeeds through sidecar/submit after review approval.

_decision_id: decision_18b0a9d0e41d76a8_6a36479d | importance: 8_

## Files Changed
- `src/interfaces/mcp_interface.py` (modified)
- `src/managers/tranche_manager.py` (modified)
- `smoke_test.py` (modified)
- `README.md` (modified)
- `_docs/continuity/ONBOARDING.md` (modified)

## Tests Run
- `smoke_test.py` → PASS (at 2026-05-18T12:52:09.130Z)

## Open Questions (carry forward)
- smoke review return for T10.2 MCP gate coverage _(raised 2026-05-18T12:52:09.337Z)_

## Next Tranche
T10.3 Explicit Authority Registration Hardening

## Additional Notes
Mechanical vs manual closeout note:
- Mechanical: tranche checklist gating, review packet generation/export, review status transitions, closeout metadata generation, park-notes compilation, journal tranche entry creation, and latest-closeout alias updates all ran through the existing spine surfaces.
- Manual: I declared the tranche, recorded the two decisions, listed the touched files, interpreted one smoke-discovered continuity drift in WE_ARE_HERE_NOW.md, and aligned that doc before close so the active-tranche handoff wording matched the live state.
- Boundary: this park is mostly mechanical once tranche inputs exist, but it still depends on a human/agent to keep continuity docs truthful when the work changes the meaning of current-vs-next horizon surfaces.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-18T12:56:44.943Z._
_Source: tranche_id=tranche_18b0a9cc2d5d3830_2ecda529_
