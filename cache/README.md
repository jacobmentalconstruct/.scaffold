# `cache/` — Derived / Regenerable Caches

> **Status:** Tranche 0 plan. Empty until something needs caching.

## Purpose

Holds any artifact that is **derivable from authoritative state** (the DB) and is kept on disk only for speed. Anything in this folder must be safely deletable: deleting `cache/` and rebooting should yield identical behavior, just slower.

## Planned uses (illustrative, not committed)

| Subfolder / file | Purpose |
|---|---|
| `file_index/` | Pickled file-tree scans of the host project, keyed by content hash. Refreshed by `scan_orchestrator`. |
| `git_state/` | Cached git status / diff results, keyed by commit + worktree state. |
| `projection_cache/` | Materialized projection slices that are expensive to rebuild on demand. |
| `tool_metadata/` | Cached `FILE_METADATA` dicts from `src/tools/*.py`, refreshed when files change. |

## Rules

- **Never authoritative.** If state lives only in `cache/`, that is a defect — push it into the DB or accept it as ephemeral.
- The folder is gitignored.
- A cache entry must include enough provenance (source hash, build time) that a stale entry is detectable.
- Components that write here must also handle the case where their cache is missing.
