"""
FILE: src/orchestrators/install_orchestrator.py
ROLE: First-boot installer. Initializes the SQLite spine and seeds defaults.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WORKFLOW
--------
The first-boot orchestrator. Runs once when `data/sidecar.db` does not
exist (or when an explicit `reinstall` envelope is approved). Coordinates
across multiple managers/components to bring a fresh sidecar to life.

STEPS (in order)
----------------
1. Resolve sidecar root and host project root from `SidecarState`.
2. Open SQLite store; run schema creation.
3. Seed `journal_meta`: schema_version, sidecar_id (generated), project_root,
   initialized_at.
4. Read `contracts/builder_constrant_contract.md`; compute hash; write
   into `blob_store`; create the contract record.
5. Seed ontology with built-in object types and the closed predicate set.
6. Write the seed `journal_config.json` and `db_manifest.json` into
   `config/` (using ContractAuthority-permitted writes since this is
   bootstrap).
7. Emit a `project` stream event: `install` with summary.
8. Construct the agent bootstrap packet projection for the first time.
9. Hand off to whichever interface invoked install (UI or MCP) with a
   summary envelope.

OPERATION INTENTS HANDLED
-------------------------
- `install`
- `reinstall` (requires Apply authority + human approval)

DEPENDENCIES
------------
- Managers: journal_manager, ontology_manager, tool_registry_manager,
  project_index_manager (for first scan, optional in MVP install).
- Components: sqlite_store, blob_store.

SPINE FIT
---------
- Receives the install envelope from Router.
- Calls into managers via Router (NOT directly), so each step is itself
  an envelope chain. The bootstrap exception in ContractAuthority allows
  these initial envelopes through before the first acknowledgment.
- Returns a result envelope summarizing installed state.

NON-GOALS
---------
- Does not perform a full project scan automatically — that's
  `scan_orchestrator`, optionally invoked after install completes.
- Does not start the UI or MCP server — `app.py` does that after install
  returns.

OPEN QUESTIONS
--------------
- Should install offer a "minimal" vs "full" mode? Plan: one install
  path; scope is set by what the user does next.
- Idempotency: install on an existing DB should be a no-op with a clear
  warning. `reinstall` is the explicit destructive variant.
"""
