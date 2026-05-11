"""
FILE: src/ui/journal_panel.py
ROLE: Tkinter panel showing the Journal Timeline projection.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WHAT IT SHOWS
-------------
The Journal Timeline projection (`proj_journal_timeline`):
- A list (Treeview) of journal entries: created_at, kind, source, title,
  status, importance, tags.
- Filter controls: kind (multi-select), source, status, importance >= N,
  tag contains.
- A detail pane on selection showing the full body and the linked
  evidence_refs / related_path.

DATA SOURCE
-----------
Reads `state.current_projections["journal_timeline"]`. Filters apply
client-side; full-text search submits a `query_journal` envelope.

ACTIONS
-------
- "New entry" — opens a modal to compose a new journal entry; on submit
  builds a `create_journal_entry` envelope.
- "Close" / "Archive" / "Reopen" on selected entry — corresponding
  envelope intents.
- "Attach evidence" — opens evidence picker; submits `attach_evidence`.
- "Export filtered" — submits `export_journal_bundle` (requires Export
  authority).

SPINE FIT
---------
- Read from projection; write via envelopes.
- Never queries the journal_entries table directly — always through the
  read-side envelope intent or a projection slice.

NON-GOALS
---------
- Not a markdown editor. Plain text input; markdown is rendered on read.
- No drag-and-drop reordering — entries are append-only.

OPEN QUESTIONS
--------------
- Rich text rendering: optional; markdown body shown as plain text MVP.
- Pagination: projection rows can be many; lean on filters + a row cap
  with "load more."
"""
