"""
FILE: src/ui/evidence_panel.py
ROLE: Tkinter panel showing the Evidence Bag projection.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WHAT IT SHOWS
-------------
The Evidence Bag projection (`proj_evidence_bag`):
- A list of evidence items: id, kind, summary, attached_to, status,
  created_at.
- A detail pane on selection: full metadata, hash, content excerpt
  (loaded lazily from blob_store via a `read_blob` envelope).

DATA SOURCE
-----------
Reads `state.current_projections["evidence_bag"]`.

ACTIONS
-------
- "Verify" — submits `verify_evidence` envelope; updates the row's
  verification status.
- "Open source" — if the evidence cites a host project file with line
  range, opens the file in the project map at that line.
- "Detach" / "Re-attach" — manage which object the evidence is bound to.

SPINE FIT
---------
- Reads projection, submits envelopes for actions.

NON-GOALS
---------
- Not a content viewer for arbitrary blob types — text and JSON only
  for MVP.
- Does not mutate evidence content (immutability is the point).

OPEN QUESTIONS
--------------
- How to handle large blob preview: truncate at N lines / KB; "view
  full" opens in an external editor.
- Diff-kind evidence: render as side-by-side or unified? Unified, MVP.
"""
