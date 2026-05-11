"""
FILE: src/ui/contracts_panel.py
ROLE: Tkinter panel showing the Contract Status projection.
WHAT IT DOES (planned): see prose plan below.

================================================================================
TRANCHE 0 PROSE PLAN — DO NOT EXECUTE
================================================================================

WHAT IT SHOWS
-------------
The Contract Status projection (`proj_contract_status`):
- Currently in-force contract: id, version, hash.
- Acknowledgments: who, when, hash at time of ack.
- Outstanding scoped grants: actor, intent, scope, expires_at.
- Recent contract events (acks, grants, revocations, contract revisions).

A read-only viewer for the contract text itself (loaded from blob_store
via the contract record's `text_blob_ref`).

DATA SOURCE
-----------
Reads `state.current_projections["contract_status"]`. The full contract
text is loaded on demand from blob_store.

ACTIONS
-------
- "Acknowledge contract" — for the current human user; submits
  `acknowledge_contract` envelope.
- "Approve grant" — for a pending elevation request; submits a `grant`
  envelope.
- "Revoke grant" — submits `revoke` envelope.
- "Propose revision" — opens modal; submits a `propose_contract_revision`
  envelope (which becomes a journal entry of kind='specification' and
  triggers human review).

APPROVAL UX
-----------
This panel is the primary place where a human approves elevation
requests from the agent. When the agent submits
`request_authority_elevation`, a row appears here with:
- The intent the agent wants to perform.
- Why (from the request envelope's narrative).
- A preview of what the elevated envelope would do.
- Approve / Deny / Approve-once buttons.

SPINE FIT
---------
- Reads projection.
- Submits envelopes for ack, grant, revoke, propose-revision, approve.
- Never mutates contract records directly.

NON-GOALS
---------
- Not a contract editor. Revisions are proposed, then a human authors
  the new contract text outside the UI; the panel only tracks the
  proposal lifecycle.

OPEN QUESTIONS
--------------
- Markdown rendering of contract text: defer; show as monospaced text.
- Approval audit: the approval itself is an envelope and recorded as
  an event; the panel just shows it.
"""
