"""
FILE: src/components/test_runner.py
ROLE: Runs host project tests inside a sandbox workspace.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

PURPOSE
-------
When the agent proposes a patch and wants to validate it before requesting
Apply authority, the patch is materialized inside a workspace and the
host project's tests are run there. This component runs them.

WHAT IT EXPOSES
---------------
- `class TestRunner`
- `TestRunner.detect(project_root) -> Detected`
       Returns the detected test framework: pytest, unittest, jest, etc.,
       and the recommended command.
- `TestRunner.run(workspace_root, command, env=None, timeout=...)
       -> TestRunResult`
       Returns:
           command, exit_code, stdout_ref (blob hash),
           stderr_ref (blob hash), summary, started_at, finished_at,
           parsed_failures (best-effort framework-specific extraction)

SAFETY
------
- Runs ONLY inside a workspace under `workspaces/<id>/`. Refuses to run
  if the working directory is outside `.scaffold/workspaces/`.
- Process is sandboxed by environment: a clean `PATH`, no inherited env
  vars unless explicitly passed.
- Hard timeout; on timeout, terminate the process tree.

SPINE FIT
---------
- Called by tools (Sandbox Execute authority required).
- Output (stdout/stderr) is written to blob_store; envelope evidence_refs
  point to those hashes.

NON-GOALS
---------
- Does not run tests in the host project tree.
- Does not interpret test results beyond best-effort framework parsing
  for the summary.
- Does not retry, schedule, or watch.

OPEN QUESTIONS
--------------
- Framework auto-detection vs explicit configuration: support both, with
  config in `config/sidecar.json`.
- How to surface live progress to the UI: probably stream stdout to a
  log file in the workspace; UI polls the file. Defer until UI panel
  exists.
"""
