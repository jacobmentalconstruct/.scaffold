"""
FILE: src/managers/evidence_manager.py
ROLE: Owner of the evidence domain. Validates and stores evidence items.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

DOMAIN
------
"Evidence" = any piece of supporting content that backs a claim made by an
envelope. Examples: a file excerpt with line range, a tool output, a
diff summary, a screenshot capture, a citation to an external source.

Evidence is content-addressed (CAS); the bytes live in `blob_store` and
the evidence row carries the hash plus metadata about kind, source, and
what it supports.

OPERATION INTENTS HANDLED
-------------------------
- `attach_evidence` — register a new evidence item, attach to an object
  (file, journal entry, task, patch proposal).
- `verify_evidence` — recompute the hash and confirm integrity.
- `list_evidence_for(object_id)` — read-side helper used by ProjectionManager.

STATE
-----
- Owns the `evidence` table:
      evidence_id, hash, kind, summary, source_event, source_path,
      source_line_range, attached_to_object, attached_to_type, status,
      created_at.
- Updates `SidecarState.evidence_bag_state` on accept.

SPINE FIT
---------
- Receives envelopes from Router via `handle(envelope, state)`.
- Writes the evidence row.
- Returns a result envelope; Router records the event and adds graph
  relations: `(evidence:X) cites (object:Y)`, `(envelope:Z) produces
  (evidence:X)`.

DEPENDENCIES
------------
- `src/components/blob_store.py` for content-addressed storage.
- `src/components/sqlite_store.py` for the evidence table writes.

NON-GOALS
---------
- Does not decide what to do with evidence — orchestrators do.
- Does not call other managers directly. If evidence verification implies
  a journal entry, that flows back through the Router as a new envelope.

OPEN QUESTIONS
--------------
- Evidence kinds: free-form string vs enum? Lean enum with extension
  registry. Decide at code time.
- Whether to support evidence chains (evidence A `derives_from` evidence B):
  yes, via the standard relation type; no special handling needed here.
"""
