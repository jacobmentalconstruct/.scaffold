# WE_ARE_HERE_NOW.md — Fast Pickup

## Snapshot

- Latest parked feature tranche: T8.1 Post-Park Training Handoff Alignment
- Latest fully closed feature tranche before the active follow-up: T8 Teaching Sandbox + Training Runway
- Current substrate state: contract-bound, Tk-native, MCP-capable, local-agent-capable, runtime-traced, training-capable, workspace-first bounded mutation loop working
- Active horizon: T9 Installed-Project Proof + Vendability Seal
- Deferred backlog status: normalized into `IMPLEMENTATION_ROADMAP.md` and mirrored as open journal todos

## What just landed

- T8 is parked and schema v10 is live
- T8.1 reconciled roadmap parsing and handoff/bootstrap visibility so T9 still appears as concrete next-step work in smoke and agent bootstrap surfaces
- `training_runway` is now a real projection and is surfaced through CLI and the Tk Training Runway panel
- tracked scenarios now live under `training_scenarios/definitions/`
- disposable teaching sandboxes now materialize under `workspaces/teaching_sandbox/projects/`
- mocked pass/fail scenario runs now produce trace-linked scorecards, reviewer exports, evidence refs, and journal entries
- one live Ollama proof was captured for `python_notes_cli`; it failed as `malformed_tool_call`, but the teaching substrate preserved the full review packet
- T8 park notes now live at `_docs/T8_PARK_NOTES.md`
- T8.1 follow-up notes now live at `_docs/T8_1_PARK_NOTES.md`
- continuity docs now agree that T9 is the next horizon

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
python -m src.app cli journal-query --kind todo --status open
python -m src.app cli approval-list --all
python -m src.app cli local-agent-status
python -m src.app cli local-agent-run-list
python -m src.app cli local-agent-recovery-summary
python -m src.app cli training-scenario-list
python -m src.app ui
```

## Immediate next job

T9 now owns the next substantive expansion pass: prove this branch as the default installable substrate in a fresh host project, then seal vendability and supersession.

The deferred backlog is no longer just prose in architecture notes: query `journal-query --kind todo --status open` to see the tranche-owned carry-forward list.
