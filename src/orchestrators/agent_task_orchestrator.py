"""
FILE: src/orchestrators/agent_task_orchestrator.py
ROLE: Coordinates an agent's task lifecycle — accept task, run, propose,
      mark complete or supersede.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WORKFLOW
--------
Models the lifecycle of a task an agent works on:
1. **accept_task** — agent declares intent to work on a task. Records who,
   when, with what authority level.
2. **observe** — agent reads projections to gather context.
3. **propose** — agent emits proposal envelopes (journal entries, patch
   plans, evidence attachments). Authority required: Propose.
4. **request_elevation** — if the agent needs Sandbox Execute or Apply,
   it submits a request that pauses for human approval.
5. **complete_task** — agent declares the task done; orchestrator records
   summary, supersedes prior open tasks if appropriate, refreshes
   projections.

OPERATION INTENTS HANDLED
-------------------------
- `accept_task`
- `complete_task`
- `supersede_task`
- `request_authority_elevation`

STATE
-----
- Reads/writes via managers (no direct DB access). The task records live
  in `journal_entries` (kind='task') per the precursor's pattern.
- Updates `SidecarState.active_task` as tasks are accepted/completed.

SPINE FIT
---------
- Receives envelopes from MCP interface (agent-driven) or UI (human can
  start a task on behalf of the agent).
- Coordinates across journal_manager (for the task record),
  evidence_manager (for attached evidence), tool_registry_manager (for
  tool invocations within a task).

NON-GOALS
---------
- Does not decide what the agent should do — that's the agent.
- Does not enforce approval flow — ContractAuthority does. The
  orchestrator submits the elevation request envelope; whether it's
  approved is the human's call recorded as an `approved_by` relation.

OPEN QUESTIONS
--------------
- Should an agent be able to have multiple active tasks? MVP: one at a
  time. Concurrency adds little until we're sure about the spine's
  load behavior.
- Task hierarchy (subtasks)? Probably yes; model via `belongs_to`
  relations between task journal entries.
"""
