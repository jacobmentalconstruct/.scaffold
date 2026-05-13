# SOURCE_PROVENANCE.md

Tracks the origin of any logic, document, or pattern that was re-homed into `.scaffold/` from an external source. Each entry records: what was brought in, where it came from, when, what was changed in the re-homing, and who approved it.

The purpose is to keep the vended sidecar honest about its lineage so future agents can audit decisions and so we never lose track of whether a piece of code is original to this project or adapted from elsewhere.

---

## Entries

### 2026-05-10 — Builder Constraint Contract (Tranche 0 revision)

- **Re-homed into:** `contracts/builder_constraint_contract.md`
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

A bundle of structural borrows committed during the planning phase. Full per-item analysis lives in [`_docs/INCORPORATION_INVENTORY.md`](_docs/INCORPORATION_INVENTORY.md). Recorded here as a single dated entry; individual code copies will get their own dated entries when the borrowed material actually lands in `src/` during Tranches 2–5.

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
- `IMPLEMENTATION_ROADMAP.md` (top-level).
- `_docs/INCORPORATION_INVENTORY.md` (Tranche A output).
- `src/managers/constraint_manager.py` (prose plan; informed by `_constraint-registry/` package).
- `config/toolbox_manifest.json.PLAN.md` (shape adapted from `.parts/.dev-tools-REF/toolbox_manifest.json` and `tool_manifest.json`).
- `config/tool_manifest.json.PLAN.md` (shape adapted from `.parts/.dev-tools-REF/tool_manifest.json`).

**Updates to existing scaffold files:**
- `ARCHITECTURE.md` — substantial revision to fold in the new sections (see above).
- `data/README.md` — extended table list and reserved-field section.
- `src/schemas/event_schema.py` — reserved-fields section added.
- `config/README.md` — `tool_manifest.json` (renamed from `mcp_tools.json`) and `toolbox_manifest.json` added to planned files table.

**Approved by:** user (this conversation, sequence of Q&A through Tranches A + B).

**Notes:**
- The precursor `.parts/.dev-tools-REF/` remains untouched (read-only per contract §1.1).
- Tools and code from the precursor have NOT been copied yet — that happens in Tranches 2–5 when the spine is up. Each code copy will get its own dated entry here.
- Concepts deferred to later tranches (Bag/Shelf overflow, recovery flows, teaching sandbox harness, k8s wrapper, Ollama agent runtime) are listed in `IMPLEMENTATION_ROADMAP.md` "Files DEFERRED past prototype" — they will get provenance entries when adopted.

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
- **Resolved code-time decisions:** see `_docs/T1_CLOSEOUT_NOTES.md` § "Decisions made at code time" (13 items) and `ARCHITECTURE.md` §15 (open-questions list updated).
- **Evidence captured (CAS):**
  - `_docs/T1_CLOSEOUT_NOTES.md` blob hash: `26a89b86a7fcdd1097470e0c5ffda4ca947e5b7b4274c08866b9f2a2e57def28` (10,240 bytes).
  - Merkle root of `blob_store` after T1 close: `3403e5ff31bc690b4856f0f3229a57964a8c0659e0ae0ce25f05024388dfc471`.
  - `data/sidecar.db` exists with 19 tables, 1 migration applied (v1).
- **Approved by:** user (this conversation, T1 implementation greenlight + Park Phase greenlight).
- **Handoff promise:** T2's first act is to write a `kind='tranche'` journal entry that supersedes `_docs/T1_CLOSEOUT_NOTES.md`, citing the evidence hash above. After that, all subsequent tranches close with proper journal entries (no degraded Park Phase needed).

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
- **Resolved code-time decisions:** see `_docs/T2_PARK_NOTES.md` § "Decisions made at code time" (10 items). Highlights: per-file scan events DEFERRED (envelope lightness), graph edges during scan DEFERRED, tool registry dual in-memory+DB, MCP actor resolution from `_meta.client_name`, HARD_BLOCK gate still advisory (tools enforce their own required_authority).
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
- **Architecture documents updated:** ARCHITECTURE.md §3.7 (Active Tranche Ledger), §15 (Resolved at T2.5); IMPLEMENTATION_ROADMAP.md (T2.5 complete block); ONBOARDING.md (tranche commands + CLI reference updated); SOURCE_PROVENANCE.md (this entry).
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
  - corrected live-project `constrant` -> `constraint` spelling drift
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
