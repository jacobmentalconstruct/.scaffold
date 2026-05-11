"""
FILE: src/interfaces/cli_interface.py
ROLE: CLI dispatch. One-shot command execution by translating argv into envelopes.
WHAT IT DOES (T1): minimal subcommand surface for spine smoke testing:
                   ack-contract, status, projection, version.
                   Heavier operations (install, scan, journal_*) land in T2.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING

from src.core.envelope import SidecarEnvelope
from src.lib.common import safe_json_dumps
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.core.state import SidecarState


log = get_logger("interfaces.cli")


def dispatch(state: "SidecarState", argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return 2

    handler = _COMMANDS.get(args.command)
    if handler is None:
        sys.stderr.write(f"unknown command: {args.command}\n")
        return 2
    return handler(state, args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sidecar",
        description="Sidecar CLI (T1 surface — limited to spine verification).",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Print only the result envelope's status line.",
    )
    parser.add_argument(
        "--raw", action="store_true",
        help="Print the full envelope (not just the result surface).",
    )
    sub = parser.add_subparsers(dest="command")

    p_ack = sub.add_parser("ack-contract", help="Acknowledge the binding contract.")
    p_ack.add_argument("--actor", required=True, help="Actor id (e.g. human:jacob, agent:test).")

    sub.add_parser("status", help="Print the current sidecar state projection.")
    sub.add_parser("version", help="Print the sidecar version + sidecar_id.")

    p_proj = sub.add_parser("projection", help="Read a projection by name.")
    p_proj.add_argument("name", help="Projection name (e.g. contract_status).")

    sub.add_parser("list-projections", help="List registered projections.")

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_ack_contract(state, args) -> int:
    envelope = SidecarEnvelope.new(
        object_type="contract_ack",
        actor_id=args.actor,
        operation_intent="acknowledge_contract",
        contract_refs=[
            f"{(state.current_contract or {}).get('contract_id', '')}:"
            f"{(state.current_contract or {}).get('version', '')}"
        ],
    )
    result = state.router.dispatch(envelope)
    return _print_result(result, args)


def _cmd_status(state, args) -> int:
    snapshot = state.projections.read("current_sidecar_state")
    _print_json({
        "projection": "current_sidecar_state",
        "last_refreshed_at": snapshot.last_refreshed_at,
        "rows": snapshot.rows,
    })
    return 0


def _cmd_version(state, args) -> int:
    _print_json({
        "sidecar_id": state.sidecar_id,
        "sidecar_root": str(state.sidecar_root),
        "project_root": str(state.project_root),
        "schema_version": state.store.schema_version(),
        "current_contract": state.current_contract or {},
    })
    return 0


def _cmd_projection(state, args) -> int:
    try:
        result = state.projections.read(args.name)
    except KeyError as e:
        sys.stderr.write(f"unknown projection: {e}\n")
        return 2
    _print_json({
        "projection": result.name,
        "last_refreshed_at": result.last_refreshed_at,
        "rows": result.rows,
    })
    return 0


def _cmd_list_projections(state, args) -> int:
    _print_json({"projections": state.projections.list()})
    return 0


_COMMANDS = {
    "ack-contract": _cmd_ack_contract,
    "status": _cmd_status,
    "version": _cmd_version,
    "projection": _cmd_projection,
    "list-projections": _cmd_list_projections,
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_json(obj) -> None:
    sys.stdout.write(safe_json_dumps(obj, indent=2) + "\n")


def _print_result(envelope, args) -> int:
    if args.quiet:
        sys.stdout.write(f"{envelope.status}\n")
    elif args.raw:
        _print_json(envelope.to_dict())
    else:
        _print_json({
            "status": envelope.status,
            "event_id": envelope.event_id,
            "operation_intent": envelope.operation_intent,
            "actor_id": envelope.actor_id,
            "correlation_id": envelope.correlation_id,
        })
    return 0 if envelope.status in ("accepted", "completed") else 1
