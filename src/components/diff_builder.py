"""
FILE: src/components/diff_builder.py
ROLE: Constructs unified diffs from before/after content for proposals.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

PURPOSE
-------
Mechanical worker that builds unified diff text from a (before, after)
pair. Used by patch proposals so the agent can show a human exactly
what would change before requesting Apply authority.

WHAT IT EXPOSES
---------------
- `class DiffBuilder`
- `DiffBuilder.from_strings(path, before, after) -> DiffResult`
       Returns a DiffResult with:
           path, unified_diff_text, hunk_count, added_lines,
           removed_lines, context_hash
- `DiffBuilder.from_files(project_root, path, after_text) -> DiffResult`
       Reads `path` as the "before"; `after_text` is the proposal.
- `DiffBuilder.preview(diff_result, max_lines=80) -> str` — truncated
  preview for envelope evidence_refs (the full diff lives in blob_store).

OUTPUT DISCIPLINE
-----------------
- Unified format with 3 lines of context by default, configurable.
- Line endings preserved; no auto-normalization.
- Diff bytes are written into `blob_store`; the envelope carries only
  the hash + a summary (hunk_count, added/removed counts).

SPINE FIT
---------
- Called by tools that produce patch proposals.
- Output flows into evidence_manager via the standard envelope chain.

NON-GOALS
---------
- Does not apply diffs. That's `patch_applier`.
- Does not interpret semantics — pure text diffing.
- Does not handle binary files. Returns `kind="binary"` in the result;
  caller decides what to do.

OPEN QUESTIONS
--------------
- Whitespace handling: ignore-whitespace as an option? Default off.
- Chunk size limits: massive diffs should still produce a result, but
  the preview gets truncated. Decide threshold at code time.
"""
