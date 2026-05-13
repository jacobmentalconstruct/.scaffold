"""
FILE: src/core/router.py
ROLE: Router — receives envelopes, gates them via ContractAuthority, dispatches
      to handlers, records events, refreshes projections.
WHAT IT DOES: Single dispatch entrypoint for the spine. Holds the handler
              registry. Implements the ordering:
                validate -> gate -> handler -> record -> graph -> projections
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.core.contracts import ContractAuthority
    from src.core.envelope import SidecarEnvelope
    from src.core.events import EventStore
    from src.core.graph import Graph
    from src.core.projections import ProjectionManager
    from src.core.state import SidecarState


log = get_logger("core.router")


HandlerFn = Callable[["SidecarEnvelope", "SidecarState"], "SidecarEnvelope"]


@dataclass
class HandlerEntry:
    operation_intent: str
    handler: HandlerFn
    kind: str  # "orchestrator" | "manager"


class UnrouteableEnvelope(Exception):
    """Raised when no handler is registered for an operation_intent."""


_JOURNAL_INTENTS = frozenset({
    "create_journal_entry",
    "update_journal_entry",
    "close_journal_entry",
    "archive_journal_entry",
})

_SCAN_INTENTS = frozenset({"scan", "rescan_path"})

# T2.5: Tranche Ledger intents that need PENDING → real event_id finalization.
_TRANCHE_DECLARE_INTENTS = frozenset({"declare_tranche"})
_DECISION_INTENTS = frozenset({"record_decision"})


class Router:
    def __init__(
        self,
        state: "SidecarState",
        contract_authority: "ContractAuthority",
        event_store: "EventStore",
        graph: "Graph",
        projections: "ProjectionManager",
        journal_manager=None,    # T2.1+: needed to finalize journal entry event_ids
        scan_orchestrator=None,  # T2.2+: needed to finalize scan event_ids
    ):
        self._state = state
        self._contract = contract_authority
        self._events = event_store
        self._graph = graph
        self._projections = projections
        self._journal = journal_manager
        self._scan_orchestrator = scan_orchestrator
        self._tranche_manager = None    # set in app.py after construction
        self._handlers: dict[str, HandlerEntry] = {}

    # --- registration --------------------------------------------------

    def register(self, operation_intent: str, handler: HandlerFn,
                 kind: str = "manager") -> None:
        if operation_intent in self._handlers:
            raise ValueError(
                f"handler already registered for intent {operation_intent!r}"
            )
        self._handlers[operation_intent] = HandlerEntry(
            operation_intent=operation_intent,
            handler=handler,
            kind=kind,
        )
        log.debug("registered handler: %s (%s)", operation_intent, kind)

    def handlers(self) -> dict[str, dict]:
        return {
            intent: {"kind": entry.kind, "handler": entry.handler.__qualname__}
            for intent, entry in self._handlers.items()
        }

    # --- dispatch ------------------------------------------------------

    def dispatch(self, envelope: "SidecarEnvelope") -> "SidecarEnvelope":
        # Stamp project_id and sidecar_id from state if caller left them blank.
        if not envelope.project_id and self._state.project_id:
            envelope = envelope.__class__.from_dict(
                {**envelope.to_dict(), "project_id": self._state.project_id}
            )
        if not envelope.sidecar_id:
            envelope = envelope.__class__.from_dict(
                {**envelope.to_dict(), "sidecar_id": self._state.sidecar_id}
            )

        log.info(
            "dispatch: intent=%s actor=%s correlation=%s",
            envelope.operation_intent, envelope.actor_id, envelope.correlation_id,
        )

        # 1. Gate.
        check = self._contract.check(envelope)
        if not check.accepted:
            rejected = envelope.with_status("rejected")
            log.warning(
                "REJECTED intent=%s actor=%s outcome=%s reason=%s section=%s",
                envelope.operation_intent, envelope.actor_id,
                check.outcome, check.reason, check.contract_section,
            )
            # Failed envelopes do NOT enter the event log.
            return rejected

        # 2. Handler dispatch.
        entry = self._handlers.get(envelope.operation_intent)
        if entry is None:
            failed = envelope.with_status("failed")
            log.error(
                "UNROUTEABLE intent=%s actor=%s -- no handler registered",
                envelope.operation_intent, envelope.actor_id,
            )
            raise UnrouteableEnvelope(envelope.operation_intent)

        try:
            result_envelope = entry.handler(envelope, self._state)
        except Exception as e:
            log.exception(
                "HANDLER FAILED intent=%s actor=%s -- %s",
                envelope.operation_intent, envelope.actor_id, e,
            )
            return envelope.with_status("failed")

        # 3. Record event.
        sealed = self._events.append(result_envelope)

        # 3a. Special: tie ack rows to their event_id.
        if envelope.operation_intent == "acknowledge_contract":
            self._contract.finalize_ack_event_id(envelope.actor_id, sealed.event_id)
        # 3b. Special: tie journal entries to their event_id (PENDING → real).
        elif envelope.operation_intent in _JOURNAL_INTENTS and self._journal is not None:
            try:
                self._journal.finalize_entry_event_id(sealed)
            except Exception as e:
                log.error("journal finalize failed for event %s: %s", sealed.event_id, e)
        # 3c. Special: tie scan records to their event_id.
        elif envelope.operation_intent in _SCAN_INTENTS and self._scan_orchestrator is not None:
            try:
                self._scan_orchestrator.finalize_scan_event_id(sealed)
            except Exception as e:
                log.error("scan finalize failed for event %s: %s", sealed.event_id, e)
        # 3d. Special: tie active_tranche rows to their event_id.
        elif envelope.operation_intent in _TRANCHE_DECLARE_INTENTS \
                and self._tranche_manager is not None:
            try:
                self._tranche_manager.finalize_declare_event_id(sealed)
            except Exception as e:
                log.error("tranche finalize failed for event %s: %s", sealed.event_id, e)
        # 3e. Special: tie decision_record rows to their event_id.
        elif envelope.operation_intent in _DECISION_INTENTS \
                and self._tranche_manager is not None:
            try:
                self._tranche_manager.finalize_decision_event_id(sealed)
            except Exception as e:
                log.error("decision finalize failed for event %s: %s", sealed.event_id, e)

        # 4. Apply graph relations from envelope's relation_refs.
        try:
            self._graph.add_from_envelope(sealed)
        except Exception as e:
            log.error("graph apply failed for event %s: %s", sealed.event_id, e)

        # 5. Refresh projections affected by this intent.
        self._state.advance_event_position(1)
        try:
            self._projections.refresh_for(sealed)
        except Exception as e:
            log.error("projection refresh failed for event %s: %s", sealed.event_id, e)

        log.info("ACCEPTED event_id=%s intent=%s", sealed.event_id, sealed.operation_intent)
        return sealed
