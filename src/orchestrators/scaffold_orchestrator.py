"""
FILE: src/orchestrators/scaffold_orchestrator.py
ROLE: Coordinates scaffold operations — file/folder skeletons inside a workspace
      or (with Apply authority) inside the host project.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WORKFLOW
--------
Given a scaffold spec (a declared file tree map), produce that tree:
- in `workspaces/<workspace_id>/` under Sandbox Execute authority (default), or
- in the host project tree under Apply authority (with explicit approval).

STEPS
-----
1. Validate the scaffold spec against the declared schema.
2. Resolve target root (workspace vs host project) based on envelope's
   authority.
3. For each declared file/folder:
   - Create the path.
   - If a content template is provided, write it (sourced from
     `src/tools/` template registry or inline in the spec).
   - Hash and record in `project_index` if target is the host project.
4. Emit a `project` stream event: `scaffold_completed` with file list and
   target root.
5. Return result envelope with the list of created paths and their hashes.

OPERATION INTENTS HANDLED
-------------------------
- `scaffold_in_workspace`
- `scaffold_into_project` (requires Apply authority)

DEPENDENCIES
------------
- Managers: project_index_manager, tool_registry_manager (for templates).
- Components: file_scanner (for verification post-write).

SPINE FIT
---------
- Receives envelope from Router; produces sub-envelopes for each
  significant write (back through Router for events + projections).
- Returns a single result envelope summarizing the scaffold action.

NON-GOALS
---------
- Does not author scaffold specs — they come from tools or human input.
- Does not promote workspace output to host project — that's a separate
  envelope chain (`promote_workspace`).
- Does not modify existing files at the destination — scaffolding is for
  new structures only. Modifications go through `patch_orchestrator`
  (deferred).

OPEN QUESTIONS
--------------
- Conflict policy when target paths exist: refuse, warn-and-skip, or
  overwrite-with-backup? Plan: refuse unless the spec explicitly opts in
  to overwrite, in which case emit a backup envelope first.
- Templates with variable interpolation: probably needed; defer the
  template engine choice.
"""
