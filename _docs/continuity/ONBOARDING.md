# ONBOARDING.md — Read This First

> **For:** any agent or human picking up this project cold.
> **Status:** convenience orientation surface derived from `contracts/BCC.md` and `_docs/reference/PROJECT_BINDINGS.md`. The contract remains the sole binding doctrine source and first-read surface.

## The 30-second pitch

`.scaffold/` is a **vended sidecar package** that drops into any project root. It carries: a binding contract, a SQLite spine (events + graph + projections), an MCP server for agents, a Tkinter operator surface for humans, a local Ollama-backed sidecar agent floor, 8 registered tools, and a journal that records every meaningful decision.

The current target state is now explicitly **chat-centered**: chat is intended to become the primary cockpit over the governed spine, while Tk remains the secondary operator surface for monitoring, traces, queues, and deeper inspection. Read [`_docs/planning/TARGET_STATE.md`](../planning/TARGET_STATE.md) if you are touching the interaction model or planning future tranches.

Current branch work for `T10.5` also exposes `projection://bcc_constraint_map`, a derived and non-authoritative surface hash-bound to `contracts/BCC.md`. It exists to reduce token cost during intent decomposition. If the compiled hash drifts from the live contract, run `python -m src.app cli contract-constraint-map-refresh`; T10.5 exposes runtime authority drift there rather than correcting it.

The working tree also carries a derived public-share export boundary for safe outside sharing. `public-export-preview`, `public-export-write`, and `public-export-audit` generate or verify sanitized non-authoritative bundles; they do not rewrite or downgrade the private authoritative spine.

The host project **never knows the sidecar exists** — no imports across the boundary; the sidecar only writes inside its own subtree unless explicit `Apply`/`Export` authority is granted.

## What state is the project in right now?

Run this:
```
python -m src.app cli version
python smoke_test.py
```

If smoke test exits 0 with all sections PASS, the project is in a known-good state. If it fails, **do not proceed with new work** — the Park Phase closure rule (`BCC.md §10.8`, historically `contract §D`) makes drift mechanically detectable, and a failed smoke test means the previous tranche didn't properly park.

## Reading order

Read in this order after reading `contracts/BCC.md`. This file mirrors the contract bootstrap order for convenience and inspection speed; it does not outrank the binding, doctrine, continuity, provenance, tool, or verification surfaces listed before it.

1. **`contracts/BCC.md`** — the active binding contract and sole authored doctrine source. **You must read and acknowledge this before doing meaningful work.**
2. **`_docs/reference/PROJECT_BINDINGS.md`** — the local binding artifact. Read this immediately after the contract to resolve repo-local paths, continuity surfaces, package facts, and verification entrypoints.
3. **`_docs/reference/ARCHITECTURE.md`** — design truth. Critical sections:
   - §1 (spine rule)
   - §3 (memory model: LTM / STM / Bag of Evidence)
   - §3.6 (three temporal directions)
   - §12.2 (Park Phase — explicit 7 steps)
   - §13 (cross-cutting principles)
   - §15 (resolved-by-tranche status + still-open questions)
4. **`_docs/planning/TARGET_STATE.md`** — the binding target map for the chat-centered sidecar phase. Read this before proposing new interface or workflow work.
5. **`_docs/continuity/WE_ARE_HERE_NOW.md`** — the fastest pickup note. If you need the “where are we now?” answer first, read this before the deeper docs.
6. **`_docs/planning/IMPLEMENTATION_ROADMAP.md`** — tranche-by-tranche plan. Look at which tranches are marked `✓ COMPLETE` and which is next. The "Tranche status" headers carry metrics + the journal entry uid + evidence hashes from each closeout.
7. **`_docs/reference/SOURCE_PROVENANCE.md`** — what was written fresh vs structurally borrowed from `.parts/.dev-tools-REF/`. Includes per-tranche entries with evidence hashes.
8. **`_docs/reference/TOOLS.md`** — registered tools index. Source of truth for tool count is the `tool_registry` table; this file is its mirror, regenerated each Park Phase.
9. **`_docs/reference/TRAINING_RUNWAY.md`** — T8 teaching/evaluation runway, seed scenarios, reviewer export flow, and live-proof doctrine.
10. **`_docs/continuity/ONBOARDING.md`** (this file) — convenience orientation and command surface.
11. **`README.md`** — current status banner, folder map, the invariant.
12. **`_docs/planning/NORTHSTARS.md`** — what the substrate can already do vs what still separates it from the chat-centered prototype target.
13. **`_docs/history/DEV_LOG.md`** — append-only milestone narrative.
14. **`_docs/`** — supporting docs:
   - `migration/INCORPORATION_INVENTORY.md` — what was reviewed from the precursor at Tranche A.
   - `continuity/LATEST_PARKED_TRANCHE.json` / `.md` — generated authoritative closeout metadata for the latest parked tranche.
   - `history/tranches/T1_CLOSEOUT_NOTES.md` — T1 Park artifact (now SUPERSEDED by its journal entry, retained as code-time mirror).
   - `history/tranches/T2_PARK_NOTES.md` — T2 Park artifact.
   - `history/tranches/T2_AUDIT_DECISION.md` — why Park Phase is now contract-bound + mechanically enforced.

## Live-state verification commands (read-only)

```bash
# What is the schema, who has acked, what's the contract hash?
python -m src.app cli version

# What projections are queryable?
python -m src.app cli list-projections

# What does the human dashboard look like right now?
python -m src.app cli projection human_dashboard

# What does the Tk viewport bundle look like right now?
python -m src.app cli projection viewport_state

# What does the agent bootstrap (PAST/PRESENT/FUTURE) look like?
python -m src.app cli projection agent_bootstrap
python -m src.app cli projection bcc_constraint_map
python -m src.app cli projection runtime_cockpit
python -m src.app cli projection training_runway
python -m src.app cli projection installed_project_proof
python -m src.app cli public-export-preview
python -m src.app cli public-export-audit

# Show every tranche journal entry (the canonical closeout records)
python -m src.app cli journal-query --kind tranche

# Show every decision journal entry
python -m src.app cli journal-query --kind decision

# Show the deferred carry-forward backlog (journal is the source of truth)
python -m src.app cli journal-query --kind todo --status open

# What tools are registered?
python -m src.app cli tool-list

# What is the cold-team handoff packet?
python -m src.app cli projection handoff
python -m src.app cli projection training_runway

# What approvals or sessions are live?
python -m src.app cli approval-list --all
python -m src.app cli session-list
python -m src.app cli local-agent-status
python -m src.app cli local-agent-run-list
python -m src.app cli local-agent-models
python -m src.app cli local-agent-preflight --actor "agent:local:ollama" --model "qwen3.5:9b"
python -m src.app cli training-scenario-list
python -m src.app cli training-run-scenario --scenario-id python_notes_cli --mode mocked --variant good
python -m src.app cli installed-proof-show
python -m src.app cli installed-proof-verify

# What's the latest scan and git state?
python -m src.app cli scan-status
python -m src.app cli git-status

# Active Tranche Ledger (T2.5+)
python -m src.app cli tranche-status        # current tranche + live checklist
python -m src.app cli decision-list         # decisions recorded this tranche
python -m src.app cli projection tranche_checklist   # raw checklist projection

# Smoke-test the full stack (the gate that says "this is in good order")
python smoke_test.py

# Launch the Tk monitoring console
python -m src.app ui
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

Starts the MCP stdio server. Supports `initialize`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, `sidecar/submit`, `ping`. Tool calls become `tool_invoked` envelopes routed through the spine; `sidecar/submit` sends non-tool envelopes (including `acknowledge_contract` and `request_authority_elevation`) through the same gate and event log.

By default, starting MCP also launches the Tk monitor as a companion window so a human can watch the sidecar live while an agent is attached. Use:

```bash
python -m src.app mcp --no-ui
```

when you explicitly want a headless agent session.

**First read for an MCP-connected agent:**
1. `sidecar/submit` an `acknowledge_contract` envelope for your MCP actor.
2. `resources/read` with `uri="projection://agent_bootstrap"` for the PAST/PRESENT/FUTURE snapshot.
3. `tools/list` to see what's available.
4. `sidecar/submit` a `request_authority_elevation` envelope when you need approval for a bounded mutation.
5. `tools/call` for `read_projection`, `file_tree_snapshot`, `text_file_writer`, etc.

**Chat review / park flow (T10.2 surface):**
1. `resources/read` with `uri="projection://tranche_review_gate"` to inspect the current tranche state and allowed actions.
2. If a review packet exists, `resources/read` with `uri="review://latest"` to inspect both the structured JSON packet and the Markdown review packet.
3. Use `sidecar/submit` for `request_tranche_review`, `return_tranche_review`, `approve_tranche_review`, and `close_tranche`.
4. Only submit `close_tranche` after `projection://tranche_review_gate` shows `close_tranche` in `allowed_actions` or `park_phase_allowed=1`.
5. After Park Phase, `resources/read` with `uri="closeout://latest"` to inspect the derived closeout metadata in both JSON and Markdown form.

These chat-cockpit resources are inspectable surfaces over existing truth, not a second memory system:
- `projection://tranche_review_gate`
- `projection://handoff`
- `projection://agent_bootstrap`
- `review://latest` and `review://<review_id>`
- `closeout://latest` and `closeout://<journal_entry_uid>`

## Memory model in one breath

- **LTM** = everything on disk the agent can read: journal, projections, project code, sidecar code, contract, event log.
- **STM** = the active working window. MCP-connected agents still manage this externally; the local sidecar agent now has sidecar-managed STM persisted in `session_memory_items`.
- **Bag of Evidence** = the bridge layer. Older local-agent working context overflows from STM into Bag rows so it can be recalled later without pretending it is LTM.
- **Evidence Shelf** = the compact working set derived from STM + Bag + recent hunk provenance. It is surfaced in `agent_bootstrap` and the Tk monitor for quick continuity.

When designing anything that persists, ask: STM, Bag, or LTM?

## How to resume the previous session's work

1. Read `_docs/planning/IMPLEMENTATION_ROADMAP.md` — find the next tranche **not** marked `✓ COMPLETE` (now T10).
2. Read the latest `_docs/history/tranches/T_n_PARK_NOTES.md` — it captures the previous tranche's closeout in detail.
3. Run `python -m src.app cli projection agent_bootstrap` — gives you PAST + PRESENT + FUTURE in one read.
4. Run `python smoke_test.py` — verifies the state is clean. If it's not, **fix Park Phase drift first**.
5. Run `python -m src.app cli journal-query --kind todo --status open` — review the normalized deferred backlog before starting new work.
6. If the work touches the interaction model, read `_docs/planning/TARGET_STATE.md` before shaping any plan.
7. Read the relevant runtime and doc surfaces for the next tranche's target files.
8. Begin work. Acknowledge the contract if you haven't.

## How to close a tranche (the codified ritual)

Per **BCC §10.8 / ARCHITECTURE.md §12.2 + §3.7** — tranche close now has a required **Review Gate** before the existing Park Phase artifacts are sealed. Manual steps are kept for reference.

### Active Tranche Ledger path (T2.5+, recommended)

During the tranche, capture work as you go:
```bash
# Declare the tranche at the start (creates the ledger record):
python -m src.app cli tranche-declare --actor "human:you" --title "T4 Proposal + Approval Cycle" \
    --scope "Build approval queue, human grants, and guarded Apply workflows" \
    --completion-criteria "Approved proposals can move from queue to recorded mutation"

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

# Request the mechanical review packet:
python -m src.app cli tranche-review-request --actor "human:you"

# Inspect the generated packet:
python -m src.app cli tranche-review-show

# Either return the tranche to the agent:
python -m src.app cli tranche-review-return --actor "human:you" --reason "Tighten the out-of-scope list first"

# Or approve review and immediately run Park Phase:
python -m src.app cli tranche-review-approve --actor "human:you"
```

At close, the orchestrator now:
1. Validates the checklist (contract acked, scope declared, smoke passed)
2. Generates a mechanical review packet and moves the tranche to `review_pending`
3. Requires explicit human approval before Park Phase can begin
4. Compiles `_docs/history/tranches/Tn_PARK_NOTES.md` from the structured ledger data
5. Creates + closes the tranche journal entry with evidence refs
6. Seals the `active_tranche` record (status → 'parked')
7. Updates continuity meta key

### Manual path (pre-T2.5 reference, still valid)
1. Write `_docs/history/tranches/T_n_PARK_NOTES.md` manually.
2. Capture: `python -m src.app cli ...`; record the blob hash.
3. Journal: `python -m src.app cli journal-write --kind tranche --title "..." --body-file _docs/history/tranches/T_n_PARK_NOTES.md --evidence-hash <hash> --importance 8`
4. Update continuity docs: `_docs/planning/IMPLEMENTATION_ROADMAP.md`, `_docs/reference/SOURCE_PROVENANCE.md`, `_docs/reference/TOOLS.md`, `_docs/reference/ARCHITECTURE.md §15`, `README.md`.
5. Close: `accept_task` → `complete_task` → `close_journal_entry`.
6. Re-run `python smoke_test.py` — must PASS.

If `smoke_test.py` fails after Park Phase, **the tranche is not parked.** Fix and repeat.

## Approval loop quick path

```bash
# Agent or simulated actor requests elevation for one bounded workspace write
python -m src.app cli approval-request --actor "agent:mcp:demo" \
    --requested-level Apply \
    --summary "Write workspace proof" \
    --justification "Need a bounded text write inside workspaces/ for T4 workflow proof" \
    --scope-json "{\"tool_name\":\"text_file_writer\",\"target_domain\":\"workspace\",\"path\":\"demo/proof.txt\"}"

# Human approves from CLI (the Tk Contracts tab can do the same)
python -m src.app cli approval-approve --actor "human:you" --request-id "<approval_id>"

# Approved actor performs the bounded write
python -m src.app cli tool-invoke --actor "agent:mcp:demo" --tool text_file_writer \
    --input-json "{\"path\":\"demo/proof.txt\",\"content\":\"approved\\n\",\"confirm\":true,\"create_dirs\":true,\"target_domain\":\"workspace\"}"
```

## Local-agent quick path

```bash
# Check that the local runtime is healthy and the target model is available
python -m src.app cli local-agent-status
python -m src.app cli local-agent-preflight --actor "agent:local:ollama" --model "qwen3.5:9b"

# Run the bounded local-agent floor
python -m src.app cli local-agent-run --actor "agent:local:ollama" --model "qwen3.5:9b" \
    --prompt "Read the bootstrap, inspect the project, and propose the next safe step."

# Keep the run headless when needed
python -m src.app cli local-agent-run --no-ui --actor "agent:local:ollama" --model "qwen3.5:9b" \
    --prompt "Headless local-agent run."

# If you need to stop a long run cooperatively
python -m src.app cli local-agent-stop --actor "agent:local:ollama"
```

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
