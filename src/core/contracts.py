"""
FILE: src/core/contracts.py
ROLE: ContractAuthority — the gate. Authorizes envelopes before any handler runs.
WHAT IT DOES: check(envelope) returns ACCEPT or one of REJECT_* with a reason
              the Router converts into a failure envelope. Consults
              ConstraintManager for the relevant rules. Owns acknowledgments
              and grants.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import TYPE_CHECKING

from src.lib.common import (
    AUTHORITY_LEVELS,
    authority_at_least,
    gen_id,
    now_iso,
)
from src.lib.logging_setup import get_logger
from src.schemas.contract_schema import (
    BOOTSTRAP_EXEMPT_INTENTS,
    DEFAULT_AGENT_AUTHORITY,
    DEFAULT_HUMAN_AUTHORITY,
    DEFAULT_SYSTEM_AUTHORITY,
    DEFAULT_TOOL_AUTHORITY,
    required_authority,
)


if TYPE_CHECKING:
    from src.components.sqlite_store import Store
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState
    from src.managers.constraint_manager import ConstraintManager


log = get_logger("core.contracts")


# Outcome codes.
ACCEPT = "ACCEPT"
REJECT_UNACKNOWLEDGED_CONTRACT = "REJECT_UNACKNOWLEDGED_CONTRACT"
REJECT_INSUFFICIENT_AUTHORITY = "REJECT_INSUFFICIENT_AUTHORITY"
REJECT_MISSING_CONTRACT_REF = "REJECT_MISSING_CONTRACT_REF"
REJECT_BAD_RELATION_TYPE = "REJECT_BAD_RELATION_TYPE"
REJECT_INVALID_ENVELOPE = "REJECT_INVALID_ENVELOPE"
REJECT_HARD_BLOCK_VIOLATION = "REJECT_HARD_BLOCK_VIOLATION"


@dataclass(frozen=True)
class CheckResult:
    outcome: str
    reason: str
    contract_section: str = ""

    @property
    def accepted(self) -> bool:
        return self.outcome == ACCEPT


class ContractAuthority:
    def __init__(self, state: "SidecarState", store: "Store",
                 constraint_manager: "ConstraintManager"):
        self._state = state
        self._store = store
        self._constraints = constraint_manager

    # --- bootstrap loads ------------------------------------------------

    def bootstrap(self) -> None:
        """Load the in-force contract record into state."""
        row = self._store.query_one(
            "SELECT * FROM contracts WHERE superseded_at IS NULL ORDER BY introduced_at DESC LIMIT 1;"
        )
        if row is None:
            log.warning("no in-force contract found; gate will reject everything except bootstrap intents")
            self._state.set_current_contract({})
            return
        contract = {
            "contract_id": row["contract_id"],
            "version": row["version"],
            "text_hash": row["text_hash"],
            "text_blob_ref": row["text_blob_ref"],
            "introduced_at": row["introduced_at"],
            "acked_by": self._all_acks_for(row["contract_id"], row["version"]),
        }
        self._state.set_current_contract(contract)
        log.info("contract loaded: %s v%s hash=%s acks=%d",
                 contract["contract_id"], contract["version"],
                 contract["text_hash"][:12], len(contract["acked_by"]))

    # --- the gate ------------------------------------------------------

    def check(self, envelope: "SidecarEnvelope") -> CheckResult:
        # 1. Validate envelope shape.
        errors = envelope.validate()
        if errors:
            return CheckResult(
                outcome=REJECT_INVALID_ENVELOPE,
                reason="envelope schema violations: " + "; ".join(errors),
                contract_section="Pledge.6",
            )

        # 2. Closed-relation-set check on relation_refs.
        from src.lib.common import RELATION_TYPES_CLOSED_SET
        for i, rel in enumerate(envelope.relation_refs):
            pred = (rel or {}).get("predicate") if isinstance(rel, dict) else None
            if pred and pred not in RELATION_TYPES_CLOSED_SET:
                return CheckResult(
                    outcome=REJECT_BAD_RELATION_TYPE,
                    reason=f"relation_refs[{i}].predicate={pred!r} not in closed set",
                    contract_section="4.relations",
                )

        intent = envelope.operation_intent
        is_bootstrap = intent in BOOTSTRAP_EXEMPT_INTENTS

        # 3. Acknowledgment check (skipped for bootstrap-exempt intents
        #    AND skipped specifically for the very first acknowledgment).
        contract = self._state.current_contract or {}
        contract_acked = bool(contract.get("acked_by"))
        if not contract_acked and not is_bootstrap:
            return CheckResult(
                outcome=REJECT_UNACKNOWLEDGED_CONTRACT,
                reason="contract has not been acknowledged; submit acknowledge_contract first",
                contract_section="0.10",
            )

        # 4. Authority check.
        actor_authority = self._actor_authority(envelope.actor_id)
        # Apply any per-envelope grants.
        granted_level = self._lookup_grant(
            envelope,
            consume=envelope.operation_intent != "tool_invoked",
        )
        effective_authority = _max_level(actor_authority, granted_level) if granted_level else actor_authority

        required = required_authority(intent)
        if not authority_at_least(effective_authority, required):
            return CheckResult(
                outcome=REJECT_INSUFFICIENT_AUTHORITY,
                reason=(
                    f"actor {envelope.actor_id!r} has authority {effective_authority!r} "
                    f"but intent {intent!r} requires {required!r}"
                ),
                contract_section="Authority Levels",
            )

        # 5. Consult constraint registry for HARD_BLOCK rules.
        for unit in self._constraints.query_for_intent(intent):
            if unit.severity == "HARD_BLOCK" and unit.tier == "gate":
                violation = self._check_hard_block(unit, envelope)
                if violation:
                    return CheckResult(
                        outcome=REJECT_HARD_BLOCK_VIOLATION,
                        reason=f"{unit.title}: {violation}",
                        contract_section=unit.section,
                    )

        return CheckResult(outcome=ACCEPT, reason="")

    # --- handlers used by the router for contract-related intents -----

    def handle_acknowledge(self, envelope: "SidecarEnvelope", state: "SidecarState"):
        """Handler for `acknowledge_contract`.

        Records the acknowledgment row, refreshes contract record on state.
        Returns the envelope (status -> completed). Router will append the
        event with a freshly-minted event_id.
        """
        contract = state.current_contract or {}
        contract_id = contract.get("contract_id")
        contract_version = contract.get("version")
        text_hash = contract.get("text_hash")
        if not contract_id or not text_hash:
            raise RuntimeError(
                "cannot acknowledge: no in-force contract loaded "
                "(was seed_from_contract called and ContractAuthority.bootstrap()?)"
            )
        actor_type = self._actor_type(envelope.actor_id)
        self._store.execute(
            """
            INSERT INTO acknowledgments(
                ack_id, contract_id, contract_version, text_hash,
                actor_id, actor_type, acknowledged_at, event_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                gen_id("ack_"),
                contract_id,
                contract_version,
                text_hash,
                envelope.actor_id,
                actor_type,
                now_iso(),
                # event_id will be the envelope's event_id once committed;
                # for now we use a placeholder. The Router updates the
                # acknowledgments row's event_id after EventStore.append.
                "PENDING",
            ),
        )
        # Refresh in-state contract record.
        self.bootstrap()
        return envelope.with_status("completed")

    def finalize_ack_event_id(self, actor_id: str, event_id: str) -> None:
        """After EventStore.append assigns a real event_id, update the ack row."""
        self._store.execute(
            "UPDATE acknowledgments SET event_id = ? "
            "WHERE event_id = 'PENDING' AND actor_id = ?;",
            (event_id, actor_id),
        )

    # --- introspection -------------------------------------------------

    def has_acked(self, actor_id: str) -> bool:
        contract = self._state.current_contract or {}
        return actor_id in (contract.get("acked_by") or [])

    def required_authority_for(self, operation_intent: str) -> str:
        return required_authority(operation_intent)

    def effective_authority_for_tool(
        self,
        actor_id: str,
        tool_name: str,
        arguments: dict,
    ) -> tuple[str, dict | None]:
        base = self._actor_authority(actor_id)
        grant = self._matching_tool_grant(actor_id, tool_name, arguments)
        level = _max_level(base, grant["elevated_level"]) if grant else base
        return level, grant

    def consume_grant(self, grant_id: str) -> None:
        self._store.execute("UPDATE grants SET consumed = 1 WHERE grant_id = ?;", (grant_id,))

    # --- internals -----------------------------------------------------

    def _actor_authority(self, actor_id: str) -> str:
        # Check explicit authority record first.
        row = self._store.query_one(
            "SELECT base_level FROM authorities WHERE actor_id = ? "
            "AND (effective_until IS NULL OR effective_until > ?);",
            (actor_id, now_iso()),
        )
        if row:
            return row["base_level"]
        return _default_authority_for(actor_id)

    def _actor_type(self, actor_id: str) -> str:
        if actor_id.startswith("human:"):
            return "human"
        if actor_id.startswith("agent:"):
            return "agent"
        if actor_id.startswith("tool:"):
            return "tool"
        return "system"

    def _lookup_grant(self, envelope: "SidecarEnvelope", *, consume: bool = True) -> str | None:
        row = self._matching_grant_row(envelope.actor_id, envelope.operation_intent, envelope)
        if row is None:
            return None
        if consume and int(row["single_use"]) == 1:
            self.consume_grant(row["grant_id"])
        return row["elevated_level"]

    def _all_acks_for(self, contract_id: str, version: str) -> list[str]:
        rows = self._store.query(
            "SELECT DISTINCT actor_id FROM acknowledgments "
            "WHERE contract_id = ? AND contract_version = ?;",
            (contract_id, version),
        )
        return [r["actor_id"] for r in rows]

    def _matching_tool_grant(self, actor_id: str, tool_name: str, arguments: dict) -> dict | None:
        rows = self._store.query(
            """
            SELECT * FROM grants
            WHERE actor_id = ? AND operation_intent = 'tool_invoked' AND consumed = 0
            ORDER BY granted_at ASC;
            """,
            (actor_id,),
        )
        for row in rows:
            if row["expires_at"] and row["expires_at"] < now_iso():
                continue
            scope = _parse_scope_pattern(row["scope_pattern"])
            if scope and not _tool_scope_matches(scope, tool_name, arguments):
                continue
            return dict(row)
        return None

    def _matching_grant_row(self, actor_id: str, operation_intent: str, envelope: "SidecarEnvelope"):
        rows = self._store.query(
            """
            SELECT * FROM grants
            WHERE actor_id = ? AND operation_intent = ? AND consumed = 0
            ORDER BY granted_at ASC;
            """,
            (actor_id, operation_intent),
        )
        for row in rows:
            if row["expires_at"] and row["expires_at"] < now_iso():
                continue
            scope = _parse_scope_pattern(row["scope_pattern"])
            if scope and not self._scope_matches_envelope(scope, envelope):
                continue
            return row
        return None

    def _scope_matches_envelope(self, scope: dict, envelope: "SidecarEnvelope") -> bool:
        if envelope.operation_intent != "tool_invoked":
            return True
        if not envelope.payload_ref or self._state.blob_store is None:
            return False
        try:
            payload = self._state.blob_store.get_json(envelope.payload_ref)
        except Exception:
            return False
        tool_name = str(payload.get("tool_name", ""))
        arguments = payload.get("arguments") or {}
        return _tool_scope_matches(scope, tool_name, arguments)

    def _check_hard_block(self, unit, envelope: "SidecarEnvelope") -> str | None:
        """T1: hard-block constraints are advisory in this implementation.
        Specific enforcement (e.g., path containment for Apply) lives in
        the relevant managers/orchestrators when those land in T2+.
        Returning None = no violation detected at the gate.
        """
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_authority_for(actor_id: str) -> str:
    if actor_id.startswith("human:"):
        return DEFAULT_HUMAN_AUTHORITY
    if actor_id.startswith("agent:"):
        return DEFAULT_AGENT_AUTHORITY
    if actor_id.startswith("tool:"):
        return DEFAULT_TOOL_AUTHORITY
    return DEFAULT_SYSTEM_AUTHORITY


def _max_level(a: str, b: str) -> str:
    rank_a = AUTHORITY_LEVELS.index(a) if a in AUTHORITY_LEVELS else -1
    rank_b = AUTHORITY_LEVELS.index(b) if b in AUTHORITY_LEVELS else -1
    return AUTHORITY_LEVELS[max(rank_a, rank_b)] if max(rank_a, rank_b) >= 0 else a


def _parse_scope_pattern(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _tool_scope_matches(scope: dict, tool_name: str, arguments: dict) -> bool:
    requested_tool = str(scope.get("tool_name", "")).strip()
    if requested_tool and requested_tool != tool_name:
        return False

    requested_domain = str(scope.get("target_domain", "")).strip()
    if requested_domain:
        actual_domain = str(arguments.get("target_domain", "workspace")).strip()
        if requested_domain != actual_domain:
            return False

    requested_path = str(scope.get("path", "")).strip()
    if requested_path:
        actual_path = str(arguments.get("path", "")).replace("\\", "/")
        if requested_path.replace("\\", "/") != actual_path:
            return False

    requested_prefix = str(scope.get("path_prefix", "")).strip()
    if requested_prefix:
        actual_path = str(arguments.get("path", "")).replace("\\", "/")
        if not actual_path.startswith(requested_prefix.replace("\\", "/")):
            return False

    return True
