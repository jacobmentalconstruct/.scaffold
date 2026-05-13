# `snapshots/` — Spine Snapshots

> **Status:** Tranche 0 plan. Empty until the first snapshot is taken.

## Purpose

Holds **point-in-time snapshots of the spine**: the SQLite DB, a Merkle root computed over `blob_store`, and any associated manifest needed to verify integrity later.

Snapshots exist for three reasons:

1. **Recovery** — restore the spine to a known-good state after corruption or experimentation.
2. **Audit** — prove what the spine looked like at a moment in time, with a hash that can be referenced from elsewhere.
3. **Sharing** — bundle a snapshot to send to another agent or human for parallel inspection.

## Planned shape

```
snapshots/
├── <iso_timestamp>__<merkle_root_short>/
│   ├── sidecar.db                   ← copy of the DB at snapshot time
│   ├── manifest.json                ← schema version, blob count, merkle root, sidecar version, triggering event
│   ├── relations.csv                ← graph relations dumped flat (optional, for human reading)
│   └── README.md                    ← what triggered this snapshot, who approved it
```

## Merkle root construction

Per the precursor contract: sort all `blob_store` hashes, concatenate, SHA-256. This is the deterministic root and the snapshot's identifier short-form.

## When snapshots happen

(Open question, see `ARCHITECTURE.md` §11.) Candidates:
- On tranche close (programmatic, manual trigger).
- On contract revision acknowledgment.
- On demand via the `snapshot` tool category.
- Scheduled (e.g., daily) — likely deferred.

## Rules

- Snapshots are immutable. Never edit one in place.
- Snapshot creation emits an event in the `project` stream with `operation_intent="snapshot"`.
- Snapshots are gitignored by default; only `.gitkeep` is tracked. Specific snapshots may be checked in deliberately by copying them out of this folder.
- Restore is destructive — it requires its own approval flow and an event recording the restore.
