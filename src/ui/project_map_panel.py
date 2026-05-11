"""
FILE: src/ui/project_map_panel.py
ROLE: Tkinter panel showing the Project Map projection.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WHAT IT SHOWS
-------------
The Project Map projection (`proj_project_map`):
- A tree view of the host project: directories and files, last_observed_at,
  size, kind.
- Annotations: which files have journal entries citing them; which have
  evidence attached; which are dirty (per git_manager observation).
- Counts at directory level (file count, total size).

DATA SOURCE
-----------
Reads `state.current_projections["project_map"]`.

ACTIONS
-------
- "Scan now" — submits `scan` envelope.
- "Rescan path" — on directory selection, submits `rescan_path`.
- "Open file" — opens the file in the system's default editor (host
  project tree, read-only by sidecar; the user owns whether to edit).
- "Show citations" — opens evidence_panel filtered by this file.
- "New journal entry about this file" — opens journal_panel composer
  pre-filled with `related_path`.

SPINE FIT
---------
- Read projection; submit envelopes for actions.
- Does NOT modify any host project file. The "Open file" action is a
  host-OS handoff, not a sidecar write.

NON-GOALS
---------
- Not an editor.
- Not a search across file content (that needs an index; defer).

OPEN QUESTIONS
--------------
- Tree expand/collapse persistence: remember per-session? Defer.
- Performance on large trees: virtualize the Treeview if needed.
"""
