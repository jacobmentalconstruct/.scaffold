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
import os
import re
import sqlite3
import subprocess
import sys
import traceback
from pathlib import Path

# Allow `import src.*` regardless of where the test is invoked from.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from src.lib.common import public_root_labels, safe_json_dumps
from src.lib.bcc_constraint_map import CURRENT_MAP_META_KEY
from src.lib.doc_registry import doc_path, doc_relpath, root_alias_paths
from src.orchestrators.closeout_orchestrator import evaluate_park_continuity_drift


INSTALLED_CHILD_SMOKE = os.environ.get("SIDE_CAR_INSTALLED_CHILD_SMOKE", "").strip() == "1"


def _section(title: str) -> None:
    bar = "-" * 60
    print(f"\n{bar}\n{title}\n{bar}")


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def _fail(msg: str) -> str:
    print(f"  FAIL  {msg}")
    return msg


def _warn(msg: str) -> str:
    print(f"  WARN  {msg}")
    return msg


def _first_projection_row(rows: list[dict]) -> dict:
    return rows[0] if rows else {}


def _contains_absolute_path(value) -> bool:
    if isinstance(value, dict):
        return any(_contains_absolute_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_absolute_path(item) for item in value)
    if isinstance(value, str):
        text = value.strip()
        if re.match(r"^[A-Za-z]:[\\/]", text):
            return True
        if text.startswith("\\\\"):
            return True
        if text.startswith("/") and not text.startswith("//"):
            return True
    return False


def _find_constraint_typo_hits(root: Path) -> dict[str, list[str]]:
    needle = "constrant"
    text_hits: list[str] = []
    db_hits: list[str] = []
    text_exts = {".md", ".json", ".py", ".txt"}
    skip_dirs = {".git", "node_modules", "__pycache__"}
    self_path = Path(__file__).resolve()

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == self_path:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if "installed_project_proof" in path.parts:
            continue

        suffix = path.suffix.lower()
        if suffix in text_exts:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if needle in text:
                text_hits.append(str(path.relative_to(root)))
            continue

        if suffix not in {".db", ".sqlite", ".sqlite3"}:
            continue

        try:
            conn = sqlite3.connect(path)
        except sqlite3.Error:
            continue
        try:
            cur = conn.cursor()
            # Historical blob_store payloads are immutable content-addressed
            # artifacts; typo repair should target current docs and current
            # journal truth rather than archaeology inside superseded blobs.
            try:
                count = cur.execute(
                    """
                    SELECT COUNT(*) FROM journal_entries
                    WHERE superseded_by IS NULL
                      AND CAST(body AS TEXT) LIKE ?
                    """,
                    (f"%{needle}%",),
                ).fetchone()[0]
            except sqlite3.Error:
                count = 0
            if count:
                rel = path.relative_to(root)
                db_hits.append(f"{rel} :: journal_entries.body live rows ({count})")
        finally:
            conn.close()

    return {"text_hits": text_hits, "db_hits": db_hits}


def main() -> int:
    failures: list[str] = []
    warnings: list[str] = []

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
        project_root_label, sidecar_root_label = public_root_labels(
            state.sidecar_root, state.project_root
        )
        installed_mode = (
            state.sidecar_root.name == ".scaffold"
            and state.project_root.resolve() == state.sidecar_root.parent.resolve()
        )
        _ok(f"sidecar_id={state.sidecar_id}")
        _ok(f"sidecar_root={sidecar_root_label}")
        _ok(f"project_root={project_root_label}")
        _ok(f"schema_version={state.store.schema_version()}")
        _ok(f"installed_mode={installed_mode}")
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

    _section("10. Post-ack: deferred-tranche intent still raises UnrouteableEnvelope")
    # Use apply_patch (deferred to T4 — no handler). After ack, the gate
    # ACCEPTS, then dispatch reaches the handler-lookup phase and raises
    # UnrouteableEnvelope — proving the dispatch path is intact and the
    # gate is no longer blocking pre-ack.
    from src.core.router import UnrouteableEnvelope
    test_env = SidecarEnvelope.new(
        object_type="patch_proposal",
        actor_id=actor_id,
        operation_intent="apply_patch",
    )
    try:
        state.router.dispatch(test_env)
        failures.append(_fail("expected UnrouteableEnvelope after gate pass; got dispatch success"))
    except UnrouteableEnvelope:
        _ok("gate allows apply_patch; UnrouteableEnvelope raised as expected (no T4 handler yet)")
    except Exception as e:
        failures.append(_fail(f"unexpected exception type: {type(e).__name__}: {e}"))

    _section("11. T2.1 journal layer: schema v2 applied")
    if state.store.schema_version() >= 2:
        _ok(f"schema_version={state.store.schema_version()} (v2 LTM activation applied)")
    else:
        failures.append(_fail(f"schema_version={state.store.schema_version()} (expected >= 2)"))

    _section("12. T2.1 journal layer: handlers registered")
    handlers = state.router.handlers()
    needed = ("create_journal_entry", "update_journal_entry",
              "close_journal_entry", "archive_journal_entry")
    missing = [intent for intent in needed if intent not in handlers]
    if not missing:
        _ok(f"all 4 journal intents registered: {', '.join(needed)}")
    else:
        failures.append(_fail(f"missing journal handlers: {missing}"))

    _section("13. T2.1 journal write end-to-end")
    request = {
        "kind": "note",
        "title": "smoke test note",
        "body": "Hello from smoke_test.py",
        "tags": ["smoke", "t2.1"],
        "importance": 3,
    }
    payload_ref = state.blob_store.put_json(request)
    write_env = SidecarEnvelope.new(
        object_type="journal_entry",
        actor_id=actor_id,
        operation_intent="create_journal_entry",
        payload_ref=payload_ref,
    )
    write_result = state.router.dispatch(write_env)
    if write_result.status in ("accepted", "completed"):
        _ok(f"journal write accepted: event_id={write_result.event_id}")
    else:
        failures.append(_fail(f"journal write status={write_result.status} (expected accepted/completed)"))

    response = state.blob_store.get_json(write_result.payload_ref) if write_result.payload_ref else {}
    new_entry_uid = response.get("entry_uid")
    if new_entry_uid:
        _ok(f"response carries entry_uid={new_entry_uid}")
    else:
        failures.append(_fail("response blob missing entry_uid"))

    _section("14. T2.1 PENDING marker resolved on the new entry")
    if new_entry_uid:
        entry = state.journal_manager.get(new_entry_uid)
        if entry and entry.event_id and entry.event_id != "PENDING":
            _ok(f"entry.event_id resolved to {entry.event_id}")
        elif entry:
            failures.append(_fail(f"entry.event_id={entry.event_id!r} still PENDING"))
        else:
            failures.append(_fail(f"could not fetch entry {new_entry_uid}"))

    _section("15. T2.1 journal_timeline projection has the entry")
    timeline = state.projections.read("journal_timeline")
    if any(r.get("entry_uid") == new_entry_uid for r in timeline.rows):
        _ok("new entry visible in journal_timeline projection")
    else:
        failures.append(_fail("new entry not in journal_timeline projection"))

    _section("16. T2.1 HANDOFF HONORED: T1 closeout tranche entry exists")
    tranche_entries = state.journal_manager.query(kind="tranche", limit=100)
    matching = [e for e in tranche_entries if "T1" in e.title and "Spine Boot" in e.title]
    if matching:
        entry = matching[0]
        _ok(f"T1 closeout entry found: {entry.entry_uid}")
        _ok(f"  title: {entry.title}")
        _ok(f"  status: {entry.status}, importance: {entry.importance}")
        # Verify the closeout notes evidence hash is in the creating event.
        ev_row = state.store.query_one(
            "SELECT evidence_refs FROM events WHERE event_id = ?;",
            (entry.event_id,),
        )
        import json as _json
        ev_refs = _json.loads(ev_row["evidence_refs"]) if ev_row and ev_row["evidence_refs"] else []
        closeout_hash = "26a89b86a7fcdd1097470e0c5ffda4ca947e5b7b4274c08866b9f2a2e57def28"
        if any(ref.get("hash") == closeout_hash for ref in ev_refs):
            _ok(f"  evidence_refs cites the T1 closeout notes blob hash")
        else:
            failures.append(_fail("T1 tranche entry's event lacks the closeout notes hash"))
    elif installed_mode:
        _ok("installed context: historical dev-branch T1 closeout journal is not required")
    else:
        failures.append(_fail("no T1 closeout tranche entry found (handoff promise not honored)"))

    _section("17. T2.2 schema v3 applied")
    if state.store.schema_version() >= 3:
        _ok(f"schema_version={state.store.schema_version()}")
    else:
        failures.append(_fail(f"schema_version={state.store.schema_version()} (expected >= 3)"))

    _section("18. T2.2 install + scan handlers registered")
    handlers = state.router.handlers()
    needed = ("install", "scan")
    missing = [intent for intent in needed if intent not in handlers]
    if not missing:
        _ok(f"install + scan handlers registered")
    else:
        failures.append(_fail(f"missing handlers: {missing}"))

    _section("19. T2.2 install event recorded (idempotent)")
    install_rows = state.store.query(
        "SELECT event_id, actor_id, created_at FROM events "
        "WHERE operation_intent = 'install' ORDER BY created_at ASC;"
    )
    if install_rows:
        _ok(f"install event(s) found: {len(install_rows)} (expect 1)")
        if state.install_orchestrator.is_installed():
            _ok(f"installed_at meta key set: {state.store.get_meta('installed_at')}")
        else:
            failures.append(_fail("installed_at meta key not set"))
    else:
        failures.append(_fail("no install event in event log"))

    _section("20. T2.2 scan runs end-to-end")
    scan_env = SidecarEnvelope.new(
        object_type="scan_request",
        actor_id=actor_id,
        operation_intent="scan",
    )
    scan_result = state.router.dispatch(scan_env)
    if scan_result.status in ("accepted", "completed"):
        _ok(f"scan dispatched: event_id={scan_result.event_id}")
    else:
        failures.append(_fail(f"scan status={scan_result.status}"))
    scan_summary = {}
    if scan_result.payload_ref:
        try:
            scan_summary = state.blob_store.get_json(scan_result.payload_ref)
        except Exception:
            pass
    if scan_summary.get("file_count", 0) >= 30:
        _ok(f"scan observed {scan_summary['file_count']} files, {scan_summary.get('directory_count')} dirs")
    else:
        failures.append(_fail(
            f"scan file_count={scan_summary.get('file_count')} (expected >= 30; "
            f"the scaffold has at least 19 .py + many .md files)"
        ))

    _section("21. T2.2 scan record bound to event_id")
    scan_id = scan_summary.get("scan_id")
    if scan_id:
        scan_rec = state.project_index_manager.get_scan(scan_id)
        if scan_rec and scan_rec.event_id and scan_rec.event_id == scan_result.event_id:
            _ok(f"scan_record.event_id={scan_rec.event_id} matches dispatched event")
        else:
            failures.append(_fail(
                f"scan record event_id mismatch: rec={scan_rec.event_id if scan_rec else None} "
                f"vs envelope={scan_result.event_id}"
            ))
    else:
        failures.append(_fail("scan summary missing scan_id"))

    _section("22. T2.2 project_index populated")
    pi_stats = state.project_index_manager.stats()
    if pi_stats["file_count"] >= 30:
        _ok(f"project_index has {pi_stats['file_count']} files, {pi_stats['directory_count']} dirs")
    else:
        failures.append(_fail(f"project_index file_count={pi_stats['file_count']} (expected >= 30)"))

    _section("23. T2.2 project_map projection refreshed")
    pm = state.projections.read("project_map")
    if len(pm.rows) >= 30:
        _ok(f"project_map projection has {len(pm.rows)} rows")
        sample = next((r for r in pm.rows if r.get("path") == "_docs/reference/ARCHITECTURE.md"), None)
        if sample:
            _ok(f"  sample: _docs/reference/ARCHITECTURE.md kind={sample['kind']} size={sample['size_bytes']}")
        elif installed_mode:
            _ok("installed context: project_map is expected to reflect the host project rather than sidecar docs")
        else:
            failures.append(_fail("_docs/reference/ARCHITECTURE.md not in project_map projection"))
    else:
        failures.append(_fail(f"project_map projection has only {len(pm.rows)} rows"))

    _section("24. T2.2 human_dashboard projection refreshed")
    hd = state.projections.read("human_dashboard")
    if hd.rows:
        row = hd.rows[0]
        if row.get("last_scan_summary_json"):
            import json as _json
            scan_summary_row = _json.loads(row["last_scan_summary_json"])
            if scan_summary_row.get("scan_id") == scan_id:
                _ok(f"human_dashboard.last_scan_summary references scan {scan_id}")
            else:
                failures.append(_fail(
                    f"human_dashboard.last_scan_summary scan_id mismatch: "
                    f"{scan_summary_row.get('scan_id')} vs {scan_id}"
                ))
        else:
            failures.append(_fail("human_dashboard.last_scan_summary_json missing"))
    else:
        failures.append(_fail("human_dashboard projection has no rows"))

    _section("25. T2.2 sidecar's own code is indexed (LTM is alive)")
    own_index = state.project_index_manager.get("src/app.py")
    if own_index and own_index.kind == "file" and own_index.content_hash:
        _ok(f"src/app.py indexed: hash={own_index.content_hash[:16]}... size={own_index.size_bytes}")
    elif installed_mode:
        _ok("installed context: project_index is expected to reflect the host project rather than sidecar source files")
    else:
        failures.append(_fail("src/app.py not in project_index"))

    _section("26. T2.3 schema v4 applied")
    if state.store.schema_version() >= 4:
        _ok(f"schema_version={state.store.schema_version()}")
    else:
        failures.append(_fail(f"schema_version={state.store.schema_version()} (expected >= 4)"))

    _section("27. T2.3 handlers registered (evidence, git, tools, tasks)")
    handlers = state.router.handlers()
    needed = ("attach_evidence", "verify_evidence", "observe_git",
              "tool_invoked", "accept_task", "complete_task")
    missing = [i for i in needed if i not in handlers]
    if not missing:
        _ok(f"all 6 T2.3 handlers registered")
    else:
        failures.append(_fail(f"missing handlers: {missing}"))

    _section("28. T2.3 tool registry: 5 tools discovered")
    tool_count = state.tool_registry_manager.count()
    if tool_count >= 5:
        _ok(f"tool registry has {tool_count} tools")
        names = sorted(t.tool_name for t in state.tool_registry_manager.list_tools())
        for name in names:
            _ok(f"  - {name}")
    else:
        failures.append(_fail(f"tool registry has only {tool_count} tools"))

    _section("29. T2.3 tool invocation end-to-end")
    payload_ref = state.blob_store.put_json({
        "tool_name": "host_capability_probe",
        "arguments": {},
    })
    inv_env = SidecarEnvelope.new(
        object_type="tool_invocation",
        actor_id=actor_id,
        operation_intent="tool_invoked",
        payload_ref=payload_ref,
    )
    inv_result = state.router.dispatch(inv_env)
    if inv_result.status in ("accepted", "completed"):
        _ok(f"tool invocation accepted: event_id={inv_result.event_id}")
        if inv_result.payload_ref:
            response = state.blob_store.get_json(inv_result.payload_ref)
            if response.get("status") == "ok":
                _ok(f"tool returned status=ok")
            else:
                failures.append(_fail(f"tool response status={response.get('status')}"))
    else:
        failures.append(_fail(f"tool invocation status={inv_result.status}"))

    _section("30. T2.3 tool_invocations table records the call")
    inv_rows = state.store.query(
        "SELECT * FROM tool_invocations WHERE tool_name = 'host_capability_probe' "
        "ORDER BY started_at DESC LIMIT 1;"
    )
    if inv_rows:
        row = inv_rows[0]
        if row["status"] == "completed":
            _ok(f"tool_invocations row recorded: {row['invocation_id']} status={row['status']}")
        else:
            failures.append(_fail(f"tool_invocations row status={row['status']}"))
    else:
        failures.append(_fail("no tool_invocations row"))

    _section("31. T2.3 git observation end-to-end")
    git_env = SidecarEnvelope.new(
        object_type="git_observation",
        actor_id=actor_id,
        operation_intent="observe_git",
    )
    git_result = state.router.dispatch(git_env)
    if git_result.status in ("accepted", "completed"):
        _ok(f"git observation accepted: event_id={git_result.event_id}")
        obs = state.git_state_manager.latest()
        if obs:
            _ok(f"  latest observation: is_repo={obs.is_repo} branch={obs.branch or '(none)'}")
        else:
            failures.append(_fail("git_state_manager.latest() returned None"))
    else:
        failures.append(_fail(f"git observation status={git_result.status}"))

    _section("32. T2.3 evidence attach end-to-end")
    # Put a blob first.
    body_hash = state.blob_store.put_text("smoke test evidence body", content_type="text/plain")
    ev_request = {
        "hash": body_hash,
        "kind": "tool_output",
        "summary": "smoke test evidence",
        "attached_to_object": "smoke_test",
        "attached_to_type": "test",
    }
    ev_payload_ref = state.blob_store.put_json(ev_request)
    ev_env = SidecarEnvelope.new(
        object_type="evidence",
        actor_id=actor_id,
        operation_intent="attach_evidence",
        payload_ref=ev_payload_ref,
    )
    ev_result = state.router.dispatch(ev_env)
    if ev_result.status in ("accepted", "completed"):
        ev_response = state.blob_store.get_json(ev_result.payload_ref)
        evidence_id = ev_response.get("evidence_id")
        _ok(f"evidence attached: {evidence_id}")
        # Verify it
        vr_payload_ref = state.blob_store.put_json({"evidence_id": evidence_id})
        vr_env = SidecarEnvelope.new(
            object_type="evidence",
            actor_id=actor_id,
            operation_intent="verify_evidence",
            payload_ref=vr_payload_ref,
        )
        vr_result = state.router.dispatch(vr_env)
        if vr_result.status in ("accepted", "completed"):
            vr_response = state.blob_store.get_json(vr_result.payload_ref)
            if vr_response.get("verified"):
                _ok(f"evidence verified: hash={vr_response.get('hash')[:16]}...")
            else:
                failures.append(_fail("evidence verification returned verified=False"))
        else:
            failures.append(_fail(f"verify_evidence status={vr_result.status}"))
    else:
        failures.append(_fail(f"attach_evidence status={ev_result.status}"))

    _section("33. T2.3 MCP handler: initialize + tools/list + resources/list")
    from src.interfaces.mcp_interface import MCPHandler
    mcp = MCPHandler(state)

    init_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    init_resp = mcp.handle_message(init_msg)
    if init_resp and init_resp.get("result", {}).get("protocolVersion"):
        _ok(f"initialize ok: protocol={init_resp['result']['protocolVersion']}")
    else:
        failures.append(_fail(f"initialize bad response: {init_resp}"))

    tl_msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    tl_resp = mcp.handle_message(tl_msg)
    tools = (tl_resp or {}).get("result", {}).get("tools", [])
    if len(tools) >= 5:
        _ok(f"tools/list returned {len(tools)} tools")
    else:
        failures.append(_fail(f"tools/list returned {len(tools)} tools (expected >= 5)"))

    rl_msg = {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}}
    rl_resp = mcp.handle_message(rl_msg)
    resources = (rl_resp or {}).get("result", {}).get("resources", [])
    resource_uris = {item.get("uri", "") for item in resources}
    from src.schemas.projection_schema import PROJECTION_NAMES as _PROJ_NAMES
    expected_projection_count = len(_PROJ_NAMES)
    projection_resources = [uri for uri in resource_uris if uri.startswith("projection://")]
    if (
        len(projection_resources) == expected_projection_count
        and "review://latest" in resource_uris
        and "closeout://latest" in resource_uris
    ):
        _ok(f"resources/list returned {len(projection_resources)} projections plus chat-cockpit resources")
    else:
        failures.append(_fail(
            f"resources/list missing expected projection/review/closeout resources: {sorted(resource_uris)}"
        ))

    _section("34. T2.3 MCP handler: tools/call (host_capability_probe)")
    tc_msg = {
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "host_capability_probe", "arguments": {}},
    }
    tc_resp = mcp.handle_message(tc_msg)
    if tc_resp and not tc_resp.get("result", {}).get("isError"):
        content = tc_resp["result"].get("content", [])
        if content and content[0].get("type") == "text":
            _ok(f"tools/call returned content (length {len(content[0]['text'])})")
        else:
            failures.append(_fail("tools/call content missing or wrong shape"))
    else:
        failures.append(_fail(f"tools/call returned error: {tc_resp}"))

    _section("35. T2.3 MCP handler: resources/read (current_sidecar_state)")
    rr_msg = {
        "jsonrpc": "2.0", "id": 5, "method": "resources/read",
        "params": {"uri": "projection://current_sidecar_state"},
    }
    rr_resp = mcp.handle_message(rr_msg)
    contents = (rr_resp or {}).get("result", {}).get("contents", [])
    if contents and contents[0].get("mimeType") == "application/json":
        _ok(f"resources/read returned content for current_sidecar_state")
    else:
        failures.append(_fail(f"resources/read bad response: {rr_resp}"))

    _section("35.5. T10.2 MCP handler: closeout resource surfaces return JSON + Markdown")
    latest_closed_entries = state.journal_manager.query(kind="tranche", status="closed", limit=1)
    latest_closed_uid = latest_closed_entries[0].entry_uid if latest_closed_entries else ""
    closeout_latest_resp = mcp.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "resources/read",
            "params": {"uri": "closeout://latest"},
        }
    )
    closeout_latest_contents = (closeout_latest_resp or {}).get("result", {}).get("contents", [])
    closeout_mimes = {item.get("mimeType") for item in closeout_latest_contents}
    if {"application/json", "text/markdown"}.issubset(closeout_mimes):
        _ok("closeout://latest returns JSON + Markdown contents")
    else:
        failures.append(_fail(f"closeout://latest returned wrong content set: {closeout_latest_resp}"))

    if latest_closed_uid:
        closeout_specific_resp = mcp.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "resources/read",
                "params": {"uri": f"closeout://{latest_closed_uid}"},
            }
        )
        specific_contents = (closeout_specific_resp or {}).get("result", {}).get("contents", [])
        specific_mimes = {item.get("mimeType") for item in specific_contents}
        if {"application/json", "text/markdown"}.issubset(specific_mimes):
            _ok("closeout://<journal_entry_uid> returns JSON + Markdown contents")
        else:
            failures.append(_fail(f"closeout://{latest_closed_uid} returned wrong content set: {closeout_specific_resp}"))

    _section("35.6. T10.5 MCP handler: projection://bcc_constraint_map is queryable")
    bcc_projection_resp = mcp.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "resources/read",
            "params": {"uri": "projection://bcc_constraint_map"},
        }
    )
    bcc_projection_contents = (bcc_projection_resp or {}).get("result", {}).get("contents", [])
    if bcc_projection_contents and bcc_projection_contents[0].get("mimeType") == "application/json":
        _ok("projection://bcc_constraint_map returns JSON content through MCP")
    else:
        failures.append(_fail(f"projection://bcc_constraint_map returned wrong content set: {bcc_projection_resp}"))

    # =============================================================
    # PARK PHASE DRIFT DETECTION (added 2026-05-11; contract §D)
    # =============================================================
    # These sections verify that continuity docs are in sync with state.
    # A failure here means the most recent tranche is not properly parked
    # (per ARCHITECTURE.md §12.2 + contract §D).
    # =============================================================

    import re as _re
    sidecar_root = state.sidecar_root
    tools_doc_path = doc_path(sidecar_root, "tools_index")
    architecture_doc_path = doc_path(sidecar_root, "architecture")
    onboarding_doc_path = doc_path(sidecar_root, "onboarding")
    where_now_doc_path = doc_path(sidecar_root, "where_we_are_now")
    target_state_doc_path = doc_path(sidecar_root, "target_state")
    northstars_doc_path = doc_path(sidecar_root, "northstars")
    dev_log_doc_path = doc_path(sidecar_root, "dev_log")
    roadmap_doc_path = doc_path(sidecar_root, "implementation_roadmap")
    latest_closeout_path = doc_path(sidecar_root, "latest_parked_tranche_json")

    _section("36. DRIFT: TOOLS.md row count matches tool_registry count")
    registered_count = state.tool_registry_manager.count()
    tools_md = tools_doc_path.read_text(encoding="utf-8")
    # Count rows in the "## Registered tools" table.
    # Match table rows that look like: | `tool_name` | ... |
    rows_md = _re.findall(r"^\|\s*`[a-z_]+`\s*\|", tools_md, _re.MULTILINE)
    if len(rows_md) == registered_count:
        _ok(f"TOOLS.md rows ({len(rows_md)}) match tool_registry count ({registered_count})")
    else:
        failures.append(_fail(
            f"TOOLS.md rows={len(rows_md)} vs tool_registry={registered_count} — DRIFT"
        ))

    _section("37. DRIFT: README.md and TOOLS.md status headers reflect current parked state")
    readme = (sidecar_root / "README.md").read_text(encoding="utf-8")
    header_lines = readme.split("\n", 10)[:6]
    header_text = "\n".join(header_lines)
    latest_closeout = {}
    if latest_closeout_path.is_file():
        try:
            latest_closeout = json.loads(latest_closeout_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            latest_closeout = {}
    latest_title = str(latest_closeout.get("title") or "").strip()
    expected_next_slice = "T10.5 Derived BCC Constraint-Map Slice for Intent Decomposition"
    if "Tranche 0" in header_text and "No executable code yet" in header_text:
        failures.append(_fail("README.md status header still says 'Tranche 0 — No executable code yet' — DRIFT"))
    elif "T10.3 in progress" in header_text:
        failures.append(_fail("README.md status header still claims 'T10.3 in progress' — DRIFT"))
    elif latest_title and latest_title in header_text and expected_next_slice in header_text:
        _ok("README.md status header matches latest parked tranche + next slice")
    else:
        failures.append(_fail("README.md status header does not match latest parked tranche + next slice"))

    tools_header = "\n".join(tools_md.split("\n", 6)[:4])
    if "T10.3 in progress" in tools_header:
        failures.append(_fail("TOOLS.md status header still claims 'T10.3 in progress' — DRIFT"))
    elif expected_next_slice in tools_header and "latest parked tranche is T10.4" in tools_header:
        _ok("TOOLS.md status header matches current parked-state wording")
    else:
        failures.append(_fail("TOOLS.md status header does not reflect current parked-state wording"))

    _section("38. DRIFT: ARCHITECTURE.md §15 has 'Resolved at T_n' for every completed tranche")
    arch = architecture_doc_path.read_text(encoding="utf-8")
    # Count completed tranches from journal_entries kind='tranche'.
    tranches = state.journal_manager.query(kind="tranche", limit=50)
    completed_tranches = sorted(
        {_re.match(r"T(\d+)", e.title).group(1) for e in tranches if _re.match(r"T(\d+)", e.title)}
    )
    missing_sections = []
    for n in completed_tranches:
        if f"Resolved at T{n}" not in arch:
            missing_sections.append(f"T{n}")
    if not missing_sections:
        _ok(f"ARCHITECTURE.md §15 has 'Resolved at T_n' for tranches: {completed_tranches}")
    else:
        failures.append(_fail(
            f"ARCHITECTURE.md §15 missing 'Resolved at T_n' for: {missing_sections} — DRIFT"
        ))

    _section("39. DRIFT: latest tranche journal entry is status='closed' (not 'open')")
    if tranches:
        # Sort by created_at desc — query returns DESC by default.
        latest = tranches[0]
        if latest.status == "closed":
            _ok(f"latest tranche entry {latest.entry_uid} is status='closed'")
        else:
            failures.append(_fail(
                f"latest tranche entry {latest.entry_uid} has status={latest.status!r} "
                f"(must be 'closed' per Park Phase step 7)"
            ))
    elif installed_mode:
        _ok("installed context: no historical parked tranches recorded yet")
    else:
        failures.append(_fail("no tranche entries found in journal — no Park Phase performed?"))

    _section("40. DRIFT: every tranche entry cites at least one evidence_ref")
    drift_count = 0
    import json as _json
    for entry in tranches:
        ev_row = state.store.query_one(
            "SELECT evidence_refs FROM events WHERE event_id = ?;", (entry.event_id,)
        )
        ev_refs = _json.loads(ev_row["evidence_refs"]) if ev_row and ev_row["evidence_refs"] else []
        valid = [ref for ref in ev_refs if state.blob_store.exists(ref.get("hash", ""))]
        if not valid:
            # Fallback: check journal entry metadata for park_notes_blob_ref.
            # close_tranche entries embed the blob ref in metadata rather than
            # on the creating event (the hash is only known after the close runs).
            raw_meta = entry.metadata
            if isinstance(raw_meta, str):
                raw_meta = _json.loads(raw_meta)
            meta = raw_meta if isinstance(raw_meta, dict) else {}
            park_ref = meta.get("park_notes_blob_ref", "")
            if park_ref and state.blob_store.exists(park_ref):
                valid = [{"hash": park_ref, "kind": "park_notes_metadata"}]
        if not valid:
            failures.append(_fail(
                f"tranche entry {entry.entry_uid} ({entry.title}) has no resolvable evidence_ref"
            ))
            drift_count += 1
    if not drift_count:
        _ok(f"all {len(tranches)} tranche entries cite valid evidence_refs")

    _section("40.5. DRIFT: generated closeout metadata matches latest parked tranche")
    if tranches:
        latest = tranches[0]
        if latest_closeout_path.is_file():
            closeout_meta = _json.loads(latest_closeout_path.read_text(encoding="utf-8"))
            latest_meta = latest.metadata if isinstance(latest.metadata, dict) else _json.loads(latest.metadata or "{}")
            if closeout_meta.get("journal_entry_uid") == latest.entry_uid:
                _ok("generated latest closeout metadata points at the latest closed tranche entry")
            else:
                failures.append(_fail("generated latest closeout metadata journal_entry_uid does not match latest closed tranche"))
            if closeout_meta.get("park_notes_blob_ref") == latest_meta.get("park_notes_blob_ref", ""):
                _ok("generated latest closeout metadata preserves the authoritative park_notes_blob_ref")
            else:
                failures.append(_fail("generated latest closeout metadata park_notes_blob_ref does not match tranche metadata"))
            park_notes_path = sidecar_root / str(closeout_meta.get("park_notes_path", ""))
            per_tranche_json_path = sidecar_root / str(closeout_meta.get("per_tranche_json_path", ""))
            if park_notes_path.is_file() and per_tranche_json_path.is_file():
                _ok("generated closeout metadata files and referenced park notes exist")
            else:
                failures.append(_fail("generated closeout metadata references missing park-notes or per-tranche metadata file"))
        elif installed_mode:
            _ok("installed context: generated closeout metadata may not exist before the first local park")
        else:
            failures.append(_fail("missing canonical latest parked tranche JSON"))
    elif installed_mode:
        _ok("installed context: no local parked tranche yet, skipping generated closeout metadata check")
    else:
        failures.append(_fail("no tranche entries found when checking generated closeout metadata"))

    _section("41. DRIFT: active BCC Park Phase clause present")
    contract_path = sidecar_root / "contracts" / "BCC.md"
    contract_text = contract_path.read_text(encoding="utf-8")
    compat_path = sidecar_root / "contracts" / "builder_constraint_contract.md"
    bindings_doc_path = doc_path(sidecar_root, "project_bindings")
    appendix_ok = "## Appendix A. Historical Equivalence Map (non-normative)" in contract_text
    appendix_b_ok = "## Appendix B. Project Binding Artifact" in contract_text
    if (
        "Park Phase closure rule" in contract_text
        and "A Park Phase record shall include:" in contract_text
        and "Governed chat and projection surface rule" in contract_text
        and "Document Authority Classes" in contract_text
        and "Presence inside the Project Root makes an artifact part of the project package" in contract_text
        and "after reading this contract, inspect the Project Binding Artifact" in contract_text
        and "Exactly one active Project Binding Artifact shall govern a given package or" in contract_text
        and "Every declared binding shall either resolve in the current package context or" in contract_text
        and "_docs/reference/PROJECT_BINDINGS.md" in contract_text
        and appendix_ok
        and appendix_b_ok
        and bindings_doc_path.is_file()
        and not compat_path.exists()
    ):
        _ok("active BCC bootloader doctrine is present, the local binding artifact exists, and no legacy contract alias remains")
    else:
        failures.append(_fail("BCC bootloader content missing or legacy contract alias still present — DRIFT"))

    # =============================================================
    # ONBOARDING GAP CLOSURES (added 2026-05-11)
    # =============================================================

    from src.lib.common import now_iso

    import json as _json2
    _section("42. ONBOARDING: canonical onboarding doc exists")
    onboarding_path = onboarding_doc_path
    if onboarding_path.is_file():
        content = onboarding_path.read_text(encoding="utf-8")
        if (
            "Reading order" in content
            and "verification commands" in content.lower()
            and "convenience orientation surface derived from `contracts/BCC.md` and `_docs/reference/PROJECT_BINDINGS.md`" in content
            and content.find("**`contracts/BCC.md`**") != -1
            and "_docs/reference/PROJECT_BINDINGS.md" in content
        ):
            _ok(f"{doc_relpath(sidecar_root, 'onboarding')} present ({len(content)} chars), covers reading order + commands")
        else:
            failures.append(_fail("canonical onboarding doc present but missing bootloader-derived wording, BCC-first order, or commands section"))
    else:
        failures.append(_fail("canonical onboarding doc missing"))

    _section("42.5. BINDINGS: local binding artifact is single-source and status-marked")
    if bindings_doc_path.is_file():
        bindings_text = bindings_doc_path.read_text(encoding="utf-8")
        if (
            "single active Project Binding Artifact" in bindings_text
            and "## Binding status semantics" in bindings_text
            and "(`generated`)" in bindings_text
            and "(`installed-context`)" in bindings_text
            and "(`development-context`)" in bindings_text
        ):
            _ok("PROJECT_BINDINGS.md declares a single active artifact and explicit binding-status semantics")
        else:
            failures.append(_fail("PROJECT_BINDINGS.md missing single-source or explicit binding-status semantics"))
    else:
        failures.append(_fail("PROJECT_BINDINGS.md missing"))

    _section("43. ONBOARDING: config/toolbox_manifest.json generated at runtime")
    tbm_path = sidecar_root / "config" / "toolbox_manifest.json"
    if tbm_path.is_file():
        tbm = _json2.loads(tbm_path.read_text(encoding="utf-8"))
        required_keys = ("manifest_version", "zero_context_entry_protocol", "authority_levels",
                        "projections", "memory_model", "spine_rule", "verification_commands")
        missing = [k for k in required_keys if k not in tbm]
        entry = tbm.get("zero_context_entry_protocol", {})
        if (
            not missing
            and entry.get("step_1") == "Read contracts/BCC.md first."
            and "PROJECT_BINDINGS.md" in str(entry.get("step_2", ""))
        ):
            _ok(f"toolbox_manifest.json present with all required keys")
        else:
            failures.append(_fail(f"toolbox_manifest.json missing keys or BCC-first bootstrap steps: {missing}"))
    else:
        failures.append(_fail("config/toolbox_manifest.json missing — not generated at boot"))

    _section("44. ONBOARDING: config/tool_manifest.json generated and matches registry")
    tm_path = sidecar_root / "config" / "tool_manifest.json"
    if tm_path.is_file():
        tm = _json2.loads(tm_path.read_text(encoding="utf-8"))
        if tm.get("tool_count") == state.tool_registry_manager.count():
            _ok(f"tool_manifest.json tool_count={tm['tool_count']} matches registry")
        else:
            failures.append(_fail(
                f"tool_manifest.json tool_count={tm.get('tool_count')} vs registry "
                f"={state.tool_registry_manager.count()}"
            ))
    else:
        failures.append(_fail("config/tool_manifest.json missing — not generated at boot"))

    _section("45. ONBOARDING: agent_bootstrap projection is REAL (not stub)")
    ab = state.projections.read("agent_bootstrap")
    if ab.rows:
        row = ab.rows[0]
        current_tranche = _json2.loads(row.get("current_tranche_scope_json") or "{}")
        next_steps = _json2.loads(row.get("next_planned_steps_json") or "[]")
        recent_events = _json2.loads(row.get("recent_events_json") or "[]")
        tool_index = _json2.loads(row.get("tool_index_json") or "[]")
        if current_tranche.get("tranche") and current_tranche.get("scope"):
            _ok(f"agent_bootstrap FUTURE: current_tranche={current_tranche.get('tranche')}")
        else:
            failures.append(_fail("agent_bootstrap.current_tranche_scope_json empty"))
        if next_steps:
            _ok(f"agent_bootstrap.next_planned_steps has {len(next_steps)} items")
        else:
            failures.append(_fail("agent_bootstrap.next_planned_steps_json empty"))
        if len(recent_events) >= 5:
            _ok(f"agent_bootstrap PAST: recent_events has {len(recent_events)} entries")
        else:
            failures.append(_fail(f"recent_events has only {len(recent_events)}"))
        if len(tool_index) == state.tool_registry_manager.count():
            _ok(f"agent_bootstrap PRESENT: tool_index has {len(tool_index)} tools")
        else:
            failures.append(_fail("agent_bootstrap.tool_index mismatch"))
        if row.get("source_plan_hash"):
            _ok(f"agent_bootstrap META: source_plan_hash={row['source_plan_hash'][:16]}...")
        else:
            failures.append(_fail("agent_bootstrap.source_plan_hash empty"))
    else:
        failures.append(_fail("agent_bootstrap projection has no rows"))

    _section("45.5. T10.5: compiled BCC constraint map is durable, relative, and bootstrap-visible")
    try:
        current_map_id = (state.store.get_meta(CURRENT_MAP_META_KEY) or "").strip()
        if current_map_id:
            _ok(f"current_bcc_constraint_map_id={current_map_id}")
        else:
            failures.append(_fail("current_bcc_constraint_map_id meta key missing"))

        compiled_row = state.store.query_one(
            "SELECT * FROM compiled_bcc_constraint_maps WHERE map_id = ?;",
            (current_map_id,),
        ) if current_map_id else None
        if compiled_row:
            _ok("compiled_bcc_constraint_maps row exists for current map")
        else:
            failures.append(_fail("compiled_bcc_constraint_maps row missing for current map"))

        if compiled_row and compiled_row["source_contract_path"] == "contracts/BCC.md":
            _ok("compiled map stores repo-relative source_contract_path")
        else:
            failures.append(_fail(f"compiled map source_contract_path unexpected: {compiled_row}"))

        constraint_projection = state.projections.read("bcc_constraint_map")
        if constraint_projection.rows:
            row = constraint_projection.rows[0]
            payload = _json2.loads(row.get("payload_json") or "{}")
            summary = _json2.loads(row.get("summary_json") or "{}")
            drift = _json2.loads(row.get("drift_json") or "{}")
            if row.get("status") == "ready" and int(row.get("guidance_allowed") or 0) == 1:
                _ok("bcc_constraint_map projection is ready and guidance-enabled")
            else:
                failures.append(_fail(f"bcc_constraint_map projection status unexpected: {row.get('status')}"))
            canonical = payload.get("authority_model", {}).get("canonical_levels", [])
            if canonical == [
                "Observe",
                "Propose",
                "Project Apply",
                "Tooling Apply",
                "Workspace Apply",
                "Export",
            ]:
                _ok("canonical authority ladder matches the six-level BCC model exactly")
            else:
                failures.append(_fail(f"canonical authority ladder drifted: {canonical}"))
            runtime_common = payload.get("authority_model", {}).get("runtime_levels_common", [])
            if "Sandbox Execute" in runtime_common:
                _ok("runtime authority drift surfaces legacy Sandbox Execute explicitly")
            else:
                failures.append(_fail(f"runtime authority drift missing Sandbox Execute: {runtime_common}"))
            if payload.get("authority_model", {}).get("resolution_status") == "exposed_not_corrected":
                _ok("authority drift is exposed without silently correcting runtime enums")
            else:
                failures.append(_fail("authority drift resolution_status is not exposed_not_corrected"))
            if drift.get("authority_model_mismatch") is True:
                _ok("projection drift_json reports authority-model mismatch explicitly")
            else:
                failures.append(_fail(f"authority_model_mismatch missing from drift_json: {drift}"))
            if not _contains_absolute_path(payload) and not _contains_absolute_path(summary):
                _ok("compiled payload and summary contain no absolute path leakage")
            else:
                failures.append(_fail("compiled payload or summary leaked an absolute path"))
        else:
            failures.append(_fail("bcc_constraint_map projection has no rows"))

        bootstrap_rows = state.projections.read("agent_bootstrap").rows
        if bootstrap_rows:
            bootstrap_summary = _json2.loads(bootstrap_rows[0].get("constraint_map_summary_json") or "{}")
            if bootstrap_summary.get("full_projection_ref") == "projection://bcc_constraint_map":
                _ok("agent_bootstrap exposes a compact constraint-map summary with the full projection ref")
            else:
                failures.append(_fail(f"agent_bootstrap constraint_map_summary_json missing projection ref: {bootstrap_summary}"))
            if bootstrap_summary.get("refresh_command") == "python -m src.app cli contract-constraint-map-refresh":
                _ok("agent_bootstrap advertises the explicit constraint-map refresh command")
            else:
                failures.append(_fail(f"agent_bootstrap constraint_map_summary_json missing refresh command: {bootstrap_summary}"))
            if not _contains_absolute_path(bootstrap_summary):
                _ok("agent_bootstrap constraint-map summary contains no absolute path leakage")
            else:
                failures.append(_fail("agent_bootstrap constraint-map summary leaked an absolute path"))
        else:
            failures.append(_fail("agent_bootstrap projection missing while checking constraint_map_summary_json"))

        cli_projection_proc = subprocess.run(
            [sys.executable, "-m", "src.app", "cli", "projection", "bcc_constraint_map"],
            cwd=str(sidecar_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if cli_projection_proc.returncode == 0:
            cli_projection_json = json.loads(cli_projection_proc.stdout)
            cli_rows = cli_projection_json.get("rows", [])
            if cli_rows and cli_rows[0].get("status") == "ready":
                _ok("CLI projection bcc_constraint_map returns the ready projection surface")
            else:
                failures.append(_fail(f"CLI projection bcc_constraint_map returned unexpected rows: {cli_projection_json}"))
        else:
            failures.append(_fail(
                f"CLI projection bcc_constraint_map failed rc={cli_projection_proc.returncode}: {cli_projection_proc.stderr.strip()}"
            ))
    except Exception as e:
        failures.append(_fail(f"T10.5 compiled-map projection/bootstrap checks failed: {e}"))

    _section("45.6. T10.5: contract-hash drift is exposed and explicit refresh restores readiness")
    bcc_path = sidecar_root / "contracts" / "BCC.md"
    original_bcc_text = bcc_path.read_text(encoding="utf-8")
    original_map_id = (state.store.get_meta(CURRENT_MAP_META_KEY) or "").strip()
    drift_suffix = "\n<!-- smoke-test temporary T10.5 drift marker -->\n"
    try:
        bcc_path.write_text(original_bcc_text + drift_suffix, encoding="utf-8")
        state.projections.refresh("bcc_constraint_map")
        state.projections.refresh("agent_bootstrap")

        stale_projection = state.projections.read("bcc_constraint_map")
        stale_row = stale_projection.rows[0] if stale_projection.rows else {}
        stale_drift = _json2.loads(stale_row.get("drift_json") or "{}")
        if stale_row.get("status") == "stale_contract_hash" and int(stale_row.get("guidance_allowed", 1)) == 0:
            _ok("bcc_constraint_map projection becomes stale_contract_hash and disables guidance on contract drift")
        else:
            failures.append(_fail(f"bcc_constraint_map drift status unexpected: {stale_row}"))
        if stale_drift.get("contract_record_hash_mismatch") is True:
            _ok("projection drift_json reports contract_record_hash_mismatch during contract drift")
        else:
            failures.append(_fail(f"contract_record_hash_mismatch missing during contract drift: {stale_drift}"))

        stale_bootstrap_rows = state.projections.read("agent_bootstrap").rows
        stale_summary = _json2.loads(stale_bootstrap_rows[0].get("constraint_map_summary_json") or "{}") if stale_bootstrap_rows else {}
        if stale_summary.get("status") == "stale_contract_hash" and stale_summary.get("guidance_allowed") is False:
            _ok("agent_bootstrap constraint-map summary reflects the stale contract state")
        else:
            failures.append(_fail(f"agent_bootstrap stale constraint-map summary unexpected: {stale_summary}"))
    except Exception as e:
        failures.append(_fail(f"T10.5 stale-contract detection failed: {e}"))
    finally:
        bcc_path.write_text(original_bcc_text, encoding="utf-8")

    try:
        refresh_proc = subprocess.run(
            [sys.executable, "-m", "src.app", "cli", "contract-constraint-map-refresh"],
            cwd=str(sidecar_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if refresh_proc.returncode != 0:
            failures.append(_fail(
                f"contract-constraint-map-refresh failed rc={refresh_proc.returncode}: {refresh_proc.stderr.strip()}"
            ))
        else:
            refresh_json = json.loads(refresh_proc.stdout)
            refreshed_map_id = (state.store.get_meta(CURRENT_MAP_META_KEY) or "").strip()
            if refresh_json.get("map_id") and refreshed_map_id and refreshed_map_id != original_map_id:
                _ok("explicit refresh creates a new compiled-map row and advances current_bcc_constraint_map_id")
            else:
                failures.append(_fail(f"constraint-map refresh did not advance map id: {refresh_json}"))
            state.projections.refresh("bcc_constraint_map")
            state.projections.refresh("agent_bootstrap")
            refreshed_row = _first_projection_row(state.projections.read("bcc_constraint_map").rows)
            if refreshed_row.get("status") == "ready" and int(refreshed_row.get("guidance_allowed") or 0) == 1:
                _ok("explicit refresh restores bcc_constraint_map to ready")
            else:
                failures.append(_fail(f"bcc_constraint_map not ready after explicit refresh: {refreshed_row}"))
    except Exception as e:
        failures.append(_fail(f"T10.5 explicit refresh recovery failed: {e}"))

    _section("46. ONBOARDING: README.md references canonical onboarding path")
    readme_text = (sidecar_root / "README.md").read_text(encoding="utf-8")
    if (
        doc_relpath(sidecar_root, "onboarding") in readme_text
        and doc_relpath(sidecar_root, "project_bindings") in readme_text
        and "Read **[contracts/BCC.md](contracts/BCC.md)** first" in readme_text
    ):
        _ok("README.md links to canonical onboarding doc and preserves BCC-first order")
    else:
        failures.append(_fail("README.md does not preserve canonical BCC-first onboarding order"))

    _section("46.5. BCC MIGRATION: migration projections are queryable")
    migration_projection_names = (
        "contract_migration_overview",
        "contract_bundle_status",
        "continuity_translation_status",
        "legacy_reference_register",
        "doc_registry_status",
        "doc_cutover_readiness",
        "journal_translation_readiness",
    )
    missing_migration_rows = []
    for projection_name in migration_projection_names:
        projection = state.projections.read(projection_name)
        if projection.rows:
            _ok(f"{projection_name} projection returned {len(projection.rows)} rows")
        else:
            missing_migration_rows.append(projection_name)
    if missing_migration_rows:
        failures.append(_fail(f"migration projections missing rows: {missing_migration_rows}"))

    _section("46.6. DOC REGISTRY: canonical docs resolve and root clutter is controlled")
    try:
        registry_projection = state.projections.read("doc_registry_status")
        if registry_projection.rows:
            _ok(f"doc_registry_status projection returned {len(registry_projection.rows)} rows")
        else:
            failures.append(_fail("doc_registry_status projection returned no rows"))
        allowed_root_docs = set(root_alias_paths(sidecar_root)) | {"README.md", "LICENSE.md"}
        root_docs = [
            path.name
            for path in sidecar_root.iterdir()
            if path.is_file() and path.suffix.lower() in {".md", ".json"}
        ]
        unexpected = sorted(name for name in root_docs if name not in allowed_root_docs)
        if unexpected:
            failures.append(_fail(f"unexpected root docs outside declared alias policy: {unexpected}"))
        else:
            _ok("root doc surface is limited to README/LICENSE and declared migration aliases")
    except Exception as e:
        failures.append(_fail(f"doc registry smoke checks failed: {e}"))

    # =============================================================
    # T2.5 ACTIVE TRANCHE LEDGER (added 2026-05-11)
    # =============================================================
    # Verifies that migration v5, the new tables, the tranche_checklist
    # projection, and the close_tranche handler are all in place.
    # =============================================================

    _section("47. T2.5: migration v5 applied — decision_records table exists")
    try:
        state.store.query("SELECT COUNT(*) AS n FROM decision_records;")
        _ok("decision_records table exists (migration v5)")
    except Exception as e:
        failures.append(_fail(f"decision_records table missing: {e}"))

    _section("48. T2.5: migration v5 applied — active_tranche table exists")
    try:
        state.store.query("SELECT COUNT(*) AS n FROM active_tranche;")
        _ok("active_tranche table exists (migration v5)")
    except Exception as e:
        failures.append(_fail(f"active_tranche table missing: {e}"))

    _section("49. T2.5: tranche_checklist projection is queryable")
    try:
        cl = state.projections.read("tranche_checklist")
        _ok(f"tranche_checklist projection returned {len(cl.rows)} rows "
            f"(last_refreshed={cl.last_refreshed_at[:19] if cl.last_refreshed_at else '?'})")
        # Verify the checklist has the expected items when a tranche IS declared.
        # No tranche is active in a fresh smoke run; rows may be empty or 9 items.
        # Just verify the projection is alive (no exception = pass).
    except Exception as e:
        failures.append(_fail(f"tranche_checklist projection failed: {e}"))

    _section("50. T2.5: close_tranche handler registered + declare/decision handlers present")
    router_handlers = state.router.handlers()
    required_t25 = ("declare_tranche", "update_tranche", "record_decision",
                    "smoke_pass", "close_tranche")
    missing_handlers = [h for h in required_t25 if h not in router_handlers]
    if not missing_handlers:
        _ok(f"all T2.5 handlers registered: {list(required_t25)}")
    else:
        failures.append(_fail(f"missing T2.5 handlers: {missing_handlers}"))

    # Quick round-trip: declare a tranche, record a decision, check checklist updates.
    _section("51. T2.5: round-trip — declare tranche + record decision")
    try:
        live_tranche = state.tranche_manager.get_current()
        if live_tranche and not live_tranche.title.startswith("T_SMOKE"):
            _ok(
                f"live tranche already active ({live_tranche.title}) — "
                "skipping synthetic declare/decision round-trip"
            )
            decisions_row = next(
                (r for r in cl.rows if r.get("item_id") == "tranche_declared"), None
            )
            if decisions_row and decisions_row.get("status") == "pass":
                _ok("tranche_checklist remains live during active user tranche")
            else:
                failures.append(_fail("tranche_checklist missing pass status during active user tranche"))
            raise StopIteration

        # Idempotent setup: seal any leftover smoke-test tranche from a prior run.
        stale = state.store.query(
            "SELECT tranche_id FROM active_tranche "
            "WHERE status = 'active' AND title LIKE 'T_SMOKE%';"
        )
        for _row in stale:
            state.store.execute(
                "UPDATE active_tranche SET status = 'parked', closed_at = ? "
                "WHERE tranche_id = ?;",
                (now_iso(), _row["tranche_id"]),
            )
        if stale:
            state.store.set_meta("current_tranche_scope", "{}")
            _ok(f"cleaned up {len(stale)} stale smoke-test tranche(s)")

        td_request = {
            "title": "T_SMOKE Active Tranche Ledger Test",
            "scope": "Smoke-test round-trip for T2.5 plumbing.",
            "non_goals": "Not a real tranche.",
            "completion_criteria": "smoke_test PASS",
        }
        td_payload = state.blob_store.put_json(td_request)
        # Use human:smoketest which is already acked by §5 above.
        td_env = SidecarEnvelope.new(
            object_type="tranche",
            actor_id="human:smoketest",
            operation_intent="declare_tranche",
            payload_ref=td_payload,
        )
        td_result = state.router.dispatch(td_env)
        if td_result.status not in ("accepted", "completed"):
            failures.append(_fail(f"declare_tranche status={td_result.status}"))
        else:
            td_response = state.blob_store.get_json(td_result.payload_ref)
            tranche_id = td_response.get("tranche_id")
            _ok(f"declare_tranche: tranche_id={tranche_id}")

            # Record a decision.
            dr_request = {
                "title": "Use typed DecisionRecord objects for Park Phase notes",
                "context": "Smoke test context",
                "rationale": "Enables compile-and-seal vs. reconstruct-and-write",
                "outcome": "DecisionRecord → decision_records table",
                "impact_area": "architecture",
                "importance": 8,
            }
            dr_payload = state.blob_store.put_json(dr_request)
            dr_env = SidecarEnvelope.new(
                object_type="decision",
                actor_id="human:smoketest",
                operation_intent="record_decision",
                payload_ref=dr_payload,
            )
            dr_result = state.router.dispatch(dr_env)
            if dr_result.status not in ("accepted", "completed"):
                failures.append(_fail(f"record_decision status={dr_result.status}"))
            else:
                dr_response = state.blob_store.get_json(dr_result.payload_ref)
                _ok(f"record_decision: decision_id={dr_response.get('decision_id')}")

            # Check checklist reflects the state.
            cl_after = state.projections.read("tranche_checklist")
            tranche_declared_row = next(
                (r for r in cl_after.rows if r.get("item_id") == "tranche_declared"), None
            )
            if tranche_declared_row and tranche_declared_row.get("status") == "pass":
                _ok("tranche_checklist: tranche_declared=pass after declare")
            else:
                failures.append(_fail(
                    f"tranche_checklist: tranche_declared status="
                    f"{(tranche_declared_row or {}).get('status')!r}"
                ))
            decisions_row = next(
                (r for r in cl_after.rows if r.get("item_id") == "decisions_recorded"), None
            )
            if decisions_row and decisions_row.get("status") in ("pass", "warn"):
                _ok(f"tranche_checklist: decisions_recorded={decisions_row['status']}")
            else:
                failures.append(_fail(
                    f"tranche_checklist: decisions_recorded status="
                    f"{(decisions_row or {}).get('status')!r}"
                ))

            # Clean up: seal the smoke-test tranche so subsequent runs can declare again.
            # (Status → 'parked', bypassing full closeout since this is a test fixture.)
            try:
                state.store.execute(
                    "UPDATE active_tranche SET status = 'parked', closed_at = ? "
                    "WHERE tranche_id = ?;",
                    (state.store.get_meta("installed_at") or "cleanup",  # any timestamp
                     tranche_id),
                )
                state.store.set_meta("current_tranche_scope", "{}")
                _ok(f"smoke-test tranche sealed (idempotent cleanup)")
            except Exception as cleanup_e:
                _ok(f"cleanup warning (non-fatal): {cleanup_e}")
    except StopIteration:
        pass
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        failures.append(_fail(f"T2.5 round-trip failed: {e}"))

    _section("53. T3: schema v6 applied — viewport_state projection table exists")
    if state.store.schema_version() >= 6:
        _ok(f"schema_version={state.store.schema_version()}")
    else:
        failures.append(_fail(f"schema_version={state.store.schema_version()} (expected >= 6)"))

    _section("54. T3: evidence_bag projection is REAL")
    evidence_projection = state.projections.read("evidence_bag")
    if evidence_projection.rows:
        sample = evidence_projection.rows[0]
        _ok(f"evidence_bag rows={len(evidence_projection.rows)}")
        if sample.get("evidence_id") and sample.get("hash") and sample.get("kind"):
            _ok("evidence_bag sample row includes evidence_id/hash/kind")
        else:
            failures.append(_fail("evidence_bag sample row missing key fields"))
    else:
        failures.append(_fail("evidence_bag projection has no rows"))

    _section("55. T3: viewport_state projection is REAL")
    viewport_projection = state.projections.read("viewport_state")
    if viewport_projection.rows:
        row = viewport_projection.rows[0]
        topbar = _json2.loads(row.get("topbar_json") or "{}")
        focus = _json2.loads(row.get("focus_json") or "{}")
        present = _json2.loads(row.get("present_json") or "{}")
        future = _json2.loads(row.get("future_json") or "{}")
        log_payload = _json2.loads(row.get("log_json") or "{}")
        if topbar.get("pills"):
            _ok(f"viewport_state.topbar has {len(topbar['pills'])} pills")
        else:
            failures.append(_fail("viewport_state.topbar_json missing pills"))
        if focus.get("options"):
            _ok(f"viewport_state.focus exposes {len(focus['options'])} surfaces")
        else:
            failures.append(_fail("viewport_state.focus_json missing options"))
        if present.get("current_state") and "contract" in present:
            _ok("viewport_state.present has current_state + contract")
        else:
            failures.append(_fail("viewport_state.present_json missing current_state/contract"))
        if future.get("drift_checks"):
            _ok(f"viewport_state.future has {len(future['drift_checks'])} drift checks")
        else:
            failures.append(_fail("viewport_state.future_json missing drift_checks"))
        if "lines" in log_payload:
            _ok(f"viewport_state.log has {len(log_payload['lines'])} log lines")
        else:
            failures.append(_fail("viewport_state.log_json missing lines"))
    else:
        failures.append(_fail("viewport_state projection has no rows"))

    _section("56. T3: Tk monitoring UI imports and instantiates")
    try:
        import tkinter as _tk
        from src.ui.main_window import MonitoringConsole

        root = _tk.Tk()
        root.withdraw()
        app = MonitoringConsole(root, state)
        root.update_idletasks()
        root.update()
        root.destroy()
        _ok(f"MonitoringConsole instantiated: {type(app).__name__}")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        failures.append(_fail(f"Tk monitoring UI failed to initialize: {e}"))

    _section("57. TYPO GUARD: warn on any lingering 'constraint' misspelling")
    typo_hits = _find_constraint_typo_hits(sidecar_root)
    text_hits = typo_hits["text_hits"]
    db_hits = typo_hits["db_hits"]
    if not text_hits and not db_hits:
        _ok("no lingering 'constrant' instances found in text files or SQLite data")
    else:
        warnings.append(_warn(
            "found lingering 'constrant' usage; intended spelling is 'constraint'. "
            "Review these locations and repair them if the typo is unintended."
        ))
        for hit in text_hits:
            _warn(f"text hit: {hit}")
        for hit in db_hits:
            _warn(f"db hit: {hit}")

    _section("58. T4: migration v7 applied — approval/session tables exist")
    try:
        state.store.query("SELECT COUNT(*) AS n FROM approval_requests;")
        state.store.query("SELECT COUNT(*) AS n FROM agent_sessions;")
        _ok("approval_requests + agent_sessions tables exist (migration v7)")
    except Exception as e:
        failures.append(_fail(f"T4 tables missing: {e}"))

    _section("59. T4: cold-team continuity docs exist and are referenced")
    required_docs = [
        where_now_doc_path,
        target_state_doc_path,
        northstars_doc_path,
        dev_log_doc_path,
    ]
    missing_docs = [str(path.relative_to(sidecar_root)) for path in required_docs if not path.is_file()]
    if missing_docs:
        failures.append(_fail(f"missing T4 continuity docs: {missing_docs}"))
    else:
        _ok("T4 continuity docs exist at canonical registry-backed paths")
        onboarding_text = onboarding_doc_path.read_text(encoding="utf-8")
        if all(
            name in onboarding_text
            for name in (
                doc_relpath(sidecar_root, "where_we_are_now"),
                doc_relpath(sidecar_root, "target_state"),
                doc_relpath(sidecar_root, "northstars"),
                doc_relpath(sidecar_root, "dev_log"),
            )
        ):
            _ok("ONBOARDING.md references the continuity + target-state docs")
        else:
            failures.append(_fail("ONBOARDING.md does not reference all continuity + target-state docs"))

    _section("60. T4: handoff projection is REAL")
    handoff_projection = state.projections.read("handoff")
    if handoff_projection.rows:
        row = handoff_projection.rows[0]
        latest_closed = _json2.loads(row.get("latest_closed_tranche_json") or "{}")
        active_horizon = _json2.loads(row.get("active_horizon_json") or "{}")
        reading_order = _json2.loads(row.get("reading_order_json") or "[]")
        verification_commands = _json2.loads(row.get("verification_commands_json") or "[]")
        if latest_closed.get("title"):
            _ok(f"handoff.latest_closed_tranche={latest_closed['title']}")
        elif installed_mode:
            _ok("installed context: handoff latest_closed_tranche may be empty before the first local park")
        else:
            failures.append(_fail("handoff.latest_closed_tranche_json empty"))
        if active_horizon.get("current") and active_horizon.get("label") == "Next horizon":
            _ok("handoff.active_horizon is populated with explicit Next horizon semantics")
        else:
            failures.append(_fail("handoff.active_horizon_json missing Next horizon semantics"))
        if (
            doc_relpath(sidecar_root, "where_we_are_now") in reading_order
            and doc_relpath(sidecar_root, "target_state") in reading_order
            and doc_relpath(sidecar_root, "dev_log") in reading_order
        ):
            _ok("handoff.reading_order includes continuity + target-state docs")
        else:
            failures.append(_fail("handoff.reading_order_json missing continuity + target-state docs"))
        if any("projection handoff" in cmd for cmd in verification_commands):
            _ok("handoff.verification_commands includes projection handoff")
        else:
            failures.append(_fail("handoff.verification_commands missing projection handoff"))
    else:
        failures.append(_fail("handoff projection has no rows"))

    _section("61. T4: MCP sidecar/submit supports contract ack + approval request")
    try:
        from src.interfaces.mcp_interface import MCPHandler
        from src.lib.common import gen_id

        handler = MCPHandler(state)
        client_name = f"smoke_t4_{gen_id('')[-6:]}"
        target_rel = f"smoke_test/{client_name}.txt"

        ack_msg = {
            "jsonrpc": "2.0",
            "id": 101,
            "method": "sidecar/submit",
            "params": {
                "_meta": {"client_name": client_name},
                "operationIntent": "acknowledge_contract",
                "objectType": "contract_ack",
            },
        }
        ack_response = handler.handle_message(ack_msg)
        if ack_response and ack_response.get("result", {}).get("accepted"):
            _ok(f"MCP sidecar/submit ack accepted for agent:mcp:{client_name}")
        else:
            failures.append(_fail(f"MCP ack response unexpected: {ack_response}"))

        submit_msg = {
            "jsonrpc": "2.0",
            "id": 102,
            "method": "sidecar/submit",
            "params": {
                "_meta": {"client_name": client_name},
                "operationIntent": "request_authority_elevation",
                "objectType": "authority_request",
                "payload": {
                    "requested_level": "Apply",
                    "operation_intent": "tool_invoked",
                    "summary": "Smoke-test bounded workspace write",
                    "justification": "Need one approved T4 workspace write to verify the proposal-approval loop.",
                    "scope_pattern": {
                        "tool_name": "text_file_writer",
                        "target_domain": "workspace",
                        "path": target_rel,
                    },
                    "source_channel": "mcp",
                },
            },
        }
        submit_response = handler.handle_message(submit_msg)
        submit_payload = ((submit_response or {}).get("result") or {}).get("payload") or {}
        request_id = submit_payload.get("request_id")
        if request_id:
            _ok(f"MCP approval request created: {request_id}")
        else:
            failures.append(_fail(f"MCP approval request missing request_id: {submit_response}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T4 MCP sidecar/submit failed: {e}"))
        request_id = ""
        target_rel = ""
        client_name = ""

    _section("62. T4: approval queue surfaces the pending request")
    if request_id:
        state.projections.refresh("human_dashboard")
        hd_row = _first_projection_row(state.projections.read("human_dashboard").rows)
        pending = _json2.loads(hd_row.get("pending_approvals_json") or "[]")
        if any(item.get("request_id") == request_id for item in pending):
            _ok("human_dashboard.pending_approvals_json includes the MCP request")
        else:
            failures.append(_fail("pending approval missing from human_dashboard"))
        if any(item.request_id == request_id for item in state.human_approval_manager.pending()):
            _ok("human_approval_manager.pending() includes the MCP request")
        else:
            failures.append(_fail("human_approval_manager.pending() missing the MCP request"))

    _section("63. T4: approval grant enables bounded workspace write")
    if request_id:
        approve_payload = state.blob_store.put_json(
            {
                "request_id": request_id,
                "expires_minutes": 60,
                "single_use": True,
                "decision_reason": "smoke test approval",
            }
        )
        approve_env = SidecarEnvelope.new(
            object_type="authority_grant",
            actor_id="human:smoketest",
            operation_intent="approve_authority_request",
            payload_ref=approve_payload,
        )
        approve_result = state.router.dispatch(approve_env)
        approve_response = state.blob_store.get_json(approve_result.payload_ref) if approve_result.payload_ref else {}
        grant_id = approve_response.get("grant_id")
        if grant_id:
            _ok(f"approval produced grant_id={grant_id}")
        else:
            failures.append(_fail("approval response missing grant_id"))

        tool_payload = state.blob_store.put_json(
            {
                "tool_name": "text_file_writer",
                "arguments": {
                    "path": target_rel,
                    "content": "T4 smoke approved write\n",
                    "confirm": True,
                    "create_dirs": True,
                    "target_domain": "workspace",
                    "validate_after_write": True,
                    "file_type": "text",
                },
            }
        )
        tool_env = SidecarEnvelope.new(
            object_type="tool_invocation",
            actor_id=f"agent:mcp:{client_name}",
            operation_intent="tool_invoked",
            payload_ref=tool_payload,
        )
        tool_result = state.router.dispatch(tool_env)
        tool_response = state.blob_store.get_json(tool_result.payload_ref) if tool_result.payload_ref else {}
        result_payload = tool_response.get("result", tool_response)
        target_file = sidecar_root / "workspaces" / Path(target_rel)
        if tool_result.status in ("accepted", "completed") and target_file.is_file():
            _ok(f"approved workspace write created {target_file.relative_to(sidecar_root).as_posix()}")
        else:
            failures.append(_fail(f"approved workspace write failed: status={tool_result.status}"))
        if target_file.is_file():
            content = target_file.read_text(encoding="utf-8")
            if "T4 smoke approved write" in content:
                _ok("approved workspace write content matches expectation")
            else:
                failures.append(_fail("approved workspace write content mismatch"))
        if grant_id:
            row = state.store.query_one("SELECT consumed FROM grants WHERE grant_id = ?;", (grant_id,))
            if row and int(row["consumed"]) == 1:
                _ok("single-use grant was consumed after successful write")
            else:
                failures.append(_fail("single-use grant was not consumed"))
        state.projections.refresh("human_dashboard")
        hd_row = _first_projection_row(state.projections.read("human_dashboard").rows)
        pending = _json2.loads(hd_row.get("pending_approvals_json") or "[]")
        if not any(item.get("request_id") == request_id for item in pending):
            _ok("approved request left the pending approval queue")
        else:
            failures.append(_fail("approved request still appears in pending approvals"))

    _section("64. T4: continuity docs align with latest parked tranche")
    latest_closed = state.journal_manager.query(kind="tranche", status="closed", limit=1)
    latest_title = latest_closed[0].title if latest_closed else ""
    where_now_text = where_now_doc_path.read_text(encoding="utf-8")
    dev_log_text = dev_log_doc_path.read_text(encoding="utf-8")
    northstars_text = northstars_doc_path.read_text(encoding="utf-8")
    if latest_title and latest_title in where_now_text:
        _ok("WE_ARE_HERE_NOW.md names the latest parked tranche")
    elif installed_mode:
        _ok("installed context: WE_ARE_HERE_NOW.md can point at the current shipped baseline before local parks exist")
    else:
        failures.append(_fail("WE_ARE_HERE_NOW.md does not name the latest parked tranche"))
    active_tranche_now = state.tranche_manager.get_current()
    if active_tranche_now:
        if "Current tranche:" in where_now_text and "Next horizon" in northstars_text:
            _ok("handoff docs separate current tranche from next horizon")
        else:
            failures.append(_fail("handoff docs do not separate current tranche from next horizon"))
    else:
        if "Next horizon:" in where_now_text and "Active horizon:" not in where_now_text and "Next horizon" in northstars_text:
            _ok("parked-state handoff docs use Next horizon wording")
        else:
            failures.append(_fail("parked-state handoff docs still use ambiguous Active horizon wording"))
    if "T4" in dev_log_text:
        _ok("DEV_LOG.md contains the T4 milestone entry")
    else:
        failures.append(_fail("DEV_LOG.md missing the T4 milestone entry"))

    _section("64.5. T10.4: authoritative park drift helper reports aligned parked state")
    try:
        drift = evaluate_park_continuity_drift(state)
        if drift.get("ok"):
            _ok("authoritative park drift helper reports aligned latest-closeout and WE_ARE_HERE_NOW state")
        else:
            failures.append(_fail(f"authoritative park drift helper reported unexpected issues: {drift.get('issues')}"))
    except Exception as e:
        failures.append(_fail(f"T10.4 park drift helper failed: {e}"))

    _section("64.6. T10.4: declare_tranche blocks when authoritative park drift exists")
    original_where_now = where_now_doc_path.read_text(encoding="utf-8")
    expected_phrase = "Current tranche:" if state.tranche_manager.get_current() else "Next horizon:"
    broken_where_now = (
        original_where_now.replace(expected_phrase, "Broken horizon:", 1)
        if expected_phrase in original_where_now
        else (original_where_now + "\nBroken horizon:\n")
    )
    try:
        where_now_doc_path.write_text(broken_where_now, encoding="utf-8")
        bad_declare_payload = state.blob_store.put_json(
            {
                "title": "T10.4 drift block smoke fixture",
                "scope": "Prove declare_tranche refuses to start on top of continuity drift.",
                "non_goals": "No actual tranche should be created.",
                "completion_criteria": "declare_tranche returns a drift-blocked failure.",
            }
        )
        bad_declare_env = SidecarEnvelope.new(
            object_type="tranche",
            actor_id="human:smoketest",
            operation_intent="declare_tranche",
            payload_ref=bad_declare_payload,
        )
        bad_declare_result = state.router.dispatch(bad_declare_env)
        bad_declare_payload_data = state.blob_store.get_json(bad_declare_result.payload_ref) if bad_declare_result.payload_ref else {}
        error_text = str(bad_declare_payload_data.get("error", ""))
        if bad_declare_result.status == "failed" and "declare_tranche blocked until Park/continuity drift is resolved" in error_text:
            _ok("declare_tranche fails fast when WE_ARE_HERE_NOW drift is introduced")
        else:
            failures.append(_fail(f"declare_tranche did not expose the expected drift-block failure: {bad_declare_result.status} / {bad_declare_payload_data}"))
    except Exception as e:
        failures.append(_fail(f"T10.4 declare_tranche drift blocking failed: {e}"))
    finally:
        where_now_doc_path.write_text(original_where_now, encoding="utf-8")
        state.projections.refresh("handoff")

    _section("65. T5: local-agent runtime surfaces are wired")
    try:
        status = state.local_agent_runtime.status()
        if status.get("status") == "ok":
            _ok("local_agent_runtime.status() returned ok")
        else:
            failures.append(_fail(f"local_agent_runtime.status unexpected: {status}"))
        if "current_agent_status" in status and "active_local_sessions" in status:
            _ok("local agent status includes runtime + session surfaces")
        else:
            failures.append(_fail("local agent status missing runtime/session keys"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T5 local agent status failed: {e}"))

    local_actor = ""
    local_rel = ""
    local_request_id = ""
    local_session_id = ""
    second_run: dict = {}

    _section("66. T5: local agent can request approval through the spine")
    try:
        from src.lib.common import gen_id

        local_actor = f"agent:local:smoke_t5_{gen_id('')[-6:]}"
        local_rel = f"smoke_test/{local_actor.split(':')[-1]}.txt"
        first_run = state.local_agent_runtime.run(
            prompt="Read bootstrap, then request approval for a bounded workspace proof write.",
            actor_id=local_actor,
            model="qwen3.5:9b",
            max_rounds=3,
            mock_responses=[
                safe_json_dumps(
                    {
                        "summary": "Need bootstrap context.",
                        "action": {
                            "type": "tool_call",
                            "tool_name": "read_projection",
                            "arguments": {"name": "agent_bootstrap"},
                        },
                    }
                ),
                safe_json_dumps(
                    {
                        "summary": "Need approval before writing the workspace proof file.",
                        "action": {
                            "type": "request_approval",
                            "requested_level": "Apply",
                            "summary": f"Allow the local agent to write workspaces/{local_rel}",
                            "justification": "Need a bounded workspace artifact to prove the T5 local-agent loop.",
                            "scope_pattern": {
                                "tool_name": "text_file_writer",
                                "target_domain": "workspace",
                                "path": local_rel,
                            },
                        },
                    }
                ),
            ],
        )
        local_request_id = ((first_run.get("approval_request") or {}).get("request_id") or "").strip()
        local_session_id = str(first_run.get("session_id", "")).strip()
        if first_run.get("status") == "awaiting_approval" and local_request_id:
            _ok(f"local agent created approval request: {local_request_id}")
        else:
            failures.append(_fail(f"local agent did not reach awaiting_approval as expected: {first_run}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T5 local agent approval-request run failed: {e}"))
        local_actor = ""
        local_rel = ""
        local_request_id = ""
        local_session_id = ""

    _section("67. T5: approved local-agent write completes through the spine")
    if local_request_id and local_actor and local_rel:
        try:
            approve_payload = state.blob_store.put_json(
                {
                    "request_id": local_request_id,
                    "expires_minutes": 60,
                    "single_use": True,
                    "decision_reason": "smoke test local-agent approval",
                }
            )
            approve_env = SidecarEnvelope.new(
                object_type="authority_grant",
                actor_id="human:smoketest",
                operation_intent="approve_authority_request",
                payload_ref=approve_payload,
            )
            approve_result = state.router.dispatch(approve_env)
            approve_response = state.blob_store.get_json(approve_result.payload_ref) if approve_result.payload_ref else {}
            grant_id = approve_response.get("grant_id")
            if grant_id:
                _ok(f"local-agent approval produced grant_id={grant_id}")
            else:
                failures.append(_fail("local-agent approval response missing grant_id"))

            final_text = "T5 smoke local-agent proof through the spine\n"
            second_run = state.local_agent_runtime.run(
                prompt="With approval granted, write the bounded workspace proof file and conclude.",
                actor_id=local_actor,
                model="qwen3.5:9b",
                max_rounds=3,
                mock_responses=[
                    safe_json_dumps(
                        {
                            "summary": "Approval exists; write the workspace proof file.",
                            "action": {
                                "type": "tool_call",
                                "tool_name": "text_file_writer",
                                "arguments": {
                                    "path": local_rel,
                                    "content": final_text,
                                    "target_domain": "workspace",
                                },
                            },
                        }
                    ),
                    safe_json_dumps(
                        {
                            "summary": "The bounded workspace write completed through the spine.",
                            "action": {"type": "final", "message": "T5 smoke proof complete."},
                        }
                    ),
                ],
            )
            if second_run.get("status") == "completed":
                _ok("local agent completed the bounded write loop")
            else:
                failures.append(_fail(f"local agent did not complete after approval: {second_run}"))

            proof_path = sidecar_root / "workspaces" / Path(local_rel)
            if proof_path.is_file():
                actual_text = proof_path.read_text(encoding="utf-8")
                if actual_text == final_text:
                    _ok(f"local agent wrote expected workspace file {proof_path.relative_to(sidecar_root)}")
                else:
                    failures.append(_fail("local agent workspace file content mismatch"))
            else:
                failures.append(_fail(f"local agent workspace file missing: {proof_path}"))

            session = state.agent_session_manager.get(local_session_id) if local_session_id else None
            if session and session.channel == "local":
                _ok("local agent session is visible through agent_session_manager")
            else:
                failures.append(_fail("local agent session not visible after run"))

            authority_row = state.store.query_one(
                """
                SELECT actor_id, base_level, granted_by FROM authorities
                WHERE actor_id = ?;
                """,
                (local_actor,),
            )
            if authority_row and authority_row["base_level"] == "Propose":
                _ok("local agent actor has an explicit authorities row")
            else:
                failures.append(_fail("local agent actor missing explicit authorities row"))
        except Exception as e:
            traceback.print_exc()
            failures.append(_fail(f"T5 approved local-agent write failed: {e}"))

    _section("67.5. T10.4: project-targeted mutation paths hard-block before tool execution")
    try:
        blocked_cases = [
            (
                "text_file_writer",
                {
                    "path": "README.md",
                    "content": "blocked",
                    "confirm": True,
                    "target_domain": "project",
                },
                "host-project write requires allow_host_project_write=true",
            ),
            (
                "directory_scaffold",
                {
                    "entries": [{"type": "file", "path": "smoke_test/t10_4_blocked.txt", "content": "blocked"}],
                    "confirm": True,
                    "dry_run": False,
                    "target_domain": "project",
                },
                "host-project write requires allow_host_project_write=true",
            ),
            (
                "text_file_writer",
                {
                    "path": ".scaffold/t10_4_blocked.txt",
                    "content": "blocked",
                    "confirm": True,
                    "target_domain": "project",
                    "allow_host_project_write": True,
                },
                "project-targeted mutation may not write into the sidecar runtime subtree",
            ),
        ]
        for tool_name, arguments, expected_error in blocked_cases:
            payload_ref = state.blob_store.put_json({"tool_name": tool_name, "arguments": arguments})
            env = SidecarEnvelope.new(
                object_type="tool_invocation",
                actor_id="human:smoketest",
                operation_intent="tool_invoked",
                payload_ref=payload_ref,
            )
            result = state.router.dispatch(env)
            payload = state.blob_store.get_json(result.payload_ref) if result.payload_ref else {}
            error_text = str(payload.get("error", ""))
            if result.status == "rejected" and expected_error in error_text:
                _ok(f"{tool_name} rejected early with the expected trust-gate reason")
            else:
                failures.append(_fail(f"{tool_name} hard-block mismatch: status={result.status} payload={payload}"))
        if not (sidecar_root / ".scaffold" / "t10_4_blocked.txt").exists():
            _ok("blocked project-targeted mutation created no sidecar-subtree file")
        else:
            failures.append(_fail("blocked project-targeted mutation wrote into the sidecar subtree"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T10.4 project hard-block checks failed: {e}"))

    _section("67.6. T10.4: scaffold approval scope is manifest-aware and exact")
    try:
        from src.lib.common import gen_id as _gen_id

        scaffold_actor = f"agent:local:smoke_t10_4_{_gen_id('')[-6:]}"
        scaffold_entries = [
            {"type": "directory", "path": "smoke_test/t10_4_scope"},
            {"type": "file", "path": "smoke_test/t10_4_scope/alpha.txt", "content": "alpha\n"},
        ]
        scaffold_run = state.local_agent_runtime.run(
            prompt="Request approval for a bounded workspace scaffold, then stop.",
            actor_id=scaffold_actor,
            model="qwen3.5:9b",
            max_rounds=2,
            mock_responses=[
                safe_json_dumps(
                    {
                        "summary": "Need approval before creating the workspace scaffold.",
                        "action": {
                            "type": "tool_call",
                            "tool_name": "directory_scaffold",
                            "arguments": {"entries": scaffold_entries, "target_domain": "workspace"},
                        },
                    }
                ),
            ],
        )
        scaffold_request_id = str((scaffold_run.get("approval_request") or {}).get("request_id") or "")
        if scaffold_run.get("status") == "awaiting_approval" and scaffold_request_id:
            _ok(f"directory_scaffold requested approval through the local-agent runtime: {scaffold_request_id}")
        else:
            failures.append(_fail(f"directory_scaffold approval request did not stop as expected: {scaffold_run}"))
            scaffold_request_id = ""

        scope_record = state.human_approval_manager.get(scaffold_request_id) if scaffold_request_id else None
        expected_entry_paths = sorted(["smoke_test/t10_4_scope", "smoke_test/t10_4_scope/alpha.txt"])
        if scope_record and scope_record.scope_pattern.get("entry_paths") == expected_entry_paths:
            _ok("local-agent scaffold approval request derived exact entry_paths scope")
        else:
            failures.append(_fail(f"directory_scaffold approval scope missing exact entry_paths: {getattr(scope_record, 'scope_pattern', None)}"))

        if scaffold_request_id:
            approve_payload = state.blob_store.put_json(
                {
                    "request_id": scaffold_request_id,
                    "expires_minutes": 60,
                    "single_use": False,
                    "decision_reason": "smoke test scaffold approval",
                }
            )
            approve_env = SidecarEnvelope.new(
                object_type="authority_grant",
                actor_id="human:smoketest",
                operation_intent="approve_authority_request",
                payload_ref=approve_payload,
            )
            approve_result = state.router.dispatch(approve_env)
            approve_payload_data = state.blob_store.get_json(approve_result.payload_ref) if approve_result.payload_ref else {}
            if approve_result.status in ("accepted", "completed") and approve_payload_data.get("grant_id"):
                _ok("directory_scaffold approval grant issued")
            else:
                failures.append(_fail(f"directory_scaffold approval grant failed: {approve_result.status} / {approve_payload_data}"))

            scaffold_apply = state.local_agent_runtime.run(
                prompt="Use the approved scaffold manifest, then finish.",
                actor_id=scaffold_actor,
                model="qwen3.5:9b",
                max_rounds=3,
                mock_responses=[
                    safe_json_dumps(
                        {
                            "summary": "Apply the approved scaffold manifest.",
                            "action": {
                                "type": "tool_call",
                                "tool_name": "directory_scaffold",
                                "arguments": {"entries": scaffold_entries, "target_domain": "workspace"},
                            },
                        }
                    ),
                    safe_json_dumps({"summary": "Scaffold applied.", "action": {"type": "final", "message": "done"}}),
                ],
            )
            created_scaffold_file = sidecar_root / "workspaces" / "smoke_test" / "t10_4_scope" / "alpha.txt"
            if scaffold_apply.get("status") == "completed" and created_scaffold_file.is_file():
                _ok("directory_scaffold succeeds when invocation entries exactly match approved entry_paths")
            else:
                failures.append(_fail(f"directory_scaffold exact-scope approval did not apply cleanly: {scaffold_apply}"))

            changed_entries = scaffold_entries + [
                {"type": "file", "path": "smoke_test/t10_4_scope/beta.txt", "content": "beta\n"},
            ]
            scaffold_changed = state.local_agent_runtime.run(
                prompt="Try the scaffold again after changing the manifest.",
                actor_id=scaffold_actor,
                model="qwen3.5:9b",
                max_rounds=2,
                mock_responses=[
                    safe_json_dumps(
                        {
                            "summary": "The scaffold manifest changed; try again.",
                            "action": {
                                "type": "tool_call",
                                "tool_name": "directory_scaffold",
                                "arguments": {"entries": changed_entries, "target_domain": "workspace"},
                            },
                        },
                    ),
                ],
            )
            changed_request = str((scaffold_changed.get("approval_request") or {}).get("request_id") or "")
            if scaffold_changed.get("status") == "awaiting_approval" and changed_request and changed_request != scaffold_request_id:
                _ok("directory_scaffold stops matching the grant when entry_paths change")
            else:
                failures.append(_fail(f"directory_scaffold changed manifest did not require fresh approval: {scaffold_changed}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T10.4 scaffold entry_paths scope checks failed: {e}"))

    _section("68. T5: local-agent stop requests are honored cooperatively")
    try:
        stop_actor = f"agent:local:stop_t5_{gen_id('')[-6:]}"
        stop_result = state.local_agent_runtime.request_stop(actor_id=stop_actor)
        if stop_result.get("stop_requested"):
            _ok("local-agent stop request recorded")
        else:
            failures.append(_fail(f"local-agent stop request did not acknowledge: {stop_result}"))
        stopped_run = state.local_agent_runtime.run(
            prompt="This run should stop before taking any action.",
            actor_id=stop_actor,
            model="qwen3.5:9b",
            max_rounds=2,
            mock_responses=[
                safe_json_dumps(
                    {
                        "summary": "Would have read bootstrap.",
                        "action": {
                            "type": "tool_call",
                            "tool_name": "read_projection",
                            "arguments": {"name": "agent_bootstrap"},
                        },
                    }
                )
            ],
        )
        if stopped_run.get("status") == "stopped":
            _ok("local-agent cooperative stop ended the run")
        else:
            failures.append(_fail(f"local-agent stop was not honored: {stopped_run}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T5 local-agent stop path failed: {e}"))

    _section("69. T6: schema v8 applied — memory + change_hunks tables exist")
    if state.store.schema_version() >= 8:
        _ok(f"schema_version={state.store.schema_version()}")
    else:
        failures.append(_fail(f"schema_version={state.store.schema_version()} (expected >= 8)"))
    for table_name in ("session_memory_items", "change_hunks"):
        row = state.store.query_one(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = ?;
            """,
            (table_name,),
        )
        if row and row["name"] == table_name:
            _ok(f"{table_name} table exists")
        else:
            failures.append(_fail(f"{table_name} table missing"))

    _section("70. T6: agent bootstrap exposes STM + Bag + Evidence Shelf")
    try:
        bootstrap = state.projections.refresh("agent_bootstrap")
        row = _first_projection_row(bootstrap.rows)
        stm_items = json.loads(row.get("stm_json") or "[]")
        bag_items = json.loads(row.get("bag_json") or "[]")
        shelf_items = json.loads(row.get("evidence_shelf_json") or "[]")
        if stm_items:
            _ok(f"agent_bootstrap.stm_json has {len(stm_items)} item(s)")
        else:
            failures.append(_fail("agent_bootstrap.stm_json is empty after T6 proof run"))
        if bag_items:
            _ok(f"agent_bootstrap.bag_json has {len(bag_items)} item(s)")
        else:
            failures.append(_fail("agent_bootstrap.bag_json is empty after T6 proof run"))
        if shelf_items:
            _ok(f"agent_bootstrap.evidence_shelf_json has {len(shelf_items)} item(s)")
        else:
            failures.append(_fail("agent_bootstrap.evidence_shelf_json is empty after T6 proof run"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T6 bootstrap memory surfaces failed: {e}"))

    _section("71. T6: viewport memory surfaces + per-hunk provenance are real")
    try:
        viewport = state.projections.refresh("viewport_state")
        row = _first_projection_row(viewport.rows)
        present = json.loads(row.get("present_json") or "{}")
        past = json.loads(row.get("past_json") or "{}")
        memory = present.get("memory") or {}
        if int(memory.get("stm_count", 0)) >= 1 and int(memory.get("shelf_count", 0)) >= 1:
            _ok("viewport present.memory exposes STM and shelf counts")
        else:
            failures.append(_fail(f"viewport present.memory missing expected counts: {memory}"))
        recent_hunks = past.get("recent_change_hunks") or []
        if recent_hunks:
            sample = recent_hunks[0]
            if {"path", "old_start", "new_start"} <= set(sample):
                _ok("viewport past.recent_change_hunks exposes line-range provenance")
            else:
                failures.append(_fail(f"recent_change_hunks sample missing expected keys: {sample}"))
        else:
            failures.append(_fail("viewport past.recent_change_hunks is empty after T6 proof write"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T6 viewport memory surfaces failed: {e}"))

    _section("72. T6: memory manager can summarize the local-agent session")
    if local_session_id:
        try:
            summary = state.memory_manager.session_summary(local_session_id)
            if summary.get("stm_count", 0) >= 1:
                _ok(f"memory_manager.session_summary stm_count={summary['stm_count']}")
            else:
                failures.append(_fail(f"memory summary stm_count too small: {summary}"))
            if summary.get("recent_change_hunks"):
                _ok(f"memory_manager tracked {len(summary['recent_change_hunks'])} change hunk(s)")
            else:
                failures.append(_fail("memory_manager recent_change_hunks empty"))
        except Exception as e:
            traceback.print_exc()
            failures.append(_fail(f"T6 memory summary failed: {e}"))

    _section("73. T7: schema v9 applied — runtime trace tables exist")
    if state.store.schema_version() >= 9:
        _ok(f"schema_version={state.store.schema_version()}")
    else:
        failures.append(_fail(f"schema_version={state.store.schema_version()} (expected >= 9)"))
    for table_name in (
        "local_agent_runs",
        "local_agent_run_rounds",
        "local_agent_runtime_events",
        "local_agent_run_touched_paths",
        "local_agent_run_links",
        "local_agent_claim_grounding",
    ):
        row = state.store.query_one(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = ?;
            """,
            (table_name,),
        )
        if row and row["name"] == table_name:
            _ok(f"{table_name} table exists")
        else:
            failures.append(_fail(f"{table_name} table missing"))

    _section("74. T7: successful, failed, stopped, and retried runs are traced")
    t7_completed_run: dict = {}
    t7_failed_run: dict = {}
    t7_retry_run: dict = {}
    t7_stopped_run: dict = {}
    try:
        from src.lib.common import gen_id

        success_actor = f"agent:local:smoke_t7_success_{gen_id('')[-6:]}"
        failure_actor = f"agent:local:smoke_t7_failure_{gen_id('')[-6:]}"
        stop_actor = f"agent:local:smoke_t7_stop_{gen_id('')[-6:]}"
        t7_completed_run = state.local_agent_runtime.run(
            prompt="Inspect and complete without mutation for T7 smoke.",
            actor_id=success_actor,
            model="qwen3.5:9b",
            max_rounds=2,
            mock_responses=[
                safe_json_dumps(
                    {
                        "summary": "Completed without mutation after inspection.",
                        "action": {"type": "final", "message": "Completed without changing files."},
                    }
                )
            ],
        )
        if t7_completed_run.get("status") == "completed":
            _ok(f"successful traced run completed: {t7_completed_run.get('run_id')}")
        else:
            failures.append(_fail(f"T7 completed run unexpected: {t7_completed_run}"))

        t7_failed_run = state.local_agent_runtime.run(
            prompt="Fail deterministically for T7 recovery classification.",
            actor_id=failure_actor,
            model="qwen3.5:9b",
            max_rounds=2,
            mock_failure="ollama_unreachable",
        )
        if t7_failed_run.get("status") == "failed" and t7_failed_run.get("recovery_class") == "model_transport_error":
            _ok(f"failed traced run classified correctly: {t7_failed_run.get('run_id')}")
        else:
            failures.append(_fail(f"T7 failed run unexpected: {t7_failed_run}"))

        t7_retry_run = state.local_agent_runtime.retry_run(str(t7_failed_run.get("run_id", "")))
        if (
            t7_retry_run.get("status") == "failed"
            and t7_retry_run.get("retried_from_run_id") == t7_failed_run.get("run_id")
        ):
            _ok(f"retry lineage created a fresh run: {t7_retry_run.get('run_id')}")
        else:
            failures.append(_fail(f"T7 retry run unexpected: {t7_retry_run}"))

        stop_result = state.local_agent_runtime.request_stop(actor_id=stop_actor)
        if stop_result.get("stop_requested"):
            _ok("T7 stop request recorded")
        else:
            failures.append(_fail(f"T7 stop request failed: {stop_result}"))
        t7_stopped_run = state.local_agent_runtime.run(
            prompt="This run should stop before taking action for T7 smoke.",
            actor_id=stop_actor,
            model="qwen3.5:9b",
            max_rounds=2,
            mock_responses=[
                safe_json_dumps(
                    {
                        "summary": "Would have read bootstrap.",
                        "action": {
                            "type": "tool_call",
                            "tool_name": "read_projection",
                            "arguments": {"name": "agent_bootstrap"},
                        },
                    }
                )
            ],
        )
        if t7_stopped_run.get("status") == "stopped":
            _ok(f"stopped traced run recorded: {t7_stopped_run.get('run_id')}")
        else:
            failures.append(_fail(f"T7 stopped run unexpected: {t7_stopped_run}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T7 traced run scenarios failed: {e}"))

    _section("75. T7: trace records preserve grounding, recovery, and retry snapshot")
    try:
        completed_run_id = str(t7_completed_run.get("run_id", ""))
        failed_run_id = str(t7_failed_run.get("run_id", ""))
        retry_run_id = str(t7_retry_run.get("run_id", ""))
        stopped_run_id = str(t7_stopped_run.get("run_id", ""))
        if completed_run_id:
            completed_trace = state.run_trace_manager.get_run(completed_run_id)
            completed_grounding = state.run_trace_manager.get_run_grounding(completed_run_id)
            if completed_trace and completed_trace.config_snapshot.get("prompt"):
                _ok("successful run stored config_snapshot_json")
            else:
                failures.append(_fail("successful traced run missing config snapshot"))
            if any(item.get("grounding_kind") == "no_mutation_trace" for item in completed_grounding):
                _ok("successful no-mutation run grounded its final claim")
            else:
                failures.append(_fail(f"successful traced run missing no_mutation_trace grounding: {completed_grounding}"))
        if failed_run_id:
            failed_trace = state.run_trace_manager.get_run(failed_run_id)
            failed_events = state.run_trace_manager.get_run_events(failed_run_id, limit=20)
            if failed_trace and failed_trace.recovery_class == "model_transport_error":
                _ok("failed traced run stored normalized recovery_class")
            else:
                failures.append(_fail(f"failed traced run recovery mismatch: {failed_trace}"))
            if any(event.get("event_type") == "run_failed" for event in failed_events):
                _ok("failed traced run emitted run_failed runtime event")
            else:
                failures.append(_fail(f"failed traced run missing run_failed event: {failed_events}"))
        if retry_run_id:
            retry_trace = state.run_trace_manager.get_run(retry_run_id)
            if (
                retry_trace
                and retry_trace.retried_from_run_id == failed_run_id
                and retry_trace.config_snapshot.get("mock_failure") == "ollama_unreachable"
            ):
                _ok("retry run preserved lineage and replay snapshot")
            else:
                failures.append(_fail(f"retry traced run missing lineage/snapshot: {retry_trace}"))
        if stopped_run_id:
            stopped_trace = state.run_trace_manager.get_run(stopped_run_id)
            if stopped_trace and stopped_trace.status == "stopped":
                _ok("stopped run persisted stopped status")
            else:
                failures.append(_fail(f"stopped traced run missing stopped status: {stopped_trace}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T7 trace detail verification failed: {e}"))

    _section("76. T7: projection surfaces expose runtime cockpit state")
    try:
        runtime_cockpit = state.projections.refresh("runtime_cockpit")
        runtime_row = _first_projection_row(runtime_cockpit.rows)
        recent_runs = json.loads(runtime_row.get("recent_runs_json") or "[]")
        recent_failures = json.loads(runtime_row.get("recent_failures_json") or "[]")
        grounding_counts = json.loads(runtime_row.get("grounding_counts_json") or "{}")
        if recent_runs:
            _ok(f"runtime_cockpit.recent_runs_json has {len(recent_runs)} run(s)")
        else:
            failures.append(_fail("runtime_cockpit.recent_runs_json is empty"))
        if recent_failures:
            _ok(f"runtime_cockpit.recent_failures_json has {len(recent_failures)} failure(s)")
        else:
            failures.append(_fail("runtime_cockpit.recent_failures_json is empty"))
        if grounding_counts:
            _ok("runtime_cockpit exposes grounding counts")
        else:
            failures.append(_fail("runtime_cockpit.grounding_counts_json is empty"))

        bootstrap = state.projections.refresh("agent_bootstrap")
        bootstrap_row = _first_projection_row(bootstrap.rows)
        runtime_summary = json.loads(bootstrap_row.get("runtime_summary_json") or "{}")
        if runtime_summary.get("recent_runs"):
            _ok("agent_bootstrap.runtime_summary_json exposes recent runs")
        else:
            failures.append(_fail("agent_bootstrap.runtime_summary_json is empty"))

        viewport = state.projections.refresh("viewport_state")
        viewport_row = _first_projection_row(viewport.rows)
        present = json.loads(viewport_row.get("present_json") or "{}")
        past = json.loads(viewport_row.get("past_json") or "{}")
        present_runtime = present.get("runtime") or {}
        if present_runtime.get("recent_runs") or present_runtime.get("active_run"):
            _ok("viewport_state.present.runtime exposes runtime summary")
        else:
            failures.append(_fail(f"viewport_state.present.runtime missing runtime summary: {present_runtime}"))
        if past.get("recent_runs"):
            _ok("viewport_state.past.recent_runs exposes recent traced runs")
        else:
            failures.append(_fail("viewport_state.past.recent_runs is empty"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T7 runtime projection surfaces failed: {e}"))

    _section("77. T7: approved local-agent write records touched paths and hunk grounding")
    try:
        traced_write_run_id = str(second_run.get("run_id", ""))
        if traced_write_run_id:
            touched_paths = state.run_trace_manager.get_run_touched_paths(traced_write_run_id)
            grounding = state.run_trace_manager.get_run_grounding(traced_write_run_id)
            if touched_paths:
                _ok(f"traced write run recorded {len(touched_paths)} touched path(s)")
            else:
                failures.append(_fail("traced write run has no touched_path records"))
            if any(str(item.get("linked_hunk_id") or "").strip() for item in touched_paths):
                _ok("traced write run touched-path records link to change hunks")
            else:
                failures.append(_fail(f"traced write run missing linked_hunk_id values: {touched_paths}"))
            if any(item.get("grounding_kind") == "touched_path" for item in grounding):
                _ok("traced write run grounded its final claim in touched paths")
            else:
                failures.append(_fail(f"traced write run missing touched_path grounding: {grounding}"))
        else:
            failures.append(_fail("T5 proof write run_id unavailable for T7 touched-path verification"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T7 touched-path verification failed: {e}"))

    _section("78. T7: Tk local-agent cockpit hydrates from runtime_cockpit")
    try:
        import tkinter as _tk
        from src.ui.local_agent_panel import LocalAgentPanel

        runtime_cockpit = state.projections.refresh("runtime_cockpit")
        runtime_row = _first_projection_row(runtime_cockpit.rows)
        viewport = state.projections.refresh("viewport_state")
        viewport_row = _first_projection_row(viewport.rows)
        bundle = {
            "viewport": {
                "present": json.loads(viewport_row.get("present_json") or "{}"),
                "past": json.loads(viewport_row.get("past_json") or "{}"),
            },
            "runtime_cockpit": {
                "active_run": json.loads(runtime_row.get("active_run_json") or "{}"),
                "recent_runs": json.loads(runtime_row.get("recent_runs_json") or "[]"),
                "recent_failures": json.loads(runtime_row.get("recent_failures_json") or "[]"),
                "latest_recovery_summary": json.loads(runtime_row.get("latest_recovery_summary_json") or "{}"),
                "run_heartbeat": json.loads(runtime_row.get("run_heartbeat_json") or "{}"),
                "last_runtime_event": json.loads(runtime_row.get("last_runtime_event_json") or "{}"),
                "touched_path_counts": json.loads(runtime_row.get("touched_path_counts_json") or "{}"),
                "grounding_counts": json.loads(runtime_row.get("grounding_counts_json") or "{}"),
                "selected_run_ids": json.loads(runtime_row.get("selected_run_ids_json") or "[]"),
            },
        }
        root = _tk.Tk()
        root.withdraw()
        panel = LocalAgentPanel(root, state)
        panel.refresh(bundle)
        root.update_idletasks()
        root.update()
        root.destroy()
        _ok(f"LocalAgentPanel hydrated from runtime_cockpit: {type(panel).__name__}")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        failures.append(_fail(f"T7 Tk cockpit hydration failed: {e}"))

    _section("79. T8: schema v10 applied — teaching sandbox tables exist")
    if state.store.schema_version() >= 10:
        _ok(f"schema_version={state.store.schema_version()}")
    else:
        failures.append(_fail(f"schema_version={state.store.schema_version()} (expected >= 10)"))
    for table_name in (
        "teaching_scenario_runs",
        "teaching_scenario_run_trace_links",
        "teaching_scorecards",
        "teaching_reviewer_exports",
    ):
        row = state.store.query_one(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?;",
            (table_name,),
        )
        if row and row["name"] == table_name:
            _ok(f"{table_name} table exists")
        else:
            failures.append(_fail(f"{table_name} table missing"))

    _section("80. T8: deterministic teaching scenarios pass and fail with trace linkage")
    t8_good_run: dict = {}
    t8_bad_run: dict = {}
    try:
        scenarios = state.training_runway_manager.list_scenarios()
        if len(scenarios) >= 3:
            _ok(f"training scenario inventory has {len(scenarios)} scenario(s)")
        else:
            failures.append(_fail(f"training scenario inventory too small: {scenarios}"))

        created = state.training_runway_manager.create_sandbox("python_notes_cli", reset=True)
        recreated = state.training_runway_manager.create_sandbox("python_notes_cli", reset=True)
        if created.get("sandbox_root") == recreated.get("sandbox_root"):
            _ok("training sandbox create/reset is idempotent")
        else:
            failures.append(_fail(f"training sandbox create/reset mismatch: {created} vs {recreated}"))

        t8_good_run = state.training_runway_manager.run_scenario("python_notes_cli", run_mode="mocked", mock_variant="good")
        good_scorecard = t8_good_run.get("scorecard", {})
        if (
            good_scorecard.get("aggregate_result") == "pass"
            and good_scorecard.get("linked_run_ids")
            and good_scorecard.get("evidence_refs")
            and t8_good_run.get("journal_entry_uid")
        ):
            _ok("mocked good training scenario produced passing trace-linked scorecard")
        else:
            failures.append(_fail(f"T8 mocked good scenario unexpected: {t8_good_run}"))

        t8_bad_run = state.training_runway_manager.run_scenario("python_notes_cli", run_mode="mocked", mock_variant="bad")
        bad_scorecard = t8_bad_run.get("scorecard", {})
        if (
            bad_scorecard.get("aggregate_result") == "fail"
            and any(check.get("status") == "fail" for check in bad_scorecard.get("checks", []))
            and bad_scorecard.get("evidence_refs")
        ):
            _ok("mocked bad training scenario produced failing structured scorecard")
        else:
            failures.append(_fail(f"T8 mocked bad scenario unexpected: {t8_bad_run}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T8 deterministic scenario verification failed: {e}"))

    _section("81. T8: training projection and reviewer export surfaces are real")
    try:
        runway = state.projections.refresh("training_runway")
        runway_row = _first_projection_row(runway.rows)
        inventory = json.loads(runway_row.get("scenario_inventory_json") or "[]")
        recent_runs = json.loads(runway_row.get("recent_runs_json") or "[]")
        recent_scorecards = json.loads(runway_row.get("recent_scorecards_json") or "[]")
        counts = json.loads(runway_row.get("pass_fail_counts_json") or "{}")
        if inventory:
            _ok(f"training_runway inventory exposes {len(inventory)} scenario(s)")
        else:
            failures.append(_fail("training_runway inventory is empty"))
        if len(recent_runs) >= 2:
            _ok(f"training_runway recent_runs exposes {len(recent_runs)} run(s)")
        else:
            failures.append(_fail("training_runway recent_runs missing mocked pass/fail coverage"))
        if recent_scorecards:
            _ok(f"training_runway recent_scorecards exposes {len(recent_scorecards)} scorecard(s)")
        else:
            failures.append(_fail("training_runway recent_scorecards is empty"))
        if counts.get("pass", 0) >= 1 and counts.get("fail", 0) >= 1:
            _ok("training_runway pass/fail counts reflect deterministic pass and fail paths")
        else:
            failures.append(_fail(f"training_runway pass/fail counts unexpected: {counts}"))

        export_payload = state.training_runway_manager.export_review(
            scenario_run_id=str(t8_bad_run.get("scenario_run_id", ""))
        )
        export_md = HERE / str(export_payload.get("markdown_path", ""))
        if export_md.is_file():
            export_text = export_md.read_text(encoding="utf-8")
            if "## Checks" in export_text and "fail" in export_text.lower():
                _ok("training reviewer export shows failed checks clearly")
            else:
                failures.append(_fail("training reviewer export missing failed-check detail"))
        else:
            failures.append(_fail(f"training reviewer export file missing: {export_payload}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"T8 projection/export verification failed: {e}"))

    _section("82. T8: Tk training runway panel hydrates from training projection")
    try:
        import tkinter as _tk
        from src.ui.training_runway_panel import TrainingRunwayPanel

        runway = state.projections.refresh("training_runway")
        runway_row = _first_projection_row(runway.rows)
        bundle = {
            "training_runway": {
                "scenario_inventory": json.loads(runway_row.get("scenario_inventory_json") or "[]"),
                "recent_runs": json.loads(runway_row.get("recent_runs_json") or "[]"),
                "recent_scorecards": json.loads(runway_row.get("recent_scorecards_json") or "[]"),
                "pass_fail_counts": json.loads(runway_row.get("pass_fail_counts_json") or "{}"),
                "latest_live_proof": json.loads(runway_row.get("latest_live_proof_json") or "{}"),
                "reviewer_export_handles": json.loads(runway_row.get("reviewer_export_handles_json") or "[]"),
            }
        }
        root = _tk.Tk()
        root.withdraw()
        panel = TrainingRunwayPanel(root, state)
        panel.refresh(bundle)
        root.update_idletasks()
        root.update()
        root.destroy()
        _ok(f"TrainingRunwayPanel hydrated from training_runway projection: {type(panel).__name__}")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        failures.append(_fail(f"T8 Tk panel hydration failed: {e}"))

    _section("83. T9: schema v11 applied — installed proof table exists")
    if state.store.schema_version() >= 11:
        _ok(f"schema_version={state.store.schema_version()}")
    else:
        failures.append(_fail(f"schema_version={state.store.schema_version()} (expected >= 11)"))
    proof_table = state.store.query_one(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='installed_project_proofs';"
    )
    if proof_table is not None:
        _ok("installed_project_proofs table exists")
    else:
        failures.append(_fail("installed_project_proofs table missing"))

    _section("84. T9: installed-project proof loop completes end to end")
    if INSTALLED_CHILD_SMOKE:
        _ok("installed-child smoke skips recursive installed-project proof loop")
        t9_result = {}
    else:
        try:
            t9_result = state.installed_project_proof_manager.run_proof()
            if t9_result.get("status") == "ok":
                _ok(f"installed proof completed: {t9_result.get('proof_run_id', '')}")
            else:
                failures.append(_fail(f"installed proof failed: {t9_result}"))
            t9_verification = t9_result.get("verification", {})
            if t9_verification.get("ok"):
                _ok("installed proof verification passed")
            else:
                failures.append(_fail(f"installed proof verification failed: {t9_verification}"))
        except Exception as e:
            traceback.print_exc()
            failures.append(_fail(f"T9 installed-project proof raised exception: {e}"))
            t9_result = {}

    _section("85. T9: installed proof projection is REAL")
    try:
        if INSTALLED_CHILD_SMOKE:
            proof_projection = state.projections.refresh("installed_project_proof")
            proof_row = _first_projection_row(proof_projection.rows)
            _ok("installed-child smoke refreshed installed_project_proof projection without recursive proof execution")
        else:
            proof_projection = state.projections.refresh("installed_project_proof")
            proof_row = _first_projection_row(proof_projection.rows)
            latest_proof = json.loads(proof_row.get("latest_proof_json") or "{}")
            proof_verification = json.loads(proof_row.get("verification_result_json") or "{}")
            if latest_proof.get("proof_run_id"):
                _ok(f"installed_project_proof.latest_proof={latest_proof['proof_run_id']}")
            else:
                failures.append(_fail("installed_project_proof.latest_proof_json empty"))
            if proof_verification.get("ok"):
                _ok("installed_project_proof verification result shows ok=true")
            else:
                failures.append(_fail(f"installed_project_proof verification result unexpected: {proof_verification}"))
    except Exception as e:
        traceback.print_exc()
        failures.append(_fail(f"installed_project_proof projection failed: {e}"))
        proof_row = {}

    _section("86. T9: Tk installed proof panel hydrates from installed proof projection")
    try:
        import tkinter as _tk
        from src.ui.installed_project_proof_panel import InstalledProjectProofPanel

        bundle = {
            "installed_project_proof": {
                "fixture_summary": json.loads(proof_row.get("fixture_summary_json") or "{}"),
                "latest_proof": json.loads(proof_row.get("latest_proof_json") or "{}"),
                "recent_proofs": json.loads(proof_row.get("recent_proofs_json") or "[]"),
                "verification_result": json.loads(proof_row.get("verification_result_json") or "{}"),
                "handoff_status": json.loads(proof_row.get("handoff_status_json") or "{}"),
                "supersession_status": json.loads(proof_row.get("supersession_status_json") or "{}"),
            }
        }
        root = _tk.Tk()
        root.withdraw()
        panel = InstalledProjectProofPanel(root, state)
        panel.refresh(bundle)
        root.update_idletasks()
        root.update()
        root.destroy()
        _ok(f"InstalledProjectProofPanel hydrated from installed_project_proof: {type(panel).__name__}")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        failures.append(_fail(f"T9 Tk panel hydration failed: {e}"))

    _section("84. T10: review-gate schema + handlers are live")
    try:
        review_table = state.store.query_one(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tranche_review_packets';"
        )
        if review_table:
            _ok("tranche_review_packets table exists")
        else:
            failures.append(_fail("tranche_review_packets table missing"))
        handlers = state.router.handlers()
        required_t10 = ("request_tranche_review", "return_tranche_review", "approve_tranche_review", "close_tranche")
        missing = [name for name in required_t10 if name not in handlers]
        if not missing:
            _ok("T10 review-gate handlers registered")
        else:
            failures.append(_fail(f"T10 review-gate handlers missing: {missing}"))
    except Exception as e:
        failures.append(_fail(f"T10 review-gate schema/handler check failed: {e}"))

    _section("85. T10: tranche_review_gate projection hydrates")
    try:
        review_projection = state.projections.refresh("tranche_review_gate")
        row = _first_projection_row(review_projection.rows)
        current_tranche = _json2.loads(row.get("current_tranche_json") or "{}")
        allowed_actions = _json2.loads(row.get("allowed_actions_json") or "[]")
        live_tranche = state.tranche_manager.get_current()
        if live_tranche:
            if current_tranche.get("title"):
                _ok(f"tranche_review_gate current_tranche={current_tranche.get('title')}")
            else:
                failures.append(_fail("tranche_review_gate current_tranche_json empty while a tranche is open"))
        else:
            if not current_tranche:
                _ok("tranche_review_gate clears current_tranche_json after park")
            else:
                failures.append(_fail("tranche_review_gate retained current_tranche_json after park"))
        if isinstance(allowed_actions, list):
            _ok(f"tranche_review_gate exposes allowed_actions={allowed_actions}")
        else:
            failures.append(_fail("tranche_review_gate allowed_actions_json malformed"))
    except Exception as e:
        failures.append(_fail(f"T10 tranche_review_gate projection failed: {e}"))

    _section("86. T10: direct close is blocked before review approval")
    review_tranche = state.tranche_manager.get_current()
    review_exercised = False
    temp_review_tranche_id = ""
    if not review_tranche:
        try:
            temp_request = {
                "title": "T10.2 MCP chat review smoke fixture",
                "scope": "Exercise MCP review/approve/close surfaces without full Park write-through.",
                "non_goals": "No persisted park closeout from the smoke fixture.",
                "completion_criteria": "MCP review resources and review action flow verified.",
            }
            temp_payload = state.blob_store.put_json(temp_request)
            temp_env = SidecarEnvelope.new(
                object_type="tranche",
                actor_id="human:smoketest",
                operation_intent="declare_tranche",
                payload_ref=temp_payload,
            )
            temp_result = state.router.dispatch(temp_env)
            if temp_result.status in ("accepted", "completed"):
                temp_response = state.blob_store.get_json(temp_result.payload_ref) if temp_result.payload_ref else {}
                temp_review_tranche_id = str(temp_response.get("tranche_id", ""))
                review_tranche = state.tranche_manager.get_current()
                if temp_review_tranche_id and review_tranche:
                    _ok(f"declared temporary review-gate tranche fixture: {temp_review_tranche_id}")
                    decision_payload = state.blob_store.put_json(
                        {
                            "title": "Use MCP review resources for chat-cockpit verification",
                            "context": "Smoke fixture for T10.2 MCP review-gate coverage.",
                            "rationale": "Need a deterministic tranche with at least one decision.",
                            "outcome": "Use review:// and closeout:// resources plus sidecar/submit actions.",
                            "impact_area": "verification",
                            "importance": 6,
                        }
                    )
                    decision_env = SidecarEnvelope.new(
                        object_type="decision",
                        actor_id="human:smoketest",
                        operation_intent="record_decision",
                        payload_ref=decision_payload,
                    )
                    decision_result = state.router.dispatch(decision_env)
                    if decision_result.status in ("accepted", "completed"):
                        _ok("temporary review-gate tranche fixture has a recorded decision")
                    else:
                        failures.append(_fail(f"record_decision for temporary review tranche failed: {decision_result.status}"))
            else:
                failures.append(_fail(f"temporary review-gate tranche declare failed: {temp_result.status}"))
        except Exception as e:
            failures.append(_fail(f"could not create temporary review-gate tranche fixture: {e}"))

    if review_tranche and review_tranche.status == "active":
        close_payload = state.blob_store.put_json({"extra_notes": "smoke direct-close rejection"})
        close_env = SidecarEnvelope.new(
            object_type="tranche",
            actor_id="human:smoketest",
            operation_intent="close_tranche",
            payload_ref=close_payload,
        )
        close_result = state.router.dispatch(close_env)
        if close_result.status in {"rejected", "failed"}:
            _ok(f"close_tranche blocked while tranche is still active (status={close_result.status})")
        else:
            failures.append(_fail(f"close_tranche expected blocked before review approval, got {close_result.status}"))
    else:
        _ok("no active tranche available for direct-close rejection check")

    _section("87. T10.2 MCP handler: request/return/approve/close review flow works")
    if review_tranche and review_tranche.status == "active":
        smoke_payload = state.blob_store.put_json(
            {
                "test_name": "smoke_test.py",
                "passed": True,
                "details": "T10 review-gate smoke path",
            }
        )
        smoke_env = SidecarEnvelope.new(
            object_type="smoke_test",
            actor_id="human:smoketest",
            operation_intent="smoke_pass",
            payload_ref=smoke_payload,
        )
        smoke_result = state.router.dispatch(smoke_env)
        if smoke_result.status in ("accepted", "completed"):
            _ok("recorded smoke PASS on the active tranche before requesting review")
        else:
            failures.append(_fail(f"smoke_pass before review request failed: {smoke_result.status}"))

        request_resp = mcp.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 87,
                "method": "sidecar/submit",
                "params": {
                    "actorId": "human:smoketest",
                    "operationIntent": "request_tranche_review",
                },
            }
        )
        request_result = (request_resp or {}).get("result", {})
        if request_result.get("accepted"):
            request_payload = request_result.get("payload") or {}
            review_id = request_payload.get("review_id", "")
            current_after_request = state.tranche_manager.get_current()
            if current_after_request and current_after_request.status == "review_pending":
                _ok(f"request_tranche_review moved tranche to review_pending (review_id={review_id})")
            else:
                failures.append(_fail("request_tranche_review did not move the tranche to review_pending"))
            review_gate = state.projections.refresh("tranche_review_gate")
            review_row = _first_projection_row(review_gate.rows)
            latest_review = _json2.loads(review_row.get("latest_review_json") or "{}")
            if latest_review.get("review_id") == review_id:
                _ok("tranche_review_gate latest_review matches the requested review packet")
            else:
                failures.append(_fail("tranche_review_gate latest_review does not match requested review packet"))
            review_latest_resp = mcp.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 88,
                    "method": "resources/read",
                    "params": {"uri": "review://latest"},
                }
            )
            review_latest_contents = (review_latest_resp or {}).get("result", {}).get("contents", [])
            review_latest_mimes = {item.get("mimeType") for item in review_latest_contents}
            if {"application/json", "text/markdown"}.issubset(review_latest_mimes):
                _ok("review://latest returns JSON + Markdown contents")
            else:
                failures.append(_fail(f"review://latest returned wrong content set: {review_latest_resp}"))
            if review_id:
                review_specific_resp = mcp.handle_message(
                    {
                        "jsonrpc": "2.0",
                        "id": 89,
                        "method": "resources/read",
                        "params": {"uri": f"review://{review_id}"},
                    }
                )
                review_specific_contents = (review_specific_resp or {}).get("result", {}).get("contents", [])
                review_specific_mimes = {item.get("mimeType") for item in review_specific_contents}
                if {"application/json", "text/markdown"}.issubset(review_specific_mimes):
                    _ok("review://<review_id> returns JSON + Markdown contents")
                else:
                    failures.append(_fail(f"review://{review_id} returned wrong content set: {review_specific_resp}"))

            blocked_close_resp = mcp.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 90,
                    "method": "sidecar/submit",
                    "params": {
                        "actorId": "human:smoketest",
                        "operationIntent": "close_tranche",
                        "payload": {"dry_run": True, "extra_notes": "blocked before approval"},
                    },
                }
            )
            blocked_close_result = (blocked_close_resp or {}).get("result", {})
            if not blocked_close_result.get("accepted"):
                _ok("sidecar/submit close_tranche stays blocked before review approval")
            else:
                failures.append(_fail(f"close_tranche unexpectedly accepted before approval: {blocked_close_resp}"))

            return_resp = mcp.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 91,
                    "method": "sidecar/submit",
                    "params": {
                        "actorId": "human:smoketest",
                        "operationIntent": "return_tranche_review",
                        "payload": {
                            "review_id": review_id,
                            "return_reason": "smoke review return for T10.2 MCP gate coverage",
                        },
                    },
                }
            )
            return_result = (return_resp or {}).get("result", {})
            if return_result.get("accepted"):
                current_after_return = state.tranche_manager.get_current()
                if current_after_return and current_after_return.status == "active":
                    _ok("return_tranche_review reopened the same tranche as active")
                else:
                    failures.append(_fail("return_tranche_review did not reopen the tranche as active"))
                questions = current_after_return.open_questions if current_after_return else []
                if any("smoke review return for T10.2 MCP gate coverage" in (item.get("question", "") if isinstance(item, dict) else str(item)) for item in questions):
                    _ok("returned review feedback was appended into tranche carry-forward questions")
                else:
                    failures.append(_fail("returned review feedback missing from tranche carry-forward questions"))
            else:
                failures.append(_fail(f"return_tranche_review status={return_result.get('status')}"))

            second_request_resp = mcp.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 92,
                    "method": "sidecar/submit",
                    "params": {
                        "actorId": "human:smoketest",
                        "operationIntent": "request_tranche_review",
                    },
                }
            )
            second_request_result = (second_request_resp or {}).get("result", {})
            second_request_payload = second_request_result.get("payload") or {}
            second_review_id = second_request_payload.get("review_id", "")
            if second_request_result.get("accepted") and second_review_id:
                _ok("a returned review can be re-requested through sidecar/submit")
            else:
                failures.append(_fail(f"second request_tranche_review failed: {second_request_resp}"))

            approve_resp = mcp.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 93,
                    "method": "sidecar/submit",
                    "params": {
                        "actorId": "human:smoketest",
                        "operationIntent": "approve_tranche_review",
                        "payload": {
                            "review_id": second_review_id,
                            "approval_notes": "smoke approval for MCP chat review gate",
                        },
                    },
                }
            )
            approve_result = (approve_resp or {}).get("result", {})
            if approve_result.get("accepted"):
                current_after_approve = state.tranche_manager.get_current()
                if current_after_approve and current_after_approve.status == "review_approved":
                    _ok("approve_tranche_review moved the tranche to review_approved")
                else:
                    failures.append(_fail("approve_tranche_review did not move the tranche to review_approved"))
                review_gate_after_approve = state.projections.refresh("tranche_review_gate")
                review_gate_row_after_approve = _first_projection_row(review_gate_after_approve.rows)
                allowed_after_approve = _json2.loads(review_gate_row_after_approve.get("allowed_actions_json") or "[]")
                if "close_tranche" in allowed_after_approve:
                    _ok("tranche_review_gate exposes close_tranche after approval")
                else:
                    failures.append(_fail("tranche_review_gate missing close_tranche after approval"))
            else:
                failures.append(_fail(f"approve_tranche_review failed through sidecar/submit: {approve_resp}"))

            close_after_approve_resp = mcp.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 94,
                    "method": "sidecar/submit",
                    "params": {
                        "actorId": "human:smoketest",
                        "operationIntent": "close_tranche",
                        "payload": {
                            "dry_run": True,
                            "extra_notes": "smoke dry-run close for MCP chat review gate",
                        },
                    },
                }
            )
            close_after_approve_result = (close_after_approve_resp or {}).get("result", {})
            if close_after_approve_result.get("accepted"):
                close_payload = close_after_approve_result.get("payload") or {}
                if close_payload.get("dry_run") is True:
                    _ok("close_tranche is accepted through sidecar/submit after approval (dry-run)")
                else:
                    failures.append(_fail(f"close_tranche dry-run payload unexpected: {close_after_approve_resp}"))
                review_exercised = True
            else:
                failures.append(_fail(f"close_tranche after approval failed through sidecar/submit: {close_after_approve_resp}"))
        else:
            failures.append(_fail(f"request_tranche_review status={request_result.get('status')}"))
    else:
        _ok("review round-trip skipped because there is no active tranche to submit")

    if temp_review_tranche_id:
        try:
            state.store.execute(
                "UPDATE active_tranche SET status = 'parked', closed_at = ? WHERE tranche_id = ?;",
                (state.store.get_meta("installed_at") or "cleanup", temp_review_tranche_id),
            )
            state.store.set_meta("current_tranche_scope", "{}")
            state.projections.refresh("tranche_review_gate")
            state.projections.refresh("handoff")
            _ok("temporary MCP review-gate tranche fixture cleaned up")
        except Exception as cleanup_e:
            failures.append(_fail(f"temporary MCP review-gate tranche cleanup failed: {cleanup_e}"))

    _section("87.5. T10.3: routed non-session actors gain explicit authority rows")
    try:
        actor_id = "agent:smoke:authority_seed"
        state.store.execute("DELETE FROM authorities WHERE actor_id = ?;", (actor_id,))
        if state.store.query_one("SELECT actor_id FROM authorities WHERE actor_id = ?;", (actor_id,)) is None:
            _ok("authority smoke actor starts without an authorities row")
        else:
            failures.append(_fail("authority smoke actor unexpectedly started with an authorities row"))

        payload_ref = state.blob_store.put_json(
            {
                "kind": "note",
                "title": "T10.3 authority auto-registration smoke",
                "body": "Verify router-path actors are materialized into authorities.",
                "importance": 1,
                "tags": ["smoke", "T10.3", "authority"],
            }
        )
        env = SidecarEnvelope.new(
            object_type="journal_entry",
            actor_id=actor_id,
            operation_intent="create_journal_entry",
            payload_ref=payload_ref,
        )
        result = state.router.dispatch(env)
        if result.status in ("accepted", "completed"):
            _ok("non-session actor journal write routed successfully")
        else:
            failures.append(_fail(f"non-session actor journal write failed: status={result.status}"))

        authority_row = state.store.query_one(
            "SELECT base_level, granted_by FROM authorities WHERE actor_id = ?;",
            (actor_id,),
        )
        if authority_row and authority_row["base_level"] == "Propose":
            _ok("router-path non-session actor now has an explicit authority row")
        else:
            failures.append(_fail(f"missing or wrong authority row for routed non-session actor: {authority_row}"))
        if authority_row and authority_row["granted_by"] == "system:router_authority_seed":
            _ok("router-seeded authority row records its provenance")
        else:
            failures.append(_fail(f"router-seeded authority provenance missing: {authority_row}"))
    except Exception as e:
        failures.append(_fail(f"T10.3 routed authority-row seeding failed: {e}"))

    _section("88. T10: Tranche Review Tk panel hydrates")
    try:
        import tkinter as _tk
        from src.ui.tranche_review_panel import TrancheReviewPanel

        review_projection = state.projections.refresh("tranche_review_gate")
        review_row = _first_projection_row(review_projection.rows)
        root = _tk.Tk()
        root.withdraw()
        panel = TrancheReviewPanel(root, state)
        panel.refresh(
            {
                "tranche_review_gate": {
                    "current_tranche": _json2.loads(review_row.get("current_tranche_json") or "{}"),
                    "latest_review": _json2.loads(review_row.get("latest_review_json") or "{}"),
                    "history": _json2.loads(review_row.get("history_json") or "[]"),
                    "allowed_actions": _json2.loads(review_row.get("allowed_actions_json") or "[]"),
                    "park_phase_allowed": bool(review_row.get("park_phase_allowed") or 0),
                },
                "default_operator_actor": "human:smoketest",
            }
        )
        root.update_idletasks()
        root.update()
        root.destroy()
        _ok(f"TrancheReviewPanel hydrated from tranche_review_gate: {type(panel).__name__}")
    except Exception as e:
        import traceback as _tb
        _tb.print_exc()
        failures.append(_fail(f"T10 Tk tranche review panel failed to initialize: {e}"))

    _section("RESULT")
    if failures:
        print(f"\n  {len(failures)} FAILURE(S):")
        for f in failures:
            print(f"    - {f}")
        if warnings:
            print(f"\n  {len(warnings)} WARNING(S):")
            for w in warnings:
                print(f"    - {w}")
        print("\nSMOKE TEST: FAIL")
        return 1
    if warnings:
        print(f"\n  {len(warnings)} WARNING(S):")
        for w in warnings:
            print(f"    - {w}")
    print("\nSMOKE TEST: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
