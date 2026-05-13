# WE_ARE_HERE_NOW.md — Fast Pickup

## Snapshot

- Latest parked feature tranche: T6 STM + Bag of Evidence + Evidence Shelf
- Continuity follow-up tranche: T6.1 Post-Park Continuity Alignment
- Current substrate state: contract-bound, Tk-native, MCP-capable, local-agent-capable, workspace-first bounded mutation loop working
- Active horizon: T7 Run Trace, Recovery, and Operator Cockpit
- Deferred backlog status: normalized into `IMPLEMENTATION_ROADMAP.md` and mirrored as open journal todos

## What just landed

- T6 is now parked and schema v8 is live
- local-agent STM now persists in SQLite-backed session memory rows
- older local-agent working context overflows into a Bag of Evidence instead of disappearing with the window
- an Evidence Shelf is now exposed through `agent_bootstrap` and `viewport_state`
- bounded text writes now persist per-hunk line provenance (`path`, old/new line ranges, raw diff text)
- T6 park notes now live at `_docs/T6_PARK_NOTES.md`
- T6.1 sealed the continuity wording so the roadmap, onboarding flow, architecture, and handoff docs all agree that T7 is the next horizon

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
python -m src.app cli journal-query --kind todo --status open
python -m src.app cli approval-list --all
python -m src.app cli local-agent-status
python -m src.app cli local-agent-preflight --actor "agent:local:ollama" --model "qwen3.5:9b"
python -m src.app ui
```

## Immediate next job

T7 now owns the next substantive hardening pass: run traces, recovery classes, retry guidance, and a fuller operator cockpit over the local sidecar agent.

The deferred backlog is no longer just prose in architecture notes: query `journal-query --kind todo --status open` to see the tranche-owned carry-forward list.
