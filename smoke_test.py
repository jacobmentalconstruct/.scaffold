"""
FILE: smoke_test.py
ROLE: Top-level portable verification — Tranche 1 spine.
WHAT IT DOES: Boots the sidecar, submits an acknowledge_contract envelope,
              verifies the event lands, the projection refreshes, the
              contract is now acked, and the gate now requires
              acknowledgment for non-bootstrap intents. Exits 0 on full pass.

USAGE:
    python smoke_test.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

# Allow `import src.*` regardless of where the test is invoked from.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _section(title: str) -> None:
    bar = "-" * 60
    print(f"\n{bar}\n{title}\n{bar}")


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def _fail(msg: str) -> str:
    print(f"  FAIL  {msg}")
    return msg


def main() -> int:
    failures: list[str] = []

    _section("0. Imports")
    try:
        from src.app import boot
        from src.core.envelope import SidecarEnvelope
        _ok("imported src.app + src.core.envelope")
    except Exception as e:
        traceback.print_exc()
        failures.append(f"import error: {e}")
        return 1

    _section("1. Boot the sidecar")
    try:
        state = boot()
        _ok(f"sidecar_id={state.sidecar_id}")
        _ok(f"sidecar_root={state.sidecar_root}")
        _ok(f"schema_version={state.store.schema_version()}")
    except Exception as e:
        traceback.print_exc()
        failures.append(f"boot failed: {e}")
        return 1

    _section("2. Constraint registry seeded")
    stats = state.constraint_manager.stats()
    if stats["constraint_count"] >= 12:
        _ok(f"constraint_count={stats['constraint_count']}")
    else:
        failures.append(_fail(f"constraint_count={stats['constraint_count']} (expected >= 12)"))
    if stats["profile_count"] >= 6:
        _ok(f"profile_count={stats['profile_count']}")
    else:
        failures.append(_fail(f"profile_count={stats['profile_count']} (expected >= 6)"))
    core_profile = state.constraint_manager.get_profile("core_implementation")
    if core_profile is not None and core_profile.constraint_uids:
        _ok(f"profile core_implementation has {len(core_profile.constraint_uids)} constraints")
    else:
        failures.append(_fail("profile core_implementation missing or empty"))

    _section("3. Contract loaded onto state")
    contract = state.current_contract or {}
    if contract.get("contract_id") and contract.get("text_hash"):
        _ok(f"contract_id={contract['contract_id']} v{contract.get('version')}")
        _ok(f"text_hash={contract['text_hash'][:16]}...")
    else:
        failures.append(_fail("contract not loaded onto state"))

    initial_acks = list(contract.get("acked_by") or [])

    _section("4. Reject non-bootstrap intent before acknowledgment")
    if not initial_acks:
        # We expect this to be rejected since no acknowledgment exists yet.
        try_envelope = SidecarEnvelope.new(
            object_type="journal_entry",
            actor_id="human:smoketest",
            operation_intent="create_journal_entry",
            payload_ref="",
        )
        result = state.router.dispatch(try_envelope)
        if result.status == "rejected":
            _ok(f"non-bootstrap intent rejected as expected (status={result.status})")
        else:
            failures.append(_fail(
                f"expected rejection of create_journal_entry pre-ack, got status={result.status}"
            ))
    else:
        _ok("acknowledgment already present from prior run; skipping pre-ack rejection check")

    _section("5. Submit acknowledge_contract envelope")
    actor_id = "human:smoketest"
    envelope = SidecarEnvelope.new(
        object_type="contract_ack",
        actor_id=actor_id,
        operation_intent="acknowledge_contract",
        contract_refs=[f"{contract.get('contract_id', '')}:{contract.get('version', '')}"],
    )
    result = state.router.dispatch(envelope)
    if result.status in ("accepted", "completed"):
        _ok(f"ack envelope status={result.status} event_id={result.event_id}")
    else:
        failures.append(_fail(f"ack envelope had status={result.status} (expected accepted/completed)"))

    _section("6. Event row recorded")
    persisted = state.events.read(result.event_id)
    if persisted is not None and persisted.operation_intent == "acknowledge_contract":
        _ok(f"event read back: {persisted.event_id}")
    else:
        failures.append(_fail("event row not found via EventStore.read()"))

    _section("7. Acknowledgment row recorded")
    rows = state.store.query(
        "SELECT actor_id, contract_id, event_id FROM acknowledgments WHERE actor_id = ?;",
        (actor_id,),
    )
    if rows:
        _ok(f"acknowledgments rows for {actor_id}: {len(rows)}")
        # All ack rows should have non-PENDING event_id after Router finalize.
        pending = [r for r in rows if r["event_id"] == "PENDING"]
        if not pending:
            _ok("all ack rows have real event_id (PENDING marker resolved)")
        else:
            failures.append(_fail(f"{len(pending)} ack rows still have event_id='PENDING'"))
    else:
        failures.append(_fail(f"no acknowledgments rows for actor {actor_id}"))

    _section("8. Contract status projection refreshed")
    contract_status = state.projections.read("contract_status")
    if contract_status.rows:
        row = contract_status.rows[0]
        acks = json.loads(row.get("acks_json") or "[]")
        if any(a.get("actor_id") == actor_id for a in acks):
            _ok(f"contract_status acks include {actor_id}")
        else:
            failures.append(_fail(f"contract_status.acks_json missing {actor_id}"))
        if row.get("last_refreshed_at"):
            _ok(f"last_refreshed_at={row['last_refreshed_at']}")
        else:
            failures.append(_fail("contract_status.last_refreshed_at missing"))
    else:
        failures.append(_fail("contract_status projection has no rows"))

    _section("9. Current sidecar state projection refreshed")
    cur = state.projections.read("current_sidecar_state")
    if cur.rows:
        row = cur.rows[0]
        if row.get("current_contract_acked"):
            _ok(f"current_contract_acked=1")
        else:
            failures.append(_fail("current_contract_acked is not truthy after ack"))
        if row.get("event_log_position", 0) >= 1:
            _ok(f"event_log_position={row['event_log_position']}")
        else:
            failures.append(_fail("event_log_position did not advance"))
    else:
        failures.append(_fail("current_sidecar_state projection has no rows"))

    _section("10. Post-ack: previously rejected intent now passes the gate (validation only)")
    # We don't have a handler for create_journal_entry yet (T2), so an UnrouteableEnvelope
    # is the EXPECTED outcome here -- which proves the gate now allows the intent through.
    from src.core.router import UnrouteableEnvelope
    test_env = SidecarEnvelope.new(
        object_type="journal_entry",
        actor_id=actor_id,
        operation_intent="create_journal_entry",
    )
    try:
        state.router.dispatch(test_env)
        failures.append(_fail("expected UnrouteableEnvelope after gate pass; got dispatch success"))
    except UnrouteableEnvelope:
        _ok("gate now allows create_journal_entry; UnrouteableEnvelope raised as expected (no T2 handler)")
    except Exception as e:
        failures.append(_fail(f"unexpected exception type: {type(e).__name__}: {e}"))

    _section("RESULT")
    if failures:
        print(f"\n  {len(failures)} FAILURE(S):")
        for f in failures:
            print(f"    - {f}")
        print("\nSMOKE TEST: FAIL")
        return 1
    print("\nSMOKE TEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
