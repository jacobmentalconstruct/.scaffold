# `data/` — Sidecar Spine

> **Status:** Tranche 0 plan. The DB does not exist yet. It will be created by `install_orchestrator` on first sidecar boot.

## Purpose

Holds the **single SQLite database** that is the sidecar's spine. This is the only authoritative store of builder memory (per contract §C, Truth-Layer Separation).

## Planned files

| File | Purpose |
|---|---|
| `sidecar.db` | The hybrid-in-SQLite spine: event log, graph index, projection tables, journal entries, blob_store, journal_meta. |
| `sidecar.db-wal`, `sidecar.db-shm` | SQLite WAL companions. Generated automatically. Do not edit. |
| `.gitkeep` | Placeholder so the folder is tracked even when the DB is gitignored. |

## Schema layers (planned, see `src/storage/` and `src/schemas/`)

The DB carries three layered concerns inside one file:

1. **Authoritative event log** — table `events` keyed by `event_id`, partitioned across streams (`project`, `task`, `object`, `tool`).
2. **Graph index** — table `relations` storing `(subject_id, predicate, object_id)` triples drawn from the closed relation type set.
3. **Projection tables** — one table per projection (e.g., `proj_human_dashboard`, `proj_project_map`, `proj_journal_timeline`, `proj_evidence_bag`, `proj_contract_status`, `proj_agent_bootstrap`, `proj_current_state`).

Plus core tables:

- `journal_entries` — the journal proper.
- `blob_store` — CAS, keyed by SHA-256.
- `journal_meta` — manifest, schema version, contract hash, contract acknowledgment.
- `journal_migrations` — migration history.
- `constraint_units` — atomic constraint units extracted from the binding contract; owned by `src/managers/constraint_manager.py` (NEW per Tranche B Q2).
- `task_profiles` — named bundles of constraint UIDs by task type (`core_implementation`, `refactoring`, etc.); owned by constraint_manager.
- `project_registry` — registry of projects this sidecar has been pointed at; tracks `project_id` referenced in events (NEW per Tranche B Q5).
- `tool_registry` — registered tools with metadata, source hashes, registration timestamps; owned by `src/managers/tool_registry_manager.py`.
- `tool_invocations` — per-invocation records of tool runs; owned by tool_registry_manager.
- `evidence` — evidence items (CAS-backed, attached to objects); owned by `src/managers/evidence_manager.py`.
- `agents`, `acknowledgments`, `grants` — contract authority records (per-actor authority, contract acks, scoped grants).
- `scans`, `git_observations`, `git_dirty_paths`, `git_commits` — observation tables owned by `project_index_manager` and `git_state_manager`.

### Reserved nullable fields on `events` (Tranche B Q4)

Added at T1 with no behavior at MVP; avoids future migration when corresponding tranches enable use:

- **Recovery (deferred to T7+):** `recovery_class`, `recovery_decision`, `evidence_id`
- **Session/training (deferred to T13+):** `session_id`, `run_id`, `scenario_id`, `run_mode`, `timeout_seconds`, `max_tool_rounds`, `score_result`, `pass_fail_state`, `touched_paths` (JSON)
- **Journal durability (used from T2):** `journal_entry_id` (FK to `journal_entries`), `is_durable` (bool), `append_only` (bool)

These fields are NULL on events that don't carry the corresponding semantics. See [`src/schemas/event_schema.py`](../src/schemas/event_schema.py) for the full row shape.

## Rules

- All DB access goes through `src/components/sqlite_store.py` and `src/managers/journal_manager.py`. Nothing else opens the file. (Single Store pledge.)
- Schema changes are additive and versioned; destructive changes require a migration plan.
- The DB is gitignored; only `.gitkeep` is committed. Snapshots for sharing go in `snapshots/`.
- The DB is self-orienting — `journal_meta` carries enough info that an agent can boot from the file alone.
