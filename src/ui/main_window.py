"""
FILE: src/ui/main_window.py
ROLE: Tkinter root window. Hosts the panels. Drives polling and submits
      envelopes from human actions.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

PURPOSE
-------
The Tkinter root window. Mostly a monitoring surface (the human watches
the sidecar do its work) with selective action affordances (approve a
patch, acknowledge contract, kick off a scan).

LAYOUT (planned)
----------------
A multi-pane layout:

    +--------------------------------------------------------+
    | Menu:  File | View | Actions | Help                    |
    +-------------+------------------------------------------+
    | Side nav    | Active panel (one of the 5 panels)       |
    | - State     |                                          |
    | - Journal   |                                          |
    | - Evidence  |                                          |
    | - Contracts |                                          |
    | - Map       |                                          |
    +-------------+------------------------------------------+
    | Status bar: connection | last refresh | unread approvals|
    +--------------------------------------------------------+

POLLING
-------
- The status bar polls every 3 seconds for projection refresh times and
  unread approval count.
- Each panel has its own refresh policy (poll, on-demand, or push when
  we add a notification channel).

ACTION SUBMISSION
-----------------
- When the human clicks an action button in a panel, the panel calls
  back into `main_window.submit(envelope_template)`.
- `submit` fills in `actor_id`, `created_at`, `correlation_id`,
  validates, and calls `state.router.dispatch(envelope)`.
- Result is shown to the human; on failure, the contract section that
  was violated is shown so the user can choose to elevate (request
  approval) and re-submit.

WHAT IT EXPOSES
---------------
- `run(state)` — boot the Tk root, instantiate panels, enter mainloop.
- `submit(envelope_template)` — used by panels to submit envelopes.

SPINE FIT
---------
- The UI is a peer of the MCP interface. Both produce envelopes. Both
  go through the Router. The UI does not bypass the spine.
- Panels never touch the DB directly. They read projections and submit
  envelopes.

NON-GOALS
---------
- Not pretty. Functional Tk widgets are the bar; styling can come later.
- Not asynchronous. Tkinter mainloop is the loop; long actions show a
  modal "working..." indicator and run on a background thread, posting
  back via `after()`.
- Not multi-window. One root, one panel at a time, MVP. Tabs or
  multi-window can come later.

OPEN QUESTIONS
--------------
- Threading: long actions on a worker thread, marshalled back via
  `root.after`. Decide pattern at code time.
- Theme: stick with default ttk; revisit if it looks too 1998.
- Cross-platform paths: ensure `pathlib.Path` everywhere, no string
  concatenation.
"""
