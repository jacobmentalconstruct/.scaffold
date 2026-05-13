# IMPLEMENTATION_ROADMAP.md

> **Status:** Tranche B output. Defines the First Working Prototype, the minimum-file slate to reach it, and the Tranche 1–5 ordering. References Tranche A output at `_docs/INCORPORATION_INVENTORY.md`.

---

## Context

Tranche 0 produced the scaffold + plan files. Tranche A reviewed the precursor at `.parts/.dev-tools-REF/` and produced the inventory of what's worth ADOPT/ADAPT/INSPIRE/SKIP/DEFER. This document is Tranche B: the ordered path from current state (plan files only) to a working sidecar that can demonstrate the proving loop end-to-end.

All Decision Points are locked:

- **DP1** Agent runtime out of scope for first prototype (agent-agnostic).
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
- `sqlite_store.py`, `blob_store.py`, `file_scanner.py`, `git_reader.py` (minimal — observation only)
- **PLAN only:** `diff_builder.py`, `patch_applier.py`, `test_runner.py` (T6+)

### Managers (`src/managers/`)
- **CODE:** `journal_manager.py`, `project_index_manager.py`, `evidence_manager.py` (lightweight — no Bag/Shelf overflow), `tool_registry_manager.py`, `git_state_manager.py`, `constraint_manager.py` (NEW per Q2)
- **PLAN only:** `ontology_manager.py`, `agent_session_manager.py`, `human_approval_manager.py` (T6+)

### Orchestrators (`src/orchestrators/`)
- **CODE:** `install_orchestrator.py`, `scan_orchestrator.py`, `journal_orchestrator.py` (basic), `agent_task_orchestrator.py` (basic)
- **PLAN only:** `scaffold_orchestrator.py` (T6+)

### Interfaces (`src/interfaces/`)
- **CODE:** `cli_interface.py`, `mcp_interface.py` (read-only in T2; full in T3+)
- (Tk wiring lives in `src/ui/main_window.py`, not as a separate adapter.)

### UI (`src/ui/`)
- **CODE:** `main_window.py`, `state_panel.py`, `journal_panel.py`, `evidence_panel.py`, `project_map_panel.py`
- **PLAN only:** `contracts_panel.py` (lands in T4 with approval flow)

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

### **Tranche 4 — Proposal & approval cycle**

**Scope:** Full agent-proposes → human-approves → state-mutates loop. The contract gate enforces authority elevation. Apply-authority writes happen, but only with explicit per-envelope approval.

**Files implemented (~7 additional):**
- `src/ui/`: contracts_panel (approval queue + grant/revoke UI)
- `src/managers/`: agent_session_manager (track agent identity + authority), human_approval_manager (manage approval grants)
- `src/tools/`: tools 12–18 (text_file_writer Apply-gated, directory_scaffold Sandbox-Execute-gated, session_evidence_store, text_file_validator, secret_surface_audit, repo_search, read_projection)
- Full `agent_task_orchestrator` (accept_task → propose → request_authority_elevation → complete_task lifecycle)
- mcp_interface upgrades from read-only to full (accepts envelope submissions from agents)

**Non-goals:** no Bag/Shelf overflow logic; no diff_builder / patch_applier (T6+); no test_runner (T6+); no snapshot orchestrator.

**Completion criteria:**
- An agent connected via MCP can: read its bootstrap packet, scan a file, propose a journal entry citing the file, request `Apply` authority elevation to write a new file in the host project, the request appears in the Tk approval queue, the human approves, the file gets written (or, in prototype, written to a sandbox workspace under `workspaces/<id>/`), an event is recorded, the relations land in the graph, the projections refresh.
- The full proving loop §9 of ARCHITECTURE.md works end-to-end.

**Memory model status:** Full LTM operational. Contract gate enforces authority. The sidecar is a working organism.

---

### **Tranche 5 — End-to-end validation**

**Scope:** Automated proof that the prototype works.

**Files implemented:**
- `smoke_test.py` extended to cover the full proving loop from §9 of ARCHITECTURE.md as an automated test sequence.
- Possibly: a `tests/` directory with focused unit tests for the spine (envelope validation, router dispatch, contract gate edge cases). Decision deferred to T5 start.

**Completion criteria:**
- `python smoke_test.py` exits 0 with all proving-loop steps passing.
- A "test project" subdirectory is included (small, ignorable) that smoke_test.py runs against.
- Documentation updates: `README.md` shows the smoke-test invocation; `ARCHITECTURE.md` notes "MVP achieved" with a date.

**Prototype is DONE when T5 completes and the user signs off on the smoke test.**

---

## Files DEFERRED past the first prototype

These exist as Tranche-0 prose plans but are not implemented in T1–T5:

| File / concept | Defer to | Reason |
|---|---|---|
| `src/components/diff_builder.py` | T6 | Required for patch proposals beyond simple file writes. |
| `src/components/patch_applier.py` | T6 | Same. |
| `src/components/test_runner.py` | T6 | Sandbox test execution. |
| `src/orchestrators/scaffold_orchestrator.py` | T6 | Beyond prototype scope. |
| `src/managers/ontology_manager.py` | T6+ | Object-type / tag registry beyond minimal MVP needs. |
| Bag / Shelf overflow logic in `evidence_manager.py` | T7+ | Per memory model — needed when we run our own local agent (DP1 deferred). |
| `recovery_class` *use* (field reserved in T1) | T7+ | Same. |
| Snapshot orchestrator (`snapshots.py` adoption) | T6+ | Useful for audit; not first-prototype critical. |
| Teaching Sandbox / Training Runway | T13+ | Schema fields reserved in T1; harness deferred. |
| Onboarding HTML microsite | DP5 — deferred indefinitely | Not blocking; rebuild later if needed. |
| `_v2-pod/` containerization | DP6 — deferred indefinitely | Not blocking. |
| Local agent runtime (Ollama-backed) | DP1 — Phase 2+ | First prototype is agent-agnostic. |
| `_manifold-mcp/` corpus / hypergraph adoption | T8+ if ever | INSPIRE only — not adopting the data model. |
| Most of the 50 precursor tools (32 of them) | T6+ on a case basis | First prototype needs only the 18 in §2.1. |

---

## Northstars — what's in scope vs later expansion

(Per inventory §1.1, item 1.8 — adopted as a lightweight pattern.)

### Active scope (T1–T5)
- Spine integrity (envelope, router, contract gate, event log, graph, projections).
- LTM operational (journal, projections, project_index).
- Read-only MCP for external agents.
- Tk dashboard for humans.
- Agent-propose / human-approve cycle with Apply-authority gating.
- Sandboxed file writes via `workspaces/`.
- Smoke-tested proving loop.

### Later expansion (post-prototype)
- Bag / Shelf evidence overflow + sliding-window agent memory management.
- Local agent runtime (Ollama-backed).
- Diff/patch infrastructure beyond simple writes.
- Snapshot system (Merkle-rooted DB snapshots).
- Teaching Sandbox + Training Runway.
- Multi-project registry / cross-project view.
- Containerization (`_v2-pod/`).
- Onboarding HTML microsite.
- Most of the precursor's specialty tools (k8s_ops, docker_ops, dev_server_manager, dead_code_finder, etc.).

### Explicit non-goals
- No tool that mutates the host project tree without `Apply` authority + explicit per-envelope human approval.
- No agent runtime baked into the sidecar before Phase 2.
- No external runtime dependencies beyond Python stdlib (per contract Pledge 1).
- No sub-agents, web browsing, image generation, or full terminal parity in Phase 1.

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
