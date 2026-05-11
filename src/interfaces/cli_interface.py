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

    # ---- journal -------------------------------------------------------
    p_write = sub.add_parser("journal-write", help="Create a journal entry.")
    p_write.add_argument("--actor", required=True, help="Actor id (e.g. human:jacob, agent:test).")
    p_write.add_argument("--kind", default="note", help="Entry kind: note|decision|todo|issue|tranche|...")
    p_write.add_argument("--title", required=True, help="Entry title.")
    p_write.add_argument("--body", help="Entry body (inline).")
    p_write.add_argument("--body-file", help="Path to a file whose contents become the body.")
    p_write.add_argument("--tags", help="Comma-separated tags.")
    p_write.add_argument("--importance", type=int, default=5, help="Importance 0..10.")
    p_write.add_argument("--related-path", help="Optional related file path.")
    p_write.add_argument("--related-ref", help="Optional related git ref / URL.")
    p_write.add_argument("--evidence-hash", action="append", default=[],
                        help="SHA-256 blob hash to attach as evidence (repeatable).")

    p_query = sub.add_parser("journal-query", help="Query journal entries.")
    p_query.add_argument("--kind", help="Filter by kind.")
    p_query.add_argument("--status", help="Filter by status.")
    p_query.add_argument("--min-importance", type=int, help="Filter by importance >= N.")
    p_query.add_argument("--limit", type=int, default=20, help="Max rows.")
    p_query.add_argument("--include-superseded", action="store_true",
                        help="Include entries that have been superseded.")

    p_show = sub.add_parser("journal-show", help="Show one journal entry by uid.")
    p_show.add_argument("entry_uid", help="Entry uid (e.g. journal_...).")

    # ---- install / scan ------------------------------------------------
    p_install = sub.add_parser(
        "install",
        help="Record an install event (idempotent; no-op if already installed).",
    )
    p_install.add_argument("--actor", default="human:cli", help="Actor id.")

    p_scan = sub.add_parser("scan", help="Scan the project tree and update project_index.")
    p_scan.add_argument("--actor", default="human:cli", help="Actor id.")

    sub.add_parser("scan-status", help="Show the latest scan record + project_index stats.")

    # ---- git observation ----------------------------------------------
    p_git = sub.add_parser("git-observe", help="Observe and record host git state.")
    p_git.add_argument("--actor", default="human:cli", help="Actor id.")

    sub.add_parser("git-status", help="Show the latest git observation record.")

    # ---- evidence -----------------------------------------------------
    p_ev = sub.add_parser("evidence-attach", help="Attach an evidence item.")
    p_ev.add_argument("--actor", required=True, help="Actor id.")
    p_ev.add_argument("--hash", required=True, help="SHA-256 blob hash (must exist in blob_store).")
    p_ev.add_argument("--kind", required=True, help="Evidence kind (file_excerpt|tool_output|...).")
    p_ev.add_argument("--summary", default="", help="One-line summary.")
    p_ev.add_argument("--attached-to", help="Object id this evidence is attached to.")
    p_ev.add_argument("--attached-to-type", help="Type of the attached object.")
    p_ev.add_argument("--source-path", help="Optional source path.")

    sub.add_parser("evidence-list", help="List recent evidence records.")

    # ---- tools --------------------------------------------------------
    sub.add_parser("tool-list", help="List registered tools.")
    p_call = sub.add_parser("tool-invoke", help="Invoke a registered tool.")
    p_call.add_argument("--actor", required=True, help="Actor id.")
    p_call.add_argument("--tool", required=True, help="Tool name.")
    p_call.add_argument("--input-json", help="Arguments as inline JSON.")
    p_call.add_argument("--input-file", help="Arguments as path to JSON file.")

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


def _cmd_journal_write(state, args) -> int:
    from pathlib import Path

    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif args.body:
        body = args.body
    else:
        sys.stderr.write("error: must provide --body or --body-file\n")
        return 2

    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    evidence_refs = [
        {"hash": h, "kind": "external"} for h in (args.evidence_hash or [])
    ]

    request = {
        "kind": args.kind,
        "title": args.title,
        "body": body,
        "tags": tags,
        "importance": args.importance,
        "related_path": args.related_path,
        "related_ref": args.related_ref,
    }
    payload_ref = state.blob_store.put_json(request)

    envelope = SidecarEnvelope.new(
        object_type="journal_entry",
        actor_id=args.actor,
        operation_intent="create_journal_entry",
        payload_ref=payload_ref,
        evidence_refs=evidence_refs,
    )
    result = state.router.dispatch(envelope)

    # Resolve response blob → entry_uid for human-readable output.
    response_data = {}
    if result.payload_ref:
        try:
            response_data = state.blob_store.get_json(result.payload_ref)
        except Exception:
            pass

    if args.quiet:
        sys.stdout.write(f"{result.status}\n")
    elif args.raw:
        _print_json(result.to_dict())
    else:
        _print_json({
            "status": result.status,
            "event_id": result.event_id,
            "entry_uid": response_data.get("entry_uid"),
            "title": response_data.get("title"),
            "kind": response_data.get("kind"),
        })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_journal_query(state, args) -> int:
    entries = state.journal_manager.query(
        kind=args.kind,
        status=args.status,
        min_importance=args.min_importance,
        limit=args.limit,
        include_superseded=args.include_superseded,
    )
    _print_json({
        "count": len(entries),
        "entries": [
            {
                "entry_uid": e.entry_uid,
                "kind": e.kind,
                "title": e.title,
                "status": e.status,
                "importance": e.importance,
                "created_at": e.created_at,
                "tags": e.tags,
                "event_id": e.event_id,
            }
            for e in entries
        ],
    })
    return 0


def _cmd_journal_show(state, args) -> int:
    entry = state.journal_manager.get(args.entry_uid)
    if entry is None:
        sys.stderr.write(f"no such entry: {args.entry_uid}\n")
        return 2
    _print_json({
        "entry_uid": entry.entry_uid,
        "kind": entry.kind,
        "source": entry.source,
        "author": entry.author,
        "status": entry.status,
        "importance": entry.importance,
        "title": entry.title,
        "body": entry.body,
        "body_hash": entry.body_hash,
        "tags": entry.tags,
        "related_path": entry.related_path,
        "related_ref": entry.related_ref,
        "metadata": entry.metadata,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "superseded_by": entry.superseded_by,
        "event_id": entry.event_id,
    })
    return 0


def _cmd_install(state, args) -> int:
    if state.install_orchestrator.is_installed():
        installed_at = state.store.get_meta("installed_at")
        _print_json({
            "status": "already_installed",
            "installed_at": installed_at,
            "sidecar_id": state.sidecar_id,
        })
        return 0
    envelope = SidecarEnvelope.new(
        object_type="sidecar_install",
        actor_id=args.actor,
        operation_intent="install",
    )
    result = state.router.dispatch(envelope)
    return _print_result(result, args)


def _cmd_scan(state, args) -> int:
    envelope = SidecarEnvelope.new(
        object_type="scan_request",
        actor_id=args.actor,
        operation_intent="scan",
    )
    result = state.router.dispatch(envelope)
    # Resolve summary blob for nice output.
    summary = {}
    if result.payload_ref:
        try:
            summary = state.blob_store.get_json(result.payload_ref)
        except Exception:
            pass
    if args.quiet:
        sys.stdout.write(f"{result.status}\n")
    elif args.raw:
        _print_json(result.to_dict())
    else:
        _print_json({
            "status": result.status,
            "event_id": result.event_id,
            "scan_id": summary.get("scan_id"),
            "file_count": summary.get("file_count"),
            "directory_count": summary.get("directory_count"),
            "added": summary.get("added"),
            "modified": summary.get("modified"),
            "unchanged": summary.get("unchanged"),
        })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_scan_status(state, args) -> int:
    latest = state.project_index_manager.latest_scan()
    stats = state.project_index_manager.stats()
    _print_json({
        "latest_scan": {
            "scan_id": latest.scan_id,
            "project_root": latest.project_root,
            "started_at": latest.started_at,
            "finished_at": latest.finished_at,
            "file_count": latest.file_count,
            "directory_count": latest.directory_count,
            "added_count": latest.added_count,
            "modified_count": latest.modified_count,
            "unchanged_count": latest.unchanged_count,
            "status": latest.status,
            "event_id": latest.event_id,
        } if latest else None,
        "index_stats": stats,
    })
    return 0


def _cmd_git_observe(state, args) -> int:
    envelope = SidecarEnvelope.new(
        object_type="git_observation",
        actor_id=args.actor,
        operation_intent="observe_git",
    )
    result = state.router.dispatch(envelope)
    summary = {}
    if result.payload_ref:
        try:
            summary = state.blob_store.get_json(result.payload_ref)
        except Exception:
            pass
    _print_json({
        "status": result.status,
        "event_id": result.event_id,
        "observation": summary,
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_git_status(state, args) -> int:
    obs = state.git_state_manager.latest()
    if obs is None:
        _print_json({"observation": None, "hint": "run 'git-observe' first"})
        return 0
    _print_json({
        "observation_id": obs.observation_id,
        "observed_at": obs.observed_at,
        "is_repo": obs.is_repo,
        "branch": obs.branch,
        "head_sha": obs.head_sha,
        "detached": obs.detached,
        "dirty_count": obs.dirty_count,
        "ahead": obs.ahead,
        "behind": obs.behind,
        "remote": obs.remote,
        "remote_url": obs.remote_url,
        "event_id": obs.event_id,
        "dirty_paths_sample": obs.dirty_paths[:10],
    })
    return 0


def _cmd_evidence_attach(state, args) -> int:
    request = {
        "hash": args.hash,
        "kind": args.kind,
        "summary": args.summary,
        "attached_to_object": args.attached_to,
        "attached_to_type": args.attached_to_type,
        "source_path": args.source_path,
    }
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="evidence",
        actor_id=args.actor,
        operation_intent="attach_evidence",
        payload_ref=payload_ref,
    )
    result = state.router.dispatch(envelope)
    response = {}
    if result.payload_ref:
        try:
            response = state.blob_store.get_json(result.payload_ref)
        except Exception:
            pass
    _print_json({
        "status": result.status,
        "event_id": result.event_id,
        "evidence_id": response.get("evidence_id"),
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_evidence_list(state, args) -> int:
    records = state.evidence_manager.recent(limit=50)
    _print_json({
        "count": len(records),
        "evidence": [
            {
                "evidence_id": r.evidence_id,
                "kind": r.kind,
                "summary": r.summary,
                "hash": r.hash[:16] + "...",
                "attached_to_object": r.attached_to_object,
                "status": r.status,
                "created_at": r.created_at,
            }
            for r in records
        ],
    })
    return 0


def _cmd_tool_list(state, args) -> int:
    tools = state.tool_registry_manager.list_tools()
    _print_json({
        "count": len(tools),
        "tools": [
            {
                "tool_name": t.tool_name,
                "version": t.version,
                "category": t.category,
                "mcp_name": t.mcp_name,
                "required_authority": t.required_authority,
                "summary": t.summary,
            }
            for t in sorted(tools, key=lambda x: (x.category, x.tool_name))
        ],
    })
    return 0


def _cmd_tool_invoke(state, args) -> int:
    from pathlib import Path

    if args.input_file:
        arguments = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    elif args.input_json:
        arguments = json.loads(args.input_json)
    else:
        arguments = {}

    request = {"tool_name": args.tool, "arguments": arguments}
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="tool_invocation",
        actor_id=args.actor,
        operation_intent="tool_invoked",
        payload_ref=payload_ref,
    )
    result = state.router.dispatch(envelope)
    response = {}
    if result.payload_ref:
        try:
            response = state.blob_store.get_json(result.payload_ref)
        except Exception:
            pass
    if args.raw:
        _print_json(response)
    else:
        _print_json({
            "status": result.status,
            "event_id": result.event_id,
            "tool": args.tool,
            "result": response.get("result") if isinstance(response, dict) else response,
        })
    return 0 if result.status in ("accepted", "completed") else 1


_COMMANDS = {
    "ack-contract": _cmd_ack_contract,
    "status": _cmd_status,
    "version": _cmd_version,
    "projection": _cmd_projection,
    "list-projections": _cmd_list_projections,
    "journal-write": _cmd_journal_write,
    "journal-query": _cmd_journal_query,
    "journal-show": _cmd_journal_show,
    "install": _cmd_install,
    "scan": _cmd_scan,
    "scan-status": _cmd_scan_status,
    "git-observe": _cmd_git_observe,
    "git-status": _cmd_git_status,
    "evidence-attach": _cmd_evidence_attach,
    "evidence-list": _cmd_evidence_list,
    "tool-list": _cmd_tool_list,
    "tool-invoke": _cmd_tool_invoke,
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
