"""
FILE: src/managers/journal_manager.py
ROLE: Owner of the journal domain. The single store for journal entries.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

DOMAIN
------
"Journal" = the human- and agent-readable record of decisions, notes,
todos, issues, design records, work logs, and devlogs. The journal is the
narrative layer above the event log: events record *what happened*; the
journal records *what we think about it*.

Per contract Pledge 2 (Single Store): all journal access flows through
this manager. No tool, orchestrator, or UI panel queries the journal
table directly.

OPERATION INTENTS HANDLED
-------------------------
- `create_journal_entry`
- `update_journal_entry` (updates produce a new revision row; the original
  remains for audit)
- `close_journal_entry`
- `archive_journal_entry`
- `query_journal` (read-side; bypasses the event log because reads are
  not state mutations)

STATE
-----
- Owns the `journal_entries` table per contract §"Journal Data Model":
      entry_uid, kind, source, body, body_hash, tags_json, metadata_json,
      created_at, updated_at, status, importance, title, related_path,
      related_ref, project_id, author.
- Bodies are stored both inline (in `body`, always readable) and via
  CAS (`body_hash` → `blob_store`). The dual write is the additive
  integrity layer per contract Pledge 4.

SPINE FIT
---------
- Receives envelopes from Router; writes journal rows; returns result
  envelope.
- Read API (`query_journal`) is callable by ProjectionManager when
  building Journal Timeline View.

DEPENDENCIES
------------
- `src/components/blob_store.py`
- `src/components/sqlite_store.py`

NON-GOALS
---------
- Does not decide which entries to create — orchestrators or the agent do.
- Does not build the Journal Timeline projection — that's
  ProjectionManager calling this manager's read API.

OPEN QUESTIONS
--------------
- Entry revisions: keep all, or coalesce? Plan: keep all, mark superseded
  with the standard relation type.
- Importance scale: 0–10 per precursor. Confirm at code time.
- Soft-delete vs archive: archive only; no hard delete. The contract
  prohibits reckless pruning.
"""
