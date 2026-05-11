# T1 Closeout Notes — Spine Boot

> **Status:** TEMPORARY PARKING RECORD. To be **superseded by a proper journal entry of `kind='tranche'`** as the first act of T2, once `journal_manager` exists. This file exists because Park Phase step 4 (write a journal entry) is blocked at T1 — no journal yet.
>
> Per the explicit handoff promise on T2 open: T2's first act is to write the proper journal entry citing the evidence captured here.

---

## Tranche scope (declared at open)

Per `IMPLEMENTATION_ROADMAP.md` T1 spec:

> Build the spine so envelopes can be accepted, gated, recorded, and trigger projection refresh. Nothing useful happens yet — but the machinery works.

Files declared: `src/core/{state,envelope,events,router,contracts,projections,graph}.py`, `src/schemas/*` (all four), `src/components/{sqlite_store,blob_store}.py`, `src/lib/{logging_setup,common}.py`, `src/managers/constraint_manager.py`, `src/app.py`, `smoke_test.py`. ~17 files target.

## Non-goals (declared)

- No install_orchestrator, no scan, no journal_manager, no UI, no MCP server, no real tools.

## What was actually built

**19 implementation files, ~3,850 lines of code.** All matched the declared scope; nothing extra crept in.

| Layer | Files | Lines |
|---|---|---|
| `src/lib/` | common.py, logging_setup.py | 243 |
| `src/schemas/` | envelope, event, contract, projection | 626 |
| `src/components/` | sqlite_store, blob_store | 440 |
| `src/core/` | envelope, state, events, graph, contracts, projections, router | 1,343 |
| `src/managers/` | constraint_manager (only) | 516 |
| `src/interfaces/` | cli_interface (only) | 162 |
| Top-level | src/app.py, smoke_test.py | 319 |

**19 SQLite tables created** (one migration v1 covers all):
- Core (5): journal_meta, journal_migrations, blob_store, events, relations
- Constraints (2): constraint_units, task_profiles
- Contract authority (4): contracts, acknowledgments, authorities, grants
- Project tracking (1): project_registry
- Projection tables (7): proj_current_sidecar_state, proj_agent_bootstrap, proj_human_dashboard, proj_evidence_bag, proj_contract_status, proj_project_map, proj_journal_timeline

**Constraint registry seeded:** 12 hand-curated constraint units (covering Pledges 1, 2, 3, 4, 6, 7 + sections 1.1, 1.2, 1.4, 2.1, 2.2, 4.relations) and 6 task profiles (core_implementation, ui_implementation, tool_creation, scaffolding, documentation, cleanup).

## Verification

**Smoke test result: 10/10 PASS.** `python smoke_test.py` exits 0.

Verified end-to-end:
1. Spine boots, DB+log files materialize.
2. Constraint registry seeds (12 constraints, 6 profiles, core_implementation has 10 constraints).
3. Contract record loads onto state with text_hash.
4. Pre-acknowledgment: non-bootstrap intents REJECTED with `REJECT_UNACKNOWLEDGED_CONTRACT`.
5. `acknowledge_contract` envelope passes via bootstrap exception, lands as event.
6. Event row recoverable via `EventStore.read(event_id)`.
7. Acknowledgments row written, PENDING marker resolved to real `event_id`.
8. `contract_status` projection rebuilds with the new ack visible.
9. `current_sidecar_state` projection shows `current_contract_acked=1`, `event_log_position` advanced.
10. Post-ack: previously-rejected intent now passes the gate (raises `UnrouteableEnvelope` because no T2 handler — *expected*, proves the gate stopped blocking).

CLI surface verified:
- `python -m src.app cli version` → schema_version=1, contract record visible
- `python -m src.app cli list-projections` → 7 projections registered
- `python -m src.app cli ack-contract --actor "human:..."` → round-trip with event_id
- `python -m src.app cli projection contract_status` → live read, ack visible

## Decisions made at code time

These were undecided in the prose plans; resolved during implementation:

1. **ID format** — chose **stdlib-only sortable IDs** (`{prefix}{time_ns:016x}_{8 hex random}`) instead of ulid or uuid7. Rationale: contract Pledge 1 (Python stdlib only). Format is monotonic-ish, sortable, dedupable.
2. **Connection model** — single `sqlite3.Connection` per `Store` instance, `check_same_thread=False`. Single-threaded use in T1; multi-threaded handling deferred until UI thread + MCP thread emerge in T3.
3. **SQLite pragmas** — WAL mode + foreign_keys=ON + busy_timeout=10000 + synchronous=NORMAL. WAL + NORMAL is the precursor's profile and matches our concurrent-reader expectations.
4. **Failed envelopes do NOT enter the event log** — per plan; logged at WARNING with full reason. A future "rejected_envelopes" table for forensics is a noted defer.
5. **Bootstrap exception in gate** — implemented via `BOOTSTRAP_EXEMPT_INTENTS` tuple in `contract_schema.py` (currently: `acknowledge_contract`, `install`, `seed_constraints`). Acknowledgment-presence check is bypassed *only* for these intents, and only while no acknowledgment exists.
6. **Two-phase ack/event commit** — ack rows are written with `event_id='PENDING'` inside `handle_acknowledge`, then the Router calls `ContractAuthority.finalize_ack_event_id` after `EventStore.append` returns the real event_id. Avoids a chicken-and-egg between ack write and event append.
7. **Stub builders for T2+ projections** — `agent_bootstrap`, `human_dashboard`, `evidence_bag`, `project_map`, `journal_timeline` have stub builders registered that just stamp a `journal_meta` key. This means `refresh_for(envelope)` doesn't blow up when an intent's `INTENT_AFFECTS_PROJECTIONS` mapping names a not-yet-built projection.
8. **HARD_BLOCK gate enforcement is currently advisory** — `ContractAuthority._check_hard_block` returns `None` for all units. The actual containment / shape checks (e.g., path-under-sidecar, no-write-to-host-without-Apply) belong in the managers/orchestrators that touch the relevant resources. The gate enforces authority + contract-acknowledgment + envelope-shape + closed-relation-set; it consults constraints but doesn't synthesize new rules from them at T1.
9. **`detect_sidecar_root`** — walks up from any source file looking for either a directory named `.scaffold` *or* a directory containing `contracts/builder_constrant_contract.md`. Robust to where you invoke `python -m src.app` from.
10. **Default authorities by actor prefix** — `human:*` → Apply; `agent:*` → Propose; `tool:*` → Observe; everything else (system) → Apply. Set in `_default_authority_for`. Specific actor records in the `authorities` table override.
11. **Smoke test idempotency** — designed so re-runs don't fail; the pre-ack rejection check is conditional on whether acks already exist from a prior run. Acceptable because the test verifies the spine, not the empty-DB state.
12. **Deterministic relation_id** — implemented per ARCHITECTURE.md §13.3: `gen_relation_id(subject, predicate, object, emitted_by)` returns `rel_<sha256[:24]>`. Idempotent inserts.
13. **Deterministic constraint_uid** — `con_<sha256(section|title)[:16]>`. Re-seeding produces identical UIDs, so seed is idempotent via INSERT...ON CONFLICT DO UPDATE.

## Open questions discovered (beyond ARCHITECTURE.md §15)

- **Contract-revision-aware seed:** when the contract markdown changes, should `seed_from_contract` produce a new contract record (new version), or upsert in-place? Currently it upserts. A real contract revision flow needs versioning + a supersedes relation. Defer until contract revisions become real.
- **Authorities table is unpopulated by default:** `_actor_authority` falls back to default-by-prefix when no row exists. This is fine but means there's no "actor record was never created" vs "actor exists with default authority" distinction. May need explicit `register_actor` envelope in T2.
- **Multi-process safety:** SQLite WAL + busy_timeout handles multiple readers concurrently with a single writer. When T3 introduces the Tk UI as a separate process from MCP, we'll exercise this. T1 only has one process at a time; not exercised yet.
- **Event order vs commit order:** `event_id` and `created_at` are time-derived and monotonic-ish, but multi-process or rapid-fire could see clock-skew. The `(stream, stream_key, sequence)` UNIQUE constraint provides the authoritative order per partition. Reads sort by `created_at, sequence` — works for now, revisit if drift observed.

## Files touched (full list)

**New code (T1 implementation):**
- `src/lib/common.py`, `src/lib/logging_setup.py`
- `src/schemas/envelope_schema.py`, `src/schemas/event_schema.py`, `src/schemas/contract_schema.py`, `src/schemas/projection_schema.py`
- `src/components/sqlite_store.py`, `src/components/blob_store.py`
- `src/core/envelope.py`, `src/core/state.py`, `src/core/events.py`, `src/core/graph.py`, `src/core/contracts.py`, `src/core/projections.py`, `src/core/router.py`
- `src/managers/constraint_manager.py`
- `src/interfaces/cli_interface.py`
- `src/app.py`
- `smoke_test.py` (NEW at top level)

**Updated docs (Park Phase):**
- `IMPLEMENTATION_ROADMAP.md` — T1 marked COMPLETE
- `SOURCE_PROVENANCE.md` — T1 implementation entry (no new borrows)
- `ARCHITECTURE.md` §15 — open questions updated with resolved decisions
- `_docs/T1_CLOSEOUT_NOTES.md` — this file

**Runtime artifacts created (gitignored, not source):**
- `data/sidecar.db` (212 KB after smoke test)
- `data/sidecar.db-shm`, `data/sidecar.db-wal` (WAL companions)
- `logs/sidecar.log`

## Next tranche

**T2 — Install + Scan + Journal + read-only MCP.** First act: write the proper `kind='tranche'` journal entry that supersedes this notes file, citing the evidence captured here.

Specifically T2's opening sequence:
1. Implement `journal_manager.py` (CRUD on `journal_entries` table).
2. Register `create_journal_entry` handler with the Router.
3. Submit a `create_journal_entry` envelope with `kind='tranche'`, `title='T1 Spine Boot — COMPLETE'`, body that absorbs this file's content, and `evidence_refs` citing the `_docs/T1_CLOSEOUT_NOTES.md` blob hash captured in `IMPLEMENTATION_ROADMAP.md`.
4. Once that entry is recorded, this file may be left in place (as a code-time artifact) or removed (the journal entry is now authoritative LTM).

After that, the discipline becomes automatic: every tranche close → journal entry → next tranche open.
