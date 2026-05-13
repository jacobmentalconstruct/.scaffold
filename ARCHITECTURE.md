# ARCHITECTURE.md — Design Truth

> **Status:** Tranche B revision. Folds in the Memory Model + Operational Rituals + Cross-cutting Principles + Constraint Registry from precursor doctrine review (see [`_docs/INCORPORATION_INVENTORY.md`](_docs/INCORPORATION_INVENTORY.md)). The original Tranche 0 design (sections 1–11 below, renumbered) is preserved verbatim where it stood; new content is in §3, §12, §13, §14.

> The code in `src/` is being scaffolded toward this design. As code lands, this document remains the authoritative source for *intent*; the code is the authoritative source for *behavior*. Drift between the two is a defect.

---

## 1. The spine, in one sentence

> Every state mutation flows: **Interface → Envelope → Router → ContractCheck → Orchestrator → Manager → Event → derived views.** No sideways calls. No back-channels. The envelope is the only currency.

If something feels awkward to build later, it will be because someone wanted to violate this rule.

---

## 2. The hybrid-in-SQLite spine

A single SQLite database at `data/sidecar.db` carries three layered concerns:

1. **Authoritative event log** — append-only record of every accepted envelope. This is the durable memory.
2. **Graph index** — typed relations between objects, derived from events. The "branch/root/leaf" connective tissue.
3. **Projection tables** — current-state read models built from events + graph. The UI and the agent only read these.

The state on disk evolves to be event-sourced. Day-one shape is dual-write (state tables + event log) for simplicity, but every event must carry enough information to reconstruct the mutation it represents — the door to true event-sourcing stays open.

---

## 3. The Memory Model (LTM / STM / Bag of Evidence) — *load-bearing*

This is the conceptual reason the spine, the journal, the projections, and the evidence layer all exist together. Three layers, one bridge.

### 3.1 LTM — Long-Term Memory

Everything persistent on disk that the agent can read. **Not a single artifact — a *surface*.**

LTM includes:
- The **journal** (`journal_entries` table + projection)
- The **event log** (`events` table)
- The **graph relations** (`relations` table)
- All **projections** (`proj_*` tables)
- The **project_index** (the sidecar's understanding of the host project's files)
- The **logs** under `logs/`
- The **contracts** under `contracts/` and the seeded constraint registry tables
- The **host project's own code and docs** (read-only from the sidecar's perspective)
- The **sidecar's own code** (the runtime can introspect itself)

Each piece is durable, addressable, re-readable across sessions, and constitutes part of the agent's long-term knowledge of "what has happened" and "what is true."

### 3.2 STM — Short-Term Memory

The sliding window inside the agent's current context. Provides *causal perspective* — "here's what we just talked about," "here's the envelope I'm currently constructing," "here's the projection I just read."

Bounded by the LLM's context window. **In our first prototype the agent is external (e.g., Claude Code via MCP), so STM is managed by the agent's runtime, not by the sidecar.** When we eventually run our own local agent (DP1 deferred), the sidecar will manage STM directly.

### 3.3 Bag of Evidence — the bridge

When STM overflows (the context window is about to be exceeded), items archive into the **Bag of Evidence**: a session-scoped store with hashed bodies + searchable summaries. From the Bag, important items can be **promoted** to journal entries (i.e., promoted into LTM proper).

The flow (precursor terminology, adopted): `Window → Archive → Shelf → Retrieve → Promote`.

The Bag is what lets a multi-turn agent session exceed the context window without losing continuity. On a new session, the agent boots from LTM (journal + projections); the prior session's Bag may or may not be loaded.

### 3.4 Status in the first prototype

- **LTM:** fully built out (journal_manager, project_index_manager, evidence_manager, projections, event log).
- **STM:** out of scope (managed externally by the agent client).
- **Bag of Evidence:** **schema fields reserved on `events` and `evidence` tables** (`session_id`, `evidence_kind`, `body_hash`, `summary`, `is_durable`), but the overflow logic and promotion flows are **DEFERRED** until we run our own local agent. See `IMPLEMENTATION_ROADMAP.md` deferred list.

### 3.5 Why this matters for design decisions

Whenever a piece of state is being designed, ask: *does this belong in STM, the Bag, or LTM?*

- If it dies with the conversation: STM (don't persist).
- If it overflowed STM but is still session-relevant: Bag (persist, hash, summarize).
- If it should outlive any session: LTM (journal entry or projection row).

This test prevents two classes of drift: (a) treating transient context as if it were durable truth, and (b) losing session-relevant context because there was nowhere bridge-shaped to put it.

### 3.6 Three temporal directions: past, present, future

The agent's accuracy in translating "the next step → code or structure" depends on three temporal directions converging at the moment of action:

- **Past — via the sliding window over history.** The STM is not just current context; it is the agent's *view backward into LTM.* The window scans recent journal entries, recent events, prior envelopes in the correlation chain, the trail of decisions that led here.
- **Present — the anchor.** The window terminates at the present moment: the current task, the active envelope, the current authority, the right-now state. The anchor is *where the agent is acting from.*
- **Future — awareness of the plan.** The agent also carries forward intent: the current tranche scope, the next step in [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md), the goals not yet met, what comes next.

Lose any one and the work degrades:
- Lose the **past** → reinvent wheels, contradict prior decisions, miss prior context.
- Lose the **present anchor** → act in the abstract, untethered from current state.
- Lose the **plan** → drift into local optimization with no global direction.

This is why the `agent_bootstrap` projection (see [`src/schemas/projection_schema.py`](src/schemas/projection_schema.py)) carries all three temporal layers: PAST (recent_events_json, recent_journal slices), PRESENT (current_task_json, authority_json, state snapshot), FUTURE (current_tranche_scope_json, next_planned_steps_json, active_goals_json). When an agent connects, it gets all three in one read.

The "plan" is itself a piece of LTM, but it has a special role: it is the only LTM content that is *forward-looking by nature*. The journal and events record the past; the projections describe the present; the plan describes the intended future. Keeping the agent's perception of the plan consistent with what the journal and event log show is the job of the bootstrap projection's forward fields — they're regenerated every time `IMPLEMENTATION_ROADMAP.md` revises or a tranche closes.

### 3.7 Active Tranche Ledger — "capture once, derive many"

Added at T2.5 (2026-05-11). The problem it solves: the Park Phase rituals in §12.2 historically required reconstructing park notes from scratch at tranche close — a manual, error-prone process that produced drift.

The Active Tranche Ledger makes documentation **a continuous accumulation, not a final reconstruction**:

| Concept | Where it lives | What it captures |
|---|---|---|
| **`active_tranche`** table | `data/sidecar.db` | Single active tranche object: declared_scope, non_goals, completion_criteria, files_changed, tests_run, deviations, open_questions, evidence_refs |
| **`decision_records`** table | `data/sidecar.db` | Typed decisions: title, context, rationale, outcome, impact_area, alternatives, evidence_refs |
| **`proj_tranche_checklist`** projection | `data/sidecar.db` | Live readiness check — 9 items, each 'pass'/'fail'/'warn'/'pending' |
| **`close_tranche`** envelope | `closeout_orchestrator.py` | Reads the ledger, compiles park notes, writes `_docs/Tn_PARK_NOTES.md`, creates + closes tranche journal entry, seals ledger |

**The workflow:**
1. `tranche-declare` → creates `active_tranche` row with scope + goals.
2. During work: `decision-record` captures typed decisions as they happen.
3. `tranche-update` appends files_changed, deviations, open_questions.
4. `tranche-smoke-pass` records a smoke test PASS in tests_run.
5. `tranche-status` shows the live checklist (are required items satisfied?).
6. `tranche-close` — the "push a button" step. Reads all accumulated data, compiles Markdown park notes, creates + closes the tranche journal entry, seals the ledger. All 5 Park Phase artifacts are produced atomically.

**Principle:** *capture once, derive many.* A single `DecisionRecord` feeds:
- The `decision_records` table (queryable by future agents)
- The compiled park notes (`_docs/Tn_PARK_NOTES.md`)
- The tranche journal body
- The `agent_bootstrap.recent_decisions` PAST field

The `tranche_checklist` projection is the live gate. Before `close_tranche` runs, required items must all be 'pass'. After `close_tranche`, the entire checklist should be green.

---

## 4. The MVP-5 (+ ConstraintManager)

In this implementation order:

1. **`SidecarState`** (`src/core/state.py`) — the in-memory current-state registry. Knows project root, sidecar root, current contract, registered objects, registered tools, active task, current projections, event log position, journal state, evidence bag state, ontology state, agent status, human UI status. Nothing bypasses this.
2. **`SidecarEnvelope`** (`src/core/envelope.py`) — the unified message shape. Eighteen frozen fields (see §7). Routes and identifies; does not carry heavy payloads.
3. **`EventStore`** (`src/core/events.py`) — appends every accepted envelope as an event in the appropriate stream (`project`, `task`, `object`, `tool`).
4. **`Router`** (`src/core/router.py`) — accepts envelopes and dispatches them after contract check.
5. **`ProjectionManager`** (`src/core/projections.py`) — builds read models from events + graph for the UI and agent.

**Plus `ConstraintManager`** (`src/managers/constraint_manager.py`) — owns the constraint registry tables that the gate consults. ContractAuthority cannot do its job without ConstraintManager being present, so the two are bootstrapped together in T1.

Once these six exist, every other department attaches without bending the shape.

---

## 5. The ten layers (reference model)

| # | Layer | Lives in | Role |
|---|---|---|---|
| 1 | State Spine | `src/core/state.py` | Central living state registry. |
| 2 | Interface Layer | `src/interfaces/`, `src/ui/` | MCP and Tkinter as peers; both produce envelopes. |
| 3 | Router | `src/core/router.py` | Nervous system; dispatches envelopes. |
| 4 | Orchestrators | `src/orchestrators/` | Coordinate workflows across managers. |
| 5 | Managers | `src/managers/` | Own one domain each; validate/update/query their state. |
| 6 | Components | `src/components/` | Small replaceable mechanical workers. |
| 7 | Envelope | `src/core/envelope.py` + `src/schemas/envelope_schema.py` | The polymorphic object that travels through the spine; surfaces consumed selectively by each participant. |
| 8 | Event Store | `src/core/events.py` | Durable append-only memory. |
| 9 | Graph | `src/core/graph.py` | Typed relations (closed set; see §8). |
| 10 | Projections | `src/core/projections.py` | Read models for UI/agent. |

The hard rule: **Managers own one domain's state. Orchestrators coordinate across domains. If a manager calls another manager directly, it should have been an orchestrator.**

---

## 6. Authority levels

Every envelope carries an authority claim. The agent's default is `Observe` or `Propose`. Authority climbs only by contract and approval.

| Level | Meaning |
|---|---|
| Observe | Read sidecar and project state. No writes. |
| Propose | Create draft envelopes (journal proposals, patch plans). No state change outside the proposal record. |
| Sandbox Execute | Run tools in an isolated `workspaces/` workspace. No project-tree writes. |
| Apply | Write to the host project tree. Requires explicit human approval per envelope. |
| Export | Emit artifacts outside `.scaffold/`. Requires explicit human approval per envelope. |

The authority decision is made by `ContractAuthority` (`src/core/contracts.py`), which consults `ConstraintManager` (`src/managers/constraint_manager.py`) for the relevant constraints.

---

## 7. The frozen envelope (eighteen fields)

```
envelope_version    object_id           object_type
project_id          sidecar_id          actor_id
created_at          operation_intent    status
source_refs         relation_refs       contract_refs
evidence_refs       event_id            correlation_id
causation_id        surface_manifest    payload_ref
```

**Surfaces** (sections of the envelope) are consumed selectively:
- *Router* reads routing identity and authority.
- *ContractAuthority* reads `contract_refs`, `actor_id`, `operation_intent`.
- *Orchestrator* reads `operation_intent` and `surface_manifest`.
- *Manager* reads `payload_ref`, `evidence_refs`, `relation_refs`.
- *EventStore* records the whole envelope verbatim.
- *Projections* consume the historical record, not envelopes in flight.

**Lightness rule:** envelopes route and identify. Heavy content (diffs, vectors, ASTs, screenshots, large text bodies, logs) is stored separately and referenced via `payload_ref` and `evidence_refs`.

---

## 8. Event streams (mixed) and relation types (closed)

**Event streams** (no single dumping ground):
- `project` — install, scan completed, project map updated
- `task` — task created, superseded, completed
- `object` — file observed, journal entry created, contract acknowledged
- `tool` — tool invoked, tool result, tool failed

**Relation types** (closed set; generic `related_to` is banned):
`belongs_to`, `observes`, `derives_from`, `supersedes`, `cites`, `modifies`, `validates`, `requires`, `emitted_by`, `approved_by`, `failed_due_to`, `produces`.

---

## 9. Day-one projections

The first set of projections built from events + graph:

- Current Sidecar State
- Agent Bootstrap Packet
- Human Dashboard View
- Evidence Bag View
- Contract Status View
- Project Map View
- Journal Timeline View

---

## 10. The first proving loop

The end-to-end scenario that proves the sidecar exists, sees, records, links, projects, and explains — *before* it tries to change anything:

1. Install sidecar into project.
2. Scan project files.
3. Create project map.
4. Emit events for scan.
5. Create graph edges for file structure.
6. Generate human dashboard projection.
7. Generate agent bootstrap packet.
8. Agent proposes a small journal entry or patch plan.
9. Human can inspect the evidence.

Nothing mutates the host project at this stage. See [`IMPLEMENTATION_ROADMAP.md`](IMPLEMENTATION_ROADMAP.md) for the tranche order to reach this loop end-to-end.

---

## 11. Truth-layer separation (per contract §C)

| Layer | Source of truth | Lives at |
|---|---|---|
| Builder memory | Sidecar SQLite | `data/sidecar.db` |
| Design | This document | `/ARCHITECTURE.md` |
| Runtime-consumed | Host project's own stores | wherever the host puts them; the sidecar reads but does not own |

---

## 12. Operational rituals

Folded in from precursor doctrine (Tranche A.1). These are *governance rhythms*, not architecture primitives. They shape how humans and agents collaborate across sessions and how work is bounded.

### 12.1 Setup Phase

When the sidecar is first dropped into a new project, the **Setup Phase** must complete before any feature work begins. The phase is owned by `install_orchestrator` and consists of:

1. Verify project root and sidecar root.
2. Open / create `data/sidecar.db`; run schema creation.
3. Seed contract; compute hash; record acknowledgment slot (still empty).
4. Seed ontology + closed predicate set + constraint registry from the binding contract.
5. Write seed config files (`config/sidecar.json`, `journal_config.json`, `db_manifest.json`, `toolbox_manifest.json`).
6. Emit `install` event in the `project` stream.
7. Build the first agent bootstrap projection.
8. **Gate further work** until contract acknowledgment is recorded.

The discipline is "setup before features." A fresh agent connecting to a freshly-installed sidecar must complete the acknowledgment step (via `journal_acknowledge` tool) before any other operation than `Observe` is permitted.

### 12.2 Park Phase (tranche closeout) — EXPLICIT and MECHANICALLY ENFORCED

When a tranche of meaningful work completes, the **Park Phase** produces a structured *parking record* that allows the next session (human or agent) to resume cleanly. **The phase is not optional and is not "ritual we remember in conversation"** — it is codified in this section, bound by `contracts/builder_constraint_contract.md §D`, and mechanically enforced by `smoke_test.py` drift-detection sections that fail when any continuity doc is stale.

#### The seven steps

1. **Inspect.** Gather metrics for the tranche: files added/modified, lines, new tables, new handlers, new tools, new projection builders, schema migration applied. State and host-project deltas since tranche open.

2. **Verify.** Run `python smoke_test.py`. All sections must PASS before proceeding. If any fail, fix and re-run; do not proceed with Park Phase until verification is green.

3. **Capture.** Write `_docs/T_n_PARK_NOTES.md` (code-time mirror) capturing the inspect output, decisions made at code time, files touched, proving-loop status. Put the file's bytes in `blob_store` via `state.blob_store.put`; record the SHA-256 hash and the post-capture Merkle root.

4. **Journal.** Dispatch a `create_journal_entry` envelope with:
    - `kind='tranche'`
    - title `"T_n <subject> — COMPLETE"`
    - body from `_docs/T_n_PARK_NOTES.md`
    - `evidence_refs=[{"hash": "<park_notes_hash>", "kind": "external"}]`
    - tags `["tranche", "closeout", "t_n", ...]`
    - importance ≥ 8
    - `related_path` pointing at the park notes file.

5. **Update continuity docs (explicit checklist).** Every item below must be touched, otherwise smoke test drift-detection (step 6) will fail:
    - **`IMPLEMENTATION_ROADMAP.md`** — mark the tranche `✓ COMPLETE` with metrics + evidence hash + the tranche journal entry's uid + the `task_completed` event id.
    - **`SOURCE_PROVENANCE.md`** — append a dated entry distinguishing original code from structurally-borrowed patterns; cite evidence hashes; record the new journal entry uid.
    - **`TOOLS.md`** — regenerate/update so the registered-tools table row count equals `tool_registry` table row count. Any tools added in the tranche get a row here.
    - **`ARCHITECTURE.md §15`** — add a `Resolved at T_n` subsection listing the open questions this tranche resolved. Carry the still-open list forward.
    - **`README.md`** — update the top-level status header if it references a prior tranche. The header must reflect current state.
    - Any other doc with a status banner referencing a prior tranche.

6. **Re-verify.** Run `python smoke_test.py` again. The drift-detection sections (introduced 2026-05-11) verify mechanically that step 5 was performed:
    - `TOOLS.md` row count equals `tool_registry` count.
    - `README.md` status header does not name a prior tranche as current.
    - `ARCHITECTURE.md §15` has `Resolved at T_n` for every completed tranche.
    - The latest tranche journal entry has `status='closed'` (after step 7).
    - The latest tranche journal entry's `evidence_refs` cite an existing `blob_store` hash.

   If smoke test fails, the tranche is NOT parked. Fix and repeat from step 5.

7. **Report and close.** In the spine, dispatch in order:
    - `accept_task` envelope marking the tranche lifecycle (informational).
    - `complete_task` envelope (correlated to the above by `correlation_id`).
    - `close_journal_entry` envelope for the tranche entry written in step 4, moving its status from `'open'` → `'closed'`. The tranche entry CONTENT is immutable per Journal Doctrine §13.1; the status change is a non-destructive lifecycle update.

#### What a parking record IS

A complete parking record is the union of five artifacts:

a) The tranche journal entry (`kind='tranche'`, `status='closed'`).
b) The linked park-notes blob in `blob_store` (cited via `evidence_refs`).
c) The updated continuity docs (per the §5 checklist).
d) The `accept_task` + `complete_task` events.
e) The `close_journal_entry` event for the tranche entry.

If any of the five is missing, the tranche is **not parked**, the next tranche **must not begin**, and `smoke_test.py` drift-detection should be the one to surface it.

#### Why this is contract-bound

Without mechanical enforcement, Park Phase discipline drifts back into conversational ritual within a few sessions. The contract clause (`§D Park Phase Discipline`) makes it a HARD_BLOCK gate violation to begin a new tranche while drift exists. The smoke test makes the violation observable to any agent or human inspecting the codebase cold.

### 12.3 Collaboration Rhythm

The lived rhythm of how humans and agents share the sidecar:

- **Orient from manifests, not from weeds.** New session starts by reading `config/toolbox_manifest.json` and the `agent_bootstrap` projection. Don't dive into source code first.
- **Choose the right surface.** Some intents are tools (envelope-routed); some are projections (read-only); some are journal entries (durable narrative); some are evidence attachments. Use the surface that fits.
- **Work inside boundaries.** The sidecar writes only inside `.scaffold/` unless an envelope carries `Apply` or `Export` authority. The agent never bypasses this.
- **Verify before celebrating.** Smoke test before declaring a tranche done. Look at what changed; don't trust the absence of error messages.
- **Leave a clean return path.** Park before stopping. The next session shouldn't have to reverse-engineer state.

---

## 13. Cross-cutting principles

Folded in from precursor patterns (Tranche A.1, A.3).

### 13.1 Journal Doctrine

The journal is **authoritative builder memory.** Three rules:

1. **Append-only.** Updates create new revision rows; original rows are retained for audit. Never overwrite, never delete (archive is the only "removal" mode).
2. **No generated mirrors as truth.** If a fact lives in a generated config file (`db_manifest.json`, `toolbox_manifest.json`, `tool_manifest.json`), the *source* of that fact lives in the DB. The mirror is a convenience for human inspection and external tooling; the DB wins on conflict.
3. **Deferred work belongs in the journal, not in chat memory.** A TODO becomes a `kind='todo' status='open'` entry. A decision becomes a `kind='decision'` entry. Never "I'll remember to do X" — the journal remembers, not us.

### 13.2 Guarded mutation

Every envelope that *mutates* anything outside `.scaffold/` (i.e., any `Apply` or `Export` authority operation) must follow the **guarded mutation** pattern:

- **Dry-run first.** Tool emits a description of what would change without doing it. Human (or higher-authority agent) reviews.
- **Explicit reason.** Envelope carries a `reason` payload — not just "what" but "why."
- **Confirmation step.** Approval is recorded as an `approved_by` relation in the graph, citing the approving actor and timestamp.
- **Reversible where possible.** File writes go to a `workspaces/<id>/` sandbox first; promotion to the host project tree is a *separate* envelope under separate approval.

This pattern is universal for anything authority-elevated. The contract gate (`ContractAuthority`) enforces it by requiring `Apply`/`Export` envelopes to carry an `approved_by` relation_ref or a one-shot grant id.

### 13.3 Deterministic IDs

All identifiers in the sidecar — `event_id`, `object_id`, `evidence_id`, `relation_id`, `entry_uid` — use **deterministic, content-derivable** IDs where feasible:

- **`evidence_id`:** SHA-256 of body bytes (truncated to 16 hex chars).
- **`event_id`:** ulid (sortable, monotonic-ish) — not strictly content-derivable, but reproducible from a given `(timestamp, sidecar_id, sequence)`.
- **`relation_id`:** SHA-256 of `(subject_id, predicate, object_id, emitted_by)`.
- **`entry_uid`:** `journal_<sha256_of_body[:12]>`.

Why: deduplication, replayability, mergeability across sidecar instances. If two sidecars independently create "the same" evidence (same bytes), they get the same `evidence_id` and the merge is trivial.

(This principle is the one carry-forward from the `_manifold-mcp` package's design — see [`_docs/INCORPORATION_INVENTORY.md`](_docs/INCORPORATION_INVENTORY.md) §3.2.)

---

## 14. The constraint registry

The binding contract at `contracts/builder_constraint_contract.md` is a long-form document. The **constraint registry** projects it into addressable, queryable units so the contract gate can ask narrow questions and get focused answers.

Two tables, owned by `src/managers/constraint_manager.py`:

- **`constraint_units`** — each row is one atomic constraint, with `severity` (HARD_BLOCK | PUSHBACK | ADVISORY) and `tier` (spirit | letter | gate).
- **`task_profiles`** — named bundles of constraint UIDs (e.g., `core_implementation`, `refactoring`, `documentation`, `cleanup`, `tool_creation`, `scaffolding`).

**Gate flow:** `ContractAuthority.check(envelope)` consults `ConstraintManager.query_for_intent(envelope.operation_intent)` to get the relevant constraints, evaluates them against the envelope's authority + actor + payload, and returns ACCEPT / REJECT.

This separation keeps `core/contracts.py` thin (gate only) while letting the registry be queryable independently — for the agent bootstrap projection, for the contracts UI panel, for tools that introspect rules.

See [`src/managers/constraint_manager.py`](src/managers/constraint_manager.py) for the full plan.

---

## 15. Open questions — status by tranche

### Resolved at T1 (2026-05-10)

- **ID format** — RESOLVED: chose stdlib-only sortable IDs (`{prefix}{time_ns:016x}_{8 hex random}`) over ulid/uuid7. Contract Pledge 1 (stdlib only) was the deciding constraint. Format is monotonic-ish, sortable, and dedupable.
- **Constraint decomposition format** — RESOLVED for now: hand-curated seed (12 constraint units, 6 task profiles) lives in `src/managers/constraint_manager.py` `_SEED_CONSTRAINTS`/`_SEED_PROFILES` constants. Markdown-decomposition tooling deferred to T6+.
- **Connection model** — RESOLVED for T1: single `sqlite3.Connection` per `Store` instance, `check_same_thread=False`. Will revisit when T3 Tk UI process meets T2 MCP server process at the SQLite spine.
- **SQLite pragmas** — RESOLVED: WAL + foreign_keys=ON + busy_timeout=10000 + synchronous=NORMAL.
- **Bootstrap exception in gate** — RESOLVED: `BOOTSTRAP_EXEMPT_INTENTS` tuple in `contract_schema.py`. The acknowledgment-presence check is bypassed only for these intents and only while no acknowledgment exists.
- **Two-phase ack/event commit** — RESOLVED: ack rows written with `event_id='PENDING'` inside `handle_acknowledge`, then Router calls `ContractAuthority.finalize_ack_event_id` after `EventStore.append` returns the real id.

### Resolved at T2 (2026-05-11)

- **MCP transport** — RESOLVED: stdio. JSON-RPC 2.0 framed by newline-delimited JSON. Single-process MCP server reads stdin, writes stdout. HTTP transport deferred to Phase 2.
- **Two-phase pattern generalization** — RESOLVED: the T1 ack-row PENDING pattern was extended to journal entries (`journal_manager.finalize_entry_event_id`) and scan records (`scan_orchestrator.finalize_scan_event_id`). Router has explicit elif chain for each. Will refactor to callback registry if a 4th case appears.
- **Tool registry architecture** — RESOLVED: dual in-memory + DB. The `tool_registry` table persists metadata + source_hash; an in-memory `dict[tool_name, RegisteredTool]` carries the live `run_fn` callable. Discovery on every boot is idempotent via INSERT...ON CONFLICT.
- **HARD_BLOCK gate enforcement strategy** — PARTIALLY RESOLVED: the gate (`core/contracts.py`) enforces authority + ack + envelope shape + closed-relation-set; HARD_BLOCK constraint texts are surfaced via `ConstraintManager.query_for_intent` but the gate's `_check_hard_block` is currently advisory (returns None). Specific enforcement (e.g., path containment for `Apply`) lives in the managers/orchestrators that actually mutate the relevant resource. Tools enforce their own `required_authority` inside `tool_registry_manager.handle_invoke`.
- **Per-file scan events** — RESOLVED (design choice): scan emits ONE event with a summary blob; per-file observations live in `project_index` table. Per-file events would violate Envelope Lightness (Pledge 7). If per-file audit ever needed, add a separate `observe_file` event variant.
- **Per-file graph edges during scan** — RESOLVED (deferred): graph stays sparse; project_index carries the density. Graph relations land for journal/evidence chains, not for bulk file observations.
- **Actor identity for MCP sessions** — PARTIALLY RESOLVED: T2.3 uses `agent:mcp:<client_name>` derived from `params._meta.client_name`. Real per-session identity (token-based or capability-based) is deferred to T3+ when MCP sessions become first-class.
- **Tool source hash drift detection** — RESOLVED: `tool_registry.source_hash` is computed on every discovery; mismatch is logged. Hot-reload-on-mismatch is deferred to when it matters.
- **Park Phase discipline** — RESOLVED (Decision 2026-05-11, see journal entry `journal_18ae7fbc35603af0_ec2ea642`): the Park Phase is now an explicit checklist in §12.2, contract-bound in `builder_constraint_contract.md §D`, and mechanically enforced by `smoke_test.py` drift-detection sections. No more conversational ritual.

### Resolved at T2.5 (2026-05-11)

- **Park Phase documentation gap** — RESOLVED: the Active Tranche Ledger (`active_tranche` + `decision_records` tables, `tranche_checklist` projection, `close_tranche` orchestrator) replaces manual Park Phase documentation reconstruction with a "compile-and-seal" model. Decisions are captured as typed `DecisionRecord` objects during the tranche; `tranche-close` compiles the park notes programmatically. See §3.7 and `src/managers/tranche_manager.py`, `src/orchestrators/closeout_orchestrator.py`.
- **Two-phase PENDING pattern — 4th and 5th cases** — RESOLVED: `declare_tranche` → `TrancheManager.finalize_declare_event_id` and `record_decision` → `TrancheManager.finalize_decision_event_id` added to the Router elif chain. Contract noted in the T2 entry: "Will refactor to callback registry if a 4th case appears." That case appeared; refactor deferred to T3+ (the 5 cases are all explicitly handled).
- **Tranche checklist as live projection** — RESOLVED: `proj_tranche_checklist` added to `PROJECTION_NAMES` (8 projections total). Builder reads `TrancheManager.build_checklist(state)` which evaluates 9 items including `contract_acked`, `tranche_declared`, `scope_declared`, `smoke_test_passed`, and Park Phase completion items.
- **Decision capture during work** — RESOLVED: `decision-record` CLI command creates typed `DecisionRecord` with context/rationale/outcome/impact_area/alternatives. Records are queryable via `decision-list` and are automatically included in compiled park notes.

### Resolved at T2.6 / T2.6.1 (2026-05-11)

- **Ollama-generated park notes** — RESOLVED (T2.6): `OllamaClient` (`src/components/ollama_client.py`) wraps Ollama's `/api/generate` with stdlib only (Contract Pledge 1). `close_tranche --with-ollama` attempts LLM prose generation; falls back to template compiler on any failure. Park Phase never blocks on an external service.
- **qwen3.5 extended-thinking mode / empty response** — RESOLVED (T2.6.1): qwen3.5 routes reasoning to a separate `thinking` field by default, leaving `response` empty. Fixed by adding `"think": false` top-level in the Ollama payload. Exposed as `think=True` kwarg for callers that explicitly want chain-of-thought.
- **GPU OOM / token cap** — RESOLVED (T2.6.1): `num_predict: 8192` in Ollama `options` caps output tokens. Park notes are ~2–3k tokens; 8192 is a generous ceiling with no VRAM risk. Exposed as `--ollama-num-predict` CLI flag.

### Resolved at T3 (2026-05-12)

- **Human monitoring surface shape** — RESOLVED: the Tk UI landed as an observational monitoring console, not a mutation surface. `python -m src.app ui` boots a native Tk window with a tri-temporal dashboard plus state, journal, evidence, project-map, and contract drill-down panels.
- **Aggregated UI read model** — RESOLVED: `proj_viewport_state` added to `PROJECTION_NAMES` (9 projections total). It bundles topbar pills, focus counts, PAST/PRESENT/FUTURE slices, log tail, and status-bar data into one deterministic read model for the dashboard.
- **Evidence visibility** — RESOLVED: `evidence_bag` now has a real projection builder and is readable from both CLI and the Tk console. Full Bag/Shelf overflow workflows remain deferred, but evidence is no longer a stubbed surface.
- **Contracts panel staging** — PARTIALLY RESOLVED: a read-only `contracts_panel` landed in T3 so humans can inspect contract status, acknowledgments, and recent contract-related events. Approval queue actions and grant/revoke controls remain a T4 concern.
- **Process model first exercise** — PARTIALLY RESOLVED: the Tk surface now exists as a real `ui` app mode reading the SQLite spine. Sustained concurrent MCP + Tk usage against the same store is still deferred, but the "single store, multiple surfaces" architecture is now materially exercised.

### Still open (deferred to later tranches)

- **Concurrent multi-process behavior:** the Tk UI and MCP server now both exist as real surfaces, but long-lived concurrent use against the same SQLite spine has not yet been stress-tested. Expect WAL + busy_timeout to carry the prototype; verify under T4/T5 workload.
- **MCP transport:** stdio vs HTTP. Default to stdio for vendability. Decide in T2 when MCP interface is built.
- **Approval UX:** monitoring-only `contracts_panel` exists in T3; the actual approval queue shape (modal vs queue panel vs staged grant rail) remains a T4 decision.
- **Snapshot cadence:** on tranche close, on demand, both? Decide when building snapshot_orchestrator (T6+, deferred).
- **Schema migration test harness:** plan but defer.
- **Bag/Shelf overflow logic:** schema fields reserved (T1 ✓). Overflow flows deferred until we run our own local agent (Phase 2+).
- **HARD_BLOCK gate enforcement:** currently advisory in `ContractAuthority._check_hard_block` (returns None). Specific path-containment / shape checks live in the managers/orchestrators that touch the relevant resources, lands T2 with `install_orchestrator` and the project_index_manager.
- **Contract-revision-aware seed:** new T1 question — when contract markdown changes, should `seed_from_contract` produce a new contract record (new version row), or upsert in-place? Currently it upserts. Real revision flow needs versioning + a `supersedes` relation.
- **Authorities table empty-by-default:** new T1 question — `_actor_authority` falls back to default-by-prefix when no row exists. Need an explicit `register_actor` envelope in T2 to make actor identity first-class.
- **Per-hunk change records with LLM summaries (DEFERRED — T4+):** `git diff` hunk metadata (file, old/new line ranges, raw diff text) is deterministic and cheap to capture at tranche-close. The *reason* for each hunk is already in the `decision_records` table. Storing hunk↔decision linkage + a 1-sentence Ollama summary per hunk in the `evidence` table would give exact per-line provenance and dramatically compress the context a resuming agent needs. This is the natural implementation of the Bag of Evidence layer (§3.3) for code-change evidence. `git_reader` already exists; `OllamaClient` is already wired. The surface to display hunk summaries belongs in T3's project_map_panel or a future diff_panel. Implement in T4+ alongside the proposal/approval cycle where diffs become first-class.
