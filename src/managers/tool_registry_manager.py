"""
FILE: src/managers/tool_registry_manager.py
ROLE: Owner of the tool registry. Discovers, validates, and indexes tools.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

DOMAIN
------
The set of tools available in `src/tools/`. Each tool follows the
Standard Tool Contract (`FILE_METADATA + run(arguments)` per contract
§"Standard Tool Contract").

This manager is responsible for:
- Discovering tool files in `src/tools/`.
- Loading their `FILE_METADATA`.
- Validating they conform to the contract (required fields, JSON schema
  for `input_schema`, run() signature).
- Registering them with their `mcp_name` for the MCP interface.
- Indexing them by category for `TOOLS.md` regeneration.

OPERATION INTENTS HANDLED
-------------------------
- `register_tool` (auto-discovery on boot, also callable manually)
- `unregister_tool`
- `query_tools`
- `invoke_tool` — the standard tool execution entrypoint. Wraps the tool's
  `run()` and emits `tool_invoked` / `tool_result` / `tool_failed` events.

STATE
-----
- Owns `tool_registry` table: tool_name, version, entrypoint, category,
  summary, mcp_name, input_schema_json, registered_at.
- Owns `tool_invocations` table: invocation_id, tool_name, envelope_id,
  arguments_ref, result_ref, status, started_at, finished_at.
- Updates `SidecarState.registered_tools` on register/unregister.

INVOCATION FLOW
---------------
When the Router routes `invoke_tool` here:
1. Load the tool by name; validate arguments against its `input_schema`.
2. Emit `tool_invoked` event (Router does this on return).
3. Call `tool.run(arguments)`; capture result or exception.
4. On success: return result envelope with tool's result envelope nested
   under `payload_ref` (the result is itself a structured envelope per
   the Standard Tool Contract).
5. On failure: return failure envelope with traceback in
   `evidence_refs`.

SPINE FIT
---------
- Receives envelopes from Router for `register_tool` / `invoke_tool`.
- Read API consulted by MCP interface for the tool list.
- Read API consulted by the agent bootstrap projection.

DEPENDENCIES
------------
- `src/components/sqlite_store.py`
- The tool files themselves (imported dynamically).

NON-GOALS
---------
- Does not author tools.
- Does not decide WHICH tool to invoke — the agent or human chooses.
- Does not maintain TOOLS.md directly — a separate tool category=export
  regenerates it.

OPEN QUESTIONS
--------------
- Hot reload: should tool changes be picked up at runtime? Probably yes
  via a "reload tool" intent. Defer.
- Sandbox isolation for tool execution: which tools require Sandbox
  Execute authority? Default to "tools that write files outside
  blob_store"; refine per-tool via `FILE_METADATA["required_authority"]`.
"""
