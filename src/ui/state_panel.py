"""
FILE: src/ui/state_panel.py
ROLE: Tkinter panel showing the Current Sidecar State projection.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WHAT IT SHOWS
-------------
The Current Sidecar State projection (`proj_current_state`):
- Project root + sidecar root paths.
- Sidecar id and version.
- Current contract: hash, version, ack status (per actor).
- Counts: registered objects, registered tools, open journal entries,
  open evidence, open approvals.
- Active task summary (id, kind, started_at).
- Event log position.
- Agent status (connected? authority?).
- Last refreshed timestamp.

DATA SOURCE
-----------
Reads from `state.current_projections["current_sidecar_state"]`.
Polls every 3 seconds.

ACTIONS
-------
- "Refresh now" — submits a `read_projection` envelope to force refresh.
- "Open contract" — switches focus to contracts_panel.
- "View tools" — opens a modal with the tool index.

SPINE FIT
---------
- Read-only consumer of one projection.
- Action buttons construct envelopes and submit via `main_window.submit`.

NON-GOALS
---------
- Does not edit state.
- Does not show event log directly — that's a future panel.

OPEN QUESTIONS
--------------
- How to render counts (raw numbers vs sparkline)? Start with raw.
- Whether to embed tiny mini-charts: defer; Tkinter without extra deps
  means custom canvas drawing.
"""
