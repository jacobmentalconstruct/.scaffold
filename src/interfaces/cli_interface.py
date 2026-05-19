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
from src.lib.common import public_root_labels, safe_json_dumps
from src.lib.bcc_constraint_map import refresh_bcc_constraint_map
from src.lib.logging_setup import get_logger
from src.lib.public_export_sanitizer import (
    audit_public_share_surfaces,
    build_public_share_bundle,
    write_public_share_bundle,
)
from src.lib.ui_launcher import launch_monitor
from src.orchestrators.closeout_orchestrator import (
    derive_closeout_metadata,
    write_closeout_metadata_files,
)


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

    p_ar = sub.add_parser("approval-request", help="Submit an authority elevation request.")
    p_ar.add_argument("--actor", required=True, help="Actor id.")
    p_ar.add_argument("--requested-level", required=True, help="Sandbox Execute|Apply|Export")
    p_ar.add_argument("--operation-intent", default="tool_invoked", help="Intent the grant should cover.")
    p_ar.add_argument("--summary", required=True, help="Short human-facing summary.")
    p_ar.add_argument("--justification", required=True, help="Why this needs elevation.")
    p_ar.add_argument("--scope-json", default="{}", help="Scope pattern JSON, e.g. {\"tool_name\":\"text_file_writer\",\"path\":\"t4/foo.txt\"}")
    p_ar.add_argument("--source-channel", default="cli", help="Source channel label.")

    p_al = sub.add_parser("approval-list", help="List approval requests.")
    p_al.add_argument("--all", action="store_true", help="Show approved/rejected requests too.")

    p_aa = sub.add_parser("approval-approve", help="Approve a pending authority request.")
    p_aa.add_argument("--actor", required=True, help="Human actor id.")
    p_aa.add_argument("--request-id", required=True, help="Approval request id.")
    p_aa.add_argument("--expires-minutes", type=int, default=60, help="Grant lifetime in minutes.")
    p_aa.add_argument("--single-use", action="store_true", help="Issue a single-use grant (recommended).")
    p_aa.add_argument("--decision-reason", default="", help="Optional approval note.")

    p_arj = sub.add_parser("approval-reject", help="Reject a pending authority request.")
    p_arj.add_argument("--actor", required=True, help="Human actor id.")
    p_arj.add_argument("--request-id", required=True, help="Approval request id.")
    p_arj.add_argument("--decision-reason", default="", help="Optional rejection reason.")

    sub.add_parser("session-list", help="List recent agent sessions.")

    # ---- local sidecar agent runtime ----------------------------------
    p_las = sub.add_parser("local-agent-status", help="Show current local-agent runtime status.")
    p_las.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL.")

    p_lam = sub.add_parser("local-agent-models", help="List locally available Ollama models.")
    p_lam.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL.")

    p_lap = sub.add_parser("local-agent-preflight", help="Check local-agent prerequisites.")
    p_lap.add_argument("--actor", default="agent:local:ollama", help="Agent actor id.")
    p_lap.add_argument("--model", default="qwen3.5:9b", help="Ollama model name.")
    p_lap.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL.")

    p_lar = sub.add_parser("local-agent-run", help="Run the local sidecar agent floor.")
    p_lar.add_argument("--actor", default="agent:local:ollama", help="Agent actor id.")
    p_lar.add_argument("--model", default="qwen3.5:9b", help="Ollama model name.")
    p_lar.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL.")
    p_lar.add_argument("--prompt", help="Task prompt for the local agent.")
    p_lar.add_argument("--prompt-file", help="Path to a text/markdown file whose contents become the prompt.")
    p_lar.add_argument("--max-rounds", type=int, default=4, help="Maximum local agent rounds (1..8).")
    p_lar.add_argument("--mock-response", action="append", default=[],
                       help="Deterministic mock model response JSON/string (repeatable).")
    p_lar.add_argument("--mock-failure", default="",
                       help="Deterministic failure label for smoke tests (e.g. ollama_unreachable).")
    p_lar.add_argument("--no-ui", action="store_true",
                       help="Do not auto-launch the Tk monitor for this local-agent run.")

    p_lastop = sub.add_parser("local-agent-stop", help="Request a cooperative stop for the local sidecar agent.")
    p_lastop.add_argument("--actor", default="", help="Agent actor id to stop.")
    p_lastop.add_argument("--session-id", default="", help="Specific session id to stop.")
    p_larl = sub.add_parser("local-agent-run-list", help="List recent traced local-agent runs.")
    p_larl.add_argument("--limit", type=int, default=20, help="Max runs to return.")
    p_lars = sub.add_parser("local-agent-run-show", help="Show one traced local-agent run.")
    p_lars.add_argument("--run-id", required=True, help="Run id.")
    p_lare = sub.add_parser("local-agent-run-events", help="Show runtime events for one traced run.")
    p_lare.add_argument("--run-id", required=True, help="Run id.")
    p_lare.add_argument("--limit", type=int, default=200, help="Max events to return.")
    sub.add_parser("local-agent-recovery-summary", help="Show recent classified local-agent failures/stops.")
    p_larr = sub.add_parser("local-agent-run-retry", help="Retry a retryable local-agent run from its captured snapshot.")
    p_larr.add_argument("--run-id", required=True, help="Run id to retry.")

    # ---- teaching sandbox / training runway --------------------------
    sub.add_parser("training-scenario-list", help="List tracked T8 teaching scenarios.")
    p_tss = sub.add_parser("training-scenario-show", help="Show one tracked teaching scenario.")
    p_tss.add_argument("--scenario-id", required=True, help="Scenario id.")
    p_tsc = sub.add_parser("training-sandbox-create", help="Create or reset a disposable teaching sandbox.")
    p_tsc.add_argument("--scenario-id", required=True, help="Scenario id.")
    p_tsc.add_argument("--reset", action="store_true", help="Reset the sandbox before materializing the scenario.")
    p_trs = sub.add_parser("training-run-scenario", help="Run a teaching scenario in mocked or live mode.")
    p_trs.add_argument("--scenario-id", required=True, help="Scenario id.")
    p_trs.add_argument("--mode", default="mocked", choices=["mocked", "live"], help="Run mode.")
    p_trs.add_argument("--variant", default="good", help="Mocked variant id (for mocked mode).")
    p_trs.add_argument("--model", default="qwen3.5:9b", help="Ollama model name for live mode.")
    p_trs.add_argument("--base-url", default="http://localhost:11434", help="Ollama base URL.")
    p_trs.add_argument("--max-rounds", type=int, default=6, help="Maximum rounds.")
    p_tsv = sub.add_parser("training-verify", help="Re-run deterministic verification for one scenario run.")
    p_tsv.add_argument("--scenario-run-id", required=True, help="Scenario run id.")
    p_tsscore = sub.add_parser("training-scorecard-show", help="Show one training scorecard.")
    p_tsscore.add_argument("--scorecard-id", default="", help="Scorecard id.")
    p_tsscore.add_argument("--scenario-run-id", default="", help="Scenario run id.")
    p_tsexport = sub.add_parser("training-review-export", help="Export a compact reviewer packet for one scenario run.")
    p_tsexport.add_argument("--scenario-run-id", required=True, help="Scenario run id.")
    p_tscompare = sub.add_parser("training-compare-runs", help="Compare a small set of training scenario runs.")
    p_tscompare.add_argument("--scenario-run-id", action="append", default=[], help="Scenario run id (repeatable).")

    # ---- installed-project proof / vendability -----------------------
    p_ipc = sub.add_parser("installed-proof-create", help="Create or reset the tiny installed-project proof fixture.")
    p_ipc.add_argument("--reset", action="store_true", help="Reset the proof fixture before creating it.")
    sub.add_parser("installed-proof-run", help="Run the full installed-project vendability proof.")
    p_ipv = sub.add_parser("installed-proof-verify", help="Verify the latest or selected installed-project proof.")
    p_ipv.add_argument("--proof-run-id", default="", help="Proof run id.")
    p_ips = sub.add_parser("installed-proof-show", help="Show the latest or selected installed-project proof.")
    p_ips.add_argument("--proof-run-id", default="", help="Proof run id.")
    p_ipe = sub.add_parser("installed-proof-export", help="Export the installed-project proof handoff packet.")
    p_ipe.add_argument("--proof-run-id", default="", help="Proof run id.")

    p_cms = sub.add_parser("closeout-metadata-show", help="Show derived closeout metadata for the latest or selected closed tranche.")
    p_cms.add_argument("--journal-entry-uid", default="", help="Closed tranche journal entry uid.")
    p_cmsync = sub.add_parser("closeout-metadata-sync", help="Write generated closeout metadata files for the latest or selected closed tranche.")
    p_cmsync.add_argument("--journal-entry-uid", default="", help="Closed tranche journal entry uid.")
    sub.add_parser("contract-constraint-map-refresh", help="Recompile and persist the derived BCC constraint map.")
    sub.add_parser("public-export-preview", help="Preview a derived public-safe export bundle.")
    sub.add_parser("public-export-write", help="Write a derived public-safe export bundle under exports/public_share/.")
    sub.add_parser("public-export-audit", help="Audit selected shareable surfaces and the public bundle for unsafe path leakage.")

    # ---- tranche ledger (T2.5) ----------------------------------------
    p_td = sub.add_parser("tranche-declare", help="Declare a new active tranche.")
    p_td.add_argument("--actor", required=True, help="Actor id.")
    p_td.add_argument("--title", required=True, help="Tranche title (e.g. 'T3 Tk UI').")
    p_td.add_argument("--scope", default="", help="Declared scope summary.")
    p_td.add_argument("--non-goals", default="", help="What this tranche will NOT do.")
    p_td.add_argument("--completion-criteria", default="", help="What 'done' means.")
    p_td.add_argument("--next", default="", dest="next_tranche",
                      help="Name of the next planned tranche.")

    sub.add_parser("tranche-status", help="Show current active tranche + checklist.")

    p_tu = sub.add_parser("tranche-update", help="Append data to the active tranche ledger.")
    p_tu.add_argument("--actor", required=True, help="Actor id.")
    p_tu.add_argument("--file", action="append", default=[],
                      help="File changed: 'path:change_type' e.g. src/foo.py:modified (repeatable).")
    p_tu.add_argument("--deviation", action="append", default=[],
                      help="Scope deviation: 'description|reason' (repeatable).")
    p_tu.add_argument("--question", action="append", default=[],
                      help="Open question to carry forward (repeatable).")

    p_tc = sub.add_parser("tranche-close", help="Run the Park Phase closeout.")
    p_tc.add_argument("--actor", required=True, help="Actor id.")
    p_tc.add_argument("--dry-run", action="store_true",
                      help="Compile notes + validate but don't write files.")
    p_tc.add_argument("--skip-smoke-check", action="store_true",
                      help="Skip the smoke-test-passed gate (use when smoke runs separately).")
    p_tc.add_argument("--extra-notes", default="", help="Freeform text appended to park notes.")
    p_tc.add_argument("--with-ollama", action="store_true",
                      help="Use a local Ollama model to generate prose park notes "
                           "(falls back to template compiler if model unavailable).")
    p_tc.add_argument("--ollama-model", default="qwen3.5:9b",
                      help="Ollama model name (default: qwen3.5:9b). "
                           "Only used when --with-ollama is set.")
    p_tc.add_argument("--ollama-num-predict", type=int, default=8192,
                      help="Max tokens the model may generate (default: 8192). "
                           "Lower values reduce GPU memory pressure.")

    p_trr = sub.add_parser("tranche-review-request", help="Generate the mechanical review packet and move the tranche to review_pending.")
    p_trr.add_argument("--actor", required=True, help="Actor id.")

    p_trshow = sub.add_parser("tranche-review-show", help="Show the latest tranche review packet for the current open tranche.")
    p_trshow.add_argument("--review-id", default="", help="Optional review id.")

    p_trret = sub.add_parser("tranche-review-return", help="Return a pending tranche review to the agent and reopen the same tranche.")
    p_trret.add_argument("--actor", required=True, help="Human actor id.")
    p_trret.add_argument("--review-id", default="", help="Optional review id.")
    p_trret.add_argument("--reason", required=True, help="Return reason / feedback for the agent.")

    p_trapp = sub.add_parser("tranche-review-approve", help="Approve a pending tranche review and immediately run Park Phase closeout.")
    p_trapp.add_argument("--actor", required=True, help="Human actor id.")
    p_trapp.add_argument("--review-id", default="", help="Optional review id.")
    p_trapp.add_argument("--approval-notes", default="", help="Optional human approval notes.")
    p_trapp.add_argument("--skip-smoke-check", action="store_true",
                         help="Skip the smoke-test-passed gate while closing.")
    p_trapp.add_argument("--extra-notes", default="", help="Freeform text appended to park notes.")
    p_trapp.add_argument("--with-ollama", action="store_true",
                         help="Use a local Ollama model to generate prose park notes during close.")
    p_trapp.add_argument("--ollama-model", default="qwen3.5:9b",
                         help="Ollama model name (default: qwen3.5:9b).")
    p_trapp.add_argument("--ollama-num-predict", type=int, default=8192,
                         help="Max tokens the model may generate (default: 8192).")

    p_tsp = sub.add_parser("tranche-smoke-pass", help="Record a smoke test PASS for the active tranche.")
    p_tsp.add_argument("--actor", required=True, help="Actor id.")
    p_tsp.add_argument("--test-name", default="smoke_test.py", help="Test name.")
    p_tsp.add_argument("--details", default="", help="Optional details.")

    p_dr = sub.add_parser("decision-record", help="Record a typed decision.")
    p_dr.add_argument("--actor", required=True, help="Actor id.")
    p_dr.add_argument("--title", required=True, help="Decision title (the choice made).")
    p_dr.add_argument("--context", default="", help="What problem were we solving?")
    p_dr.add_argument("--rationale", default="", help="Why this choice?")
    p_dr.add_argument("--outcome", default="", help="What exactly did we decide?")
    p_dr.add_argument("--area", default="", dest="impact_area",
                      help="Impact area: schema|architecture|tools|process|...")
    p_dr.add_argument("--importance", type=int, default=5, help="Importance 0–10.")
    p_dr.add_argument("--tags", default="", help="Comma-separated tags.")

    sub.add_parser("decision-list", help="List decisions recorded for the active tranche.")

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
    project_root_label, sidecar_root_label = public_root_labels(
        state.sidecar_root, state.project_root
    )
    _print_json({
        "sidecar_id": state.sidecar_id,
        "sidecar_root": sidecar_root_label,
        "project_root": project_root_label,
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


def _cmd_approval_request(state, args) -> int:
    request = {
        "requested_level": args.requested_level,
        "operation_intent": args.operation_intent,
        "summary": args.summary,
        "justification": args.justification,
        "scope_pattern": json.loads(args.scope_json or "{}"),
        "source_channel": args.source_channel,
    }
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="authority_request",
        actor_id=args.actor,
        operation_intent="request_authority_elevation",
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
        "request_id": response.get("request_id"),
        "requested_level": response.get("requested_level"),
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_approval_list(state, args) -> int:
    requests = (
        state.human_approval_manager.recent(limit=100)
        if args.all
        else state.human_approval_manager.pending(limit=100)
    )
    _print_json({
        "count": len(requests),
        "requests": [
            {
                "request_id": record.request_id,
                "actor_id": record.actor_id,
                "requested_level": record.requested_level,
                "operation_intent": record.operation_intent,
                "summary": record.summary,
                "status": record.status,
                "requested_at": record.requested_at,
                "decided_at": record.decided_at,
                "decided_by": record.decided_by,
                "grant_id": record.grant_id,
                "scope_pattern": record.scope_pattern,
            }
            for record in requests
        ],
    })
    return 0


def _cmd_approval_approve(state, args) -> int:
    request = {
        "request_id": args.request_id,
        "expires_minutes": args.expires_minutes,
        "single_use": True if args.single_use else True,
        "decision_reason": args.decision_reason,
    }
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="authority_grant",
        actor_id=args.actor,
        operation_intent="approve_authority_request",
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
        "request_id": response.get("request_id"),
        "grant_id": response.get("grant_id"),
        "expires_at": response.get("expires_at"),
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_approval_reject(state, args) -> int:
    request = {
        "request_id": args.request_id,
        "decision_reason": args.decision_reason,
    }
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="authority_grant",
        actor_id=args.actor,
        operation_intent="reject_authority_request",
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
        "request_id": response.get("request_id"),
        "decision_reason": response.get("decision_reason"),
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_session_list(state, args) -> int:
    sessions = state.agent_session_manager.list_recent(limit=50)
    _print_json({
        "count": len(sessions),
        "sessions": [
            {
                "session_id": session.session_id,
                "actor_id": session.actor_id,
                "channel": session.channel,
                "client_name": session.client_name,
                "authority_level": session.authority_level,
                "started_at": session.started_at,
                "last_seen_at": session.last_seen_at,
            }
            for session in sessions
        ],
    })
    return 0


def _cmd_local_agent_status(state, args) -> int:
    status = state.local_agent_runtime.status()
    status["preflight"] = state.local_agent_runtime.preflight(
        base_url=args.base_url,
        model=(state.agent_status or {}).get("model", "qwen3.5:9b"),
        actor_id=(state.agent_status or {}).get("actor_id", "agent:local:ollama"),
    )
    _print_json(status)
    return 0


def _cmd_local_agent_models(state, args) -> int:
    _print_json(state.local_agent_runtime.list_models(base_url=args.base_url))
    return 0


def _cmd_local_agent_preflight(state, args) -> int:
    _print_json(
        state.local_agent_runtime.preflight(
            actor_id=args.actor,
            model=args.model,
            base_url=args.base_url,
        )
    )
    return 0


def _cmd_local_agent_run(state, args) -> int:
    from pathlib import Path

    prompt = ""
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    elif args.prompt:
        prompt = args.prompt
    else:
        sys.stderr.write("error: provide --prompt or --prompt-file\n")
        return 2

    if not args.no_ui:
        launch_monitor(state.sidecar_root)

    result = state.local_agent_runtime.run(
        prompt=prompt,
        actor_id=args.actor,
        model=args.model,
        base_url=args.base_url,
        max_rounds=args.max_rounds,
        mock_responses=args.mock_response or [],
        mock_failure=args.mock_failure or "",
    )
    _print_json(result)
    return 0 if result.get("status") in {"completed", "awaiting_approval", "ok"} else 1


def _cmd_local_agent_stop(state, args) -> int:
    if not (args.actor or args.session_id):
        sys.stderr.write("error: provide --actor or --session-id\n")
        return 2
    _print_json(
        state.local_agent_runtime.request_stop(
            actor_id=args.actor or "",
            session_id=args.session_id or "",
        )
    )
    return 0


def _cmd_local_agent_run_list(state, args) -> int:
    runs = state.run_trace_manager.list_runs(limit=args.limit) if getattr(state, "run_trace_manager", None) else []
    _print_json({"count": len(runs), "runs": [_run_to_dict(run) for run in runs]})
    return 0


def _cmd_local_agent_run_show(state, args) -> int:
    manager = getattr(state, "run_trace_manager", None)
    if manager is None:
        _print_json({"error": "run_trace_manager unavailable"})
        return 1
    run = manager.get_run(args.run_id)
    if run is None:
        sys.stderr.write(f"no such run: {args.run_id}\n")
        return 2
    _print_json(
        {
            "run": _run_to_dict(run),
            "rounds": manager.get_run_rounds(args.run_id),
            "touched_paths": manager.get_run_touched_paths(args.run_id),
            "links": manager.get_run_links(args.run_id),
            "grounding": manager.get_run_grounding(args.run_id),
        }
    )
    return 0


def _cmd_local_agent_run_events(state, args) -> int:
    manager = getattr(state, "run_trace_manager", None)
    if manager is None:
        _print_json({"error": "run_trace_manager unavailable"})
        return 1
    _print_json({"run_id": args.run_id, "events": manager.get_run_events(args.run_id, limit=args.limit)})
    return 0


def _cmd_local_agent_recovery_summary(state, args) -> int:
    manager = getattr(state, "run_trace_manager", None)
    if manager is None:
        _print_json({"error": "run_trace_manager unavailable"})
        return 1
    _print_json({"recoveries": manager.recovery_summary(limit=20)})
    return 0


def _cmd_local_agent_run_retry(state, args) -> int:
    result = state.local_agent_runtime.retry_run(args.run_id)
    _print_json(result)
    return 0 if result.get("status") in {"completed", "awaiting_approval", "ok"} else 1


def _cmd_training_scenario_list(state, args) -> int:
    _print_json({"scenarios": state.training_runway_manager.list_scenarios()})
    return 0


def _cmd_training_scenario_show(state, args) -> int:
    _print_json(state.training_runway_manager.get_scenario(args.scenario_id))
    return 0


def _cmd_training_sandbox_create(state, args) -> int:
    _print_json(state.training_runway_manager.create_sandbox(args.scenario_id, reset=bool(args.reset)))
    return 0


def _cmd_training_run_scenario(state, args) -> int:
    result = state.training_runway_manager.run_scenario(
        args.scenario_id,
        run_mode=args.mode,
        mock_variant=args.variant,
        model=args.model,
        base_url=args.base_url,
        max_rounds=args.max_rounds,
    )
    _print_json(result)
    scorecard = result.get("scorecard", {})
    return 0 if scorecard.get("aggregate_result") in {"pass", "partial"} else 1


def _cmd_training_verify(state, args) -> int:
    _print_json(state.training_runway_manager.verify_scenario_run(args.scenario_run_id))
    return 0


def _cmd_training_scorecard_show(state, args) -> int:
    _print_json(state.training_runway_manager.get_scorecard(scorecard_id=args.scorecard_id, scenario_run_id=args.scenario_run_id))
    return 0


def _cmd_training_review_export(state, args) -> int:
    _print_json(state.training_runway_manager.export_review(scenario_run_id=args.scenario_run_id))
    return 0


def _cmd_training_compare_runs(state, args) -> int:
    _print_json(state.training_runway_manager.compare_runs(args.scenario_run_id))
    return 0


def _cmd_installed_proof_create(state, args) -> int:
    _print_json(state.installed_project_proof_manager.create_fixture(reset=bool(args.reset)))
    return 0


def _cmd_installed_proof_run(state, args) -> int:
    result = state.installed_project_proof_manager.run_proof()
    _print_json(result)
    return 0 if result.get("status") == "ok" else 1


def _cmd_installed_proof_verify(state, args) -> int:
    result = state.installed_project_proof_manager.verify_proof(proof_run_id=args.proof_run_id or "")
    _print_json(result)
    return 0 if result.get("ok") else 1


def _cmd_installed_proof_show(state, args) -> int:
    _print_json(state.installed_project_proof_manager.get_proof(proof_run_id=args.proof_run_id or ""))
    return 0


def _cmd_installed_proof_export(state, args) -> int:
    result = state.installed_project_proof_manager.export_handoff_packet(proof_run_id=args.proof_run_id or "")
    _print_json(result)
    return 0 if result.get("status") == "ok" else 1


def _cmd_closeout_metadata_show(state, args) -> int:
    _print_json(derive_closeout_metadata(state, args.journal_entry_uid or ""))
    return 0


def _cmd_closeout_metadata_sync(state, args) -> int:
    metadata = derive_closeout_metadata(state, args.journal_entry_uid or "")
    _print_json(write_closeout_metadata_files(state, metadata))
    return 0


def _cmd_contract_constraint_map_refresh(state, args) -> int:
    record = refresh_bcc_constraint_map(state)
    state.projections.refresh("bcc_constraint_map")
    state.projections.refresh("agent_bootstrap")
    _print_json(
        {
            "map_id": record.map_id,
            "source_contract_path": record.source_contract_path,
            "source_contract_hash": record.source_contract_hash,
            "compiler_version": record.compiler_version,
            "generated_at": record.generated_at,
            "summary": record.summary,
        }
    )
    return 0


def _cmd_public_export_preview(state, args) -> int:
    _print_json(build_public_share_bundle(state))
    return 0


def _cmd_public_export_write(state, args) -> int:
    result = write_public_share_bundle(state)
    _print_json(result)
    return 0 if result.get("status") == "ok" else 1


def _cmd_public_export_audit(state, args) -> int:
    result = audit_public_share_surfaces(state)
    _print_json(result)
    return 0 if result.get("safe_to_share") else 1


def _cmd_tranche_declare(state, args) -> int:
    request = {
        "title": args.title,
        "scope": args.scope,
        "non_goals": args.non_goals,
        "completion_criteria": args.completion_criteria,
        "next_tranche_candidate": args.next_tranche or None,
    }
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="tranche",
        actor_id=args.actor,
        operation_intent="declare_tranche",
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
        "tranche_id": response.get("tranche_id"),
        "title": response.get("title"),
        "started_at": response.get("started_at"),
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_tranche_status(state, args) -> int:
    tranche = state.tranche_manager.get_current()
    checklist = state.tranche_manager.build_checklist(state)
    latest_review = state.tranche_manager.get_latest_review(tranche.tranche_id) if tranche else None
    _print_json({
        "current_tranche": {
            "tranche_id": tranche.tranche_id,
            "title": tranche.title,
            "status": tranche.status,
            "started_at": tranche.started_at,
            "decisions_count": tranche.decisions_count,
            "files_changed_count": len(tranche.files_changed),
            "tests_run_count": len(tranche.tests_run),
            "scope_preview": tranche.declared_scope[:120],
            "current_review_id": tranche.current_review_id,
            "last_review_status": tranche.last_review_status,
        } if tranche else None,
        "latest_review": _review_to_dict(latest_review) if latest_review else None,
        "checklist": [
            {
                "item_id": c.item_id,
                "status": c.status,
                "required": c.required,
                "label": c.label,
                "detail": c.detail,
            }
            for c in checklist
        ],
        "ready_to_close": all(
            c.status == "pass"
            for c in checklist
            if c.required and c.item_id not in ("park_notes_written", "journal_entry_closed")
        ),
    })
    return 0


def _cmd_tranche_review_request(state, args) -> int:
    envelope = SidecarEnvelope.new(
        object_type="tranche_review",
        actor_id=args.actor,
        operation_intent="request_tranche_review",
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
        "review": response,
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_tranche_review_show(state, args) -> int:
    tranche = state.tranche_manager.get_current()
    review = None
    history = []
    if tranche:
        history = [_review_to_dict(item) for item in state.tranche_manager.list_reviews(tranche.tranche_id, limit=10)]
        if args.review_id:
            review = next((item for item in history if item.get("review_id") == args.review_id), None)
        else:
            latest = state.tranche_manager.get_latest_review(tranche.tranche_id)
            review = _review_to_dict(latest) if latest else None
    packet_json = {}
    packet_markdown = ""
    if review:
        try:
            packet_json = state.blob_store.get_json(review.get("review_packet_json_ref", ""))
        except Exception:
            packet_json = {}
        try:
            packet_markdown = state.blob_store.get_text(review.get("review_packet_markdown_ref", ""))
        except Exception:
            packet_markdown = ""
    _print_json({
        "current_tranche": {
            "tranche_id": tranche.tranche_id,
            "title": tranche.title,
            "status": tranche.status,
            "current_review_id": tranche.current_review_id,
        } if tranche else None,
        "latest_review": review,
        "packet_json": packet_json,
        "packet_markdown": packet_markdown,
        "history": history,
    })
    return 0


def _cmd_tranche_review_return(state, args) -> int:
    payload_ref = state.blob_store.put_json(
        {
            "review_id": args.review_id or "",
            "return_reason": args.reason,
        }
    )
    envelope = SidecarEnvelope.new(
        object_type="tranche_review",
        actor_id=args.actor,
        operation_intent="return_tranche_review",
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
        "review": response,
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_tranche_review_approve(state, args) -> int:
    approve_payload_ref = state.blob_store.put_json(
        {
            "review_id": args.review_id or "",
            "approval_notes": args.approval_notes,
        }
    )
    approve_env = SidecarEnvelope.new(
        object_type="tranche_review",
        actor_id=args.actor,
        operation_intent="approve_tranche_review",
        payload_ref=approve_payload_ref,
    )
    approve_result = state.router.dispatch(approve_env)
    approve_response = {}
    if approve_result.payload_ref:
        try:
            approve_response = state.blob_store.get_json(approve_result.payload_ref)
        except Exception:
            pass
    if approve_result.status not in ("accepted", "completed"):
        _print_json({"status": approve_result.status, "approval": approve_response})
        return 1

    close_payload_ref = state.blob_store.put_json(
        {
            "skip_smoke_check": bool(args.skip_smoke_check),
            "extra_notes": args.extra_notes,
            "use_ollama": bool(getattr(args, "with_ollama", False)),
            "ollama_model": getattr(args, "ollama_model", "qwen3.5:9b"),
            "ollama_num_predict": getattr(args, "ollama_num_predict", 8192),
        }
    )
    close_env = SidecarEnvelope.new(
        object_type="tranche",
        actor_id=args.actor,
        operation_intent="close_tranche",
        payload_ref=close_payload_ref,
    )
    close_result = state.router.dispatch(close_env)
    close_response = {}
    if close_result.payload_ref:
        try:
            close_response = state.blob_store.get_json(close_result.payload_ref)
        except Exception:
            pass
    _print_json(
        {
            "approval": {
                "status": approve_result.status,
                "response": approve_response,
            },
            "closeout": {
                "status": close_result.status,
                "response": close_response,
            },
        }
    )
    return 0 if close_result.status in ("accepted", "completed") else 1


def _cmd_tranche_update(state, args) -> int:
    from src.lib.common import now_iso
    request: dict = {}

    if args.file:
        files_changed = []
        for f in args.file:
            if ":" in f:
                path, change_type = f.split(":", 1)
            else:
                path, change_type = f, "modified"
            files_changed.append({"path": path.strip(), "change_type": change_type.strip()})
        request["files_changed"] = files_changed

    if args.deviation:
        deviations = []
        for d in args.deviation:
            parts = d.split("|", 1)
            desc = parts[0].strip()
            reason = parts[1].strip() if len(parts) > 1 else ""
            deviations.append({"description": desc, "reason": reason})
        request["deviations"] = deviations

    if args.question:
        now = now_iso()
        request["open_questions"] = [
            {"question": q.strip(), "raised_at": now} for q in args.question
        ]

    if not request:
        sys.stderr.write("error: provide at least --file, --deviation, or --question\n")
        return 2

    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="tranche",
        actor_id=args.actor,
        operation_intent="update_tranche",
        payload_ref=payload_ref,
    )
    result = state.router.dispatch(envelope)
    return _print_result(result, args)


def _cmd_tranche_close(state, args) -> int:
    request = {
        "dry_run": args.dry_run,
        "skip_smoke_check": args.skip_smoke_check,
        "extra_notes": args.extra_notes,
        "use_ollama": getattr(args, "with_ollama", False),
        "ollama_model": getattr(args, "ollama_model", "qwen3.5:9b"),
        "ollama_num_predict": getattr(args, "ollama_num_predict", 8192),
    }
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="tranche",
        actor_id=args.actor,
        operation_intent="close_tranche",
        payload_ref=payload_ref,
    )
    result = state.router.dispatch(envelope)
    response = {}
    if result.payload_ref:
        try:
            response = state.blob_store.get_json(result.payload_ref)
        except Exception:
            pass
    if args.quiet:
        sys.stdout.write(f"{result.status}\n")
    else:
        _print_json({
            "status": result.status,
            "title": response.get("title"),
            "park_notes_path": response.get("park_notes_path"),
            "park_notes_blob_ref": response.get("park_notes_blob_ref"),
            "journal_entry_uid": response.get("journal_entry_uid"),
            "decisions_count": response.get("decisions_count"),
            "files_changed_count": response.get("files_changed_count"),
            "checklist_pass_count": response.get("checklist_pass_count"),
            "checklist_total": response.get("checklist_total"),
            "dry_run": response.get("dry_run", False),
        })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_tranche_smoke_pass(state, args) -> int:
    request = {
        "test_name": args.test_name,
        "passed": True,
        "details": args.details,
    }
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="smoke_test",
        actor_id=args.actor,
        operation_intent="smoke_pass",
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
        "tranche_id": response.get("tranche_id"),
        "test_name": response.get("test_name"),
        "passed": response.get("passed"),
        "ran_at": response.get("ran_at"),
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_decision_record(state, args) -> int:
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    request = {
        "title": args.title,
        "context": args.context,
        "rationale": args.rationale,
        "outcome": args.outcome,
        "impact_area": args.impact_area,
        "importance": args.importance,
        "tags": tags,
    }
    payload_ref = state.blob_store.put_json(request)
    envelope = SidecarEnvelope.new(
        object_type="decision",
        actor_id=args.actor,
        operation_intent="record_decision",
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
        "decision_id": response.get("decision_id"),
        "tranche_id": response.get("tranche_id"),
        "title": response.get("title"),
        "created_at": response.get("created_at"),
    })
    return 0 if result.status in ("accepted", "completed") else 1


def _cmd_decision_list(state, args) -> int:
    tranche = state.tranche_manager.get_current()
    tranche_id = tranche.tranche_id if tranche else None
    decisions = state.tranche_manager.get_decisions(tranche_id)
    _print_json({
        "active_tranche_id": tranche_id,
        "count": len(decisions),
        "decisions": [
            {
                "decision_id": d.decision_id,
                "title": d.title,
                "impact_area": d.impact_area,
                "importance": d.importance,
                "created_at": d.created_at,
                "context_preview": d.context[:120] if d.context else "",
                "outcome_preview": d.outcome[:120] if d.outcome else "",
            }
            for d in decisions
        ],
    })
    return 0


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
    "approval-request": _cmd_approval_request,
    "approval-list": _cmd_approval_list,
    "approval-approve": _cmd_approval_approve,
    "approval-reject": _cmd_approval_reject,
    "session-list": _cmd_session_list,
    "local-agent-status": _cmd_local_agent_status,
    "local-agent-models": _cmd_local_agent_models,
    "local-agent-preflight": _cmd_local_agent_preflight,
    "local-agent-run": _cmd_local_agent_run,
    "local-agent-stop": _cmd_local_agent_stop,
    "local-agent-run-list": _cmd_local_agent_run_list,
    "local-agent-run-show": _cmd_local_agent_run_show,
    "local-agent-run-events": _cmd_local_agent_run_events,
    "local-agent-recovery-summary": _cmd_local_agent_recovery_summary,
    "local-agent-run-retry": _cmd_local_agent_run_retry,
    "training-scenario-list": _cmd_training_scenario_list,
    "training-scenario-show": _cmd_training_scenario_show,
    "training-sandbox-create": _cmd_training_sandbox_create,
    "training-run-scenario": _cmd_training_run_scenario,
    "training-verify": _cmd_training_verify,
    "training-scorecard-show": _cmd_training_scorecard_show,
    "training-review-export": _cmd_training_review_export,
    "training-compare-runs": _cmd_training_compare_runs,
    "installed-proof-create": _cmd_installed_proof_create,
    "installed-proof-run": _cmd_installed_proof_run,
    "installed-proof-verify": _cmd_installed_proof_verify,
    "installed-proof-show": _cmd_installed_proof_show,
    "installed-proof-export": _cmd_installed_proof_export,
    "closeout-metadata-show": _cmd_closeout_metadata_show,
    "closeout-metadata-sync": _cmd_closeout_metadata_sync,
    "contract-constraint-map-refresh": _cmd_contract_constraint_map_refresh,
    "public-export-preview": _cmd_public_export_preview,
    "public-export-write": _cmd_public_export_write,
    "public-export-audit": _cmd_public_export_audit,
    # T2.5 Active Tranche Ledger
    "tranche-declare": _cmd_tranche_declare,
    "tranche-status": _cmd_tranche_status,
    "tranche-review-request": _cmd_tranche_review_request,
    "tranche-review-show": _cmd_tranche_review_show,
    "tranche-review-return": _cmd_tranche_review_return,
    "tranche-review-approve": _cmd_tranche_review_approve,
    "tranche-update": _cmd_tranche_update,
    "tranche-close": _cmd_tranche_close,
    "tranche-smoke-pass": _cmd_tranche_smoke_pass,
    "decision-record": _cmd_decision_record,
    "decision-list": _cmd_decision_list,
}


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_json(obj) -> None:
    sys.stdout.write(safe_json_dumps(obj, indent=2) + "\n")


def _run_to_dict(run) -> dict:
    return {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "actor_id": run.actor_id,
        "model": run.model,
        "status": run.status,
        "authority_level": run.authority_level,
        "task_summary": run.task_summary,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "final_summary": run.final_summary,
        "final_message": run.final_message,
        "recovery_class": run.recovery_class,
        "retryable": run.retryable,
        "operator_hint": run.operator_hint,
        "retried_from_run_id": run.retried_from_run_id,
        "last_round_index": run.last_round_index,
        "last_runtime_event_type": run.last_runtime_event_type,
        "journal_entry_uid": run.journal_entry_uid,
        "approval_request_id": run.approval_request_id,
        "approval_grant_id": run.approval_grant_id,
        "config_snapshot": run.config_snapshot,
        "metadata": run.metadata,
    }


def _review_to_dict(review) -> dict:
    return {
        "review_id": review.review_id,
        "tranche_id": review.tranche_id,
        "status": review.status,
        "generated_at": review.generated_at,
        "generated_by_actor": review.generated_by_actor,
        "review_packet_json_ref": review.review_packet_json_ref,
        "review_packet_markdown_ref": review.review_packet_markdown_ref,
        "smoke_snapshot": review.smoke_snapshot,
        "latest_decision_ids": review.latest_decision_ids,
        "latest_test_records": review.latest_test_records,
        "reviewed_by_actor": review.reviewed_by_actor,
        "reviewed_at": review.reviewed_at,
        "return_reason": review.return_reason,
        "approval_notes": review.approval_notes,
        "event_id": review.event_id,
        "metadata": review.metadata,
    }


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
