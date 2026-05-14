# WE_ARE_HERE_NOW.md — Fast Pickup

## Snapshot

- Latest parked feature tranche: T9 Installed-Project Proof + Vendability Seal
- Current substrate state: contract-bound, Tk-native, MCP-capable, local-agent-capable, runtime-traced, training-capable, installed-project-proof-capable, substrate baseline achieved
- Active horizon: T10 Post-Baseline Hardening + Optional Expansion
- Deferred backlog status: normalized into `IMPLEMENTATION_ROADMAP.md` and mirrored as open journal todos

## What just landed

- T9 is parked and schema v11 is live
- a fresh tiny host fixture now proves `.scaffold` can install cleanly as `<host>/.scaffold/`
- the installed-project proof loop now covers install, contract ack, scan, projections, Tk hydration, governed proposal, approval, bounded host mutation, trace/evidence/journal/projection capture, and cold-team handoff export
- `installed_project_proof` is now a real projection and is surfaced through CLI and the Tk Installed Proof panel
- the proof fixture now lives under `workspaces/installed_project_proof/tiny_notes_app/`
- the branch now formally supersedes the old experiment as the default installable substrate baseline
- T9 park notes now live at `_docs/T9_PARK_NOTES.md`
- continuity docs now agree that baseline is achieved and T10 is the next optional hardening horizon

## What to read next

1. `ONBOARDING.md`
2. `README.md`
3. `IMPLEMENTATION_ROADMAP.md`
4. `contracts/builder_constraint_contract.md`
5. `ARCHITECTURE.md`
6. `NORTHSTARS.md`
7. `DEV_LOG.md`

## Verification commands

```bash
python -m src.app cli version
python smoke_test.py
python -m src.app cli projection handoff
python -m src.app cli projection agent_bootstrap
python -m src.app cli projection runtime_cockpit
python -m src.app cli projection training_runway
python -m src.app cli projection installed_project_proof
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

If work resumes, the next horizon is T10 post-baseline hardening: only the deferred trust/perf/expansion items that still matter after the vendability seal.

The deferred backlog is no longer just prose in architecture notes: query `journal-query --kind todo --status open` to see the tranche-owned carry-forward list.
