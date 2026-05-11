"""
FILE: src/orchestrators/journal_orchestrator.py
ROLE: Higher-level journal workflows that span more than a single entry write.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WORKFLOW
--------
The journal_manager handles single-entry CRUD. This orchestrator handles
multi-entry workflows:

- **devlog tranche close** — given a tranche identifier, gather all
  envelopes since tranche open, write a summarizing devlog entry, mark
  prior open tranche entries as superseded, optionally trigger snapshot.
- **decision rollup** — gather decisions tagged with a topic, write a
  summary entry citing each, link via `cites` relations.
- **issue triage** — sweep issue-kind entries for stale ones, propose
  status changes to the human via approval queue.
- **export bundle** — produce a markdown / JSON bundle of journal entries
  matching a query, write to `exports/` with `Export` authority.

OPERATION INTENTS HANDLED
-------------------------
- `close_tranche`
- `rollup_decisions`
- `triage_issues`
- `export_journal_bundle`

STATE
-----
- All state mutation through journal_manager + evidence_manager via
  Router.

SPINE FIT
---------
- Each sub-step is its own envelope; the orchestrator coordinates
  sequencing.
- After `close_tranche`, triggers Journal Timeline View refresh and
  optionally `snapshot_orchestrator` (when that exists).

DEPENDENCIES
------------
- Managers: journal_manager, evidence_manager.
- Other orchestrators: scan_orchestrator (for tranche-close evidence
  gathering), snapshot_orchestrator (deferred).

NON-GOALS
---------
- Does not invent decisions — it consolidates decisions the agent or
  human have already journaled.
- Does not delete entries (archive only, per contract).

OPEN QUESTIONS
--------------
- "Tranche" representation: a journal entry of kind='tranche' with
  start/end timestamps and scope/non-goals fields, or a separate table?
  Lean: journal entry. Reuses the entry lifecycle.
- Where do exports go? Per `exports/` README — structured by date.
"""
