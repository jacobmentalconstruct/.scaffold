# `src/tools/` — Sidecar Tools

> **Status:** Tranche 0 plan. No tools registered yet.

## Purpose

Tools are the sidecar's **action surface**. Every action an agent or human takes that the sidecar should record, validate, and govern lands in a tool here.

The MCP interface exposes each tool by its `mcp_name`. The CLI invokes them by their `tool_name`. The Tkinter UI's action buttons construct the same envelopes that tools emit, so behavior is consistent across surfaces.

## Standard Tool Contract (per `contracts/builder_constraint_contract.md`)

Every tool file must:

1. Begin with the docstring header:
   ```python
   """
   FILE: <filename>.py
   ROLE: <one-line role>
   WHAT IT DOES: <details>
   """
   ```

2. Export `FILE_METADATA`:
   ```python
   FILE_METADATA = {
       "tool_name":  "<unique_name>",
       "version":    "<semver>",
       "entrypoint": "src/tools/<filename>.py",
       "category":   "<bootstrap|scan|write|query|export|scaffold|"
                     "contract|projection|snapshot|ledger>",
       "summary":    "<one-line description>",
       "mcp_name":   "<mcp_registration_name>",
       "input_schema": { ... },        # JSON Schema
       "required_authority": "<Observe|Propose|Sandbox Execute|Apply|Export>",
   }
   ```

3. Implement `run(arguments) -> dict` returning the standard envelope:
   ```python
   {
       "status":  "ok|error",
       "tool":    "<tool_name>",
       "input":   { ... },
       "result":  { ... },
   }
   ```

4. Support three CLI modes:
   ```bash
   python src/tools/<filename>.py metadata
   python src/tools/<filename>.py run --input-json '{...}'
   python src/tools/<filename>.py run --input-file path.json
   ```

5. Route ALL DB access through the appropriate manager via the Router. A tool **never** opens the SQLite file directly. (Single Store pledge.)

6. Construct envelopes for any state-changing action; do not mutate state outside the envelope path.

7. Be added to `TOOLS.md` once registered.

## Tool registration

Tools are discovered at boot by `src/managers/tool_registry_manager.py`. It walks this folder, loads each `.py` (excluding `_*.py` and `__init__.py`), reads `FILE_METADATA`, and validates the contract. Failures are logged but do not block boot; the failing tool is unregistered and a journal entry of kind='issue' is created.

## Categories — quick map

| Category | Examples (planned, not yet built) |
|---|---|
| `bootstrap` | install, reinstall, ack_contract |
| `scan` | scan_project, rescan_path, observe_git |
| `write` | create_journal_entry, attach_evidence, propose_patch |
| `query` | read_projection, query_journal, query_index, find_relations |
| `export` | export_journal_bundle, export_dashboard, export_bootstrap_packet |
| `scaffold` | scaffold_in_workspace, scaffold_into_project |
| `contract` | propose_revision, request_authority_elevation, grant, revoke |
| `projection` | refresh_projection, rebuild_projection |
| `snapshot` | take_snapshot, verify_snapshot, restore_snapshot |
| `ledger` | tail_events, search_events |

## Authoring a new tool

1. Pick a category. If none fit, propose a new one — categories are deliberately small and slow-growing.
2. Determine required authority. Default to the lowest level that works.
3. Define the input_schema before writing code.
4. Implement `run()`; keep it thin — push real work into managers/components.
5. Add three CLI smoke invocations to your dev notes (manual for MVP; automated tests later).
6. Register the tool by adding a row to `/TOOLS.md`.
7. Journal a `kind='specification'` entry summarizing the tool's purpose, authority, and any non-obvious behavior.
