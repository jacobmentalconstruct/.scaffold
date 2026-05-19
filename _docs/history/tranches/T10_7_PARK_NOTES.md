# Park Notes — T10.7 Sanitized Public Export Surface

> Generated: 2026-05-19T14:41:40.988Z | Status: sealed | tranche_id: tranche_18b0fe7934396c80_490489b4
> Started: 2026-05-19T14:40:49.332Z

## Declared Scope
Add a derived public-safe export bundle and audit boundary for external sharing, sanitize selected continuity/bootstrap/handoff surfaces without mutating authoritative private truth, and remove the known tracked absolute-path leak from public-facing docs.

### Non-goals
No mutation of authoritative DB truth, no reversible identity registry, no runtime authority-model rewrite, and no broad secret-management layer.

### Completion Criteria
Public-share preview/write/audit commands exist, generated bundles are explicitly derived and non-authoritative, tracked/public bundle path leakage checks pass, and full smoke remains green.

## Decisions Recorded
_2 decision(s) captured during this tranche._

### Use a derived public-share bundle instead of sanitizing authoritative truth
**Impact area:** architecture

**Context:** The exposure audit found tracked-doc and ignored-runtime path leakage risk when sharing sidecar materials externally.

**Rationale:** Preserving the private spine as authoritative avoids rewriting history in place and keeps sanitization as an explicit boundary transform.

**Outcome:** T10.7 adds a non-authoritative sanitized export bundle plus audit commands rather than mutating DB truth or introducing a second policy surface.

_decision_id: decision_18b0fe7934abe33c_8425347d | importance: 9_

### Record the README/BCC infographic as a non-authoritative visual aid
**Impact area:** docs

**Context:** A root assets infographic was added to help readers orient to the Builder Constraint Contract quickly.

**Rationale:** The image improves onboarding value as long as the docs state clearly that the contract prose remains authoritative.

**Outcome:** README.md and contracts/BCC.md embed the infographic with explicit non-authoritative framing.

_decision_id: decision_18b0fe7d35379694_921a2c3c | importance: 4_

## Files Changed
- `src/lib/public_export_sanitizer.py` (added)
- `src/interfaces/cli_interface.py` (modified)
- `smoke_test.py` (modified)
- `README.md` (modified)
- `contracts/BCC.md` (modified)
- `_docs/continuity/ONBOARDING.md` (modified)
- `_docs/continuity/WE_ARE_HERE_NOW.md` (modified)
- `_docs/reference/ARCHITECTURE.md` (modified)
- `_docs/history/DEV_LOG.md` (modified)
- `_docs/history/transitions/BRANCH_02_TRANSITION_NOTE_2026-05-12.md` (modified)
- `assets/decomposing-the-bcc.jpg` (added)
- `src/lib/public_export_sanitizer.py` (added)

## Tests Run
- `python smoke_test.py` → PASS (at 2026-05-19T14:40:49.374Z)

## Next Tranche
T10.6 Snapshot Cadence + Schema-Migration Harnesses

## Additional Notes
T10.7 remains a derived safety/export layer only. Authoritative private runtime truth was intentionally left unchanged while selected public-share surfaces and the known tracked path leak were hardened for external sharing.

---
_Park notes auto-compiled by closeout_orchestrator at 2026-05-19T14:41:40.988Z._
_Source: tranche_id=tranche_18b0fe7934396c80_490489b4_
