# WE_ARE_HERE_NOW.md — Fast Pickup

## Snapshot

- Latest parked feature tranche: T7 Run Trace, Recovery, and Operator Cockpit
- Current substrate state: contract-bound, Tk-native, MCP-capable, local-agent-capable, runtime-traced, workspace-first bounded mutation loop working
- Active horizon: T8 Teaching Sandbox + Training Runway
- Deferred backlog status: normalized into `IMPLEMENTATION_ROADMAP.md` and mirrored as open journal todos

## What just landed

- T7 is now parked and schema v9 is live
- local-agent runs, rounds, runtime events, touched paths, artifact links, and claim grounding now persist in the SQLite spine
- retry lineage now reuses a captured run snapshot instead of rebuilding state ad hoc
- `runtime_cockpit` is now a real projection and is surfaced in `agent_bootstrap`, `viewport_state`, CLI inspection commands, and the Tk local-agent panel
- final no-mutation and mutation-bearing success summaries are now grounded in trace-linked artifacts instead of being treated as opaque completion text
- T7 park notes now live at `_docs/T7_PARK_NOTES.md`
- continuity docs now agree that T8 is the next horizon

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
python -m src.app cli journal-query --kind todo --status open
python -m src.app cli approval-list --all
python -m src.app cli local-agent-status
python -m src.app cli local-agent-run-list
python -m src.app cli local-agent-recovery-summary
python -m src.app ui
```

## Immediate next job

T8 now owns the next substantive expansion pass: rebuild the Teaching Sandbox + Training Runway on top of the traced local-agent substrate so deterministic scenarios, scorecards, and reviewer exports become part of the same sidecar.

The deferred backlog is no longer just prose in architecture notes: query `journal-query --kind todo --status open` to see the tranche-owned carry-forward list.
