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
import sqlite3
import sys
import traceback
from pathlib import Path

# Allow `import src.*` regardless of where the test is invoked from.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from src.lib.common import public_root_labels


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


def _find_constrant_hits(root: Path) -> dict[str, list[str]]:
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
            tables = [
                row[0]
                for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ]
            for table in tables:
                cols = [r[1] for r in cur.execute(f"PRAGMA table_info([{table}])").fetchall()]
                for col in cols:
                    try:
                        count = cur.execute(
                            f"SELECT COUNT(*) FROM [{table}] WHERE CAST([{col}] AS TEXT) LIKE ?",
                            (f"%{needle}%",),
                        ).fetchone()[0]
                    except sqlite3.Error:
                        continue
                    if count:
                        rel = path.relative_to(root)
                        db_hits.append(f"{rel} :: {table}.{col} ({count})")
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
        _ok(f"sidecar_id={state.sidecar_id}")
        _ok(f"sidecar_root={sidecar_root_label}")
        _ok(f"project_root={project_root_label}")
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
    tranche_entries = state.journal_manager.query(kind="tranche", limit=10)
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
        sample = next((r for r in pm.rows if r.get("path") == "ARCHITECTURE.md"), None)
        if sample:
            _ok(f"  sample: ARCHITECTURE.md kind={sample['kind']} size={sample['size_bytes']}")
        else:
            failures.append(_fail("ARCHITECTURE.md not in project_map projection"))
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
    # T2.5 adds tranche_checklist → 8 projections total.
    from src.schemas.projection_schema import PROJECTION_NAMES as _PROJ_NAMES
    expected_resource_count = len(_PROJ_NAMES)
    if len(resources) == expected_resource_count:
        _ok(f"resources/list returned {len(resources)} projections")
    else:
        failures.append(_fail(
            f"resources/list returned {len(resources)} (expected {expected_resource_count})"
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

    # =============================================================
    # PARK PHASE DRIFT DETECTION (added 2026-05-11; contract §D)
    # =============================================================
    # These sections verify that continuity docs are in sync with state.
    # A failure here means the most recent tranche is not properly parked
    # (per ARCHITECTURE.md §12.2 + contract §D).
    # =============================================================

    import re as _re
    sidecar_root = state.sidecar_root

    _section("36. DRIFT: TOOLS.md row count matches tool_registry count")
    registered_count = state.tool_registry_manager.count()
    tools_md = (sidecar_root / "TOOLS.md").read_text(encoding="utf-8")
    # Count rows in the "## Registered tools" table.
    # Match table rows that look like: | `tool_name` | ... |
    rows_md = _re.findall(r"^\|\s*`[a-z_]+`\s*\|", tools_md, _re.MULTILINE)
    if len(rows_md) == registered_count:
        _ok(f"TOOLS.md rows ({len(rows_md)}) match tool_registry count ({registered_count})")
    else:
        failures.append(_fail(
            f"TOOLS.md rows={len(rows_md)} vs tool_registry={registered_count} — DRIFT"
        ))

    _section("37. DRIFT: README.md status header reflects current state (not 'Tranche 0')")
    readme = (sidecar_root / "README.md").read_text(encoding="utf-8")
    header_lines = readme.split("\n", 10)[:6]
    header_text = "\n".join(header_lines)
    if "Tranche 0" in header_text and "No executable code yet" in header_text:
        failures.append(_fail("README.md status header still says 'Tranche 0 — No executable code yet' — DRIFT"))
    else:
        _ok("README.md status header does not name a stale tranche state")

    _section("38. DRIFT: ARCHITECTURE.md §15 has 'Resolved at T_n' for every completed tranche")
    arch = (sidecar_root / "ARCHITECTURE.md").read_text(encoding="utf-8")
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

    _section("41. DRIFT: contract §D Park Phase Discipline clause present")
    contract_text = (sidecar_root / "contracts" / "builder_constraint_contract.md").read_text(encoding="utf-8")
    if "Park Phase Discipline" in contract_text and "five artifacts" in contract_text:
        _ok("contract §D Park Phase Discipline clause present")
    else:
        failures.append(_fail("contract §D Park Phase Discipline clause missing — DRIFT"))

    # =============================================================
    # ONBOARDING GAP CLOSURES (added 2026-05-11)
    # =============================================================

    from src.lib.common import now_iso

    import json as _json2
    _section("42. ONBOARDING: ONBOARDING.md exists at top level")
    onboarding_path = sidecar_root / "ONBOARDING.md"
    if onboarding_path.is_file():
        content = onboarding_path.read_text(encoding="utf-8")
        if "Reading order" in content and "verification commands" in content.lower():
            _ok(f"ONBOARDING.md present ({len(content)} chars), covers reading order + commands")
        else:
            failures.append(_fail("ONBOARDING.md present but missing reading-order or commands section"))
    else:
        failures.append(_fail("ONBOARDING.md missing at top level"))

    _section("43. ONBOARDING: config/toolbox_manifest.json generated at runtime")
    tbm_path = sidecar_root / "config" / "toolbox_manifest.json"
    if tbm_path.is_file():
        tbm = _json2.loads(tbm_path.read_text(encoding="utf-8"))
        required_keys = ("manifest_version", "zero_context_entry_protocol", "authority_levels",
                        "projections", "memory_model", "spine_rule", "verification_commands")
        missing = [k for k in required_keys if k not in tbm]
        if not missing:
            _ok(f"toolbox_manifest.json present with all required keys")
        else:
            failures.append(_fail(f"toolbox_manifest.json missing keys: {missing}"))
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

    _section("46. ONBOARDING: README.md references ONBOARDING.md")
    readme_text = (sidecar_root / "README.md").read_text(encoding="utf-8")
    if "ONBOARDING.md" in readme_text:
        _ok("README.md links to ONBOARDING.md")
    else:
        failures.append(_fail("README.md does not link to ONBOARDING.md"))

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
        live_tranche = state.tranche_manager.get_active()
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

    _section("57. TYPO GUARD: warn on any lingering 'constrant' usage")
    typo_hits = _find_constrant_hits(sidecar_root)
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
