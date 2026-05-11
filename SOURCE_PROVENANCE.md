# SOURCE_PROVENANCE.md

Tracks the origin of any logic, document, or pattern that was re-homed into `.scaffold/` from an external source. Each entry records: what was brought in, where it came from, when, what was changed in the re-homing, and who approved it.

The purpose is to keep the vended sidecar honest about its lineage so future agents can audit decisions and so we never lose track of whether a piece of code is original to this project or adapted from elsewhere.

---

## Entries

### 2026-05-10 — Builder Constraint Contract (Tranche 0 revision)

- **Re-homed into:** `contracts/builder_constrant_contract.md`
- **Source:** `.parts/IMPORTANT-DOCUMENTS-TO-READ-FIRST/builder_constrant_contract.md` (precursor copy)
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

## Conventions

- One entry per re-homing event. Append-only.
- Use ISO 8601 UTC dates.
- If a re-homed file is later modified materially (not just edits), add a follow-up entry under the same heading or a dated sub-entry.
- If a re-homed file is removed, mark it `**RETIRED:** <date> — <reason>` rather than deleting the entry.
