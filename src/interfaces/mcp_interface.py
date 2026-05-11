"""
FILE: src/interfaces/mcp_interface.py
ROLE: MCP server. The agent-facing interface. Translates MCP requests into
      envelopes; submits to Router; returns Router responses as MCP results.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

PURPOSE
-------
Exposes the sidecar to MCP-capable agents. Each registered tool from
`src/tools/` becomes an MCP tool. Each projection becomes a readable
resource. The router is the only thing that actually executes.

This file is a DUMB ADAPTER. It translates between MCP wire format and
SidecarEnvelope. It does not decide, validate business rules, or touch
the DB. Per the spine rule, all behavior is downstream.

WHAT IT EXPOSES
---------------
- `serve(state, transport="stdio") -> None` — boot the MCP server with
  the given transport.
- Internally: a registration step that:
    * Lists tools from `state.registered_tools`.
    * For each tool, declares an MCP tool with name = `mcp_name` and
      input_schema = `input_schema` (from each tool's FILE_METADATA).
    * For each projection, declares an MCP resource (read-only).

REQUEST FLOW
------------
1. MCP client calls a tool.
2. Adapter constructs a `SidecarEnvelope` with:
       operation_intent = "invoke_tool"
       payload_ref      = blob_store.put_json({tool_name, arguments})
       actor_id         = "agent:<id>" (from MCP session metadata)
       contract_refs    = derived from session's acknowledgment record
3. Adapter calls `router.dispatch(envelope)`.
4. On success: extracts `result` payload, returns to MCP client.
5. On failure: returns an MCP error with the contract section that
   was violated (helps the agent self-correct).

RESOURCE READS
--------------
For projection reads:
1. Adapter constructs an envelope with `operation_intent = "read_projection"`.
2. Router routes to `ProjectionManager.read(...)`.
3. Result payload returned to MCP client.

AUTHORITY HANDOFF
-----------------
The MCP session carries agent identity. The adapter looks up the agent's
authority from `ContractAuthority` and stamps the envelope. The agent
cannot lie about its authority — the adapter overrides whatever the
client claims.

SPINE FIT
---------
- Single function `serve()` is the entrypoint.
- Translates wire format ↔ envelopes.
- All real logic lives in the router and downstream.

NON-GOALS
---------
- Does not implement tools.
- Does not authenticate beyond what MCP provides.
- Does not stream results (MCP supports streaming for some content;
  defer until needed).

OPEN QUESTIONS
--------------
- Transport: stdio is the default for vendability (works with Claude
  Code etc.); HTTP optional for remote agents. Configurable in
  `config/sidecar.json`.
- Session identity: how does the agent identify itself? MCP capabilities
  may include client info; otherwise we generate a session-bound id and
  require the human to bind it to a known actor.
- Tool versioning: MCP tools versioned by `tool_name@version`?
  Decide at code time.
"""
