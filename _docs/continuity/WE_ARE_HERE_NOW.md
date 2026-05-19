# WE_ARE_HERE_NOW.md — Fast Pickup

## Snapshot

- Latest parked tranche: T10.7 Sanitized Public Export Surface
- Current substrate state: contract-bound, Tk-backed, MCP-capable, local-agent-capable, runtime-traced, training-capable, installed-project-proof-capable, substrate baseline achieved, chat-centered target codified
- Next horizon: T10.6 Snapshot Cadence + Schema-Migration Harnesses
- Deferred backlog status: normalized into `_docs/planning/IMPLEMENTATION_ROADMAP.md` and mirrored as open journal todos

## What just landed

- T9 is parked and schema v11 is live
- a fresh tiny host fixture now proves `.scaffold` can install cleanly as `<host>/.scaffold/`
- the installed-project proof loop now covers install, contract ack, scan, projections, Tk hydration, governed proposal, approval, bounded host mutation, trace/evidence/journal/projection capture, and cold-team handoff export
- `installed_project_proof` is now a real projection and is surfaced through CLI and the Tk Installed Proof panel
- the proof fixture now lives under `workspaces/installed_project_proof/tiny_notes_app/`
- the branch now formally supersedes the old experiment as the default installable substrate baseline
- T9 park notes now live at `_docs/history/tranches/T9_PARK_NOTES.md`
- T10 closed the tranche-review gate + horizon semantics hardening slice
- generated closeout metadata now lives at `_docs/continuity/LATEST_PARKED_TRANCHE.json`, `_docs/history/tranches/T10_CLOSEOUT_METADATA.json`, and `_docs/history/tranches/T10_1_CLOSEOUT_METADATA.json`
- continuity docs now treat generated closeout metadata as the authoritative mirror source for latest parked tranche identifiers
- the tranche-review gate hardening slice added a mechanical pre-park review packet plus explicit human approval before Park Phase can seal a tranche
- T10.1 added `_docs/planning/TARGET_STATE.md` as the binding prototype target map for the next phase
- the project now explicitly treats chat as the planned primary cockpit and Tk as the secondary operator surface
- T10.2 parked the first MCP chat-cockpit review/closeout slice and generated park notes at `_docs/history/tranches/T10_2_PARK_NOTES.md`
- T10.3 parked explicit authority-row materialization for ordinary routed actors and generated park notes at `_docs/history/tranches/T10_3_PARK_NOTES.md`
- T10.4 parked the trust-gate floor: project-targeted mutation now fails early at the contract gate, scaffold approvals require exact manifest `entry_paths`, and tranche declaration blocks on authoritative Park/continuity drift
- T10.5 parked the first derived BCC constraint-map slice: `projection://bcc_constraint_map` is now a durable, non-authoritative, hash-bound mirror of `contracts/BCC.md` for lower-token intent decomposition; explicit refresh is required on contract-hash drift, and runtime authority drift is exposed there rather than corrected
- T10.7 parked the derived public-share boundary: `public-export-preview`, `public-export-write`, and `public-export-audit` now generate or verify sanitized non-authoritative share bundles while leaving authoritative private runtime truth unchanged

## What to read next

1. `_docs/continuity/ONBOARDING.md`
2. `_docs/planning/TARGET_STATE.md`
3. `README.md`
4. `_docs/planning/IMPLEMENTATION_ROADMAP.md`
5. `contracts/BCC.md`
6. `_docs/reference/ARCHITECTURE.md`
7. `_docs/planning/NORTHSTARS.md`
8. `_docs/history/DEV_LOG.md`

## Verification commands

```bash
python -m src.app cli version
python smoke_test.py
python -m src.app cli projection handoff
python -m src.app cli projection agent_bootstrap
python -m src.app cli projection bcc_constraint_map
python -m src.app cli projection tranche_review_gate
python -m src.app cli projection runtime_cockpit
python -m src.app cli projection training_runway
python -m src.app cli projection installed_project_proof
python -m src.app cli public-export-preview
python -m src.app cli public-export-audit
python -m src.app cli journal-query --kind todo --status open
python -m src.app cli approval-list --all
python -m src.app cli local-agent-status
python -m src.app cli local-agent-run-list
python -m src.app cli local-agent-recovery-summary
python -m src.app cli training-scenario-list
python -m src.app cli installed-proof-show
python -m src.app ui
```

## Immediate next job

The substrate baseline is now achieved. There is no active tranche open.

The latest parked tranche is `T10.7 Sanitized Public Export Surface`.

The next narrow implementation slice after that park is `T10.6 Snapshot Cadence + Schema-Migration Harnesses`.

The broader T10 horizon remains post-baseline hardening plus the chat-centered recentering now codified in `_docs/planning/TARGET_STATE.md`.

The deferred backlog is no longer just prose in architecture notes: query `journal-query --kind todo --status open` to see the tranche-owned carry-forward list.
