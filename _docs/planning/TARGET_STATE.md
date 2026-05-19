# TARGET_STATE.md — Prototype Target Requirements Map

> **Title:** Chat-Centered Sidecar Alignment
> **Status:** T10.1 planning/doctrine target. Binding for near-term planning; not an implementation tranche by itself.

## Governing principle

**Chat becomes the cockpit. The DB remains the memory. The spine remains the authority path.**

Equivalent doctrine sentence:

**The chat workspace is a governed projection/action surface over the sidecar spine, not an independent memory or authority layer.**

This rule is load-bearing. Any future chat surface must read and write through existing sidecar truth surfaces rather than creating a second store of project reality.

## Prototype Target State

The near-term binding target is a **usable, project-bound, chat-centered sidecar** where:

- the human works mainly through chat
- the agent operates only through sidecar tools and envelope-routed actions
- planning, tranche work, review, approval, return, park, and continuity inspection are available from chat
- the DB remains the authoritative project memory
- approvals, traces, evidence, and review packets remain mechanically inspectable
- exports can be generated for outside review agents and enterprise chat systems
- Tk remains available for monitoring, deep inspection, queues, training/eval visibility, and emergency/manual control

The prototype target is not “a better dashboard.” It is a **governed chat cockpit over the existing sidecar spine**.

## Long-Term Evolutionary Target

The long-term direction remains valid but is **not immediate implementation scope**:

- broader chat-native task and tranche management
- richer observer-scoped context packets for humans, local agents, external reviewers, and cold-team readers
- stronger export bundles for outside verification systems
- deeper self-maintenance of the sidecar through its own governed tools
- broader autonomy modes with explicit checkpoints
- sidecar-assisted substrate self-improvement, training, and maintenance

These remain directional. They do not authorize immediate broad implementation.

## Target tiers

### Must Have for usable chat-centered prototype

| Capability | Must route through | Risk flags |
|---|---|---|
| Show current tranche state in chat | `tranche_review_gate`, `handoff`, `tranche_status` | none if projection-backed |
| Show mechanical review packet in chat | review packet export + `tranche_review_show` path | second-memory risk if transcript becomes canonical |
| Return tranche with notes from chat | `return_tranche_review` envelope | second-authority risk if not persisted |
| Approve review from chat | `approve_tranche_review` envelope | second-authority risk if approval stays in transcript only |
| Trigger park from chat only after approval | `close_tranche` through review gate | spine-bypass risk if chat closes directly |
| Show generated closeout metadata in chat | generated `_docs/continuity/LATEST_PARKED_TRANCHE.*` + projection/CLI read path | none if generated files remain mirrors |
| Export review/closeout bundle | existing export surfaces + evidence/journal linkage | second-memory risk if export becomes new truth |
| Keep chat over the spine only | projections, envelopes, journal, evidence, approvals, exports | load-bearing anti-drift rule |

### Should Have for a stronger sidecar

| Capability | Must route through | Risk flags |
|---|---|---|
| Task/tranche initiation from chat | tranche ledger + envelope path | second-authority risk if chat creates hidden work state |
| Observer-scoped context packets | projections + journal + runtime trace + export packers | second-memory risk if assembled packets become their own store |
| Export-oriented verification bundles | journal, evidence, runtime trace, closeout metadata | none if bundles remain derived |
| Context-preserving chat summaries | journal/evidence/projection source refs | second-memory risk if summaries drift from source |

### Later Evolutionary Capability

| Capability | Must route through | Risk flags |
|---|---|---|
| Broader chat-native planning workflows | tranche ledger + journal + review packets | second-memory + scope-creep risk |
| Sidecar self-maintenance through its own tools | same approval/evidence/review path as host work | authority-bypass risk if self-modification becomes special-cased |
| Rich external reviewer-agent workflows | export bundles + scorecards + traces | second-authority risk if outside reviewer decisions are imported informally |
| Stronger bounded autonomy modes | approvals, traces, runtime policy | authority-widening risk |

## Explicit non-goals

These are out of scope for the first chat-centered implementation slices:

- a broad new chat subsystem
- freeform chat memory as project truth
- direct chat-to-tool bypass
- transcript-only approval
- independent chat authority path
- autonomous project planning without tranche/governance structure
- multi-agent routing
- broad sidecar self-modification

## Spine-routing map

Future chat actions must route through existing sidecar surfaces:

| Chat intent | Canonical sidecar surface |
|---|---|
| Inspect current work state | projection |
| Inspect history / continuity | journal + handoff projection |
| Request/inspect review packet | review packet export + tranche review CLI/projection path |
| Approve / return / park | envelope-routed review/close intents |
| Inspect approval state | approval manager + projection |
| Inspect evidence / trace / grounding | evidence, runtime trace, projections |
| Export for outside review | export bundle + generated metadata + journal/evidence refs |
| Mutate project state | tool invocation only, under normal authority/approval rules |

No future chat feature may introduce:

- a second persistent memory layer
- a second authority layer
- a bypass around Interface → Envelope → Router → ContractCheck → Orchestrator → Manager → Event → derived views

## Backlog reclassification

This is a classification pass only. It does **not** silently clean or close historical todos.

### Must-have for usable chat-centered prototype

- none of the current open legacy todos are a direct chat-first prototype blocker by title; the first prototype slice is mostly interface/routing work over existing surfaces

### Trust / safety gate

- `journal_18af1a1decca899c_81f9959d` — remove remaining non-session actor fallback after session-backed authority registration
- `journal_18af1a1debd30d5c_c059293a` — soak-test concurrent Tk, MCP, and local-agent workload against the single SQLite spine
- `journal_18af02bbadca2384_6e0aa42e` — snapshot cadence and migration harnesses
- `journal_18af02bb9f3c7fd8_519edd22` — HARD_BLOCK / recovery hardening (title partly stale; remaining hardening still relevant)

### Should-have later

- `journal_18af02bb8ffa7818_02c82bb2` — contract versioning / richer constraint decomposition
- `journal_18af02bb8101014c_4cb4bcc9` — bounded test runner / richer mutation support

### Long-term evolutionary

- `journal_18af02bbcc254ac0_08e00dbc` — evaluate remaining precursor tools case by case
- `journal_18af02bbdae410f0_1f256efc` — keep HTTP transport, microsite, containerization, and manifold adoption explicitly optional

### Obsolete / superseded candidate

- `journal_18af02bbbcb58604_5b49755e` — T8 training runway title is stale because the substrate is complete
- `journal_18af02bb713c1940_eb9ad4f8` — T6 diff builder / provenance title is stale because core capability landed
- `journal_18af02bb61e280b0_56e86d33` — T6 STM / Bag / Shelf title is stale because core capability landed

### Needs human review

- Any stale todo whose title mixes completed work with still-open hardening should be superseded deliberately through the normal journal/tranche process rather than silently edited away

## First implementation slice

### T10.2 — Chat Review Gate Surface

Purpose:

> Prove that chat can act as the primary HITL cockpit for the tranche review/approval/park lifecycle without creating a second memory or authority layer.

Scope:

- show current tranche state in chat
- show/generated review packet in chat
- return review with notes from chat
- approve review from chat
- trigger park only after approval
- show final generated closeout metadata
- optionally export the review/closeout bundle

Must route through:

- `tranche_review_gate`
- active tranche ledger
- review packet generation
- approval/review envelopes
- closeout metadata
- journal/evidence/export surfaces

Out of scope:

- broad task/tranche initiation
- general chat memory
- direct tool execution from freeform chat
- multi-agent routing
- long-term transcript management
- sidecar self-modification

## Proposed tranche sequence

1. **T10.2 — Chat Review Gate Surface**
   - complete
   - chat becomes the primary surface for review/return/approve/park over the existing review gate

2. **T10.3 — Explicit Authority Registration Hardening**
   - complete
   - ordinary routed actors materialize explicit authority rows through the spine instead of depending on transcript-only understanding of prefix defaults

3. **T10.4 — HARD_BLOCK and Mutation-Path Trust-Gate Completion**
   - complete
   - project-targeted mutation now fails early at the contract gate
   - scaffold approvals now enforce exact manifest `entry_paths`
   - tranche declaration now blocks on authoritative Park/continuity drift

4. **T10.5 — Derived BCC Constraint-Map Slice for Intent Decomposition**
   - complete
   - the first machine-usable constraint map is now derived from `contracts/BCC.md`
   - it guides intent decomposition before proposal/park gating
   - it remains explicitly derived and non-authoritative
   - it is bound to the live contract hash and requires explicit refresh on mismatch
   - runtime authority drift is exposed as truth instead of normalized away

5. **T10.6 — Snapshot Cadence + Schema-Migration Harnesses**
   - decide the snapshot cadence for post-baseline continuity
   - add the first explicit snapshot/migration confidence harnesses
   - keep the work narrowly focused on resilience and continuity hardening

5. **Later T10+ slices**
   - chat work declaration surfaces
   - scoped context and export surfaces
   - only after trust gates remain sound:
   - deeper autonomy scaffolding
   - broader self-maintenance surfaces
   - wider optional transport/tooling expansions

## Acceptance criteria

This target-state map is correctly locked when:

- `TARGET_STATE.md` exists and clearly separates prototype target vs long-term evolutionary target
- the governing principle appears in doctrine
- the first implementation slice is explicitly the **Chat Review Gate Surface**
- Tk is documented as the secondary operator surface
- the backlog is reclassified honestly without silent historical cleanup
- future chat work is explicitly constrained to existing spine surfaces
- second-memory, second-authority, and spine-bypass risks are explicitly named
- the tranche sequence stays truthful as slices land, rather than leaving already-parked slices presented as the next candidate
