# IMPLEMENTATION_ROADMAP.md

> **Status:** Living roadmap. T5/T5.1/T6/T6.1/T7/T8/T8.1/T9 are complete; one T10 hardening slice is also complete (`T10 Closeout Metadata Derivation Hardening`), schema v11 installed-project proof state is parked, vendability baseline is achieved, continuity is current, and the broader T10 post-baseline horizon remains open. References Tranche A output at `_docs/INCORPORATION_INVENTORY.md`.

---

## Context

Tranche 0 produced the scaffold + plan files. Tranche A reviewed the precursor at `.parts/.dev-tools-REF/` and produced the inventory of what's worth ADOPT/ADAPT/INSPIRE/SKIP/DEFER. This document is Tranche B: the ordered path from current state (plan files only) to a working sidecar that can demonstrate the proving loop end-to-end.

All Decision Points are locked:

- **DP1** Historical note: the earliest prototype plan kept agent runtime out of scope. This is now superseded by the T5–T9 setup-completion program below.
- **DP2** Inventory at `_docs/INCORPORATION_INVENTORY.md`.
- **DP3** This roadmap at top-level (here).
- **DP4** Triage-focused depth (done).
- **DP5** Onboarding microsite — DEFER.
- **DP6** Containerization — DEFER.
- **Q1** No `packages/` folder — keep flat.
- **Q2** New `src/managers/constraint_manager.py` (split from `core/contracts.py`).
- **Q3** 18-tool first-prototype slate accepted.
- **Q4** Reserved nullable schema fields land now.
- **Q5** `project_registry` table added now.
- **Q6** Top-level `config/toolbox_manifest.json` confirmed.
- **Q7** Full constraint-query API.
- **Q8** Journal + read-only MCP into T2; Tk UI in T3.

---

## First Working Prototype — Goal Statement

The sidecar can do the following end-to-end, with no host-project tree mutation:

1. **Drop into a project** as `<project>/.scaffold/` (paste-and-unzip, no installer ceremony).
2. **First-boot install** — create `data/sidecar.db`, seed schema and contract, write seed config, emit `install` event.
3. **Acknowledge contract** — agent (or human via CLI) acknowledges the binding contract; the gate opens.
4. **Scan host project** — file_tree_snapshot + workspace_boundary_audit + dependency_env_check; populate `project_index` and graph relations; emit `scan` event.
5. **Maintain LTM** — every action since install lands in the event log; the journal accumulates entries; projections refresh continuously. The sidecar's LTM (journal + projections + project_index + event log) is what an agent reads to orient.
6. **Expose via MCP (read-only)** — an external agent (e.g., Claude Code) connects via MCP, calls `read_projection(name)` and `query_journal(...)`, retrieves the agent bootstrap packet, and forms a working understanding of the project from LTM alone.
7. **Display via Tk UI** — a human launches `python -m src.app ui`, sees a Tk monitoring console populated from the same projections the agent reads, with a tri-temporal dashboard and drill-down panels.
8. **Agent proposes** — the agent, under `Propose` authority, submits a `create_journal_entry` envelope (e.g., a design observation about a file it scanned). Envelope passes Router → ContractAuthority → journal_manager → EventStore → graph apply → projection refresh.
9. **Human inspects** — the human sees the new entry in the journal panel, sees the evidence chain (which files the agent cited), can drill into the source.
10. **Smoke test passes** — `python smoke_test.py` runs the full loop above as an automated check and exits 0.

**The proof:** the sidecar exists, sees, records, links, projects, and explains — *before it has changed anything in the host project*. Every action is in the event log. Every relation is in the graph. Every projection rebuilds deterministically. The contract gate works. The host project is untouched.

---

## Minimum file set for the prototype

Files marked **CODE** must be implemented; files marked **PLAN** stay as Tranche-0 prose plans (deferred past prototype). Total: ~45 code files.

### Core spine (`src/core/`) — all CODE
- `state.py`, `envelope.py`, `events.py`, `router.py`, `contracts.py` (gate only), `projections.py`, `graph.py`

### Schemas (`src/schemas/`) — all CODE
- `envelope_schema.py`, `event_schema.py` (with reserved nullable fields per Q4), `contract_schema.py`, `projection_schema.py`

### Components (`src/components/`) — all CODE
- `sqlite_store.py`, `blob_store.py`, `file_scanner.py`, `git_reader.py` (minimal — observation only), `diff_builder.py`
- **PLAN only:** `patch_applier.py`, `test_runner.py` (T6+)

### Managers (`src/managers/`)
- **CODE:** `journal_manager.py`, `project_index_manager.py`, `evidence_manager.py` (lightweight — no Bag/Shelf overflow), `tool_registry_manager.py`, `git_state_manager.py`, `constraint_manager.py` (NEW per Q2), `agent_session_manager.py`, `human_approval_manager.py`
- **PLAN only:** `ontology_manager.py` (T6+)

### Orchestrators (`src/orchestrators/`)
- **CODE:** `install_orchestrator.py`, `scan_orchestrator.py`, `journal_orchestrator.py` (basic), `agent_task_orchestrator.py` (basic)
- **PLAN only:** `scaffold_orchestrator.py` (T6+)

### Interfaces (`src/interfaces/`)
- **CODE:** `cli_interface.py`, `mcp_interface.py` (read-only in T2; proposal-capable in T4; local-agent operator support expands in T5+)
- (Tk wiring lives in `src/ui/main_window.py`, not as a separate adapter.)

### UI (`src/ui/`)
- **CODE:** `main_window.py`, `state_panel.py`, `journal_panel.py`, `evidence_panel.py`, `project_map_panel.py`, `contracts_panel.py`, `handoff_panel.py`

### Lib (`src/lib/`) — all CODE
- `logging_setup.py`, `common.py`

### Tools (`src/tools/`) — 18 first-prototype tools (CODE)
Per [INCORPORATION_INVENTORY.md §2.1](_docs/INCORPORATION_INVENTORY.md):
1. `sidecar_install` (bootstrap)
2. `journal_init` (bootstrap)
3. `journal_write` (write)
4. `journal_query` (query)
5. `journal_acknowledge` (contract)
6. `file_tree_snapshot` (scan)
7. `workspace_boundary_audit` (scan)
8. `host_capability_probe` (scan)
9. `dependency_env_check` (scan)
10. `project_command_profile` (scan)
11. `text_file_reader` (query)
12. `text_file_writer` (write — Apply authority gated)
13. `directory_scaffold` (scaffold — Sandbox Execute only in prototype)
14. `session_evidence_store` (memory — lightweight, no overflow logic)
15. `text_file_validator` (testing)
16. `secret_surface_audit` (security)
17. `repo_search` (query)
18. `read_projection` (query — generic projection read)

### Top-level (`.scaffold/`)
- **CODE:** `app.py`, `smoke_test.py` (NEW — adopted from precursor pattern)
- **DOCS (already exist or updated):** `README.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_ROADMAP.md` (this file), `SOURCE_PROVENANCE.md`, `TOOLS.md`, `contracts/builder_constraint_contract.md`, `_docs/INCORPORATION_INVENTORY.md`

### Config (`config/`)
- **DATA (runtime-generated):** `sidecar.json`, `journal_config.json`, `db_manifest.json`, `tool_manifest.json`, `toolbox_manifest.json`
- **PLAN files:** `*.PLAN.md` for each (already done or coming in this Tranche B)

---

## Tranche order

### **Tranche 1 — Spine boot** — ✓ COMPLETE (2026-05-10)

**Status:** COMPLETE. Smoke test 10/10 PASS. Park Phase performed in degraded form (full Park Phase requires `journal_manager` from T2; closeout notes captured at `_docs/T1_CLOSEOUT_NOTES.md`).

**Metrics:**
- Files implemented: 19 (~3,850 lines of code)
- DB tables created: 19 (12 core + 7 projection)
- Constraints seeded: 12 atomic units across 6 task profiles
- Smoke test sections: 10/10 PASS

**Evidence (CAS):**
- Closeout notes blob hash (SHA-256): `26a89b86a7fcdd1097470e0c5ffda4ca947e5b7b4274c08866b9f2a2e57def28` (10,240 bytes, content_type=text/markdown)
- Source: [`_docs/T1_CLOSEOUT_NOTES.md`](_docs/T1_CLOSEOUT_NOTES.md)
- Merkle root after T1 close: `3403e5ff31bc690b4856f0f3229a57964a8c0659e0ae0ce25f05024388dfc471`

**Handoff promise:** T2's first act is to write a proper `kind='tranche'` journal entry that supersedes the closeout notes, citing the evidence hash above. After that, the Park Phase becomes automatic for all subsequent tranches.

**Handoff HONORED (2026-05-11, T2.1 first act):**
- T1 closeout journal entry written: `journal_18ae7c440531739c_104fb685`
- Created by event: `evt_18ae7c44053fd284_7cae64af`
- `_docs/T1_CLOSEOUT_NOTES.md` marked SUPERSEDED with banner pointing to the entry.

---

**Scope:** Build the spine so envelopes can be accepted, gated, recorded, and trigger projection refresh. Nothing useful happens yet — but the machinery works.

**Files implemented (~17):**
- `src/core/`: state, envelope, events, router, contracts (gate only — consults ConstraintManager via dependency injection), projections (registry + refresh API; one stub builder), graph
- `src/schemas/`: all four
- `src/components/`: sqlite_store, blob_store
- `src/lib/`: logging_setup, common
- `src/managers/`: constraint_manager (CRUD on `constraint_units` + `task_profiles` tables; loads seed constraints from contract)
- `src/app.py` (boot wiring; no UI / MCP launched yet)
- `smoke_test.py` (skeleton — passes if spine boots and one envelope round-trips)

**Non-goals:** no install_orchestrator, no scan, no journal, no UI, no MCP, no real tools.

**Completion criteria:**
- `python -m src.app cli ack-contract --actor "human:test"` works: builds an `acknowledge_contract` envelope, passes the gate (because the bootstrap exception applies for this exact intent when no prior ack exists), records the event, refreshes the contract_status projection.
- `python smoke_test.py` exits 0.
- DB at `data/sidecar.db` has: `events`, `relations`, `blob_store`, `journal_meta`, `journal_migrations`, `constraint_units`, `task_profiles`, plus the projection tables (empty). Constraint registry is seeded from the binding contract.

**Memory model status:** LTM exists (DB + log files) but is mostly empty. STM is whatever the CLI invocation provides. No Bag yet.

---

### **Tranche 2 — Install + Scan + Journal + read-only MCP** — ✓ COMPLETE (2026-05-11)

**Status:** COMPLETE. Smoke test 35/35 PASS. **First proper Park Phase** (non-degraded — journal_manager existed throughout T2 close).

**Sub-tranche breakdown:** T2.1 (Journal layer + handoff) → T2.2 (Install + Scan + Project Index) → T2.3 (Git + Evidence + Tools + MCP).

**Metrics:**
- New code files: ~25 (~5,000 additional lines)
- DB migrations applied: v2 (T2.1), v3 (T2.2), v4 (T2.3) — schema went 19 → 27 tables
- Handlers registered: 12 new (13 total including T1's ack)
- Tools registered (auto-discovered): 5 (file_tree_snapshot, host_capability_probe, text_file_reader, workspace_boundary_audit, read_projection)
- Projection builders real: 5 of 7 (current_sidecar_state, contract_status, journal_timeline, project_map, human_dashboard); 2 still stubs (agent_bootstrap, evidence_bag — defer to T3)
- CLI subcommands: 17 total
- MCP stdio server functional: `python -m src.app mcp` exposes tools/list, tools/call, resources/list, resources/read, initialize, ping

**Evidence (CAS):**
- T2 closeout notes blob hash: `9f87dcf37c9f3f7e4d5e3dedca00233a13ce375d8d8b46bc3810fd43e3703d71` (9,001 bytes, text/markdown)
- Source: [`_docs/T2_PARK_NOTES.md`](_docs/T2_PARK_NOTES.md)
- Merkle root after T2 close: `10cdf883593b558b5f835cd06ba0bacc43c8b3f56a474694f946233b1bc8d937`

**T2 closeout journal entry (kind='tranche'):**
- `entry_uid`: `journal_18ae7f230a832584_7211d04a`
- `event_id`: `evt_18ae7f230a894518_fa9d9a7e`
- Title: "T2 Install + Scan + Journal + MCP — COMPLETE"

**Park Phase task events:**
- `accept_task`: `evt_18ae7f25a0923054_29a027ea`
- `complete_task`: `evt_18ae7f25a0a1dd9c_c235e8d0`
- `correlation_id` binding: `cor_18ae7f25a08afaa0_90f7365f`

**Proving loop status:** ~70% complete. Steps 1–4 + 6 + 8 working end-to-end; per-file graph edges (step 5) deferred as design choice; agent_bootstrap projection (step 7) still stub; Tk UI human inspection (step 9) in T3.

---

**Scope:** First proving-loop walk: install, scan a project, journal it, expose projections via MCP. The sidecar becomes self-aware (its own LTM accumulates).

**Files implemented (~20 additional):**
- `src/managers/`: journal_manager, project_index_manager, evidence_manager (lightweight — `attach_evidence` + `verify_evidence` only), tool_registry_manager, git_state_manager (observation only)
- `src/orchestrators/`: install_orchestrator, scan_orchestrator, journal_orchestrator (basic — single-entry CRUD), agent_task_orchestrator (skeleton — accepts `accept_task` / `complete_task` only)
- `src/components/`: file_scanner, git_reader (read-only)
- `src/interfaces/`: cli_interface (full surface), mcp_interface (read-only — exposes `read_projection`, `query_journal`, `query_index`, plus tool list as MCP resources)
- `src/tools/`: tools 1–11 from the slate (sidecar_install, journal_init, journal_write, journal_query, journal_acknowledge, file_tree_snapshot, workspace_boundary_audit, host_capability_probe, dependency_env_check, project_command_profile, text_file_reader)
- Three projection builders implemented (in `src/core/projections.py` registry): Project Map, Journal Timeline, Current Sidecar State

**Non-goals:** no Tk UI, no write tools beyond journal, no Apply-authority operations, no proposal/approval cycle, no full evidence Bag/Shelf.

**Completion criteria:**
- `python -m src.app cli install` initializes the DB, seeds contract, writes config files, emits `install` event.
- `python -m src.app cli scan` walks the host project, populates `project_index`, emits `scan` events, refreshes Project Map projection.
- `python -m src.app mcp` starts the MCP server (stdio); an external agent (manually tested with mcp client) can call `read_projection("project_map")` and get rows back.
- `python -m src.app cli journal_write --kind note --title "..." --body "..."` creates a journal entry; `cli journal_query` returns it.
- `smoke_test.py` extends to cover install→scan→journal_write→journal_query.

**Memory model status:** LTM is alive — journal accumulates, projections refresh, project_index tracks the host. The sidecar can describe itself and its observations to a connected agent. No STM/Bag yet (deferred per DP1).

---

### **Tranche 2.5 — Active Tranche Ledger** — ✓ COMPLETE (2026-05-11)

**Status:** COMPLETE. Smoke test 51/51 PASS. This was a pre-T3 architectural enhancement — not in the original roadmap — added after explicit user request: *"I am hugely interested in harvesting what we need for the after-tranche documentation WHILE we are working through the tranche so that at the end you push a button and the docs almost fully update themselves."*

**Metrics:**
- New code files: 2 (`src/managers/tranche_manager.py`, `src/orchestrators/closeout_orchestrator.py`)
- Modified code files: 7 (sqlite_store, projection_schema, projections, router, app, cli_interface, journal_manager)
- DB migration: v5 — `decision_records` + `active_tranche` tables
- New projection: `tranche_checklist` (8th projection — 9 live checklist items)
- New handlers: 5 (`declare_tranche`, `update_tranche`, `record_decision`, `smoke_pass`, `close_tranche`)
- New CLI commands: 7 (`tranche-declare`, `tranche-status`, `tranche-update`, `tranche-close`, `tranche-smoke-pass`, `decision-record`, `decision-list`)
- New smoke test sections: 5 (§47–51)

**What changed architecturally:**
- §3.7 added to ARCHITECTURE.md: Active Tranche Ledger + "capture once, derive many" principle
- §12.2 Park Phase: `close_tranche` envelope is now the mechanical implementation of the 5 required artifacts
- `tranche_checklist` projection gives a live readiness view during work
- Journal's `create_direct` / `close_direct` bypass path added (for orchestrator use only)

**Evidence (CAS):**
- Smoke test ran clean 3× consecutively after implementation
- Smoke test PASS is the primary evidence artifact for this sub-tranche

---

### **Tranche 3 — Tk monitoring UI** — ✓ COMPLETE (2026-05-12)

**Status:** COMPLETE. Smoke test PASS. The Tk surface shipped as a monitoring-first console using the Unified Tri-Temporal mock in `.parts/UI_Concept/` as a reference artifact only.

**Metrics:**
- New app mode: `python -m src.app ui`
- DB migration: v6 — `proj_viewport_state` added for dashboard hydration
- New projection: `viewport_state` (9th projection)
- New real projection builder: `evidence_bag`
- Tk panels implemented: 6 (`main_window`, `state_panel`, `journal_panel`, `evidence_panel`, `project_map_panel`, `contracts_panel`)
- New smoke coverage: viewport projection, evidence projection, Tk import/instantiation, active-tranche-aware round-trip behavior

**Scope:** Human visibility with broad monitoring reach. The Tk UI reads the same spine-backed truth the agent reads, then aggregates it into a tri-temporal dashboard and drill-down panels.

**Files implemented (~6 additional):**
- `src/ui/`: `main_window.py`, `state_panel.py`, `journal_panel.py`, `evidence_panel.py`, `project_map_panel.py`, `contracts_panel.py`
- `src/core/projections.py`: real `viewport_state` builder plus real `evidence_bag` builder
- `src/schemas/projection_schema.py`: `viewport_state` added to projection registry + affected-intents map
- `src/components/sqlite_store.py`: migration v6 for `proj_viewport_state`
- `src/app.py`: `ui` mode wired into the application entrypoint
- `smoke_test.py`: T3 coverage + active-tranche-safe tranche round-trip logic

**Non-goals:** no approval queue, no grant/revoke UX, no UI-triggered mutation flows, no proposal submission from Tk. T3 is observational-only by design; T4 owns the approval path.

**Completion criteria:**
- `python -m src.app ui` opens the Tk window and hydrates from live projections.
- The home view is a Unified Tri-Temporal dashboard (`PAST / PRESENT / FUTURE`) backed by `viewport_state`.
- Status bar polls every 3s and refreshes the monitoring surfaces without mutating state.
- Journal, evidence, project map, contract status, and current state are all reachable from the same window.
- Manual end-to-end: install → scan → open UI → inspect populated dashboard and drill-down panels.

**Memory model status:** LTM now has a human monitoring face. Agents orient from `agent_bootstrap`; humans orient from `viewport_state`; both surfaces read the same spine.

---

### **Tranche 4 — Proposal & approval cycle** — ✓ COMPLETE (2026-05-13)

**Status:** COMPLETE. The first real proposal → approval → bounded mutation loop works through the sidecar spine, and the cold-team handoff doctrine is now codified in both docs and projections.

**Metrics:**
- schema version advanced to v7
- new tables: `agent_sessions`, `approval_requests`
- new root continuity docs: `WE_ARE_HERE_NOW.md`, `NORTHSTARS.md`, `DEV_LOG.md`
- new tools: `text_file_writer`, `directory_scaffold`

**Evidence:**
- park notes: [`_docs/T4_PARK_NOTES.md`](_docs/T4_PARK_NOTES.md)
- park-notes blob hash: `ddcaa03882b28f0519f8872fbe08ab74b784468c7e5ffa7fc45adad32d58d4b9`
- tranche journal entry: `journal_18aeffe951e29fd0_686ec667`

**What landed:**
- `agent_sessions` and `approval_requests` tables (migration v7)
- `agent_session_manager` + `human_approval_manager`
- `sidecar/submit` MCP path for non-tool envelopes
- Tk `contracts_panel` approval queue actions
- `handoff` projection
- `text_file_writer` + `directory_scaffold` as the first approval-gated mutation tools
- root continuity docs: `WE_ARE_HERE_NOW.md`, `NORTHSTARS.md`, `DEV_LOG.md`

**Non-goals:** no local sidecar agent runtime yet; no STM / Bag-of-Evidence logic yet; no training harness yet; no broad host-project writes as the default execution path.

**Completion criteria met:**
- MCP-connected agents can acknowledge the contract and submit `request_authority_elevation` envelopes.
- Approval requests appear in the Tk operator UI and in projection-backed handoff surfaces.
- Approved single-use grants unlock bounded workspace writes through the registered tool path.
- Cold-start continuity docs now exist at repo root and are part of the expected Park Phase surface.
- T4 is now fully parked with tranche journal entry `journal_18aeffe951e29fd0_686ec667`.

---

## Setup Completion Program (T5–T9)

T4 proved the approval loop and handoff doctrine, but it did **not** finish the supersession mission. From here forward, the goal is to bring this branch up to parity with the older local-agent experiment where that experiment was valuable, then exceed it on a cleaner substrate.

### **Tranche 5 — Local Sidecar Agent Reintegration** — ✓ COMPLETE (2026-05-13)

**Status:** COMPLETE. Smoke test PASS with dedicated T5 runtime sections. The local Ollama-backed sidecar agent now runs inside the existing contract/envelope spine instead of being represented only by an external stand-in.

**Metrics:**
- new runtime package surface: `src/runtime/local_agent_runtime.py`
- new Tk operator surface: `src/ui/local_agent_panel.py`
- new CLI commands: `local-agent-status`, `local-agent-models`, `local-agent-preflight`, `local-agent-run`, `local-agent-stop`
- new smoke sections: 65–68
- no schema migration required; T5 builds on T4's `agent_sessions` + `approval_requests` tables

**Evidence:**
- park notes: [`_docs/T5_PARK_NOTES.md`](_docs/T5_PARK_NOTES.md)
- park-notes blob hash: `bd0827915b9ca17d76a204c73e8032e2b5f56aec44eff021e73114ac37853e35`
- tranche journal entry: `journal_18af19e0c59104ec_fad65652`

**What landed:**
- `LocalAgentRuntime` hosted by the sidecar and wired through `src/app.py`
- Tk local-agent operator tab and matching CLI operator commands
- bootstrap parity so the local agent consumes the same `agent_bootstrap` truth as external agents
- approval-aware bounded local-agent writes through the existing envelope/grant path
- explicit session-backed authority rows for local-agent actors
- cooperative stop support for long-running local-agent sessions
- compatibility hardening so local-agent writes normalize onto `text_file_writer`'s canonical `content` field

**Non-goals kept intact:**
- no STM / Bag of Evidence / Evidence Shelf yet
- no run-trace / recovery taxonomy yet
- no Teaching Sandbox or evaluation harness yet
- no broad ungated host-project mutation

**Completion criteria met:**
- The sidecar can launch a local Ollama-backed agent inside the current architecture.
- The local agent reads the same bootstrap truth as external agents.
- The local agent can inspect, propose, request approval, and complete a bounded workspace write without bypassing the envelope chain.
- The local agent is visible through Tk, CLI, projections, and session bookkeeping.

### **Tranche 5.1 — Companion Monitor Default + UI Stability** — ✓ COMPLETE (2026-05-13)

**Status:** COMPLETE. Small post-T5 stabilization tranche that parks the new operator-default behavior instead of carrying it informally into T6.

**What landed:**
- Tk monitor auto-launch for `python -m src.app mcp` unless `--no-ui` is supplied
- Tk monitor auto-launch for `python -m src.app cli local-agent-run ...` unless `--no-ui` is supplied
- notebook/focus preservation during refresh so the UI no longer snaps back to `Dashboard`
- viewport drift-check logic aligned with smoke-test continuity truth
- onboarding/readme updates documenting the new default behavior

**Completion criteria met:**
- agent-facing runs launch the monitor by default unless explicitly suppressed
- the Tk UI preserves the active tab across refreshes
- the drift banner only warns on real continuity drift
- continuity docs and smoke remain in sync after the change

### **Tranche 6 — STM + Bag of Evidence + Evidence Shelf** — ✓ COMPLETE (2026-05-13)

**Scope:** Promote the memory model from LTM-only + reserved fields into a real three-layer stack.

**Target files / surfaces:**
- explicit STM state for the local sidecar agent session
- Bag of Evidence archival + retrieval surfaces
- Evidence Shelf summary surface for UI and bootstrap consumption
- `agent_bootstrap` and Tk monitoring updates so the memory layers are visible without conflating STM and LTM
- per-hunk diff provenance with file + old/new line ranges for bounded writes

**Evidence:**
- park notes: [`_docs/T6_PARK_NOTES.md`](_docs/T6_PARK_NOTES.md)
- park-notes blob hash: `598a76da026c778f19bdc1a4c1597cc4405a12d051d830001e190fdf002a1309`
- tranche journal entry: `journal_18af1d7325d57744_83774848`

**What landed:**
- schema v8: `session_memory_items` + `change_hunks`
- local-agent runtime STM capture and overflow into Bag rows
- Evidence Shelf summaries exposed in `agent_bootstrap` and `viewport_state`
- real `diff_builder.py` plus bounded-write hunk capture
- smoke coverage for memory layers and line-range provenance

**Completion criteria met:**
- Explicit STM exists for the local agent session.
- Bag of Evidence persists overflow from the working window.
- Evidence Shelf provides a compact handoff working set to both the local agent and the human operator.

### **Tranche 6.1 — Post-Park Continuity Alignment** — ✓ COMPLETE (2026-05-13)

**Scope:** Reconcile continuity docs and smoke assumptions after T6 close so the latest parked tranche, active horizon, roadmap parser, and architecture drift checks all agree mechanically.

**What landed:**
- continuity docs updated to name the correct parked tranche and active horizon
- roadmap + architecture wording aligned with the newly parked T6 memory layer
- smoke hardened so historical checks do not fail on stale tranche-count assumptions or hard-coded horizon text

**Completion criteria met:**
- docs, handoff packet, and roadmap all agree on the parked state
- smoke passes after the continuity alignment itself
- T7 remains the clear next tranche

### **Tranche 7 — Run Trace, Recovery, and Operator Cockpit** — ✓ COMPLETE (2026-05-14)

**Status:** COMPLETE. Smoke test PASS with dedicated T7 runtime sections. Local-agent execution is now a durable temporal object rather than an opaque final-response process.

**Evidence:**
- park notes: [`_docs/T7_PARK_NOTES.md`](_docs/T7_PARK_NOTES.md)
- park-notes blob hash: `1b8bd02c97e4aaa8a7b2f6739a3475cf3674b40b347937030e14ddc40b8d7955`
- tranche journal entry: `journal_18af45da8a7bfa1c_5b4be0dd`

**What landed:**
- schema v9: `local_agent_runs`, `local_agent_run_rounds`, `local_agent_runtime_events`, `local_agent_run_touched_paths`, `local_agent_run_links`, `local_agent_claim_grounding`
- `run_trace_manager` and `recovery_manager` for durable runtime persistence and normalized `recovery_class` handling
- local-agent runtime instrumentation for run start/finish/failure, rounds, tool activity, approval waits, retry lineage, and grounded final summaries
- `runtime_cockpit` projection plus `agent_bootstrap` / `viewport_state` runtime visibility
- CLI inspection and retry commands: `local-agent-run-list`, `local-agent-run-show`, `local-agent-run-events`, `local-agent-recovery-summary`, `local-agent-run-retry`
- Tk local-agent panel uplift into a real operator cockpit with run history, selected-run detail, recovery hints, and retry controls

**Completion criteria met:**
- Successful and failed local runs produce inspectable trace records.
- Recovery classes and retry guidance surface in the Tk operator shell.
- Final claims can be grounded in touched paths, evidence, journal refs, or explicit `no_mutation_trace` records.

### **Tranche 8 — Teaching Sandbox + Training Runway** — ✓ COMPLETE (2026-05-14)

**Status:** COMPLETE. Smoke test PASS with dedicated T8 sections. The sidecar now has a minimal teaching/evaluation substrate built on top of T7 run traces.

**Evidence:**
- live proof scenario run: `scenario_run_18af479b5372cfec_9413c8e0`
- linked live run id: `local_run_20260514T003830366Z`
- live proof scorecard: `scorecard_18af479efb34d72c_bf9535e8`
- reviewer export: `exports/training_runway/training_review_python_notes_cli_20260514T003845980Z.md`
- live proof outcome: `fail` with `malformed_tool_call`

**Scope:** Reincorporate deterministic training/evaluation infrastructure as part of the substrate, not as a separate experimental branch.

**Target files / surfaces:**
- teaching-sandbox runtime harness with deterministic scenario definitions owned by the sidecar
- scorecard / reviewer export surfaces linked to T7 run traces, evidence refs, and tranche journal state
- training-runway docs for scenario review, pass/fail taxonomy, and operator protocol
- projection and UI additions needed to inspect sandbox runs without leaving the sidecar shell

**What landed:**
- schema v10: `teaching_scenario_runs`, `teaching_scenario_run_trace_links`, `teaching_scorecards`, `teaching_reviewer_exports`
- `TrainingRunwayManager`
- tracked seed scenarios under `training_scenarios/definitions/`
- disposable sandbox materialization under `workspaces/teaching_sandbox/projects/`
- structured scorecards + reviewer exports linked to T7 run traces, evidence refs, and journal entries
- `training_runway` projection
- CLI commands for scenario list/show/create/run/verify/show-scorecard/export/compare
- Tk Training Runway panel

**Completion criteria met:**
- A minimal scenario set runs through the local agent deterministically.
- Scorecards, trace links, evidence refs, and journal records are produced for review.
- Training docs explain the reviewer protocol to a cold team.
- One live Ollama proof is documented as tranche evidence.

### **Tranche 8.1 — Post-Park Training Handoff Alignment** — ✓ COMPLETE (2026-05-14)

**Status:** COMPLETE. Small post-T8 continuity tranche that reconciled roadmap parsing and parked handoff/bootstrap surfaces after the training runway landed.

**What landed:**
- roadmap parsing now falls back from file/surface lists to completion criteria and scope sentences when deriving `next_planned_steps_json`
- `agent_bootstrap` and smoke retain concrete T9 next-step visibility even when the next tranche is described in proof-oriented terms
- continuity docs now reflect T8.1 as the latest parked tranche while preserving T9 as the next substantive horizon

**Completion criteria met:**
- `agent_bootstrap.next_planned_steps_json` is non-empty with T9 as the next horizon
- smoke passes after the parser fix
- the branch returns to a no-active-tranche parked state

### **Tranche 9 — Installed-Project Proof + Vendability Seal** — ✓ COMPLETE (2026-05-14)

**Status:** COMPLETE. Smoke test PASS with dedicated T9 installed-context sections. `.scaffold` now has a proven installed-project baseline and formally supersedes the older experiment as the default installable substrate.

**Evidence:**
- park notes: [`_docs/T9_PARK_NOTES.md`](_docs/T9_PARK_NOTES.md)
- proof run id: `proof_run_18af6bba61f19740_953e88c4`
- linked local-agent run ids: `local_run_20260514T114059490Z`, `local_run_20260514T114102189Z`
- approval request / grant: `approval_18af6bc2a5d254b0_86ecc546` / `grant_18af6bc2b8e7ea74_0cfa1c16`
- hunk ref: `hunk_18af6bc347f5fcd8_7698bda5`
- authoritative closeout metadata: [`_docs/T9_CLOSEOUT_METADATA.json`](_docs/T9_CLOSEOUT_METADATA.json)

**What landed:**
- schema v11 with `installed_project_proofs`
- `InstalledProjectProofManager`
- clean installed-context project-root resolution for `<host>/.scaffold`
- trust-gate hardening for host-project write containment in installed mode
- clean-install migration overlap tolerance for additive duplicate-column cases
- `installed_project_proof` projection
- CLI installed-proof commands
- Tk Installed Proof panel
- canonical tiny installed-host fixture at `workspaces/installed_project_proof/tiny_notes_app/`
- cold-team handoff export for the installed proof

**Completion criteria met:**
- One fresh installed-project proving loop completes end to end.
- The result can be handed to an ignorant team using only the docs, DB, UI, and verification commands already in the repo.
- The old experiment is formally superseded by this branch.

**Substrate baseline is achieved.**

### **Tranche 10 — Post-Baseline Hardening + Optional Expansion**

**Scope:** Only the remaining trust/perf/expansion items that still matter after the vendability seal. T10 is a post-baseline horizon, not a missing baseline tranche.

**Completed T10 slice:** `T10 Closeout Metadata Derivation Hardening` is parked. It mechanized latest parked tranche metadata into generated closeout files, added CLI inspection/backfill commands, and made smoke assert exact agreement between generated closeout metadata and the latest closed tranche.

**Evidence:**
- park notes: [`_docs/T10_PARK_NOTES.md`](_docs/T10_PARK_NOTES.md)
- authoritative closeout metadata: [`_docs/T10_CLOSEOUT_METADATA.json`](_docs/T10_CLOSEOUT_METADATA.json)
- latest parked tranche metadata alias: [`_docs/LATEST_PARKED_TRANCHE.json`](_docs/LATEST_PARKED_TRANCHE.json)
- tranche journal entry: `journal_18af6ec811ddaf94_e67371c3`

**Initial candidates:**
- longer concurrent Tk + MCP + local-agent stress proof
- migration-harness hardening
- snapshot policy and snapshot command adoption
- remaining authority/bootstrap cleanup outside session-backed actors
- optional tooling/transport expansion only if justified by real use

---

## Deferred backlog normalized by tranche

Deferred work must not live only in chat or in scattered prose. Each item below has a target tranche or horizon and must also exist as an open `kind='todo'` journal entry until resolved or explicitly superseded.

| Deferred item | Target tranche / horizon | Why it is deferred / what it unlocks |
|---|---|---|
| Generic actor bootstrap hardening beyond session-backed rows | T10 | T5 created explicit authorities rows for session-backed actors; finish removing default-by-prefix dependence outside that path. |
| Concurrent Tk + MCP + local-agent workload verification | T10 | T5 and T7 proved the floor; T9 proved installed vendability; a longer soak still needs a dedicated post-baseline hardening pass. |
| `src/components/patch_applier.py` | T6 | Pairs with diff proposals so approved text changes can apply as structured hunks. |
| Per-hunk line provenance + diff evidence linkage refinements | T10 | Exact hunk rows exist after T6; remaining work is deeper decision/evidence linkage and any optional summaries. |
| `src/components/test_runner.py` | T6 | Enables bounded verification runs as part of local-agent workflows. |
| `src/orchestrators/scaffold_orchestrator.py` | T6 | Deepens guarded mutation beyond the T4 workspace-first file-write floor. |
| Contract revision-aware seed / contract versioning | T10 | Replaces in-place contract upsert with explicit supersession semantics. |
| Constraint decomposition tooling + `src/managers/ontology_manager.py` | T6+ | Helpful for richer reasoning and object typing, but not critical before the first local-agent loop. |
| Run trace spine + `recovery_class` consumption | ✓ COMPLETE at T7 | Local-agent runs are now inspectable, classifiable, grounded, and explicitly retryable. |
| HARD_BLOCK enforcement hardening | T10 | T9 tightened the installed proof path; broader end-to-end enforcement can continue post-baseline. |
| Snapshot cadence decision + snapshot orchestrator adoption | T10 | Needed once runtime trace/recovery and audit expectations rise beyond baseline proof. |
| Schema migration test harness | T10 | T9 added minimal fresh-install confidence; a fuller migration harness remains post-baseline hardening. |
| Teaching Sandbox + Training Runway | T8 | Rebuild deterministic training/eval on top of the cleaned-up substrate. |
| Remaining precursor tools beyond the current registry | T6+ on a case basis | Only adopt tools that materially strengthen the substrate; do not bulk-port the precursor. |
| Optional HTTP MCP transport evaluation | T9+ / Phase 2 | `stdio` is the default vendable path; HTTP remains optional future expansion only if justified. |
| `_manifold-mcp/` corpus / hypergraph adoption | T8+ if ever | INSPIRE only; not part of the core substrate unless a later tranche deliberately adopts pieces. |
| Onboarding HTML microsite | DP5 — deferred indefinitely | Useful only if the text-first continuity set proves insufficient. |
| `_v2-pod/` containerization | DP6 — deferred indefinitely | Not needed for the local-first substrate baseline. |

---

## Northstars — what's in scope vs later expansion

(Per inventory §1.1, item 1.8 — adopted as a lightweight pattern.)

### Active scope (T1–T9 complete; baseline achieved)
- Spine integrity (envelope, router, contract gate, event log, graph, projections).
- LTM operational (journal, projections, project_index).
- Read-only MCP for external agents.
- Tk dashboard for humans.
- Agent-propose / human-approve cycle with workspace-first Apply-authority gating.
- Local Ollama sidecar runtime with bootstrap parity, approval-aware bounded writes, and operator controls.
- Sandboxed file writes via `workspaces/`.
- Smoke-tested proving loop.
- Installed-project proof runner, projection, Tk panel, and cold-team handoff export proving vendability from a fresh host context.

### Post-baseline horizons (T10+)
- Bag / Shelf evidence overflow + sliding-window agent memory management.
- Diff/patch infrastructure beyond simple writes.
- Snapshot system (Merkle-rooted DB snapshots).
- Teaching Sandbox + Training Runway.
- Multi-project registry / cross-project view.
- Containerization (`_v2-pod/`).
- Onboarding HTML microsite.
- Most of the precursor's specialty tools (k8s_ops, docker_ops, dev_server_manager, dead_code_finder, etc.).

### Explicit non-goals
- No tool that mutates the host project tree without `Apply` authority + explicit per-envelope human approval.
- No external runtime dependencies beyond Python stdlib (per contract Pledge 1).
- No sub-agents, web browsing, image generation, or full terminal parity in the substrate baseline.

---

## Verification — when planning is done

This planning phase (Tranche A + Tranche B) is complete when:

- `_docs/INCORPORATION_INVENTORY.md` exists and every reviewed precursor item has a decision tag. **Done.**
- `IMPLEMENTATION_ROADMAP.md` exists with First Working Prototype goals, minimum-file slate, T1–T5 ordering with scope/non-goals/completion criteria per tranche, and explicit deferred list. **Done (this file).**
- All Decision Points have explicit answers, recorded in this document. **Done.**
- `ARCHITECTURE.md` is updated with the Memory Model + folded operational rituals (Setup Phase, Park Phase, Collaboration Rhythm) + cross-cutting principles (Journal Doctrine, Guarded Mutation, Deterministic IDs). **Pending — being updated in this Tranche B execution.**
- `data/README.md` reflects the new tables (`constraint_units`, `task_profiles`, `project_registry`) and reserved-fields notes on `events`. **Pending.**
- `src/schemas/event_schema.py` plan reflects reserved nullable fields. **Pending.**
- `src/managers/constraint_manager.py` prose plan exists. **Done in this Tranche B execution.**
- `config/toolbox_manifest.json.PLAN.md` and `config/tool_manifest.json.PLAN.md` exist. **Done in this Tranche B execution.**
- `SOURCE_PROVENANCE.md` records the planning-phase structural borrows. **Pending.**
- No `.py` file in `src/` contains executable code (Tranche 0 invariant preserved). **Verified.**
- The user has signed off on this Roadmap. **Pending — this is the moment.**

After sign-off, **Tranche 1 (spine boot) is cleared to begin coding.**
