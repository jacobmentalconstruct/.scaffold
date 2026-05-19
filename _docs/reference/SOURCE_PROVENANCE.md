# SOURCE_PROVENANCE.md

Tracks the origin of any logic, document, or pattern that was re-homed into `.scaffold/` from an external source. Each entry records: what was brought in, where it came from, when, what was changed in the re-homing, and who approved it.

The purpose is to keep the vended sidecar honest about its lineage so future agents can audit decisions and so we never lose track of whether a piece of code is original to this project or adapted from elsewhere.

---

## Entries

### 2026-05-10 — Builder Constraint Contract (Tranche 0 revision)

- **Re-homed into:** `contracts/BCC.md`
- **Source:** `.parts/IMPORTANT-DOCUMENTS-TO-READ-FIRST/builder_constraint_contract.md` (precursor copy)
- **Changes from source:**
  - Added §0.10 (Sidecar package and sidecar root) defining the dual development/deployment scope.
  - Added §0.8 expansion to define "tranche."
  - Added Technical Pledges 6 (Spine Discipline) and 7 (Envelope Lightness).
  - Added new "Spine Architecture" reference section: MVP-5 order, Authority Levels, Event Streams, Relation Types, Day-One Projections.
  - Updated §"Required Project Documentation": journal location changed from `_docs/_journalDB/app_journal.sqlite3` to `data/sidecar.db`. Added Operational Folders table for `config/`, `contracts/`, `data/`, `logs/`, `cache/`, `exports/`, `workspaces/`, `snapshots/`.
  - Reframed §1.2 per the vended-package model: removed the "re-home into the host project" requirement (no longer applies because `.scaffold/` is itself the deliverable).
  - Replaced `_PARTS/` references with `.parts/`.
  - Added §1.4 Sidecar storage discipline.
  - Added new §"Envelope Schema (Frozen Minimum)" section listing the eighteen fields.
  - Expanded §4 Prohibited Behaviors to include sideways manager calls, oversized envelopes, and out-of-set relation types.
- **Approved by:** user (this conversation, Tranche 0 greenlight).
- **Notes:** The precursor copy in `.parts/` remains untouched (read-only by §1.1).

---

### 2026-05-10 — Planning-phase structural borrows (Tranches A + B)

A bundle of structural borrows committed during the planning phase. Full per-item analysis lives in [`_docs/migration/INCORPORATION_INVENTORY.md`](../migration/INCORPORATION_INVENTORY.md). Recorded here as a single dated entry; individual code copies will get their own dated entries when the borrowed material actually lands in `src/` during Tranches 2–5.

**Concepts folded into ARCHITECTURE.md (§3, §12, §13, §14):**
- **Memory Model (LTM / STM / Bag of Evidence)** — synthesized from `.parts/.dev-tools-REF/_docs/ARCHITECTURE.md` (precursor §348–382 on session_evidence_store) plus the user's framing during planning. Added as ARCHITECTURE.md §3 (load-bearing).
- **Setup Phase** — adapted from `.parts/.dev-tools-REF/_docs/SETUP_DOCTRINE.md` (13-step sequence). Reshaped for our scaffold; added as ARCHITECTURE.md §12.1.
- **Park Phase / parking record** — adapted from `.parts/.dev-tools-REF/_docs/PARKING_WORKFLOW.md` (9-step closeout). Added as ARCHITECTURE.md §12.2.
- **Collaboration Rhythm** — adapted from `.parts/.dev-tools-REF/_docs/EXPERIENTIAL_WORKFLOW.md`. Added as ARCHITECTURE.md §12.3.
- **Journal Doctrine tightening** — adapted from precursor SETUP_DOCTRINE.md §journal. Added as ARCHITECTURE.md §13.1.
- **Guarded Mutation pattern** — observed across the precursor's 50 tools. Promoted to a cross-cutting principle (ARCHITECTURE.md §13.2).
- **Deterministic IDs** — inspired by `.parts/.dev-tools-REF/packages/_manifold-mcp/lib/manifold_store.py` (deterministic SHA1[:12] for evidence_span_id). Adopted for our IDs; added as ARCHITECTURE.md §13.3.

**Tables planned for `data/sidecar.db` (added to `data/README.md`):**
- `constraint_units`, `task_profiles` — schema borrowed from `.parts/.dev-tools-REF/packages/_constraint-registry/`. Owner: new `src/managers/constraint_manager.py`. Constraint texts will be ours, not the precursor's 65.
- `project_registry` — borrowed from `.parts/.dev-tools-REF/src/lib/intake.py`'s registry pattern.
- Reserved nullable fields on `events` — schema-only reservation per inventory §1.2 (recovery / session-training / journal-durability fields).

**New scaffold files added during Tranche B:**
- `_docs/planning/IMPLEMENTATION_ROADMAP.md`.
- `_docs/migration/INCORPORATION_INVENTORY.md` (Tranche A output).
- `src/managers/constraint_manager.py` (prose plan; informed by `_constraint-registry/` package).
- `config/toolbox_manifest.json.PLAN.md` (shape adapted from `.parts/.dev-tools-REF/toolbox_manifest.json` and `tool_manifest.json`).
- `config/tool_manifest.json.PLAN.md` (shape adapted from `.parts/.dev-tools-REF/tool_manifest.json`).

**Updates to existing scaffold files:**
- `_docs/reference/ARCHITECTURE.md` — substantial revision to fold in the new sections (see above).
- `data/README.md` — extended table list and reserved-field section.
- `src/schemas/event_schema.py` — reserved-fields section added.
- `config/README.md` — `tool_manifest.json` (renamed from `mcp_tools.json`) and `toolbox_manifest.json` added to planned files table.

**Approved by:** user (this conversation, sequence of Q&A through Tranches A + B).

**Notes:**
- The precursor `.parts/.dev-tools-REF/` remains untouched (read-only per contract §1.1).
- Tools and code from the precursor have NOT been copied yet — that happens in Tranches 2–5 when the spine is up. Each code copy will get its own dated entry here.
- Concepts deferred to later tranches (Bag/Shelf overflow, recovery flows, teaching sandbox harness, k8s wrapper, Ollama agent runtime, per-hunk diff provenance, and related runtime hardening) are listed in `_docs/planning/IMPLEMENTATION_ROADMAP.md` under the tranche-mapped deferred backlog and mirrored as open journal todos. They will get provenance entries when adopted.

---

### 2026-05-10 — Tranche 1 implementation (Spine Boot) — ORIGINAL CODE

- **Status:** T1 ✓ COMPLETE. Smoke test 10/10 PASS. Park Phase performed in degraded form (full Park Phase deferred to T2's first act; see closeout notes).
- **Type:** Original implementation. **No precursor source files were copied during T1.** The 19 implementation files (~3,850 lines) follow the prose plans laid down in Tranche 0 and informed by the structural borrows already recorded in the prior provenance entry.
- **Files implemented (T1):**
  - `src/lib/`: common.py, logging_setup.py
  - `src/schemas/`: envelope_schema.py, event_schema.py, contract_schema.py, projection_schema.py
  - `src/components/`: sqlite_store.py, blob_store.py
  - `src/core/`: envelope.py, state.py, events.py, graph.py, contracts.py, projections.py, router.py
  - `src/managers/`: constraint_manager.py
  - `src/interfaces/`: cli_interface.py
  - Top-level: `src/app.py`, `smoke_test.py`
- **Patterns drawn from precursor (no code copied):**
  - Tool result envelope shape (`{status, tool, input, result}`) per Standard Tool Contract (already in our scaffold's contract).
  - Single-store discipline, additive migrations, contract-acknowledgment gate — all already in our scaffold's design before T1.
  - Two-table constraint registry shape (`constraint_units` + `task_profiles`) — schema design borrowed structurally; implementation written fresh.
- **Resolved code-time decisions:** see `_docs/history/tranches/T1_CLOSEOUT_NOTES.md` § "Decisions made at code time" (13 items) and `_docs/reference/ARCHITECTURE.md` §15 (open-questions list updated).
- **Evidence captured (CAS):**
  - `_docs/history/tranches/T1_CLOSEOUT_NOTES.md` blob hash: `26a89b86a7fcdd1097470e0c5ffda4ca947e5b7b4274c08866b9f2a2e57def28` (10,240 bytes).
  - Merkle root of `blob_store` after T1 close: `3403e5ff31bc690b4856f0f3229a57964a8c0659e0ae0ce25f05024388dfc471`.
  - `data/sidecar.db` exists with 19 tables, 1 migration applied (v1).
- **Approved by:** user (this conversation, T1 implementation greenlight + Park Phase greenlight).
- **Handoff promise:** T2's first act is to write a `kind='tranche'` journal entry that supersedes `_docs/history/tranches/T1_CLOSEOUT_NOTES.md`, citing the evidence hash above. After that, all subsequent tranches close with proper journal entries (no degraded Park Phase needed).

---

### 2026-05-11 — Tranche 2 implementation (Install + Scan + Journal + MCP) — ORIGINAL CODE

- **Status:** T2 ✓ COMPLETE. Smoke test 35/35 PASS. **First proper (non-degraded) Park Phase** — journal entry written as the closeout artifact, no temp banner needed.
- **Type:** Original implementation. **No precursor source files copied during T2.** All ~5,000 lines of code are fresh, following the prose plans and informed by the structural patterns recorded in the prior provenance entry.
- **Sub-tranches:**
  - **T2.1 (Journal layer + handoff):** journal_manager, journal_orchestrator, journal_timeline projection, migration v2. **T1 handoff HONORED** — proper `kind='tranche'` journal entry replaced the T1 degraded Park Phase artifact.
  - **T2.2 (Install + Scan + Project Index):** file_scanner, project_index_manager, install_orchestrator (idempotent), scan_orchestrator, project_map + human_dashboard builders, migration v3.
  - **T2.3 (Git + Evidence + Tools + MCP):** git_reader, git_state_manager, evidence_manager, tool_registry_manager (auto-discovery), agent_task_orchestrator (skeleton), 5 tools, mcp_interface (read-only MCP stdio), migration v4.
- **Files implemented (T2):**
  - `src/managers/`: journal_manager, project_index_manager, evidence_manager, git_state_manager, tool_registry_manager
  - `src/orchestrators/`: journal_orchestrator (basic), install_orchestrator, scan_orchestrator, agent_task_orchestrator (skeleton)
  - `src/components/`: file_scanner, git_reader
  - `src/interfaces/`: mcp_interface
  - `src/tools/`: file_tree_snapshot, workspace_boundary_audit, host_capability_probe, text_file_reader, read_projection
  - Major updates: sqlite_store (migrations v2/v3/v4), state, app, router (scan finalize), projections (3 real builders), cli_interface (~12 subcommands), schemas (event + contract + projection mappings extended)
- **Patterns from precursor (no code copied):**
  - Tool registry pattern (FILE_METADATA + run + source_hash) mirrors precursor's tool manifest discipline.
  - Two-phase commit for journal/scan/git observations (PENDING → real event_id post-EventStore.append) — extends T1's ack pattern.
  - Read-only MCP shape — generic; no precursor code reused.
- **Resolved code-time decisions:** see `_docs/history/tranches/T2_PARK_NOTES.md` § "Decisions made at code time" (10 items). Highlights: per-file scan events DEFERRED (envelope lightness), graph edges during scan DEFERRED, tool registry dual in-memory+DB, MCP actor resolution from `_meta.client_name`, HARD_BLOCK gate still advisory (tools enforce their own required_authority).
- **Evidence captured (CAS):**
  - T2 closeout notes blob hash: `9f87dcf37c9f3f7e4d5e3dedca00233a13ce375d8d8b46bc3810fd43e3703d71` (9,001 bytes)
  - Merkle root of `blob_store` after T2 close: `10cdf883593b558b5f835cd06ba0bacc43c8b3f56a474694f946233b1bc8d937`
  - Schema version: 4
  - Tool registry: 5 tools
  - 25 blobs in CAS
- **T2 closeout journal entry:** `journal_18ae7f230a832584_7211d04a` (created by event `evt_18ae7f230a894518_fa9d9a7e`).
- **T2 task lifecycle events:** `accept_task` (`evt_18ae7f25a0923054_29a027ea`) → `complete_task` (`evt_18ae7f25a0a1dd9c_c235e8d0`), correlation_id `cor_18ae7f25a08afaa0_90f7365f`.
- **Approved by:** user (this conversation, T2 greenlight + sub-tranche greenlights).
- **Next:** T3 — Tk UI surfaces. Real `agent_bootstrap` projection builder. Standing by.

---

### 2026-05-11 — Tranche 2.5 (Active Tranche Ledger) — ORIGINAL CODE

- **Status:** T2.5 ✓ COMPLETE. Smoke test 51/51 PASS. Pre-T3 architectural enhancement added at user request: "push a button and the docs almost fully update themselves."
- **Type:** Original implementation. **No precursor source files copied.**
- **New files:**
  - `src/managers/tranche_manager.py` — owns `decision_records` + `active_tranche` tables; handles `declare_tranche`, `update_tranche`, `record_decision`, `smoke_pass`; provides `build_checklist(state)` for projection + closeout gating.
  - `src/orchestrators/closeout_orchestrator.py` — handles `close_tranche`; reads accumulated ledger data, compiles Markdown park notes, creates + closes the tranche journal entry, seals the tranche. The "compile-and-seal" implementation of Park Phase §D.
- **Modified files:**
  - `src/components/sqlite_store.py` — migration v5 (`decision_records` + `active_tranche` tables + indices).
  - `src/schemas/projection_schema.py` — `tranche_checklist` added to `PROJECTION_NAMES` (8th projection); new `INTENT_AFFECTS_PROJECTIONS` entries for T2.5 intents.
  - `src/core/projections.py` — `_build_tranche_checklist` builder added; calls `state.tranche_manager.build_checklist`.
  - `src/core/router.py` — `_TRANCHE_DECLARE_INTENTS` + `_DECISION_INTENTS` added to the finalization elif chain (3d and 3e branches); `_tranche_manager` reference added.
  - `src/managers/journal_manager.py` — `create_direct` + `close_direct` methods added (bypass path for orchestrators).
  - `src/app.py` — wired `TrancheManager`, `CloseoutOrchestrator`; 5 new handlers registered; `router._tranche_manager` set.
  - `src/interfaces/cli_interface.py` — 7 new CLI commands (`tranche-declare`, `tranche-status`, `tranche-update`, `tranche-close`, `tranche-smoke-pass`, `decision-record`, `decision-list`).
  - `smoke_test.py` — §33 projection count updated (7→dynamic); §47–51 added (migration v5 check, table existence, projection query, handler registration, round-trip test).
- **Architecture documents updated:** `_docs/reference/ARCHITECTURE.md` §3.7 (Active Tranche Ledger), §15 (Resolved at T2.5); `_docs/planning/IMPLEMENTATION_ROADMAP.md` (T2.5 complete block); `_docs/continuity/ONBOARDING.md` (tranche commands + CLI reference updated); `_docs/reference/SOURCE_PROVENANCE.md` (this entry).
- **Design decisions captured:**
  - "capture once, derive many" principle — `DecisionRecord` is the atom; park notes, journal body, and bootstrap PAST field all derive from it.
  - `create_direct` / `close_direct` bypass on `JournalManager` for orchestrators — documents the exception to the envelope-only rule for internal choreography.
  - Checklist items `park_notes_written` and `journal_entry_closed` are produced BY `close_tranche` — excluded from the pre-close gate, included in the post-close seal check.
  - Smoke test idempotency: smoke-test tranche cleaned up at §51 start to allow repeated runs.
- **Approved by:** user (this conversation, T2.5 design session).
- **Next:** T3 — Tk UI. The tranche-declare + tranche-close workflow now provides the "Park Tranche" button that T3's Tk UI will wire to.

---

## Conventions

- One entry per re-homing event. Append-only.
- Use ISO 8601 UTC dates.
- If a re-homed file is later modified materially (not just edits), add a follow-up entry under the same heading or a dated sub-entry.
- If a re-homed file is removed, mark it `**RETIRED:** <date> — <reason>` rather than deleting the entry.

---

### 2026-05-12 — Branch 02 transition + privacy/path hardening — ORIGINAL CODE

- **Status:** Additive branch-local record created for `.scaffold_BRANCH-02`. This entry exists to mark branch-specific cleanup without rewriting prior history.
- **Type:** Original implementation and documentation updates in this branch. No precursor code copied for this adjustment.
- **What changed:**
  - corrected live-project misspelling to `constraint`
  - added a typo-warning guard to `smoke_test.py`
  - hardened live outward-facing path surfaces so branch/runtime reporting prefers relative/public-safe labels over absolute local HDD paths
  - sanitized live DB/log records in this branch where machine-specific root strings had already been persisted
- **Documentation added:**
  - `_docs/BRANCH_02_TRANSITION_NOTE_2026-05-12.md`
- **Interpretation rule:** this is a branch-local additive note, not a retroactive mutation of earlier tranche history, park notes, or provenance entries.
- **Approved by:** user (this conversation; explicit request to preserve the fact of branch divergence and session work without mutating history).

---

### 2026-05-12 — Tranche 3 (Tk Monitoring UI) — ORIGINAL CODE

- **Status:** T3 ✓ COMPLETE. Tk monitoring console implemented; smoke test PASS.
- **Type:** Original implementation. No precursor runtime code copied. `.parts/UI_Concept/` was used as a structural and visual reference only.
- **Materially implemented from placeholders:**
  - `src/ui/main_window.py`
  - `src/ui/state_panel.py`
  - `src/ui/journal_panel.py`
  - `src/ui/evidence_panel.py`
  - `src/ui/project_map_panel.py`
  - `src/ui/contracts_panel.py`
- **Modified files:**
  - `src/app.py` — added `ui` mode entrypoint
  - `src/core/state.py` — expanded state wiring for T2.5/T3 services used by the UI
  - `src/core/projections.py` — real `viewport_state` and `evidence_bag` builders
  - `src/schemas/projection_schema.py` — `viewport_state` added as the 9th projection
  - `src/components/sqlite_store.py` — migration v6 for `proj_viewport_state`
  - `smoke_test.py` — T3 coverage + active-tranche-aware round-trip behavior
- **Design borrow (structure only, no code copy):**
  - Unified Tri-Temporal (`PAST / PRESENT / FUTURE`) dashboard shape from `.parts/UI_Concept/app.jsx`
  - Monitoring-console visual hierarchy from `.parts/UI_Concept/theme.css`
  - Browser implementation, JSX fixtures, and CDN runtime were not adopted
- **What shipped:**
  - Tkinter-native monitoring console launched by `python -m src.app ui`
  - read-only dashboard backed by `viewport_state`
  - drill-down panels for state, journal, evidence, project map, and contract status
  - polling status bar + log summary surfaces
  - no UI-triggered mutation path in this tranche
- **Approved by:** user (this conversation; explicit decision to preserve Tk identity, use the browser mock as reference only, and favor broader monitoring reach over a narrower UI port).
- **Next:** T4 — proposal + approval cycle, building real approval affordances on top of the now-live Tk monitoring shell.

---

### 2026-05-13 — Tranche 4 (Approval Loop + Handoff Doctrine Uplift) — ORIGINAL CODE

- **Status:** T4 ✓ COMPLETE. Approval queue, grant issuance, proposal-capable MCP, bounded workspace mutation path, and cold-team handoff docs landed together.
- **Park record:** `_docs/history/tranches/T4_PARK_NOTES.md`; blob hash `ddcaa03882b28f0519f8872fbe08ab74b784468c7e5ffa7fc45adad32d58d4b9`; tranche journal entry `journal_18aeffe951e29fd0_686ec667`.
- **Type:** Original implementation. Structural guidance came from the current branch architecture and the precursor's operator/runtime ideas, but no runtime code was copied wholesale.
- **New files:**
  - `src/managers/agent_session_manager.py`
  - `src/managers/human_approval_manager.py`
  - `src/lib/text_workspace.py`
  - `src/tools/text_file_writer.py`
  - `src/tools/directory_scaffold.py`
  - `src/ui/handoff_panel.py`
  - `_docs/history/DEV_LOG.md`
  - `_docs/continuity/WE_ARE_HERE_NOW.md`
  - `_docs/planning/NORTHSTARS.md`
- **Modified files:**
  - `src/components/sqlite_store.py` — migration v7 (`agent_sessions`, `approval_requests`)
  - `src/core/contracts.py` — grant-aware tool authority matching and scoped grant consumption
  - `src/core/projections.py` — real `handoff` projection, pending approval aggregation, viewport/operator updates
  - `src/core/router.py` — finalization wiring for approval requests and tool invocations
  - `src/interfaces/mcp_interface.py` — `sidecar/submit`
  - `src/interfaces/cli_interface.py` — approval/session operator commands
  - `src/ui/contracts_panel.py`, `src/ui/main_window.py` — operator UI uplift
  - docs: `README.md`, `_docs/continuity/ONBOARDING.md`, `_docs/reference/ARCHITECTURE.md`, `_docs/planning/IMPLEMENTATION_ROADMAP.md`, `_docs/reference/TOOLS.md`, contract, provenance
- **Borrow/adaptation notes:**
  - bounded write safety patterns adapted conceptually from `.parts/.dev-tools/src/lib/text_workspace.py`
  - old agent-runtime lessons informed the session/approval split, but this tranche rebuilt those concerns on the current spine instead of porting the older runtime forward
- **Approved by:** user (this conversation; explicit request to treat this branch as the strangler replacement and finish setup as a cold-team-handoff substrate).

---

### 2026-05-13 — Tranche 5 (Local Sidecar Agent Reintegration) — ORIGINAL CODE

- **Status:** T5 ✓ COMPLETE. Local Ollama-backed sidecar runtime restored inside the current substrate. Park notes: `_docs/history/tranches/T5_PARK_NOTES.md`; blob hash `bd0827915b9ca17d76a204c73e8032e2b5f56aec44eff021e73114ac37853e35`; tranche journal entry `journal_18af19e0c59104ec_fad65652`.
- **Type:** Original implementation. The older `.parts/.dev-tools` local-agent experiment informed the runtime floor and operator shape, but no old runtime file was copied wholesale into this branch.
- **New or materially landed surfaces:**
  - `src/runtime/local_agent_runtime.py`
  - `src/ui/local_agent_panel.py`
  - local-agent CLI controls in `src/interfaces/cli_interface.py`
- **Key hardening done in this tranche:**
  - normalized local-agent writes onto the shared `text_file_writer` contract (`content` canonical, `body` compatibility alias)
  - explicit authorities rows created for session-backed local/MCP actors through `agent_session_manager`
  - cooperative stop support for long-running local-agent sessions
  - smoke-backed proof that the local agent can bootstrap, request approval, complete a bounded workspace write, and surface its run through the spine
- **Borrow/adaptation notes:**
  - runtime/operator lessons were adapted from the old local-agent experiment in concept only
  - the rebuilt T5 floor routes all actions through the current branch's envelope, grant, journal, and projection systems instead of reviving the older runtime as a parallel subsystem
- **Approved by:** user (this conversation; explicit request to implement the next tranche and move the project beyond external stand-in agents).

---

### 2026-05-13 — Tranche 5.1 (Companion Monitor Default + UI Stability) — ORIGINAL CODE

- **Status:** T5.1 ✓ COMPLETE. Follow-up stability/documentation tranche after T5.
- **Type:** Original implementation. No precursor code copied; this tranche tightened operator ergonomics and monitoring truth within the current branch.
- **What changed:**
  - added `src/lib/ui_launcher.py` to spawn the Tk monitor as a companion process for agent-facing runs
  - wired default monitor launch into MCP startup and local-agent CLI runs, with explicit `--no-ui` suppression
  - preserved notebook/focus selection across Tk refreshes in `src/ui/main_window.py`
  - aligned viewport drift checks with the smoke-test tranche-resolution rule in `src/core/projections.py`
  - updated onboarding and continuity docs to describe the new default behavior and mark T5.1 as the latest parked tranche

### 2026-05-13 — Tranche 6 (STM + Bag of Evidence + Evidence Shelf) — ORIGINAL CODE

- **Status:** T6 ✓ COMPLETE. Park notes: `_docs/history/tranches/T6_PARK_NOTES.md`; blob hash `598a76da026c778f19bdc1a4c1597cc4405a12d051d830001e190fdf002a1309`; tranche journal entry `journal_18af1d7325d57744_83774848`.
- **Original implementation in this branch:**
  - `src/managers/memory_manager.py` introduces session-backed STM, Bag, Shelf, and change-hunk persistence inside the current SQLite spine
  - `src/components/diff_builder.py` is now executable code rather than a prose stub
  - `src/runtime/local_agent_runtime.py`, `src/tools/text_file_writer.py`, and `src/core/projections.py` were extended to persist and surface memory state instead of keeping it ephemeral
- **Precursor influence, not code copy:**
  - the Bag / Shelf conceptual flow and session-evidence framing continue to borrow from the old `.parts/.dev-tools` experiment
  - the current implementation is a substrate-native rewrite that routes through the current branch's schema, router, tool contract, and projection surfaces rather than reviving the precursor runtime as-is
- **Approved by:** user (this conversation; explicit request to make the monitor pop up by default when an agent runs the sidecar).

### 2026-05-13 — Tranche 6.1 (Post-Park Continuity Alignment) — ORIGINAL DOC / TEST ALIGNMENT

- **Status:** T6.1 ✓ COMPLETE. Follow-up continuity seal after T6 close.
- **Type:** Original documentation and smoke-alignment work in this branch. No precursor code copied.
- **What changed:**
  - advanced continuity docs from “T6 active” to “T6/T6.1 parked, T7 next”
  - aligned roadmap + architecture wording with the parked T6 memory-layer state
  - updated smoke expectations so tranche-history and next-horizon checks track the real parked state instead of stale hard-coded assumptions

### 2026-05-14 — Tranche 7 (Run Trace, Recovery, and Operator Cockpit) — ORIGINAL CODE

- **Status:** T7 ✓ COMPLETE. Local-agent execution is now persisted as a first-class temporal object. Park notes: `_docs/history/tranches/T7_PARK_NOTES.md`; blob hash `1b8bd02c97e4aaa8a7b2f6739a3475cf3674b40b347937030e14ddc40b8d7955`; tranche journal entry `journal_18af45da8a7bfa1c_5b4be0dd`.
- **Type:** Original implementation in this branch. The old precursor’s runtime-observability ideas influenced the target shape, but the persistence model, projection layer, recovery taxonomy, CLI surfaces, and Tk cockpit uplift were rebuilt on the current spine.
- **New or materially landed surfaces:**
  - `src/managers/run_trace_manager.py`
  - `src/managers/recovery_manager.py`
  - schema v9 additions in `src/components/sqlite_store.py`
  - runtime trace integration in `src/runtime/local_agent_runtime.py`
  - `runtime_cockpit` projection plus CLI inspection commands and Tk local-agent panel uplift
- **Key hardening done in this tranche:**
  - captured run/round/runtime-event/touched-path/link/claim-grounding state in SQLite
  - normalized recovery classes and operator guidance instead of ad hoc failure strings
  - persisted retry/replay snapshots and explicit `retried_from_run_id` lineage
  - grounded final no-mutation and mutation-bearing completions in trace-linked artifacts
  - extended smoke to prove successful, failed, stopped, retried, grounded, projected, and Tk-hydrated runtime paths
- **Borrow/adaptation notes:**
  - precursor ideas informed the notion of a richer operator runtime plane
  - the T7 implementation remains substrate-native and manager-owned, not a port of the old runtime telemetry layer

## 2026-05-14 — T8 Teaching Sandbox + Training Runway

- **Status:** T8 ✓ COMPLETE. Minimal training/evaluation substrate now lives inside the cleaned-up sidecar rather than only in the precursor.
- **Fresh implementation in this branch:**
  - `src/managers/training_runway_manager.py`
  - `src/ui/training_runway_panel.py`
  - `training_scenarios/definitions/*.json`
  - schema v10 scorecard / scenario-run tables
  - `training_runway` projection and matching CLI surfaces
- **Structural borrow / adaptation from `.parts/.dev-tools`:**
  - the concept of a disposable teaching sandbox
  - the doctrine split between deterministic mocked runs and live proof evidence
  - compact reviewer export packets instead of raw transcript dumps
- **Not ported wholesale:**
  - old-harness breadth, broad scenario curriculum, and bespoke runtime stores
  - raw-toolbox execution surface from the precursor
  - any hidden or side-channel memory/evaluation paths outside the SQLite spine

## 2026-05-14 — T8.1 Post-Park Training Handoff Alignment

- **Status:** T8.1 ✓ COMPLETE. Small continuity/parser follow-up after T8 close.
- **Original implementation in this branch:**
  - patched `src/core/projections.py` so roadmap parsing preserves concrete next-step output for `agent_bootstrap` even when the upcoming tranche is defined by completion criteria rather than a file list
  - updated continuity docs to reflect the T8.1 parked state while keeping T9 as the next substantive horizon
- **Borrow/adaptation notes:** none beyond the existing continuity doctrine in this branch; this was a substrate-native fix

## 2026-05-14 — T9 Installed-Project Proof + Vendability Seal

- **Status:** T9 ✓ COMPLETE. The branch now has a proven installed-project baseline and formally supersedes the older experiment as the default installable substrate.
- **Original implementation in this branch:**
  - `src/managers/installed_project_proof_manager.py`
  - `src/ui/installed_project_proof_panel.py`
  - schema v11 `installed_project_proofs` state in `src/components/sqlite_store.py`
  - installed-context boot/root resolution in `src/app.py`
  - trust-gate hardening for installed host writes in `src/core/contracts.py`
  - `installed_project_proof` projection and CLI surfaces
  - installed-proof smoke coverage and proof-fixture/handoff export flow
- **Fresh host proof artifacts:**
  - proof run id: `proof_run_18af6bba61f19740_953e88c4`
  - linked local-agent run ids: `local_run_20260514T114059490Z`, `local_run_20260514T114102189Z`
  - approval request / grant: `approval_18af6bc2a5d254b0_86ecc546` / `grant_18af6bc2b8e7ea74_0cfa1c16`
  - hunk ref: `hunk_18af6bc347f5fcd8_7698bda5`
  - authoritative closeout metadata: `_docs/history/tranches/T9_CLOSEOUT_METADATA.json`
- **Structural borrow / adaptation notes:**
  - the idea of proving the substrate by installing it into a disposable host-like target continues the predecessor experiment’s “teach by doing” instinct
  - the actual installed-proof runner, installed-context boot semantics, projection, UI panel, and smoke path were written fresh on the current spine rather than ported from precursor code
- **Why this matters:** T9 is the tranche where `.scaffold` stops being only the project-under-construction and becomes the proven substrate that can be installed into other projects and handed to a cold team without chat context.

## 2026-05-14 — T10 Closeout Metadata Derivation Hardening

- **Status:** T10 slice ✓ COMPLETE. This is a post-baseline continuity/process hardening slice, not a new substrate-capability tranche.
- **Original implementation in this branch:**
  - `src/orchestrators/closeout_orchestrator.py` now derives and writes generated closeout metadata for the latest parked tranche and for each newly closed tranche
  - `src/interfaces/cli_interface.py` now exposes closeout-metadata inspection and backfill commands
  - `smoke_test.py` now verifies exact agreement between generated closeout metadata and the authoritative latest closed tranche state
  - `_docs/continuity/LATEST_PARKED_TRANCHE.json/.md` and `_docs/history/tranches/T10_CLOSEOUT_METADATA.json/.md` now act as generated continuity artifacts rather than hand-maintained mirrors
- **Structural borrow / adaptation notes:** none from precursor runtime code; this is substrate-native process enforcement built on top of the existing Active Tranche Ledger and Park Phase doctrine.
- **Why this matters:** T10 closes a real continuity gap discovered after T9, where stale mirrored prose could drift from the authoritative DB/projection state even though Park Phase had otherwise succeeded. Exact latest closeout ids are now derived mechanically instead of copied by hand.

## 2026-05-15 — T10.1 Prototype Target Requirements Map + Chat-Centered Sidecar Alignment

- **Status:** T10.1 planning/doctrine tranche. No new runtime subsystem was implemented here; this slice codifies the next target before any chat-centered build work begins.
- **Park record:** `_docs/history/tranches/T10_1_PARK_NOTES.md`; blob hash `afe9b35ca828a84b242e1c94b2366d51976a9e3da6a4b407567aec4ed5fa7d8a`; tranche journal entry `journal_18afc62d4ea1f43c_49c6368b`.
- **Type:** Original doctrine/planning work in this branch, informed by user workflow clarification plus external review/verification feedback gathered during the T10 discussion.
- **What landed:**
  - new target-state artifact: `_docs/planning/TARGET_STATE.md`
  - doctrine updates in `README.md`, `_docs/continuity/ONBOARDING.md`, `_docs/continuity/WE_ARE_HERE_NOW.md`, `_docs/planning/NORTHSTARS.md`, `_docs/planning/IMPLEMENTATION_ROADMAP.md`, `_docs/reference/ARCHITECTURE.md`, and `contracts/BCC.md`
  - continuity-level projection/smoke alignment so the new target-state artifact becomes part of mechanical reading-order truth
- **External conceptual influences (no code copied):**
  - the explicit split between **Prototype Target State** and **Long-Term Evolutionary Target**
  - the framing that external chat helps think while `.scaffold` helps act, record, govern, review, and continue
  - the anti-drift doctrine sentence:
    - **The chat workspace is a governed projection/action surface over the sidecar spine, not an independent memory or authority layer.**
- **What was intentionally not done:**
  - no chat workspace implementation
  - no runtime API/tool/schema expansion
  - no second memory or authority layer
  - no silent cleanup of stale historical todos
- **Why this matters:** T10.1 turns a broad intuition about “chat-centered sidecar” into a contract-bound target that later tranches can implement without accidentally creating a second brain alongside the SQLite spine.
