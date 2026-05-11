"""
FILE: src/managers/project_index_manager.py
ROLE: Owner of the project-file index — the sidecar's view of the host project.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

DOMAIN
------
The map of files in the host project: their paths, kinds, sizes, hashes,
last-observed timestamps, and any annotations the sidecar has attached.
This is the sidecar's understanding of the host project's terrain.

The index is built by scanning (via `src/components/file_scanner.py`),
maintained by `scan_orchestrator`, and consulted by anything that needs
to ask "what files exist? what changed? what does this file relate to?"

OPERATION INTENTS HANDLED
-------------------------
- `record_observed_file` — one row of scan output.
- `record_scan_summary` — closes a scan with totals.
- `query_project_index` (read).

STATE
-----
- Owns `project_index` table: path (relative to project root), kind, size,
  content_hash, last_observed_at, last_observed_event, observe_count,
  annotation_json.
- Owns `scans` table: scan_id, started_at, finished_at, file_count,
  added_count, modified_count, removed_count, summary_ref.
- Updates `SidecarState.registered_objects` for files of interest
  (selectively — not every file becomes a registered object).

SPINE FIT
---------
- Receives envelopes from Router (issued by `scan_orchestrator`).
- Read API consulted by `ProjectionManager` for Project Map View.
- Read API consulted by the file_scanner component for delta computation.

DEPENDENCIES
------------
- `src/components/sqlite_store.py`
- Indirectly: `src/components/file_scanner.py` is the producer; this
  manager is the consumer.

NON-GOALS
---------
- Does not decide WHEN to scan — `scan_orchestrator` does.
- Does not interpret file contents — it stores hashes and metadata only.
  Content interpretation lives in tools (e.g., an AST tool, a dependency
  tool).
- Does not write to the host project tree. The sidecar's job here is
  observation.

OPEN QUESTIONS
--------------
- Honor `.gitignore` and `.scaffoldignore`? Yes for both, with the
  scaffoldignore as an override. Decide format at code time.
- What about binary files? Hash them, store metadata, do not load body.
- Symlinks? Follow within project root only; never escape it.
"""
