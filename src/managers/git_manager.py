"""
FILE: src/managers/git_manager.py
ROLE: Owner of git-state observation for the host project.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

DOMAIN
------
The sidecar's understanding of the host project's git state: current
branch, HEAD commit, dirty files, ahead/behind counts, remote tracking,
recent commit log.

This manager is read-only with respect to git. The sidecar OBSERVES git;
it does not commit, push, or rebase. Any host-project git mutation that
the sidecar might propose travels through `Apply` authority and is
performed by the host (or by a tool the human explicitly approves).

OPERATION INTENTS HANDLED
-------------------------
- `observe_git_state` — record current branch, HEAD, dirty paths.
- `record_git_log` — capture last N commits.
- `query_git_state` (read).

STATE
-----
- Owns `git_observations` table: observation_id, observed_at, branch,
  head_sha, dirty_count, ahead, behind, remote, remote_url.
- Owns `git_dirty_paths` table: observation_id, path, status.
- Owns `git_commits` table (rolling cache): sha, parents_json, author,
  committed_at, subject, body_ref.

SPINE FIT
---------
- Envelopes routed here by `scan_orchestrator` and on-demand from tools.
- Read API consulted by:
    * Project Map View (annotates files with dirty status)
    * Human Dashboard View (current branch, ahead/behind)
    * Agent Bootstrap Packet

DEPENDENCIES
------------
- `src/components/git_reader.py` — the actual git invocation lives there.
- `src/components/sqlite_store.py`

NON-GOALS
---------
- Does not mutate git. Pure observation.
- Does not enforce git policy (e.g., "no commits to main"). The sidecar
  is observational; policy belongs to the host's CI.

OPEN QUESTIONS
--------------
- Worktree handling: assume single worktree for MVP; document multi-worktree
  as a future concern.
- Submodules: ignore for MVP; flag presence in observations.
- Performance: rolling git log can be expensive on large repos; bound to
  N=200 by default, configurable.
"""
