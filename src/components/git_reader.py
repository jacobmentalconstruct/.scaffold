"""
FILE: src/components/git_reader.py
ROLE: Reads git state from the host project. Read-only.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

PURPOSE
-------
Mechanical wrapper around `git` invocations to observe the host project's
git state. Used by `git_manager`.

WHAT IT EXPOSES
---------------
- `class GitReader`
- `GitReader.detect(project_root) -> bool` — is this a git repo?
- `GitReader.head(project_root) -> HeadInfo` — branch, sha, detached?
- `GitReader.status(project_root) -> StatusInfo` — dirty paths and
  their statuses.
- `GitReader.tracking(project_root) -> TrackingInfo` — remote name,
  remote URL, ahead/behind.
- `GitReader.log(project_root, count=200) -> Iterable[CommitInfo]`
- `GitReader.diff(project_root, ref_a, ref_b) -> str` — for evidence
  attachments; never auto-attached, only on explicit request.

INVOCATION DISCIPLINE
---------------------
- Use `subprocess.run` with `shell=False`, never string-concatenation.
- Run with `--porcelain` flags where possible for parseable output.
- Capture stderr; if git fails, return a structured error rather than
  raising deep into the manager.
- Set a timeout per call (e.g., 30s default, configurable).

NON-MUTATION GUARANTEE
----------------------
This reader never invokes `git` commands that mutate state. The allowlist:
`status`, `rev-parse`, `log`, `diff`, `branch`, `remote`, `ls-files`,
`show`, `cat-file`. Anything else is a programming error.

SPINE FIT
---------
- Called by `git_manager` only. No other component talks to git.

NON-GOALS
---------
- No commit, no push, no rebase, no checkout, no add.
- No GitHub / Gitea API calls — those would be a different component
  with its own credentials story.

OPEN QUESTIONS
--------------
- How to handle detached HEAD: report cleanly; don't pretend we're on
  a branch.
- Submodules: ignore by default; flag presence.
- Worktree directory: assume default; document if multi-worktree
  encountered.
"""
