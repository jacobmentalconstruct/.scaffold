# ONBOARDING.md — Read This First

> **For:** any agent or human picking up this project cold.
> **Status:** authoritative entry point. If you read nothing else, read this and the contract.

## The 30-second pitch

`.scaffold/` is a **vended sidecar package** that drops into any project root. It carries: a binding contract, a SQLite spine (events + graph + projections), an MCP server for agents, a Tkinter UI for humans (planned T3), 5 tools so far, and a journal that records every meaningful decision.

The host project **never knows the sidecar exists** — no imports across the boundary; the sidecar only writes inside its own subtree unless explicit `Apply`/`Export` authority is granted.

## What state is the project in right now?

Run this:
```
python -m src.app cli version
python smoke_test.py
```

If smoke test exits 0 with all sections PASS, the project is in a known-good state. If it fails, **do not proceed with new work** — the Park Phase discipline (contract §D) makes drift mechanically detectable, and a failed smoke test means the previous tranche didn't properly park.

## Reading order

Read in this order. Each builds on the previous.

1. **`ONBOARDING.md`** (this file) — orientation.
2. **`README.md`** — current status banner, folder map, the invariant.
3. **`IMPLEMENTATION_ROADMAP.md`** — tranche-by-tranche plan. Look at which tranches are marked `✓ COMPLETE` and which is next. The "Tranche status" headers carry metrics + the journal entry uid + evidence hashes from each closeout.
4. **`contracts/builder_constrant_contract.md`** — the binding contract. **You must acknowledge this before doing meaningful work.** Pay special attention to §D (Park Phase Discipline).
5. **`ARCHITECTURE.md`** — design truth. Critical sections:
   - §1 (spine rule)
   - §3 (memory model: LTM / STM / Bag of Evidence)
   - §3.6 (three temporal directions)
   - §12.2 (Park Phase — explicit 7 steps)
   - §13 (cross-cutting principles)
   - §15 (resolved-by-tranche status + still-open questions)
6. **`SOURCE_PROVENANCE.md`** — what was written fresh vs structurally borrowed from `.parts/.dev-tools-REF/`. Includes per-tranche entries with evidence hashes.
7. **`TOOLS.md`** — registered tools index. Source of truth for tool count is the `tool_registry` table; this file is its mirror, regenerated each Park Phase.
8. **`_docs/`** — supporting docs:
   - `INCORPORATION_INVENTORY.md` — what was reviewed from the precursor at Tranche A.
   - `T1_CLOSEOUT_NOTES.md` — T1 Park artifact (now SUPERSEDED by its journal entry, retained as code-time mirror).
   - `T2_PARK_NOTES.md` — T2 Park artifact.
   - `T2_AUDIT_DECISION.md` — why Park Phase is now contract-bound + mechanically enforced.

## Live-state verification commands (read-only)

```bash
# What is the schema, who has acked, what's the contract hash?
python -m src.app cli version

# What projections are queryable?
python -m src.app cli list-projections

# What does the human dashboard look like right now?
python -m src.app cli projection human_dashboard

# What does the agent bootstrap (PAST/PRESENT/FUTURE) look like?
python -m src.app cli projection agent_bootstrap

# Show every tranche journal entry (the canonical closeout records)
python -m src.app cli journal-query --kind tranche

# Show every decision journal entry
python -m src.app cli journal-query --kind decision

# What tools are registered?
python -m src.app cli tool-list

# What's the latest scan and git state?
python -m src.app cli scan-status
python -m src.app cli git-status

# Active Tranche Ledger (T2.5+)
python -m src.app cli tranche-status        # current tranche + live checklist
python -m src.app cli decision-list         # decisions recorded this tranche
python -m src.app cli projection tranche_checklist   # raw checklist projection

# Smoke-test the full stack (the gate that says "this is in good order")
python smoke_test.py
```

## Acknowledging the contract (required before write actions)

The gate refuses any non-bootstrap envelope from an actor that has not acknowledged the current contract. For a fresh actor:

```bash
python -m src.app cli ack-contract --actor "human:your-name"
# or
python -m src.app cli ack-contract --actor "agent:your-id"
```

`acknowledge_contract` is a `BOOTSTRAP_EXEMPT_INTENTS` operation — it can run before the actor has acked. All other intents will be rejected with `REJECT_UNACKNOWLEDGED_CONTRACT` until this is done.

## MCP usage (external agent)

```bash
python -m src.app mcp
```

Starts the MCP stdio server. Supports `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `ping`. Tool calls become `tool_invoked` envelopes routed through the spine — same gate, same event log.

**First read for an MCP-connected agent:**
1. `tools/list` to see what's available.
2. `resources/read` with `uri="projection://agent_bootstrap"` for the PAST/PRESENT/FUTURE snapshot.
3. `tools/call` for `read_projection`, `file_tree_snapshot`, etc.

## Memory model in one breath

- **LTM** = everything on disk the agent can read: journal, projections, project code, sidecar code, contract, event log.
- **STM** = the agent's sliding context window (managed externally for now — the sidecar doesn't run an agent yet).
- **Bag of Evidence** = the bridge layer (schema reserved, not implemented — DP1 deferred).

When designing anything that persists, ask: STM, Bag, or LTM?

## How to resume the previous session's work

1. Read `IMPLEMENTATION_ROADMAP.md` — find the next tranche **not** marked `✓ COMPLETE`.
2. Read the latest `_docs/T_n_PARK_NOTES.md` — it captures the previous tranche's closeout in detail.
3. Run `python -m src.app cli projection agent_bootstrap` — gives you PAST + PRESENT + FUTURE in one read.
4. Run `python smoke_test.py` — verifies the state is clean. If it's not, **fix Park Phase drift first**.
5. Read the relevant prose-plan files for the next tranche's target files.
6. Begin work. Acknowledge the contract if you haven't.

## How to close a tranche (the codified ritual)

Per **contract §D / ARCHITECTURE.md §12.2 + §3.7** — all five Park Phase artifacts are now produced by the `close_tranche` envelope (the "push a button" path). Manual steps are kept for reference.

### Active Tranche Ledger path (T2.5+, recommended)

During the tranche, capture work as you go:
```bash
# Declare the tranche at the start (creates the ledger record):
python -m src.app cli tranche-declare --actor "human:you" --title "T3 Tk UI" \
    --scope "Build Tkinter UI panels reading projections" \
    --completion-criteria "python -m src.app ui opens dashboard"

# Record decisions as they happen:
python -m src.app cli decision-record --actor "human:you" \
    --title "Use ttk.Notebook for panel tabs" \
    --context "Need a container for 4 panels" \
    --rationale "ttk is stdlib; consistent with contract Pledge 1" \
    --outcome "ttk.Notebook with state/journal/evidence/project_map tabs" \
    --area "architecture"

# Note files changed (optional — close_tranche still works without):
python -m src.app cli tranche-update --actor "human:you" \
    --file "src/ui/main_window.py:added"

# Check readiness at any time:
python -m src.app cli tranche-status

# After smoke test passes, record it:
python smoke_test.py  # must exit 0
python -m src.app cli tranche-smoke-pass --actor "human:you"

# Push the button — compile notes, create journal entry, seal ledger:
python -m src.app cli tranche-close --actor "human:you"
```

At close, the orchestrator:
1. Validates the checklist (contract acked, scope declared, smoke passed)
2. Compiles `_docs/Tn_PARK_NOTES.md` from the structured ledger data
3. Creates + closes the tranche journal entry with evidence refs
4. Seals the `active_tranche` record (status → 'parked')
5. Updates continuity meta key

### Manual path (pre-T2.5 reference, still valid)
1. Write `_docs/T_n_PARK_NOTES.md` manually.
2. Capture: `python -m src.app cli ...`; record the blob hash.
3. Journal: `python -m src.app cli journal-write --kind tranche --title "..." --body-file _docs/T_n_PARK_NOTES.md --evidence-hash <hash> --importance 8`
4. Update continuity docs: `IMPLEMENTATION_ROADMAP.md`, `SOURCE_PROVENANCE.md`, `TOOLS.md`, `ARCHITECTURE.md §15`, `README.md`.
5. Close: `accept_task` → `complete_task` → `close_journal_entry`.
6. Re-run `python smoke_test.py` — must PASS.

If `smoke_test.py` fails after Park Phase, **the tranche is not parked.** Fix and repeat.

## Boundary rules — what NOT to do

- Do NOT write outside `.scaffold/` without `Apply` or `Export` authority granted by a recorded human approval.
- Do NOT import from `.scaffold/` in the host project's application code.
- Do NOT bypass `journal_manager` / `sqlite_store` for DB access (Pledge 2: Single Store).
- Do NOT create graph relations of type `related_to` or any predicate outside the closed set (see ARCHITECTURE §8).
- Do NOT embed large payloads in envelopes (Pledge 7: Envelope Lightness). Put them in `blob_store` and reference by hash.
- Do NOT call another manager directly from a manager (Pledge 6: Spine Discipline). That's an orchestrator's job.

## When in doubt

Read the journal:
```bash
python -m src.app cli journal-query --kind decision
python -m src.app cli journal-query --kind tranche
python -m src.app cli journal-query --kind log
```

The journal is **authoritative builder memory** (per ARCHITECTURE §13.1 Journal Doctrine). If something seems unclear, the WHY is likely already journaled.
