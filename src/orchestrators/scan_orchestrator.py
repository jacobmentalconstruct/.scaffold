"""
FILE: src/orchestrators/scan_orchestrator.py
ROLE: Coordinates project file scans and git observation, building the
      project index and emitting graph edges for file structure.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WORKFLOW
--------
The scan workflow is the second step of the first proving loop:

    install → SCAN → project map → events → graph edges → projections

It walks the host project tree, observes files, observes git state, and
hands the results to managers via the Router.

STEPS
-----
1. Open a scan record (envelope to project_index_manager).
2. Walk the project tree using `file_scanner` (respecting .gitignore and
   .scaffoldignore).
3. For each file: emit `record_observed_file` envelope.
4. Run git observation via `git_manager`.
5. Compute deltas vs the prior scan (added/modified/removed).
6. Emit graph edges:
       (project) belongs_to (each_directory)
       (directory) belongs_to (each_file)
       (file) belongs_to (parent_directory)
7. Close the scan record (envelope with summary counts).
8. Trigger refresh of Project Map View, Human Dashboard View.
9. Return result envelope.

OPERATION INTENTS HANDLED
-------------------------
- `scan` (full scan)
- `rescan_path` (incremental, scoped to a subpath)

DEPENDENCIES
------------
- Managers: project_index_manager, git_manager.
- Components: file_scanner, git_reader.

SPINE FIT
---------
- Each file observation is its own envelope through the Router. For very
  large projects this could be batched — open question.
- The orchestrator does NOT touch the DB directly; everything goes through
  managers via Router.

NON-GOALS
---------
- Does not interpret file contents (no AST, no language detection beyond
  extension). Tools do that.
- Does not write to the host project tree.

OPEN QUESTIONS
--------------
- Batching: emit one envelope per file or one envelope per directory with
  a list of files? Plan: per-file for clarity; revisit if event-log
  volume is a problem.
- Concurrency: parallelize file hashing? MVP serial; revisit if scan
  time exceeds patience.
- Watch mode: a follow-up orchestrator could watch the file system and
  emit incremental scan events. Defer.
"""
