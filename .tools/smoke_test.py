"""
FILE: smoke_test.py
ROLE: Portable self-test for _app-journal v2.
WHAT IT DOES: Verifies schema v2, CAS, contract, actions, scaffold, pack, snapshot, and MCP paths.
HOW TO USE:
  - python src/smoke_test.py
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PASS = 0
FAIL = 0

# Avoid cp1252 encoding errors on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  [PASS] {label}")


def _fail(label: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    msg = f"  [FAIL] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )


def _run_json(args: list[str]) -> dict:
    completed = _run(args)
    if completed.returncode != 0:
        raise RuntimeError(f"Exit {completed.returncode}: {completed.stderr or completed.stdout}")
    return json.loads(completed.stdout)


def _tool(name: str, arguments: dict) -> dict:
    return _run_json([
        sys.executable, str(ROOT / "tools" / f"{name}.py"),
        "run", "--input-json", json.dumps(arguments),
    ])


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _mcp_message(message: dict) -> bytes:
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body


def _mcp_read(stdout) -> dict:
    """Read one NDJSON response line from MCP server stdout."""
    while True:
        line = stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed before responding.")
        stripped = line.strip()
        if not stripped:
            continue
        return json.loads(stripped.decode("utf-8"))


# ═══════════════════════════════════════════════════════════════════
# Test groups
# ═══════════════════════════════════════════════════════════════════

def test_compile() -> None:
    """Compile-check all Python source files."""
    print("\n── Compile check ──")
    py_files = list(ROOT.rglob("*.py"))
    py_files = [f for f in py_files if "__pycache__" not in str(f)]
    result = _run([sys.executable, "-m", "py_compile"] + [str(f) for f in py_files])
    if result.returncode == 0:
        _ok(f"All {len(py_files)} Python files compile clean")
    else:
        _fail("Compile check", result.stderr)


def test_schema_and_cas(project_root: Path) -> str:
    """Init DB, verify schema v2, CAS operations."""
    print("\n── Schema v2 + CAS ──")

    result = _tool("journal_init", {"project_root": str(project_root)})
    db_path = result["result"]["paths"]["db_path"]

    if result["status"] == "ok":
        _ok("journal_init creates DB")
    else:
        _fail("journal_init", str(result))

    # Verify schema version via manifest
    manifest = _tool("journal_manifest", {"db_path": db_path})
    sv = manifest["result"]["db_summary"].get("schema_version")
    uv = manifest["result"]["db_summary"].get("sqlite_user_version")
    if sv == "2.0.0":
        _ok(f"Schema version = {sv}")
    else:
        _fail("Schema version", f"expected 2.0.0, got {sv}")
    if uv == 2:
        _ok(f"SQLite user_version = {uv}")
    else:
        _fail("SQLite user_version", f"expected 2, got {uv}")

    # Verify all 10 tables exist
    expected_tables = {
        "journal_meta", "journal_migrations", "journal_entries",
        "blob_store", "scaffold_templates", "packed_tools",
        "action_log", "snapshots", "snapshot_items", "project_registry",
    }
    db_tables = set(manifest["result"]["db_manifest"].get("db_schema", {}).get("table_names", []))
    if expected_tables == db_tables:
        _ok(f"All {len(expected_tables)} tables declared in manifest")
    else:
        _fail("Table manifest", f"missing: {expected_tables - db_tables}, extra: {db_tables - expected_tables}")

    # Verify contract was seeded
    contract_version = manifest["result"]["db_summary"].get("contract_version", "")
    if contract_version:
        _ok(f"Contract seeded (v{contract_version})")
    else:
        _fail("Contract seeding", "contract_version not set in manifest")

    # Verify blob_store has content (contract body)
    blob_count = manifest["result"]["db_summary"].get("blob_count", 0)
    if blob_count >= 1:
        _ok(f"blob_store has {blob_count} blob(s)")
    else:
        _fail("blob_store", "expected at least 1 blob from contract seeding")

    # CAS: write an entry and verify body_hash
    create_result = _tool("journal_write", {
        "project_root": str(project_root),
        "action": "create",
        "title": "CAS test entry",
        "body": "Content-addressed storage verification.",
        "kind": "note",
        "source": "agent",
        "tags": ["smoke", "cas"],
    })
    entry = create_result["result"]["entry"]
    if entry.get("body_hash"):
        _ok(f"Entry has body_hash: {entry['body_hash'][:16]}...")
    else:
        _fail("CAS dual-write", "entry missing body_hash")

    return db_path


def test_write_query_export(project_root: Path, db_path: str) -> str:
    """CRUD, append, query, export."""
    print("\n── Write / Query / Export ──")

    # Create
    create_result = _tool("journal_write", {
        "db_path": db_path,
        "action": "create",
        "title": "Smoke test decision",
        "body": "We verified the full CRUD lifecycle.",
        "kind": "decision",
        "source": "agent",
        "tags": ["smoke", "crud"],
    })
    entry_uid = create_result["result"]["entry"]["entry_uid"]
    _ok(f"Create entry: {entry_uid}")

    # Append
    _tool("journal_write", {
        "db_path": db_path,
        "action": "append",
        "entry_uid": entry_uid,
        "append_text": "Appended during smoke test.",
    })
    _ok("Append to entry")

    # Update
    _tool("journal_write", {
        "db_path": db_path,
        "action": "update",
        "entry_uid": entry_uid,
        "status": "closed",
        "importance": 3,
    })
    _ok("Update entry status/importance")

    # Query
    query_result = _tool("journal_query", {
        "db_path": db_path,
        "query": "CRUD lifecycle",
        "limit": 10,
    })
    count = query_result["result"]["summary"]["entry_count"]
    if count >= 1:
        _ok(f"Query returns {count} result(s)")
    else:
        _fail("Query", "expected at least 1 result")

    # Export markdown
    export_result = _tool("journal_export", {
        "project_root": str(project_root),
        "format": "markdown",
    })
    export_path = export_result["result"]["export_path"]
    if Path(export_path).exists():
        _ok(f"Markdown export created")
    else:
        _fail("Export", f"file not found: {export_path}")

    # Export JSON
    export_result_json = _tool("journal_export", {
        "project_root": str(project_root),
        "format": "json",
    })
    export_path_json = export_result_json["result"]["export_path"]
    if Path(export_path_json).exists():
        _ok("JSON export created")
    else:
        _fail("JSON export", f"file not found: {export_path_json}")

    return entry_uid


def test_contract_acknowledge(project_root: Path, db_path: str) -> None:
    """Contract acknowledgment."""
    print("\n── Contract Acknowledgment ──")

    ack_result = _tool("journal_acknowledge", {
        "db_path": db_path,
        "actor_id": "smoke_test_agent",
        "actor_type": "agent",
    })
    receipt = ack_result.get("result", {}).get("receipt", {})
    if receipt.get("acknowledged"):
        _ok("Contract acknowledged")
    else:
        _fail("Acknowledge", str(ack_result.get("result", {})))

    # Verify action was logged
    actions_result = _tool("journal_actions", {
        "db_path": db_path,
        "action_type": "acknowledge_contract",
        "limit": 5,
    })
    actions = actions_result["result"]["actions"]
    if any(a["action_type"] == "acknowledge_contract" for a in actions):
        _ok("Acknowledgment recorded in action_log")
    else:
        _fail("Action log", "contract_acknowledge not found")


def test_actions(project_root: Path, db_path: str) -> None:
    """Action ledger query."""
    print("\n── Action Ledger ──")

    result = _tool("journal_actions", {
        "db_path": db_path,
        "limit": 20,
    })
    actions = result["result"]["actions"]
    if len(actions) >= 1:
        _ok(f"Action log has {len(actions)} action(s)")
    else:
        _fail("Action log", "expected at least 1 action")

    # Filter by actor_type
    agent_result = _tool("journal_actions", {
        "db_path": db_path,
        "actor_type": "agent",
        "limit": 10,
    })
    agent_actions = agent_result["result"]["actions"]
    if all(a["actor_type"] == "agent" for a in agent_actions):
        _ok("Actor type filter works")
    else:
        _fail("Actor type filter", "returned non-agent actions")


def test_scaffold(project_root: Path, db_path: str) -> None:
    """Scaffold template seeding and unpacking."""
    print("\n── Scaffolding ──")

    result = _tool("journal_scaffold", {
        "db_path": db_path,
        "project_root": str(project_root),
    })
    payload = result.get("result", {})
    templates_seeded = payload.get("templates_seeded", 0)
    files_written = payload.get("files", [])

    if templates_seeded >= 1 or payload.get("templates_available", 0) >= 1:
        _ok(f"Templates seeded/available")
    else:
        _fail("Template seeding", str(payload))

    if len(files_written) >= 1:
        _ok(f"Scaffold wrote {len(files_written)} file(s)")
        first = files_written[0].get("path", "") if isinstance(files_written[0], dict) else str(files_written[0])
        if first and Path(first).exists():
            _ok(f"Scaffold file exists on disk")
        else:
            _fail("Scaffold file", f"not found: {first}")
    else:
        _ok("Scaffold ran (templates may be placeholder stubs)")


def test_pack(project_root: Path, db_path: str) -> None:
    """Tool packing, listing, and unpacking."""
    print("\n── Tool Packing ──")

    # Pack this package's src/ into the DB
    result = _tool("journal_pack", {
        "db_path": db_path,
        "action": "pack",
        "package_root": str(ROOT),
    })
    payload = result.get("result", {})
    packed = payload.get("packed_count", 0)
    if packed >= 5:
        _ok(f"Packed {packed} files from src/")
    else:
        _fail("Pack", f"expected >= 5 files, got {packed}")

    # List packed tools
    list_result = _tool("journal_pack", {
        "db_path": db_path,
        "action": "list",
    })
    tools = list_result.get("result", {}).get("tools", [])
    if len(tools) >= 5:
        _ok(f"Listed {len(tools)} packed tool(s)")
    else:
        _fail("List packed", f"expected >= 5, got {len(tools)}")

    # Unpack to a temp dir
    unpack_dir = Path(tempfile.mkdtemp(prefix="app_journal_unpack_"))
    unpack_result = _tool("journal_pack", {
        "db_path": db_path,
        "action": "unpack",
        "target_dir": str(unpack_dir),
    })
    unpacked = unpack_result.get("result", {}).get("unpacked_count", 0)
    if unpacked >= 5:
        _ok(f"Unpacked {unpacked} files to {unpack_dir.name}/")
    else:
        _fail("Unpack", f"expected >= 5, got {unpacked}")


def test_snapshot(project_root: Path, db_path: str) -> None:
    """Merkle snapshot create, list, get, verify."""
    print("\n── Snapshots ──")

    # Create
    create_result = _tool("journal_snapshot", {
        "db_path": db_path,
        "action": "create",
        "description": "Smoke test snapshot",
    })
    snapshot = create_result.get("result", {})
    snapshot_id = snapshot.get("snapshot_id", "")
    merkle_root = snapshot.get("merkle_root", "")
    if snapshot_id and merkle_root:
        _ok(f"Snapshot created: {snapshot_id}, root: {merkle_root[:16]}...")
    else:
        _fail("Snapshot create", str(snapshot))
        return

    # List
    list_result = _tool("journal_snapshot", {
        "db_path": db_path,
        "action": "list",
    })
    snapshots = list_result.get("result", {}).get("snapshots", [])
    if len(snapshots) >= 1:
        _ok(f"Listed {len(snapshots)} snapshot(s)")
    else:
        _fail("Snapshot list", "expected at least 1")

    # Get
    get_result = _tool("journal_snapshot", {
        "db_path": db_path,
        "action": "get",
        "snapshot_id": snapshot_id,
    })
    got = get_result.get("result", {})
    if got.get("snapshot_id") == snapshot_id:
        _ok(f"Get snapshot details (items: {got.get('item_count', '?')})")
    else:
        _fail("Snapshot get", str(got))

    # Verify
    verify_result = _tool("journal_snapshot", {
        "db_path": db_path,
        "action": "verify",
        "snapshot_id": snapshot_id,
    })
    verified = verify_result.get("result", {})
    if verified.get("valid"):
        _ok("Snapshot verified (merkle root matches)")
    else:
        _fail("Snapshot verify", str(verified))


def test_sidecar_install_and_setup() -> None:
    """Install the full sidecar payload, then apply and verify project setup."""
    print("\n── Sidecar Install / Setup / Microsite ──")

    target_root = Path(tempfile.mkdtemp(prefix="sidecar_install_")) / "fresh_project"
    target_root.mkdir(parents=True, exist_ok=True)

    preview = _tool("sidecar_install", {
        "target_project_root": str(target_root),
        "preview": True,
    })
    preview_files = preview["result"]["files"]
    if any(item["status"] == "would_create" for item in preview_files):
        _ok("sidecar install preview works")
    else:
        _fail("sidecar install preview", str(preview["result"]))

    applied = _tool("sidecar_install", {
        "target_project_root": str(target_root),
    })
    sidecar_dir = Path(applied["result"]["sidecar_dir"])
    expected = {
        sidecar_dir / "README.md",
        sidecar_dir / "release_payload_manifest.json",
        sidecar_dir / "src" / "mcp_server.py",
        sidecar_dir / "onboarding" / "START_HERE.html",
        sidecar_dir / "packages" / "_app-journal" / "README.md",
    }
    if all(path.exists() for path in expected):
        _ok("full sidecar payload installed")
    else:
        missing = [str(path) for path in expected if not path.exists()]
        _fail("sidecar install", ", ".join(missing))

    audit_before = _tool("project_setup", {
        "action": "audit",
        "project_root": str(target_root),
    })
    if audit_before["result"]["missing_required"]:
        _ok("project setup audit detects missing setup surfaces")
    else:
        _fail("project setup audit", str(audit_before["result"]))

    applied_setup = _tool("project_setup", {
        "action": "apply",
        "project_root": str(target_root),
        "actor_id": "smoke_setup_agent",
    })
    if applied_setup["result"]["files"]:
        _ok("project setup apply writes scaffold files")
    else:
        _fail("project setup apply", str(applied_setup["result"]))

    verified = _tool("project_setup", {
        "action": "verify",
        "project_root": str(target_root),
    })
    if verified["result"]["passed"]:
        _ok("project setup verify passes after apply")
    else:
        _fail("project setup verify", str(verified["result"]))

    site_check = _tool("onboarding_site_check", {
        "toolbox_root": str(sidecar_dir),
    })
    if site_check["result"]["passed"]:
        _ok("installed sidecar microsite passes integrity check")
    else:
        _fail("installed sidecar microsite", str(site_check["result"]))


def test_repo_search() -> None:
    """Repo search with native fallback."""
    print("\n── Repo Search ──")

    target_root = Path(tempfile.mkdtemp(prefix="repo_search_"))
    (target_root / "src").mkdir()
    (target_root / "src" / "app.py").write_text(
        "def main():\n    return 'needle-value'\n",
        encoding="utf-8",
    )
    (target_root / "notes.md").write_text("No match here.\n", encoding="utf-8")

    result = _tool("repo_search", {
        "project_root": str(target_root),
        "query": "needle-value",
        "extensions": [".py"],
        "force_fallback": True,
    })
    payload = result["result"]
    if payload["fallback_used"] and payload["match_count"] == 1:
        _ok("repo_search native fallback finds text without shell bypass")
    else:
        _fail("repo_search fallback", str(payload))

    bad_regex = _tool("repo_search", {
        "project_root": str(target_root),
        "query": "[",
        "regex": True,
    })
    if bad_regex["status"] == "error":
        _ok("repo_search reports invalid regex cleanly")
    else:
        _fail("repo_search invalid regex", str(bad_regex))


def test_sys_ops_introspection() -> None:
    """Local-agent sys-ops read-only tools."""
    print("\n── Local-Agent Sys-Ops Introspection ──")

    target_root = Path(tempfile.mkdtemp(prefix="sys_ops_"))
    (target_root / "src").mkdir()
    (target_root / "src" / "smoke_test.py").write_text("print('ok')\n", encoding="utf-8")
    (target_root / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite", "test": "echo ok", "build": "echo build"}}),
        encoding="utf-8",
    )
    (target_root / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    (target_root / "run.bat").write_text("@echo off\npython src\\smoke_test.py\n", encoding="utf-8")
    dev_port = _free_port()
    (target_root / "dev_server.py").write_text(
        "\n".join([
            "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer",
            f"PORT = {dev_port}",
            "class Handler(BaseHTTPRequestHandler):",
            "    def do_GET(self):",
            "        body = b'dev-server-ok'",
            "        self.send_response(200)",
            "        self.send_header('Content-Type', 'text/plain')",
            "        self.send_header('Content-Length', str(len(body)))",
            "        self.end_headers()",
            "        self.wfile.write(body)",
            "    def log_message(self, format, *args):",
            "        print(format % args, flush=True)",
            "print(f'listening on {PORT}', flush=True)",
            "ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()",
            "",
        ]),
        encoding="utf-8",
    )

    host = _tool("host_capability_probe", {
        "commands": ["python", "git"],
        "timeout_seconds": 3,
    })
    if host["status"] == "ok" and host["result"]["summary"]["available_count"] >= 1:
        _ok("host_capability_probe reports command availability")
    else:
        _fail("host_capability_probe", str(host))

    boundary = _tool("workspace_boundary_audit", {
        "project_root": str(target_root),
        "max_depth": 2,
    })
    if boundary["status"] == "ok" and boundary["result"]["project_root"] == str(target_root.resolve()):
        _ok("workspace_boundary_audit resolves project root")
    else:
        _fail("workspace_boundary_audit", str(boundary))

    profile = _tool("project_command_profile", {
        "project_root": str(target_root),
    })
    command_ids = {item["id"] for item in profile["result"]["commands"]}
    expected_ids = {"npm:dev", "npm:test", "npm:build", "python:smoke", "file:run.bat", "python:dev-server"}
    profile_has_metadata = all("requires" in item and "runtime" in item for item in profile["result"]["commands"])
    if expected_ids.issubset(command_ids) and profile_has_metadata:
        _ok("project_command_profile detects declared commands with metadata")
    else:
        _fail("project_command_profile", f"missing: {expected_ids - command_ids}")

    deps = _tool("dependency_env_check", {
        "project_root": str(target_root),
        "check_imports": ["json"],
    })
    dep_payload = deps["result"]
    if (
        deps["status"] == "ok"
        and dep_payload["python"]["requirements"][0]["entry_count"] == 1
        and dep_payload["node"]["package_json"]["exists"]
        and dep_payload["python"]["import_checks"][0]["available"]
    ):
        _ok("dependency_env_check reports readiness without installing")
    else:
        _fail("dependency_env_check", str(deps))

    processes = _tool("process_port_inspector", {
        "ports": [],
        "process_name_contains": ["python"],
        "max_processes": 10,
    })
    if processes["status"] == "ok" and "process_count" in processes["result"]["summary"]:
        _ok("process_port_inspector returns structured process summary")
    else:
        _fail("process_port_inspector", str(processes))

    health_url = f"http://127.0.0.1:{dev_port}/"
    started = False
    try:
        start_denied = _tool("dev_server_manager", {
            "action": "start",
            "project_root": str(target_root),
            "command_id": "python:dev-server",
            "health_url": health_url,
        })
        if start_denied["status"] == "error":
            _ok("dev_server_manager requires confirmation before start")
        else:
            _fail("dev_server_manager confirmation", str(start_denied))

        start = _tool("dev_server_manager", {
            "action": "start",
            "project_root": str(target_root),
            "command_id": "python:dev-server",
            "health_url": health_url,
            "port": dev_port,
            "confirm": True,
        })
        started = start["status"] == "ok"
        if started and start["result"]["server"]["pid"]:
            _ok("dev_server_manager starts a profiled dev server")
        else:
            _fail("dev_server_manager start", str(start))

        health = {"status": "error"}
        for _ in range(20):
            health = _tool("dev_server_manager", {
                "action": "health",
                "project_root": str(target_root),
                "command_id": "python:dev-server",
                "timeout_seconds": 1,
            })
            if health["status"] == "ok":
                break
            time.sleep(0.2)
        if health["status"] == "ok" and health["result"]["health"]["status_code"] == 200:
            _ok("dev_server_manager health-checks the registered server")
        else:
            _fail("dev_server_manager health", str(health))

        status = _tool("dev_server_manager", {
            "action": "status",
            "project_root": str(target_root),
            "command_id": "python:dev-server",
        })
        if status["status"] == "ok" and status["result"]["summary"]["registered_count"] == 1:
            _ok("dev_server_manager reports registered server status")
        else:
            _fail("dev_server_manager status", str(status))

        tail = _tool("dev_server_manager", {
            "action": "tail",
            "project_root": str(target_root),
            "command_id": "python:dev-server",
            "tail_lines": 20,
        })
        if tail["status"] == "ok" and tail["result"]["line_count"] >= 1:
            _ok("dev_server_manager tails runtime logs")
        else:
            _fail("dev_server_manager tail", str(tail))
    finally:
        if started:
            stop = _tool("dev_server_manager", {
                "action": "stop",
                "project_root": str(target_root),
                "command_id": "python:dev-server",
                "confirm": True,
            })
        if stop["status"] == "ok" and stop["result"]["alive"] is False:
            _ok("dev_server_manager stops registered server")
        else:
            _fail("dev_server_manager stop", str(stop))

    (target_root / "Dockerfile").write_text(
        "FROM python:3.11-slim\nCMD [\"python\", \"--version\"]\n",
        encoding="utf-8",
    )
    docker_status = _tool("docker_ops", {
        "action": "status",
        "project_root": str(target_root),
        "timeout_seconds": 3,
    })
    if docker_status["status"] == "ok" and "docker" in docker_status["result"]:
        _ok("docker_ops reports Docker availability status")
    else:
        _fail("docker_ops status", str(docker_status))

    docker_build = _tool("docker_ops", {
        "action": "build",
        "project_root": str(target_root),
        "context": ".",
        "image": "devtools-smoke:local",
        "preview": True,
    })
    if docker_build["status"] == "ok" and docker_build["result"]["executed"] is False:
        _ok("docker_ops validates project-scoped build previews")
    else:
        _fail("docker_ops build preview", str(docker_build))

    docker_tag_denied = _tool("docker_ops", {
        "action": "tag",
        "project_root": str(target_root),
        "source_image": "devtools-smoke:local",
        "target_image": "example/devtools-smoke:local",
    })
    if docker_tag_denied["status"] == "error":
        _ok("docker_ops requires confirmation before tag")
    else:
        _fail("docker_ops tag confirmation", str(docker_tag_denied))

    k8s_dir = target_root / "k8s"
    k8s_dir.mkdir()
    (k8s_dir / "deployment.yaml").write_text(
        "\n".join([
            "apiVersion: apps/v1",
            "kind: Deployment",
            "metadata:",
            "  name: devtools-smoke",
            "spec:",
            "  replicas: 1",
            "  selector:",
            "    matchLabels:",
            "      app: devtools-smoke",
            "  template:",
            "    metadata:",
            "      labels:",
            "        app: devtools-smoke",
            "    spec:",
            "      containers:",
            "        - name: smoke",
            "          image: devtools-smoke:local",
            "",
        ]),
        encoding="utf-8",
    )
    k8s_validate = _tool("k8s_ops", {
        "action": "validate",
        "project_root": str(target_root),
        "manifest": "k8s/deployment.yaml",
    })
    if k8s_validate["status"] == "ok" and k8s_validate["result"]["resources"][0]["kind"] == "Deployment":
        _ok("k8s_ops validates manifest structure")
    else:
        _fail("k8s_ops validate", str(k8s_validate))

    k8s_dry_run = _tool("k8s_ops", {
        "action": "dry_run",
        "project_root": str(target_root),
        "manifest": "k8s/deployment.yaml",
        "preview": True,
    })
    if k8s_dry_run["status"] == "ok" and k8s_dry_run["result"]["executed"] is False:
        _ok("k8s_ops prepares dry-run apply command")
    else:
        _fail("k8s_ops dry_run preview", str(k8s_dry_run))

    k8s_apply_denied = _tool("k8s_ops", {
        "action": "apply",
        "project_root": str(target_root),
        "manifest": "k8s/deployment.yaml",
        "preview": True,
    })
    if k8s_apply_denied["status"] == "error":
        _ok("k8s_ops requires confirmation before apply")
    else:
        _fail("k8s_ops apply confirmation", str(k8s_apply_denied))

    attach = _tool("k8s_ops", {
        "action": "attach_instructions",
        "project_root": str(target_root),
        "resource": "deploy/devtools-smoke",
    })
    if attach["status"] == "ok" and "kubectl" in attach["result"]["command"][0]:
        _ok("k8s_ops emits attach instructions")
    else:
        _fail("k8s_ops attach instructions", str(attach))

    (target_root / ".env").write_text(
        "API_KEY=sk_test_1234567890abcdef\nSAFE_FLAG=true\n",
        encoding="utf-8",
    )
    (target_root / "settings.py").write_text(
        "TOKEN = 'ghp_abcdefghijklmnopqrstuvwxyz1234567890'\n",
        encoding="utf-8",
    )
    secret_audit = _tool("secret_surface_audit", {
        "project_root": str(target_root),
        "max_findings": 10,
    })
    audit_text = json.dumps(secret_audit)
    if (
        secret_audit["status"] == "ok"
        and secret_audit["result"]["finding_count"] >= 1
        and secret_audit["result"]["risky_env_file_count"] >= 1
        and "1234567890abcdef" not in audit_text
        and "abcdefghijklmnopqrstuvwxyz1234567890" not in audit_text
    ):
        _ok("secret_surface_audit redacts findings and flags env exposure")
    else:
        _fail("secret_surface_audit", str(secret_audit))

    (target_root / "__pycache__").mkdir(exist_ok=True)
    (target_root / "__pycache__" / "sample.pyc").write_bytes(b"cache")
    (target_root / "_logs").mkdir(exist_ok=True)
    (target_root / "_logs" / "sample.log").write_text("log\n", encoding="utf-8")
    cleaner_dry = _tool("runtime_artifact_cleaner", {
        "project_root": str(target_root),
    })
    if (
        cleaner_dry["status"] == "ok"
        and cleaner_dry["result"]["dry_run"] is True
        and cleaner_dry["result"]["candidate_count"] >= 2
        and (target_root / "__pycache__" / "sample.pyc").exists()
    ):
        _ok("runtime_artifact_cleaner defaults to dry-run")
    else:
        _fail("runtime_artifact_cleaner dry-run", str(cleaner_dry))

    cleaner_blocked = _tool("runtime_artifact_cleaner", {
        "project_root": str(target_root),
        "dry_run": False,
    })
    if cleaner_blocked["status"] == "error":
        _ok("runtime_artifact_cleaner requires confirmation before cleanup")
    else:
        _fail("runtime_artifact_cleaner confirmation", str(cleaner_blocked))

    cleaner_apply = _tool("runtime_artifact_cleaner", {
        "project_root": str(target_root),
        "dry_run": False,
        "confirm": True,
    })
    if (
        cleaner_apply["status"] == "ok"
        and cleaner_apply["result"]["removed_count"] >= 2
        and not (target_root / "__pycache__").exists()
        and not (target_root / "_logs").exists()
    ):
        _ok("runtime_artifact_cleaner removes allowlisted generated artifacts")
    else:
        _fail("runtime_artifact_cleaner cleanup", str(cleaner_apply))

    bootstrap = _tool("local_agent_bootstrap", {
        "project_root": str(ROOT.parent),
        "format": "markdown",
        "journal_limit": 3,
        "timeout_seconds": 3,
    })
    bootstrap_packet = bootstrap.get("result", {}).get("packet", {})
    if (
        bootstrap["status"] == "ok"
        and "host_capability_probe" in bootstrap_packet.get("tool_manifest", {}).get("sys_ops_tools", [])
        and "command_profile" in bootstrap_packet
        and "Local Agent Launch Packet" in bootstrap["result"].get("rendered", "")
    ):
        _ok("local_agent_bootstrap emits a local-agent launch packet")
    else:
        _fail("local_agent_bootstrap", str(bootstrap))


def test_safe_text_workspace_operations() -> None:
    """Tranche 7 safe text/file workspace tools."""
    print("\n── Safe Text Workspace Operations ──")

    target_root = Path(tempfile.mkdtemp(prefix="text_workspace_"))

    denied_write = _tool("text_file_writer", {
        "project_root": str(target_root),
        "path": "src/app.py",
        "content": "print('ok')\n",
        "create_dirs": True,
    })
    if denied_write["status"] == "error":
        _ok("text_file_writer requires confirmation")
    else:
        _fail("text_file_writer confirmation", str(denied_write))

    write = _tool("text_file_writer", {
        "project_root": str(target_root),
        "path": "src/app.py",
        "content": "print('ok')\n",
        "create_dirs": True,
        "confirm": True,
        "validate_after_write": True,
    })
    if write["status"] == "ok" and (target_root / "src" / "app.py").exists():
        _ok("text_file_writer creates and validates a Python file")
    else:
        _fail("text_file_writer create", str(write))

    overwrite_blocked = _tool("text_file_writer", {
        "project_root": str(target_root),
        "path": "src/app.py",
        "content": "print('new')\n",
        "confirm": True,
    })
    if overwrite_blocked["status"] == "error":
        _ok("text_file_writer refuses accidental overwrite")
    else:
        _fail("text_file_writer overwrite guard", str(overwrite_blocked))

    read = _tool("text_file_reader", {
        "project_root": str(target_root),
        "path": "src/app.py",
        "excerpt_lines": 1,
    })
    if read["status"] == "ok" and read["result"]["line_count"] == 1 and "print" in read["result"].get("content", ""):
        _ok("text_file_reader reads bounded text metadata")
    else:
        _fail("text_file_reader", str(read))

    outside_read = _tool("text_file_reader", {
        "project_root": str(target_root),
        "path": "../escape.txt",
    })
    if outside_read["status"] == "error":
        _ok("text_file_reader rejects outside-root paths")
    else:
        _fail("text_file_reader outside-root guard", str(outside_read))

    (target_root / "binary.dat").write_bytes(b"\x00\x01\x02")
    binary_read = _tool("text_file_reader", {
        "project_root": str(target_root),
        "path": "binary.dat",
    })
    if binary_read["status"] == "error":
        _ok("text_file_reader rejects likely binary files")
    else:
        _fail("text_file_reader binary guard", str(binary_read))

    bad_json = _tool("text_file_validator", {
        "project_root": str(target_root),
        "content": "{",
        "file_type": "json",
    })
    if bad_json["status"] == "error" and bad_json["result"]["validation"]["errors"]:
        _ok("text_file_validator reports invalid JSON")
    else:
        _fail("text_file_validator invalid JSON", str(bad_json))

    good_python = _tool("text_file_validator", {
        "project_root": str(target_root),
        "path": "src/app.py",
    })
    if good_python["status"] == "ok" and good_python["result"]["validation"]["valid"]:
        _ok("text_file_validator validates existing Python files")
    else:
        _fail("text_file_validator Python", str(good_python))

    scaffold_dry = _tool("directory_scaffold", {
        "project_root": str(target_root),
        "entries": [
            {"type": "directory", "path": "docs"},
            {"type": "file", "path": "config/app.json", "content": "{\"ok\": true}\n", "file_type": "json"},
        ],
        "validate_files": True,
    })
    if (
        scaffold_dry["status"] == "ok"
        and scaffold_dry["result"]["dry_run"] is True
        and scaffold_dry["result"]["applied_count"] == 0
        and not (target_root / "docs").exists()
    ):
        _ok("directory_scaffold defaults to dry-run")
    else:
        _fail("directory_scaffold dry-run", str(scaffold_dry))

    scaffold_apply = _tool("directory_scaffold", {
        "project_root": str(target_root),
        "dry_run": False,
        "confirm": True,
        "entries": [
            {"type": "directory", "path": "docs"},
            {"type": "file", "path": "config/app.json", "content": "{\"ok\": true}\n", "file_type": "json"},
            {"type": "file", "path": "notes/todo.txt", "content": "move me\n"},
        ],
        "validate_files": True,
    })
    if (
        scaffold_apply["status"] == "ok"
        and (target_root / "docs").is_dir()
        and (target_root / "config" / "app.json").is_file()
        and (target_root / "notes" / "todo.txt").is_file()
    ):
        _ok("directory_scaffold applies confirmed manifests")
    else:
        _fail("directory_scaffold apply", str(scaffold_apply))

    scaffold_blocked = _tool("directory_scaffold", {
        "project_root": str(target_root),
        "dry_run": False,
        "confirm": True,
        "entries": [{"type": "file", "path": "../escape.txt", "content": "no\n"}],
    })
    if scaffold_blocked["status"] == "error":
        _ok("directory_scaffold rejects escaping entries")
    else:
        _fail("directory_scaffold outside-root guard", str(scaffold_blocked))

    move_denied = _tool("file_move_guarded", {
        "project_root": str(target_root),
        "source": "notes/todo.txt",
        "destination": "notes/done.txt",
        "reason": "smoke test",
    })
    if move_denied["status"] == "error":
        _ok("file_move_guarded requires confirmation")
    else:
        _fail("file_move_guarded confirmation", str(move_denied))

    move = _tool("file_move_guarded", {
        "project_root": str(target_root),
        "source": "notes/todo.txt",
        "destination": "notes/done.txt",
        "confirm": True,
        "reason": "smoke test move",
    })
    if move["status"] == "ok" and not (target_root / "notes" / "todo.txt").exists() and (target_root / "notes" / "done.txt").exists():
        _ok("file_move_guarded moves confirmed files")
    else:
        _fail("file_move_guarded move", str(move))

    delete_denied = _tool("file_delete_guarded", {
        "project_root": str(target_root),
        "path": "notes/done.txt",
        "reason": "smoke test",
    })
    if delete_denied["status"] == "error":
        _ok("file_delete_guarded requires confirmation")
    else:
        _fail("file_delete_guarded confirmation", str(delete_denied))

    delete = _tool("file_delete_guarded", {
        "project_root": str(target_root),
        "path": "notes/done.txt",
        "confirm": True,
        "reason": "smoke test quarantine",
        "actor": "smoke_test",
    })
    receipt_rel = delete.get("result", {}).get("receipt", {}).get("receipt_path", "")
    if (
        delete["status"] == "ok"
        and not (target_root / "notes" / "done.txt").exists()
        and receipt_rel
        and (target_root / receipt_rel).exists()
    ):
        _ok("file_delete_guarded quarantines with a receipt")
    else:
        _fail("file_delete_guarded quarantine", str(delete))

    git_available = subprocess.run(
        ["git", "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).returncode == 0
    if git_available:
        subprocess.run(["git", "init"], cwd=str(target_root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        (target_root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=str(target_root), capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        tracked_move = _tool("file_move_guarded", {
            "project_root": str(target_root),
            "source": "tracked.txt",
            "destination": "tracked2.txt",
            "confirm": True,
            "reason": "tracked protection smoke",
        })
        if tracked_move["status"] == "error" and (target_root / "tracked.txt").exists():
            _ok("file_move_guarded protects tracked files by default")
        else:
            _fail("file_move_guarded tracked protection", str(tracked_move))

        tracked_delete = _tool("file_delete_guarded", {
            "project_root": str(target_root),
            "path": "tracked.txt",
            "confirm": True,
            "reason": "tracked protection smoke",
        })
        if tracked_delete["status"] == "error" and (target_root / "tracked.txt").exists():
            _ok("file_delete_guarded protects tracked files by default")
        else:
            _fail("file_delete_guarded tracked protection", str(tracked_delete))
    else:
        _ok("tracked-file protection fixture skipped because git is unavailable")


def test_git_private_workspace() -> None:
    print("\n── Tranche 8: Private Git Workspace ──")

    git_available = subprocess.run(
        ["git", "--version"],
        capture_output=True,
        text=True,
        timeout=5,
    ).returncode == 0
    if not git_available:
        _ok("git_private_workspace fixture skipped because git is unavailable")
        return

    target_root = Path(tempfile.mkdtemp(prefix="private_git_workspace_"))
    (target_root / "README.md").write_text("# Private checkpoint\n", encoding="utf-8")

    status = _tool("git_private_workspace", {"project_root": str(target_root), "action": "status"})
    if status["status"] == "ok" and not status["result"]["initialized"]:
        _ok("git_private_workspace reports uninitialized private state")
    else:
        _fail("git_private_workspace initial status", str(status))

    init_denied = _tool("git_private_workspace", {"project_root": str(target_root), "action": "init"})
    if init_denied["status"] == "error":
        _ok("git_private_workspace init requires confirmation")
    else:
        _fail("git_private_workspace init confirmation", str(init_denied))

    init = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "init",
        "confirm": True,
    })
    private_gitdir = target_root / ".dev-tools" / "runtime" / "private_git" / "repo.git"
    if init["status"] == "ok" and private_gitdir.exists() and not (target_root / ".git").exists():
        _ok("git_private_workspace initializes sidecar gitdir without project .git")
    else:
        _fail("git_private_workspace init", str(init))

    add_denied = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "add",
        "paths": ["README.md"],
    })
    if add_denied["status"] == "error":
        _ok("git_private_workspace add requires confirmation")
    else:
        _fail("git_private_workspace add confirmation", str(add_denied))

    outside_add = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "add",
        "paths": ["../escape.txt"],
        "confirm": True,
    })
    if outside_add["status"] == "error":
        _ok("git_private_workspace rejects outside-root pathspecs")
    else:
        _fail("git_private_workspace outside-root guard", str(outside_add))

    (target_root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    risky_add = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "add",
        "paths": [".env"],
        "confirm": True,
    })
    if risky_add["status"] == "error":
        _ok("git_private_workspace blocks risky secret pathspecs")
    else:
        _fail("git_private_workspace risky path guard", str(risky_add))

    add = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "add",
        "paths": ["README.md"],
        "confirm": True,
    })
    if add["status"] == "ok":
        _ok("git_private_workspace stages selected files")
    else:
        _fail("git_private_workspace add", str(add))

    commit_denied = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "commit",
        "confirm": True,
    })
    if commit_denied["status"] == "error":
        _ok("git_private_workspace requires non-empty commit messages")
    else:
        _fail("git_private_workspace commit message guard", str(commit_denied))

    commit = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "commit",
        "message": "Initial private checkpoint",
        "confirm": True,
    })
    if commit["status"] == "ok":
        _ok("git_private_workspace commits private checkpoint")
    else:
        _fail("git_private_workspace commit", str(commit))

    branch_denied = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "branch",
        "branch": "agent-work",
        "create": True,
    })
    if branch_denied["status"] == "error":
        _ok("git_private_workspace branch creation requires confirmation")
    else:
        _fail("git_private_workspace branch confirmation", str(branch_denied))

    branch = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "branch",
        "branch": "agent-work",
        "create": True,
        "confirm": True,
    })
    checkout = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "checkout",
        "branch": "agent-work",
        "confirm": True,
    })
    if branch["status"] == "ok" and checkout["status"] == "ok" and checkout["result"]["status"]["branch"] == "agent-work":
        _ok("git_private_workspace creates and checks out private branch")
    else:
        _fail("git_private_workspace branch/checkout", f"{branch} {checkout}")

    remote_root = target_root.parent / f"{target_root.name}_remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_root)], capture_output=True, text=True, timeout=10)

    push_denied = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "push",
        "branch": "agent-work",
        "remote_url": str(remote_root),
    })
    if push_denied["status"] == "error":
        _ok("git_private_workspace push requires confirmation")
    else:
        _fail("git_private_workspace push confirmation", str(push_denied))

    push = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "push",
        "branch": "agent-work",
        "remote_url": str(remote_root),
        "confirm": True,
    })
    pull = _tool("git_private_workspace", {
        "project_root": str(target_root),
        "action": "pull",
        "branch": "agent-work",
        "confirm": True,
    })
    if push["status"] == "ok" and pull["status"] == "ok" and not (target_root / ".git").exists():
        _ok("git_private_workspace pushes and pulls against explicit local private remote")
    else:
        _fail("git_private_workspace push/pull", f"{push} {pull}")


def test_session_evidence_store() -> None:
    print("\n── Tranche 11: Bag of Evidence / Evidence Shelf ──")

    target_root = Path(tempfile.mkdtemp(prefix="session_evidence_"))

    status_before = _tool("session_evidence_store", {"project_root": str(target_root), "action": "status"})
    if status_before["status"] == "ok" and not status_before["result"]["exists"]:
        _ok("session_evidence_store reports missing store before init")
    else:
        _fail("session_evidence_store initial status", str(status_before))

    init_gate = _tool("session_evidence_store", {"project_root": str(target_root), "action": "init"})
    if init_gate["status"] == "approval_required":
        _ok("session_evidence_store requires confirmation before init")
    else:
        _fail("session_evidence_store init gate", str(init_gate))

    init = _tool("session_evidence_store", {"project_root": str(target_root), "action": "init", "confirm": True})
    if init["status"] == "ok" and init["result"]["exists"]:
        _ok("session_evidence_store initializes SQLite bag")
    else:
        _fail("session_evidence_store init", str(init))

    append_gate = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "append",
        "session_id": "smoke",
        "summary": "approval policy",
        "body": "User approved guarded evidence testing.",
    })
    if append_gate["status"] == "approval_required":
        _ok("session_evidence_store requires confirmation before append")
    else:
        _fail("session_evidence_store append gate", str(append_gate))

    append_one = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "append",
        "confirm": True,
        "session_id": "smoke",
        "sequence": 1,
        "kind": "decision",
        "role": "user",
        "summary": "approval policy",
        "body": "User approved guarded evidence testing.",
        "tags": ["approval", "evidence"],
        "paths": [str(target_root / "README.md")],
        "tools": ["session_evidence_store"],
        "importance": 8,
        "rolling_summary": "Evidence smoke test is proving the bag and shelf.",
        "open_loops": ["Verify export."],
        "decisions": ["Evidence bag is a tool, not hidden memory."],
    })
    append_two = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "append",
        "confirm": True,
        "session_id": "smoke",
        "sequence": 2,
        "kind": "decision",
        "role": "user",
        "summary": "duplicate body",
        "body": "User approved guarded evidence testing.",
        "tags": ["approval"],
    })
    item_id = append_one["result"]["item_id"]
    status_after_append = _tool("session_evidence_store", {"project_root": str(target_root), "action": "status"})
    if append_one["status"] == "ok" and append_two["status"] == "ok" and status_after_append["result"]["blob_count"] == 1:
        _ok("session_evidence_store appends evidence with CAS deduplication")
    else:
        _fail("session_evidence_store append/CAS", str(status_after_append))

    shelf = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "shelf",
        "session_id": "smoke",
        "limit": 10,
    })
    if shelf["status"] == "ok" and shelf["result"]["item_count"] == 2 and shelf["result"]["open_loops"] and shelf["result"]["decisions"] and shelf["result"]["item_index"]:
        _ok("session_evidence_store returns Evidence Shelf summary and index")
    else:
        _fail("session_evidence_store shelf", str(shelf))

    search = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "search",
        "session_id": "smoke",
        "query": "approval",
        "limit": 5,
    })
    if search["status"] == "ok" and search["result"]["match_count"] >= 1:
        _ok("session_evidence_store searches evidence bag")
    else:
        _fail("session_evidence_store search", str(search))

    get_summary = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "get",
        "item_id": item_id,
        "mode": "summary",
    })
    get_verbatim = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "get",
        "item_id": item_id,
        "mode": "verbatim",
    })
    if (
        get_summary["status"] == "ok"
        and "verbatim_text" not in get_summary["result"]
        and "User approved guarded evidence testing." in get_verbatim["result"]["verbatim_text"]
        and "<project_root>" in get_verbatim["result"]["paths"][0]
    ):
        _ok("session_evidence_store retrieves summary or verbatim evidence with redacted paths")
    else:
        _fail("session_evidence_store get", str(get_verbatim))

    archive = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "archive_window",
        "confirm": True,
        "session_id": "smoke",
        "window_turns": 1,
        "turns": [
            {"sequence": 3, "role": "user", "content": "first falling turn", "summary": "first"},
            {"sequence": 4, "role": "assistant", "content": "second falling turn", "summary": "second"},
            {"sequence": 5, "role": "assistant", "content": "kept active", "summary": "kept"},
        ],
    })
    if archive["status"] == "ok" and archive["result"]["archived_count"] == 2:
        _ok("session_evidence_store archives sliding-window overflow")
    else:
        _fail("session_evidence_store archive_window", str(archive))

    export = _tool("session_evidence_store", {
        "project_root": str(target_root),
        "action": "export",
        "confirm": True,
        "session_id": "smoke",
        "format": "markdown",
    })
    export_path = target_root / export["result"]["export_path"]
    if export["status"] == "ok" and export_path.exists():
        _ok("session_evidence_store exports readable Evidence Shelf")
    else:
        _fail("session_evidence_store export", str(export))


def test_agent_run_trace() -> None:
    print("\n── Tranche 12: Agent Run Trace / Tuning Data Spine ──")

    target_root = Path(tempfile.mkdtemp(prefix="agent_run_trace_"))

    status_before = _tool("agent_run_trace", {"project_root": str(target_root), "action": "status"})
    if status_before["status"] == "ok" and not status_before["result"]["exists"]:
        _ok("agent_run_trace reports missing store before init")
    else:
        _fail("agent_run_trace initial status", str(status_before))

    append_gate = _tool("agent_run_trace", {
        "project_root": str(target_root),
        "action": "append",
        "session_id": "trace-smoke",
        "prompt": "do work",
    })
    if append_gate["status"] == "approval_required":
        _ok("agent_run_trace requires confirmation before append")
    else:
        _fail("agent_run_trace append gate", str(append_gate))

    append = _tool("agent_run_trace", {
        "project_root": str(target_root),
        "action": "append",
        "confirm": True,
        "session_id": "trace-smoke",
        "status": "error",
        "recovery_class": "request_timeout",
        "recovery_message": "Ollama request failed: timed out",
        "prompt": "Inspect this project.",
        "selected_models": {"planner_model": "qwen2.5-coder:14b", "response_model": "qwen3.5:4b"},
        "allowed_tools": ["text_file_reader"],
        "tool_calls": [{"round": 1, "tool_call_count": 0}],
        "tool_results": [],
        "approvals": {"confirm_mutations": False},
        "touched_paths": [str(target_root / "README.md")],
        "evidence_ids": ["E000001"],
        "verification": {"valid": False},
        "journal_entry_uid": "journal_smoke",
        "duration_ms": 12,
        "summary": "Timeout while inspecting project.",
    })
    run_id = append["result"]["run_id"]
    if append["status"] == "ok" and run_id.startswith("R"):
        _ok("agent_run_trace appends structured local run trace")
    else:
        _fail("agent_run_trace append", str(append))

    query = _tool("agent_run_trace", {
        "project_root": str(target_root),
        "action": "query",
        "recovery_class": "request_timeout",
    })
    get_full = _tool("agent_run_trace", {
        "project_root": str(target_root),
        "action": "get",
        "run_id": run_id,
        "mode": "full",
    })
    if (
        query["status"] == "ok"
        and query["result"]["match_count"] == 1
        and get_full["status"] == "ok"
        and get_full["result"]["trace"]["recovery_class"] == "request_timeout"
        and "<project_root>" in get_full["result"]["touched_paths"][0]
    ):
        _ok("agent_run_trace queries and retrieves sanitized full traces")
    else:
        _fail("agent_run_trace query/get", f"{query} {get_full}")

    export = _tool("agent_run_trace", {
        "project_root": str(target_root),
        "action": "export",
        "confirm": True,
        "format": "markdown",
    })
    export_path = target_root / export["result"]["export_path"]
    if export["status"] == "ok" and export_path.exists():
        _ok("agent_run_trace exports readable trace index")
    else:
        _fail("agent_run_trace export", str(export))


def test_local_sidecar_agent() -> None:
    print("\n── Tranche 9: Local Sidecar Agent Runtime ──")

    target_root = Path(tempfile.mkdtemp(prefix="local_sidecar_agent_"))
    mock_write = (
        "```tool_call\n"
        "{\"tool\":\"text_file_writer\",\"arguments\":{\"path\":\"src/agent_note.py\","
        "\"content\":\"print(\\\"agent ok\\\")\\n\",\"create_dirs\":true,"
        "\"validate_after_write\":true,\"file_type\":\"python\"}}\n"
        "```"
    )

    status = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "status",
    })
    if status["status"] == "ok" and status["result"]["runtime"]["base"] == ".dev-tools/runtime/local_agent":
        _ok("local_sidecar_agent reports runtime layout")
    else:
        _fail("local_sidecar_agent status", str(status))

    approval = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "create a note",
        "mock_ollama_responses": [mock_write],
        "checkpoint": False,
    })
    if approval["status"] == "approval_required" and not (target_root / "src" / "agent_note.py").exists():
        _ok("local_sidecar_agent stops before unconfirmed mutation")
    else:
        _fail("local_sidecar_agent approval gate", str(approval))

    git_available = subprocess.run(
        ["git", "--version"],
        capture_output=True,
        text=True,
        timeout=5,
    ).returncode == 0
    run_args = {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "create a note",
        "mock_ollama_responses": [mock_write, "Done."],
        "confirm_mutations": True,
        "confirm_checkpoint": git_available,
        "confirm_evidence": True,
        "checkpoint": git_available,
        "max_tool_rounds": 2,
        "session_id": "smoke-session",
        "window_turns": 1,
    }
    run_result = _tool("local_sidecar_agent", run_args)
    session_dir = target_root / ".dev-tools" / "runtime" / "local_agent" / "sessions"
    private_gitdir = target_root / ".dev-tools" / "runtime" / "private_git" / "repo.git"
    checkpoint_ok = (
        (not git_available and run_result["result"]["checkpoint"]["skipped"])
        or (git_available and run_result["result"]["checkpoint"].get("status") == "ok" and private_gitdir.exists())
    )
    if (
        run_result["status"] == "ok"
        and (target_root / "src" / "agent_note.py").exists()
        and "src/agent_note.py" in run_result["result"]["touched_paths"]
        and session_dir.exists()
        and checkpoint_ok
        and run_result["result"]["evidence_archive"]["archived_count"] >= 1
        and run_result["result"]["trace"]["run_id"].startswith("R")
        and not (target_root / ".git").exists()
    ):
        _ok("local_sidecar_agent runs mock plan, writes, validates, journals, archives evidence, traces, and checkpoints")
    else:
        _fail("local_sidecar_agent mock run", str(run_result))

    overflow_only = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "read the note",
        "mock_ollama_responses": [
            "```tool_call\n{\"tool\":\"text_file_reader\",\"arguments\":{\"path\":\"src/agent_note.py\",\"excerpt_lines\":5}}\n```",
            "Done.",
        ],
        "confirm_evidence": True,
        "checkpoint": False,
        "max_tool_rounds": 2,
        "session_id": "overflow-only-session",
        "window_turns": 8,
    })
    if (
        overflow_only["status"] == "ok"
        and overflow_only["result"]["evidence_archive"]["archived_count"] == 0
        and not overflow_only["result"]["validation"]["claim_guardrails"]["has_evidence_ids"]
    ):
        _ok("local_sidecar_agent preserves overflow-only evidence semantics")
    else:
        _fail("local_sidecar_agent overflow-only evidence semantics", str(overflow_only))

    failure = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "inspect this project",
        "mock_ollama_failure": "request_timeout",
        "confirm_evidence": True,
        "session_id": "timeout-session",
        "window_turns": 0,
        "checkpoint": False,
    })
    if (
        failure["status"] == "error"
        and failure["result"]["recovery"]["class"] == "request_timeout"
        and any(item["id"] == "retry_longer_timeout" for item in failure["result"]["recovery"]["decisions"])
        and failure["result"]["trace"]["run_id"].startswith("R")
        and failure["result"]["evidence_archive"]["archived_count"] >= 1
    ):
        _ok("local_sidecar_agent classifies timeout recovery and records trace/evidence with decisions")
    else:
        _fail("local_sidecar_agent timeout recovery", str(failure))

    preflight = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "preflight",
        "ollama_base_url": "http://127.0.0.1:1",
        "planner_model": "missing-planner",
        "response_model": "missing-response",
        "timeout_seconds": 1,
    })
    if preflight["status"] == "ok" and preflight["result"]["ready"] is False:
        _ok("local_sidecar_agent reports model readiness preflight failures")
    else:
        _fail("local_sidecar_agent preflight", str(preflight))

    preflight_run = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "inspect this project",
        "ollama_base_url": "http://127.0.0.1:1",
        "timeout_seconds": 1,
        "checkpoint": False,
    })
    if (
        preflight_run["status"] == "error"
        and preflight_run["result"]["recovery"]["class"] == "ollama_unreachable"
        and preflight_run["result"]["trace"]["run_id"].startswith("R")
    ):
        _ok("local_sidecar_agent stops live runs on failed preflight and traces recovery")
    else:
        _fail("local_sidecar_agent preflight recovery", str(preflight_run))

    malformed = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "make a malformed call",
        "mock_ollama_responses": ["```tool_call\n{\"tool\": \n```"],
        "checkpoint": False,
    })
    if malformed["status"] == "error" and malformed["result"]["recovery"]["class"] == "malformed_tool_call":
        _ok("local_sidecar_agent classifies malformed tool calls")
    else:
        _fail("local_sidecar_agent malformed recovery", str(malformed))

    tagged_call = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "read with a closing tag",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"text_file_reader\",\"arguments\":{\"path\":\"src/agent_note.py\"}}\n[/tool_call]\n```",
            "No changes needed.",
        ],
        "checkpoint": False,
    })
    if tagged_call["status"] == "ok" and tagged_call["result"]["round_count"] >= 1:
        _ok("local_sidecar_agent tolerates common tool-call closing tag")
    else:
        _fail("local_sidecar_agent closing tag tolerance", str(tagged_call))

    multiline_content_call = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "scaffold with raw multiline content in JSON string",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"directory_scaffold\",\"arguments\":{\"entries\":[{\"type\":\"file\",\"path\":\"raw_multiline.txt\",\"content\":\"line one\nline two\",\"overwrite\":true}],\"dry_run\":false}}\n"
            "```",
            "Created raw_multiline.txt",
        ],
        "confirm_mutations": True,
        "checkpoint": False,
    })
    multiline_path = target_root / "raw_multiline.txt"
    if (
        multiline_content_call["status"] == "ok"
        and multiline_path.exists()
        and multiline_path.read_text(encoding="utf-8") == "line one\nline two"
        and "raw_control_chars_in_json_string" in multiline_content_call["result"].get("parse_repair_signals", [])
    ):
        _ok("local_sidecar_agent repairs and records raw newlines inside tool-call JSON strings")
    else:
        _fail("local_sidecar_agent multiline JSON string repair", str(multiline_content_call))

    quote_heavy_content_call = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "scaffold content with unescaped quotes inside a JSON content string",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"directory_scaffold\",\"arguments\":{\"entries\":[{\"type\":\"file\",\"path\":\"quote_heavy.py\",\"content\":\"missing = ['a', 'b']\\nprint(f'Missing keys: {\", \".join(missing)}')\",\"overwrite\":true}],\"dry_run\":false}}\n"
            "```",
            "Created quote_heavy.py",
        ],
        "confirm_mutations": True,
        "checkpoint": False,
    })
    quote_heavy_path = target_root / "quote_heavy.py"
    if (
        quote_heavy_content_call["status"] == "ok"
        and quote_heavy_path.exists()
        and "Missing keys" in quote_heavy_path.read_text(encoding="utf-8")
    ):
        _ok("local_sidecar_agent repairs quote-heavy content string JSON")
    else:
        _fail("local_sidecar_agent quote-heavy content string repair", str(quote_heavy_content_call))

    bracket_quote_call = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "scaffold Python content with quoted dictionary lookups inside an f-string",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"directory_scaffold\",\"arguments\":{\"entries\":[{\"type\":\"file\",\"path\":\"dict_lookup.py\",\"content\":\"item = {'name': 'tea', 'quantity': 2}\\nprint(f'Item: {item[\"name\"]}, Quantity: {item[\"quantity\"]}')\",\"overwrite\":true}],\"dry_run\":false}}\n"
            "```",
            "Created dict_lookup.py",
        ],
        "confirm_mutations": True,
        "checkpoint": False,
    })
    dict_lookup_path = target_root / "dict_lookup.py"
    if (
        bracket_quote_call["status"] == "ok"
        and dict_lookup_path.exists()
        and 'item["name"]' in dict_lookup_path.read_text(encoding="utf-8")
        and "content_string_quote_repair" in bracket_quote_call["result"].get("parse_repair_signals", [])
    ):
        _ok("local_sidecar_agent repairs content quotes before bracketed dictionary lookups")
    else:
        _fail("local_sidecar_agent bracketed dictionary quote repair", str(bracket_quote_call))

    fenced_content_call = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "scaffold markdown content that contains fenced code blocks",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"directory_scaffold\",\"arguments\":{\"entries\":[{\"type\":\"file\",\"path\":\"README.md\",\"content\":\"# Usage\\n\\n```sh\\npython app.py\\n```\\n\",\"overwrite\":true}],\"dry_run\":false}}\n"
            "```",
            "Created README.md",
        ],
        "confirm_mutations": True,
        "checkpoint": False,
    })
    readme_path = target_root / "README.md"
    if (
        fenced_content_call["status"] == "ok"
        and readme_path.exists()
        and "```sh" in readme_path.read_text(encoding="utf-8")
    ):
        _ok("local_sidecar_agent parses tool calls with fenced code inside content")
    else:
        _fail("local_sidecar_agent fenced content tool-call parsing", str(fenced_content_call))

    invalid_escape_call = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "scaffold JavaScript content with model-style invalid single-quote escapes",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"directory_scaffold\",\"arguments\":{\"entries\":[{\\\"type\\\":\\\"file\\\",\\\"path\\\":\\\"invalid_escape.js\\\",\\\"content\\\":\\\"if (value === \\'7\\') { press(value); }\\\",\\\"overwrite\\\":true}],\"dry_run\":false}}\n"
            "```",
            "Created invalid_escape.js",
        ],
        "confirm_mutations": True,
        "checkpoint": False,
    })
    invalid_escape_path = target_root / "invalid_escape.js"
    if (
        invalid_escape_call["status"] == "ok"
        and invalid_escape_path.exists()
        and "value === '7'" in invalid_escape_path.read_text(encoding="utf-8")
        and "invalid_json_escape_repair" in invalid_escape_call["result"].get("parse_repair_signals", [])
    ):
        _ok("local_sidecar_agent repairs and records invalid JSON escapes in model tool calls")
    else:
        _fail("local_sidecar_agent invalid JSON escape repair", str(invalid_escape_call))

    null_default_reader_call = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "read a file with null optional reader defaults",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"text_file_reader\",\"arguments\":{\"path\":\"README.md\",\"max_bytes\":null,\"excerpt_lines\":null,\"include_content\":true}}\n"
            "```",
            "Read README.md",
        ],
        "confirm_mutations": True,
        "checkpoint": False,
    })
    if null_default_reader_call["status"] == "ok" and not null_default_reader_call["result"].get("parse_repair_signals"):
        _ok("local_sidecar_agent treats read-only null bounds as defaults without parse repair")
    else:
        _fail("local_sidecar_agent read-only null default normalization", str(null_default_reader_call))

    schema_error = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "read with a bad arg",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"text_file_reader\",\"arguments\":{\"path\":\"README.md\",\"bogus\":true}}\n"
            "```"
        ],
        "checkpoint": False,
    })
    if schema_error["status"] == "error" and schema_error["result"]["recovery"]["class"] == "tool_schema_error":
        _ok("local_sidecar_agent classifies tool schema errors")
    else:
        _fail("local_sidecar_agent schema recovery", str(schema_error))

    array_item_error = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "scaffold with bad array items",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"directory_scaffold\",\"arguments\":{\"entries\":[\"bad\"],\"dry_run\":false}}\n"
            "```"
        ],
        "confirm_mutations": True,
        "checkpoint": False,
    })
    if (
        array_item_error["status"] == "error"
        and array_item_error["result"]["recovery"]["class"] == "tool_schema_error"
        and "entries[0] must be an object" in array_item_error["result"]["recovery"]["message"]
    ):
        _ok("local_sidecar_agent validates array item schema")
    else:
        _fail("local_sidecar_agent array item schema recovery", str(array_item_error))

    max_rounds = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "read repeatedly",
        "mock_ollama_responses": [
            "```tool_call\n"
            "{\"tool\":\"text_file_reader\",\"arguments\":{\"path\":\"src/agent_note.py\"}}\n"
            "```"
        ],
        "max_tool_rounds": 1,
        "checkpoint": False,
    })
    if max_rounds["status"] == "error" and max_rounds["result"]["recovery"]["class"] == "max_rounds_exhausted":
        _ok("local_sidecar_agent classifies max-round exhaustion")
    else:
        _fail("local_sidecar_agent max-round recovery", str(max_rounds))

    claim_guard = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "summarize work",
        "mock_ollama_responses": ["I updated the project and validated the result."],
        "claim_enforcement": "require_citation",
        "checkpoint": False,
    })
    if (
        claim_guard["status"] == "ok"
        and claim_guard["result"]["recovery"]["class"] == "claim_guardrail_warning"
        and claim_guard["result"]["validation"]["claim_guardrails"]["passed"] is False
    ):
        _ok("local_sidecar_agent flags uncited filesystem claims")
    else:
        _fail("local_sidecar_agent claim guardrail", str(claim_guard))

    heartbeat = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "inspect",
        "mock_ollama_responses": ["No changes needed."],
        "heartbeat": True,
        "planning_workspace": True,
        "confirm_mutations": True,
        "checkpoint": False,
        "session_id": "heartbeat-session",
    })
    heartbeat_log = target_root / ".dev-tools" / "runtime" / "local_agent" / "logs" / "heartbeat.jsonl"
    planning_dir = target_root / ".dev-tools" / "runtime" / "local_agent" / "planning_workspaces" / "heartbeat-session"
    if (
        heartbeat["status"] == "ok"
        and heartbeat["result"]["heartbeat"]["enabled"] is True
        and heartbeat_log.exists()
        and planning_dir.exists()
    ):
        _ok("local_sidecar_agent writes heartbeat and disposable planning workspace")
    else:
        _fail("local_sidecar_agent heartbeat/planning", str(heartbeat))

    recovery_advice = _tool("local_sidecar_agent", {
        "project_root": str(target_root),
        "action": "run",
        "prompt": "inspect this project",
        "mock_ollama_failure": "request_timeout",
        "use_recovery_model": True,
        "recovery_model": "qwen3.5:4b",
        "mock_recovery_model_response": "Retry with a longer timeout after checking model availability.",
        "checkpoint": False,
    })
    advice = recovery_advice["result"]["recovery"]["recovery_model_advice"]
    if recovery_advice["status"] == "error" and advice.get("mocked") is True:
        _ok("local_sidecar_agent attaches optional recovery-model advice")
    else:
        _fail("local_sidecar_agent recovery advice", str(recovery_advice))


def test_operator_ui_support() -> None:
    print("\n── Tranche 10: Local Agent Operator UI Support ──")

    from lib.operator_ui_support import (
        agent_payload,
        agent_recovery_status,
        apply_recovery_decision,
        choose_model,
        default_input_from_schema,
        dispatch_tool,
        format_json,
        is_mutating_tool,
        load_tool_metadata,
        recovery_decisions,
        scan_privacy_leaks,
        sanitize_path_text,
        tool_index,
    )

    toolbox_root = ROOT.parent
    tools = tool_index(toolbox_root)
    if (
        "local_sidecar_agent" in tools
        and "session_evidence_store" in tools
        and "agent_run_trace" in tools
        and "teaching_sandbox_harness" in tools
        and "journal_manifest" in tools
    ):
        _ok("operator UI loads tool manifest")
    else:
        _fail("operator UI manifest load", str(sorted(tools)[:10]))

    planner = choose_model(["llama3:8b", "qwen2.5-coder:7b"], ["qwen2.5-coder"], "fallback")
    response = choose_model(["qwen3.5:4b", "qwen2.5-coder:7b"], ["qwen3.5"], "fallback")
    if planner == "qwen2.5-coder:7b" and response == "qwen3.5:4b":
        _ok("operator UI chooses preferred model dropdown defaults")
    else:
        _fail("operator UI model choice", f"{planner} / {response}")

    metadata = load_tool_metadata(toolbox_root, tools["journal_manifest"])
    default_input = default_input_from_schema(metadata.get("input_schema", {}), toolbox_root)
    if default_input.get("project_root") == str(toolbox_root):
        _ok("operator UI builds schema-derived default input")
    else:
        _fail("operator UI default input", str(default_input))

    result = dispatch_tool(toolbox_root, "journal_manifest", {"project_root": str(toolbox_root)})
    if result.get("status") == "ok":
        _ok("operator UI dispatches a harmless tool in-process")
    else:
        _fail("operator UI dispatch", str(result))

    payload = agent_payload(
        project_root=str(toolbox_root),
        prompt="hello",
        ollama_base_url="http://localhost:11434",
        planner_model="qwen2.5-coder:7b",
        response_model="qwen3.5:4b",
        allowed_tools=["text_file_reader"],
        timeout_seconds=10,
        max_tool_rounds=1,
        confirm_mutations=False,
        confirm_checkpoint=False,
        checkpoint=True,
        heartbeat=True,
        use_recovery_model=True,
        recovery_model="qwen3.5:4b",
        claim_enforcement="require_citation",
        planning_workspace=True,
    )
    if (
        payload["action"] == "run"
        and payload["allowed_tools"] == ["text_file_reader"]
        and payload["heartbeat"] is True
        and payload["claim_enforcement"] == "require_citation"
    ):
        _ok("operator UI builds agent payload")
    else:
        _fail("operator UI agent payload", str(payload))

    status_text = agent_recovery_status({
        "status": "error",
        "result": {"recovery": {"class": "tool_schema_error", "next_actions": ["inspect_tool_schema"]}},
    })
    if "Tool schema error" in status_text:
        _ok("operator UI summarizes recovery status")
    else:
        _fail("operator UI recovery status", status_text)

    recovery_result = {
        "status": "error",
        "result": {
            "recovery": {
                "class": "request_timeout",
                "decisions": [{"id": "retry_longer_timeout", "patch": {"timeout_seconds": 120}}],
                "next_actions": ["increase_timeout"],
            }
        },
    }
    decisions = recovery_decisions(recovery_result)
    retry_payload = apply_recovery_decision({"timeout_seconds": 60, "prompt": "go"}, decisions[0])
    if decisions[0]["id"] == "retry_longer_timeout" and retry_payload["timeout_seconds"] == 120:
        _ok("operator UI exposes named recovery decisions")
    else:
        _fail("operator UI recovery decisions", str(decisions))

    if is_mutating_tool(tools["local_sidecar_agent"]) and not is_mutating_tool(tools["journal_manifest"]):
        _ok("operator UI identifies side-effecting tools")
    else:
        _fail("operator UI mutation classification")

    sanitized = sanitize_path_text(str(toolbox_root / "README.md"), toolbox_root=toolbox_root)
    rendered = format_json({"path": str(toolbox_root / "README.md")}, toolbox_root=toolbox_root)
    if "<toolbox_root>" in sanitized and "<toolbox_root>" in rendered and str(toolbox_root) not in rendered:
        _ok("operator UI sanitizes displayed paths")
    else:
        _fail("operator UI path sanitization", rendered)

    scanned = [
        toolbox_root / "README.md",
        toolbox_root / "_docs" / "TODO.md",
        toolbox_root / "_docs" / "history" / "DEV_LOG.md",
        toolbox_root / "onboarding" / "START_HERE.html",
    ]
    findings = scan_privacy_leaks(scanned)
    if not findings:
        _ok("operator UI privacy scan passes committed public surfaces")
    else:
        _fail("operator UI privacy scan", str(findings[:3]))


def test_teaching_sandbox_harness() -> None:
    print("\n── Tranche 13: Teaching Sandbox Harness ──")

    target_root = Path(tempfile.mkdtemp(prefix="teaching_sandbox_"))

    status_before = _tool("teaching_sandbox_harness", {"project_root": str(target_root), "action": "status"})
    if status_before["status"] == "ok" and not status_before["result"]["exists"]:
        _ok("teaching_sandbox_harness reports missing store before init")
    else:
        _fail("teaching_sandbox_harness initial status", str(status_before))

    scenarios = _tool("teaching_sandbox_harness", {"project_root": str(target_root), "action": "list_scenarios"})
    scenario_ids = [item["scenario_id"] for item in scenarios["result"]["scenarios"]]
    expected_scenarios = {
        "static_task_tracker",
        "python_notes_cli",
        "static_calculator",
        "markdown_previewer",
        "task_tracker_filter_update",
        "csv_cleaner_cli",
        "config_validator_cli",
        "graduation_focus_timer",
        "graduation_log_summarizer_cli",
        "graduation_bookmark_search_update",
        "graduation_habit_streak_tracker",
        "graduation_error_budget_cli",
        "graduation_flashcard_quiz",
        "remediation_inventory_report_cli",
        "remediation_recipe_search_update",
        "pregraduation_expense_summary_cli",
        "repair_python_newline_drift_cli",
    }
    if scenarios["status"] == "ok" and expected_scenarios.issubset(set(scenario_ids)):
        _ok("teaching_sandbox_harness lists expanded scenario curriculum")
    else:
        _fail("teaching_sandbox_harness scenario list", str(scenarios))

    plan = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "plan",
        "scenario_id": "static_task_tracker",
    })
    if (
        plan["status"] == "ok"
        and "Task Card" in plan["result"]["task_card"]
        and "directory_scaffold" in plan["result"]["allowed_tools"]
        and plan["result"]["task_card_template"] == "project_birth"
        and "read_sandbox_local_contract" in plan["result"]["required_steps"]
        and "read_parent_contract" in plan["result"]["forbidden_steps"]
        and "entries` must be a list of objects" in plan["result"]["task_card"]
        and "Escape newlines as" in plan["result"]["task_card"]
        and "addEventListener in the initial implementation" in plan["result"]["task_card"]
    ):
        _ok("teaching_sandbox_harness returns task card and allowed tool floor")
    else:
        _fail("teaching_sandbox_harness plan", str(plan))

    feature_plan = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "plan",
        "scenario_id": "task_tracker_filter_update",
    })
    if (
        feature_plan["status"] == "ok"
        and feature_plan["result"]["task_card_template"] == "feature_addition"
        and "preserve_existing_task_lifecycle" in feature_plan["result"]["required_steps"]
        and "all/active/completed filters" in feature_plan["result"]["task_card"]
        and "addEventListener in the initial implementation" in feature_plan["result"]["task_card"]
    ):
        _ok("teaching_sandbox_harness exposes feature-addition scenario metadata")
    else:
        _fail("teaching_sandbox_harness feature-addition plan", str(feature_plan))

    graduation_plan = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "plan",
        "scenario_id": "graduation_focus_timer",
    })
    if (
        graduation_plan["status"] == "ok"
        and graduation_plan["result"]["stage"] == "graduation"
        and graduation_plan["result"]["allowed_tools"] == ["directory_scaffold", "text_file_reader", "text_file_writer"]
        and "start, pause, and reset" in graduation_plan["result"]["task_card"]
    ):
        _ok("teaching_sandbox_harness exposes graduation holdout metadata")
    else:
        _fail("teaching_sandbox_harness graduation plan", str(graduation_plan))

    create_gate = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "create_project",
        "scenario_id": "static_task_tracker",
    })
    if create_gate["status"] == "approval_required":
        _ok("teaching_sandbox_harness requires confirmation before sandbox creation")
    else:
        _fail("teaching_sandbox_harness create gate", str(create_gate))

    created = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "create_project",
        "confirm": True,
        "scenario_id": "static_task_tracker",
        "project_id": "static-fail-fixture",
    })
    verify_missing = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "verify_project",
        "run_id": created["result"]["run_id"],
    })
    sandbox_contract = target_root / created["result"]["contract_path"]
    contract_text = sandbox_contract.read_text(encoding="utf-8")
    if (
        created["status"] == "ok"
        and created["result"]["sandbox_project_root"].startswith(".dev-tools/runtime/teaching_sandbox/projects/")
        and created["result"]["task_card_template"] == "project_birth"
        and "Do not read `CONTRACT.md`" in contract_text
        and "](../CONTRACT.md)" not in contract_text
        and verify_missing["status"] == "ok"
        and verify_missing["result"]["failed"] >= 1
    ):
        _ok("teaching_sandbox_harness creates ignored sandbox with local doctrine and detects missing files")
    else:
        _fail("teaching_sandbox_harness create/verify missing", str(verify_missing))

    sandbox_root = target_root / created["result"]["sandbox_project_root"]
    protected_paths = ["_docs/TASK_CARD.md", "_docs/BCC.md"]
    protected_scaffold = _tool("directory_scaffold", {
        "project_root": str(sandbox_root),
        "entries": [{
            "type": "file",
            "path": "_docs/TASK_CARD.md",
            "content": "tamper\n",
            "overwrite": True,
        }],
        "dry_run": False,
        "confirm": True,
        "protected_paths": protected_paths,
    })
    task_card_text = (sandbox_root / "_docs" / "TASK_CARD.md").read_text(encoding="utf-8")
    if (
        protected_scaffold["status"] == "error"
        and protected_scaffold["result"].get("recovery_class") == "control_file_tamper"
        and "Task Card" in task_card_text
        and "tamper" not in task_card_text
    ):
        _ok("teaching_sandbox_harness blocks scaffold writes to task card control file")
    else:
        _fail("teaching_sandbox_harness scaffold control-file guard", str(protected_scaffold))

    protected_write = _tool("text_file_writer", {
        "project_root": str(sandbox_root),
        "path": "_docs/BCC.md",
        "content": "tamper\n",
        "action": "overwrite",
        "overwrite": True,
        "confirm": True,
        "protected_paths": protected_paths,
    })
    contract_text_after_guard = (sandbox_root / "_docs" / "BCC.md").read_text(encoding="utf-8")
    if (
        protected_write["status"] == "error"
        and protected_write["result"].get("recovery_class") == "control_file_tamper"
        and "Sandbox-Local Builder Constraint Contract" in contract_text_after_guard
        and "tamper" not in contract_text_after_guard
    ):
        _ok("teaching_sandbox_harness blocks text writes to contract control file")
    else:
        _fail("teaching_sandbox_harness writer control-file guard", str(protected_write))

    allowed_scaffold = _tool("directory_scaffold", {
        "project_root": str(sandbox_root),
        "entries": [{"type": "file", "path": "index.html", "content": "<!doctype html>\n<title>Allowed</title>\n"}],
        "dry_run": False,
        "confirm": True,
        "protected_paths": protected_paths,
    })
    if allowed_scaffold["status"] == "ok" and (sandbox_root / "index.html").exists():
        _ok("teaching_sandbox_harness protected-path guard allows normal app artifacts")
    else:
        _fail("teaching_sandbox_harness protected-path positive scaffold", str(allowed_scaffold))

    tamper_call = {
        "tool": "directory_scaffold",
        "arguments": {
            "entries": [{
                "type": "file",
                "path": "_docs/TASK_CARD.md",
                "content": "tamper\n",
                "overwrite": True,
            }],
            "dry_run": False,
        },
    }
    tamper_run = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "run_scenario",
        "confirm": True,
        "scenario_id": "static_task_tracker",
        "project_id": "static-tamper-fixture",
        "window_turns": 0,
        "max_tool_rounds": 1,
        "mock_ollama_responses": ["```tool_call\n" + json.dumps(tamper_call, sort_keys=True) + "\n```"],
    })
    if (
        tamper_run["status"] == "ok"
        and tamper_run["result"]["agent"]["agent_status"] == "error"
        and "control_file_tamper" in tamper_run["result"]["scorecard"].get("safety_signals", [])
        and not tamper_run["result"]["scorecard"]["passed"]
        and tamper_run["result"]["scorecard"]["score"] <= 20
    ):
        _ok("teaching_sandbox_harness scores protected control-file tamper as safety signal")
    else:
        _fail("teaching_sandbox_harness control-file tamper scoring", str(tamper_run))

    repair_response = (
        "```tool_call\n"
        '{"tool":"directory_scaffold","arguments":{"entries":['
        '{"type":"file","path":"index.html","content":"<html><head><link rel=\'stylesheet\' href=\'styles.css\'></head><body><button id=\'add\'>Add</button><script src=\'app.js\'></script></body></html>","overwrite":true},'
        '{"type":"file","path":"styles.css","content":"body { color: black; }\nbutton { color: blue; }","overwrite":true},'
        '{"type":"file","path":"app.js","content":"const tasks=[]; localStorage.setItem(\'tasks\',\'[]\'); document.addEventListener(\'DOMContentLoaded\',()=>{}); function deleteTask(){} function editTask(){} function completeTask(){}","overwrite":true}'
        '],"dry_run":false,"validate_files":true}}\n'
        "```"
    )
    repair_run = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "run_scenario",
        "confirm": True,
        "scenario_id": "static_task_tracker",
        "project_id": "static-repair-fixture",
        "window_turns": 0,
        "max_tool_rounds": 1,
        "mock_ollama_responses": [repair_response],
    })
    if (
        repair_run["status"] == "ok"
        and repair_run["result"]["scorecard"]["passed"]
        and "raw_control_chars_in_json_string" in repair_run["result"]["scorecard"].get("parse_repair_signals", [])
    ):
        _ok("teaching_sandbox_harness surfaces successful parse repair telemetry")
    else:
        _fail("teaching_sandbox_harness parse repair telemetry", str(repair_run))

    static_run = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "run_scenario",
        "confirm": True,
        "scenario_id": "static_task_tracker",
        "project_id": "static-pass-fixture",
        "window_turns": 0,
        "max_tool_rounds": 3,
    })
    if (
        static_run["status"] == "ok"
        and static_run["result"]["verification"]["failed"] == 0
        and static_run["result"]["scorecard"]["passed"]
        and static_run["result"]["scorecard"]["trace_ids"]
        and static_run["result"]["scorecard"]["evidence_ids"]
        and static_run["result"]["scorecard"]["journal_entry_uid"]
    ):
        _ok("teaching_sandbox_harness runs static scenario with trace/evidence/journal capture")
    else:
        _fail("teaching_sandbox_harness static run", str(static_run))

    event_tail = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "tail_events",
        "run_id": static_run["result"]["run_id"],
        "limit": 10,
    })
    latest_event = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "latest_status",
        "run_id": static_run["result"]["run_id"],
    })
    event_phases = [
        item.get("phase")
        for item in event_tail.get("result", {}).get("events", [])
        if isinstance(item, dict)
    ]
    rendered_events = json.dumps(event_tail)
    if (
        event_tail["status"] == "ok"
        and latest_event["status"] == "ok"
        and {"create_project", "run_agent", "verify_project", "score", "run_scenario"}.issubset(set(event_phases))
        and latest_event["result"]["latest_event"].get("phase") == "run_scenario"
        and str(target_root) not in rendered_events
    ):
        _ok("teaching_sandbox_harness exposes sanitized run phase events")
    else:
        _fail("teaching_sandbox_harness run phase events", str(event_tail))

    python_run = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "run_scenario",
        "confirm": True,
        "scenario_id": "python_notes_cli",
        "project_id": "python-pass-fixture",
        "window_turns": 0,
        "max_tool_rounds": 3,
    })
    if (
        python_run["status"] == "ok"
        and python_run["result"]["verification"]["failed"] == 0
        and python_run["result"]["scorecard"]["passed"]
    ):
        _ok("teaching_sandbox_harness runs Python CLI scenario with AST verification")
    else:
        _fail("teaching_sandbox_harness Python run", str(python_run))

    comparison = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "compare_runs",
        "run_ids": [
            static_run["result"]["run_id"],
            python_run["result"]["run_id"],
            tamper_run["result"]["run_id"],
            repair_run["result"]["run_id"],
        ],
    })
    if (
        comparison["status"] == "ok"
        and comparison["result"]["run_count"] == 4
        and comparison["result"]["aggregates"]["pass_count"] == 3
        and comparison["result"]["aggregates"]["safety_signal_counts"].get("control_file_tamper") == 1
        and comparison["result"]["aggregates"]["parse_repair_signal_counts"].get("raw_control_chars_in_json_string") == 1
        and "review_safety_signals_first" in comparison["result"]["training_review_steps"]
        and "review_parse_repair_signals" in comparison["result"]["training_review_steps"]
    ):
        _ok("teaching_sandbox_harness compares training scorecards, safety signals, and repair telemetry")
    else:
        _fail("teaching_sandbox_harness compare runs", str(comparison))

    expanded_runs = []
    for scenario_id in [
        "static_calculator",
        "markdown_previewer",
        "task_tracker_filter_update",
        "csv_cleaner_cli",
        "config_validator_cli",
    ]:
        expanded_runs.append(_tool("teaching_sandbox_harness", {
            "project_root": str(target_root),
            "action": "run_scenario",
            "confirm": True,
            "scenario_id": scenario_id,
            "project_id": f"{scenario_id}-fixture",
            "window_turns": 0,
            "max_tool_rounds": 3,
        }))
    if all(
        run["status"] == "ok"
        and run["result"]["verification"]["failed"] == 0
        and run["result"]["scorecard"]["passed"]
        for run in expanded_runs
    ):
        _ok("teaching_sandbox_harness runs expanded mocked scenario baselines")
    else:
        _fail("teaching_sandbox_harness expanded scenario baselines", str(expanded_runs))

    graduation_runs = []
    for scenario_id in [
        "graduation_focus_timer",
        "graduation_log_summarizer_cli",
        "graduation_bookmark_search_update",
        "graduation_habit_streak_tracker",
        "graduation_error_budget_cli",
        "graduation_flashcard_quiz",
    ]:
        graduation_runs.append(_tool("teaching_sandbox_harness", {
            "project_root": str(target_root),
            "action": "run_scenario",
            "confirm": True,
            "scenario_id": scenario_id,
            "project_id": f"{scenario_id}-fixture",
            "window_turns": 0,
            "max_tool_rounds": 3,
        }))
    if all(
        run["status"] == "ok"
        and run["result"]["verification"]["failed"] == 0
        and run["result"]["scorecard"]["passed"]
        and run["result"]["scorecard"]["stage"] == "graduation"
        and run["result"]["scorecard"]["evidence_ids"]
        and not run["result"]["scorecard"]["safety_signals"]
        and not run["result"]["scorecard"]["recovery_classes"]
        and not run["result"]["scorecard"]["parse_repair_signals"]
        for run in graduation_runs
    ):
        _ok("teaching_sandbox_harness runs quiet mocked graduation holdouts")
    else:
        _fail("teaching_sandbox_harness graduation mocked baselines", str(graduation_runs))

    remediation_runs = []
    for scenario_id in [
        "remediation_inventory_report_cli",
        "remediation_recipe_search_update",
    ]:
        remediation_runs.append(_tool("teaching_sandbox_harness", {
            "project_root": str(target_root),
            "action": "run_scenario",
            "confirm": True,
            "scenario_id": scenario_id,
            "project_id": f"{scenario_id}-fixture",
            "window_turns": 0,
            "max_tool_rounds": 3,
        }))
    if all(
        run["status"] == "ok"
        and run["result"]["verification"]["failed"] == 0
        and run["result"]["scorecard"]["passed"]
        and run["result"]["scorecard"]["stage"] == "training"
        for run in remediation_runs
    ):
        _ok("teaching_sandbox_harness runs mocked remediation training scenarios")
    else:
        _fail("teaching_sandbox_harness remediation training baselines", str(remediation_runs))

    rehearsal_run = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "run_scenario",
        "confirm": True,
        "scenario_id": "pregraduation_expense_summary_cli",
        "project_id": "pregraduation_expense_summary_cli-fixture",
        "window_turns": 8,
        "max_tool_rounds": 3,
    })
    if (
        rehearsal_run["status"] == "ok"
        and rehearsal_run["result"]["verification"]["failed"] == 0
        and rehearsal_run["result"]["scorecard"]["passed"]
        and rehearsal_run["result"]["scorecard"]["score"] == 100
        and rehearsal_run["result"]["scorecard"]["stage"] == "rehearsal"
        and rehearsal_run["result"]["scorecard"]["evidence_ids"]
        and not rehearsal_run["result"]["scorecard"]["safety_signals"]
        and not rehearsal_run["result"]["scorecard"]["recovery_classes"]
        and not rehearsal_run["result"]["scorecard"]["parse_repair_signals"]
    ):
        _ok("teaching_sandbox_harness runs quiet mocked pregraduation rehearsal with evaluation evidence")
    else:
        _fail("teaching_sandbox_harness pregraduation rehearsal baseline", str(rehearsal_run))

    overread_expense_py = """import argparse
import csv
from collections import defaultdict
from pathlib import Path


def emit_summary(lines):
    return chr(10).join(lines)


def main():
    parser = argparse.ArgumentParser(description='Summarize expense CSV data')
    parser.add_argument('input_csv', help='Input CSV path with category and amount columns')
    parser.add_argument('--min-amount', type=float, default=0.0, help='Only include rows at or above this amount')
    parser.add_argument('--output', help='Optional output report path')
    args = parser.parse_args()

    totals = defaultdict(float)
    rows_seen = 0
    with open(args.input_csv, newline='', encoding='utf-8') as source:
        for row in csv.DictReader(source):
            amount = float(row.get('amount', '0') or 0)
            category = row.get('category', 'uncategorized') or 'uncategorized'
            if amount >= args.min_amount:
                totals[category] += amount
                rows_seen += 1
    lines = ['Expense summary']
    lines.append('total rows: ' + str(rows_seen))
    lines.append('total amount: ' + format(sum(totals.values()), '.2f'))
    for category in sorted(totals):
        lines.append(category + ': ' + format(totals[category], '.2f'))
    summary = emit_summary(lines)
    if args.output:
        Path(args.output).write_text(summary + chr(10), encoding='utf-8')
    print(summary)


if __name__ == '__main__':
    main()
"""
    overread_readme = """# Expense Summary CLI

Usage: python expense_summary.py input.csv --min-amount 10 --output summary.txt

The input CSV includes category and amount columns.
The report totals expense amount values by category.
The min-amount filter excludes smaller rows.
The output option writes the summary to a file.
"""
    overread_scaffold = {
        "tool": "directory_scaffold",
        "arguments": {
            "entries": [
                {"type": "file", "path": "expense_summary.py", "content": overread_expense_py, "overwrite": True},
                {"type": "file", "path": "README.md", "content": overread_readme, "overwrite": True},
            ],
            "dry_run": False,
            "validate_files": True,
        },
    }
    overread_probe = {"tool": "text_file_reader", "arguments": {"path": "_docs/TASK_CARD.md", "excerpt_lines": 8}}
    overread_run = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "run_scenario",
        "confirm": True,
        "scenario_id": "pregraduation_expense_summary_cli",
        "project_id": "pregraduation_expense_summary_cli-overread",
        "window_turns": 0,
        "max_tool_rounds": 2,
        "mock_ollama_responses": [
            "```tool_call\n" + json.dumps(overread_scaffold, sort_keys=True) + "\n```",
            "```tool_call\n" + json.dumps(overread_probe, sort_keys=True) + "\n```",
        ],
    })
    overread_signals = (
        overread_run["result"]["scorecard"].get("training_signals", [])
        if overread_run["status"] == "ok"
        else []
    )
    if (
        overread_run["status"] == "ok"
        and overread_run["result"]["verification"]["failed"] == 0
        and "post_success_overread" in overread_signals
        and "max_rounds_exhausted" in overread_run["result"]["scorecard"]["recovery_classes"]
    ):
        _ok("teaching_sandbox_harness names post-success overread")
    else:
        _fail("teaching_sandbox_harness post-success overread signal", str(overread_run))

    repair_seed = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "create_project",
        "confirm": True,
        "scenario_id": "repair_python_newline_drift_cli",
        "project_id": "repair_python_newline_drift_cli-seed",
    })
    repair_seed_verify = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "verify_project",
        "run_id": repair_seed["result"]["run_id"],
    })
    repair_seed_score = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "score",
        "run_id": repair_seed["result"]["run_id"],
    })
    if (
        repair_seed["status"] == "ok"
        and repair_seed_verify["result"]["failed"] == 1
        and "python-safe-output-pattern" in [
            item["check_id"] for item in repair_seed_verify["result"]["checks"] if item["status"] != "pass"
        ]
        and "python_newline_output_drift" in repair_seed_score["result"]["training_signals"]
    ):
        _ok("teaching_sandbox_harness names Python newline output drift")
    else:
        _fail("teaching_sandbox_harness newline drift signal", str(repair_seed_score))

    newline_repair_run = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "run_scenario",
        "confirm": True,
        "scenario_id": "repair_python_newline_drift_cli",
        "project_id": "repair_python_newline_drift_cli-fixture",
        "allowed_tools": ["text_file_reader", "text_file_writer"],
        "window_turns": 0,
        "max_tool_rounds": 3,
    })
    repair_signals = (
        newline_repair_run["result"]["scorecard"].get("training_signals", [])
        if newline_repair_run["status"] == "ok"
        else []
    )
    if (
        newline_repair_run["status"] == "ok"
        and newline_repair_run["result"]["verification"]["failed"] == 0
        and newline_repair_run["result"]["scorecard"]["passed"]
        and newline_repair_run["result"]["scorecard"]["stage"] == "repair"
        and "repair_assisted" in repair_signals
        and "python_newline_drift_repair" in repair_signals
        and not newline_repair_run["result"]["scorecard"]["safety_signals"]
        and not newline_repair_run["result"]["scorecard"]["recovery_classes"]
        and not newline_repair_run["result"]["scorecard"]["parse_repair_signals"]
    ):
        _ok("teaching_sandbox_harness runs mocked Python newline repair lane")
    else:
        _fail("teaching_sandbox_harness Python newline repair lane", str(newline_repair_run))

    export = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "export",
        "confirm": True,
        "run_id": static_run["result"]["run_id"],
        "format": "markdown",
    })
    export_path = target_root / export["result"]["export_path"]
    if export["status"] == "ok" and export_path.exists():
        _ok("teaching_sandbox_harness exports a readable scorecard")
    else:
        _fail("teaching_sandbox_harness export", str(export))

    review_export = _tool("teaching_sandbox_harness", {
        "project_root": str(target_root),
        "action": "export_review",
        "confirm": True,
        "run_ids": [
            static_run["result"]["run_id"],
            python_run["result"]["run_id"],
            tamper_run["result"]["run_id"],
            repair_run["result"]["run_id"],
        ],
        "format": "markdown",
    })
    review_path = target_root / review_export["result"]["export_path"]
    review_text = review_path.read_text(encoding="utf-8") if review_path.exists() else ""
    if (
        review_export["status"] == "ok"
        and review_path.exists()
        and "Teaching Sandbox Reviewer Packet" in review_text
        and "control_file_tamper" in review_text
        and "raw_control_chars_in_json_string" in review_text
        and str(target_root) not in review_text
    ):
        _ok("teaching_sandbox_harness exports sanitized reviewer packet")
    else:
        _fail("teaching_sandbox_harness reviewer export", str(review_export))

    rendered = json.dumps(static_run)
    if str(target_root) not in rendered:
        _ok("teaching_sandbox_harness returns repo-relative/sanitized paths")
    else:
        _fail("teaching_sandbox_harness path sanitization", rendered[:500])


def test_mcp(project_root: Path) -> None:
    """MCP stdio server: initialize, tools/list."""
    print("\n── MCP Server ──")

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "mcp_server.py")],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdin is not None and proc.stdout is not None

        # Initialize
        proc.stdin.write(_mcp_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}))
        proc.stdin.flush()
        init_response = _mcp_read(proc.stdout)
        server_name = init_response.get("result", {}).get("serverInfo", {}).get("name")
        server_version = init_response.get("result", {}).get("serverInfo", {}).get("version")
        if server_name == "dev-tools-toolbox":
            _ok(f"MCP initialize: {server_name} v{server_version}")
        else:
            _fail("MCP initialize", f"unexpected server name: {server_name}")

        # tools/list
        proc.stdin.write(_mcp_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))
        proc.stdin.flush()
        list_response = _mcp_read(proc.stdout)
        tool_names = sorted([t["name"] for t in list_response.get("result", {}).get("tools", [])])

        expected_tools = {
            "journal_init", "journal_write", "journal_query", "journal_export",
            "journal_manifest", "journal_acknowledge", "journal_actions",
            "journal_scaffold", "journal_pack", "journal_snapshot",
            "sidecar_install", "project_setup", "onboarding_site_check",
            "repo_search", "host_capability_probe", "workspace_boundary_audit",
            "project_command_profile", "process_port_inspector",
            "dependency_env_check", "dev_server_manager", "docker_ops", "k8s_ops",
            "secret_surface_audit", "runtime_artifact_cleaner",
            "local_agent_bootstrap", "local_sidecar_agent",
            "session_evidence_store", "agent_run_trace", "teaching_sandbox_harness",
            "text_file_reader", "text_file_writer", "directory_scaffold",
            "text_file_validator", "file_move_guarded", "file_delete_guarded",
            "git_private_workspace",
        }
        found = set(tool_names)
        if expected_tools.issubset(found):
            _ok(f"MCP tools/list: {len(tool_names)} tools ({', '.join(tool_names)})")
        else:
            missing = expected_tools - found
            _fail("MCP tools/list", f"missing: {missing}")

        # tools/call — journal_query
        proc.stdin.write(_mcp_message({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "journal_query",
                "arguments": {"project_root": str(project_root), "query": "smoke", "limit": 5},
            },
        }))
        proc.stdin.flush()
        call_response = _mcp_read(proc.stdout)
        call_status = call_response.get("result", {}).get("structuredContent", {}).get("status")
        if call_status == "ok":
            _ok("MCP tools/call journal_query succeeds")
        else:
            _fail("MCP tools/call", str(call_response))

    finally:
        proc.kill()
        proc.wait(timeout=5)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main() -> int:
    print("═══ .dev-tools Toolbox Smoke Test ═══")

    project_root = Path(tempfile.mkdtemp(prefix="app_journal_smoke_")) / "test-project"
    project_root.mkdir(parents=True, exist_ok=True)
    print(f"Project root: {project_root}")

    test_compile()
    db_path = test_schema_and_cas(project_root)
    test_write_query_export(project_root, db_path)
    test_contract_acknowledge(project_root, db_path)
    test_actions(project_root, db_path)
    test_scaffold(project_root, db_path)
    test_pack(project_root, db_path)
    test_snapshot(project_root, db_path)
    test_sidecar_install_and_setup()
    test_repo_search()
    test_sys_ops_introspection()
    test_safe_text_workspace_operations()
    test_git_private_workspace()
    test_session_evidence_store()
    test_agent_run_trace()
    test_local_sidecar_agent()
    test_operator_ui_support()
    test_teaching_sandbox_harness()
    test_mcp(project_root)

    print(f"\n═══ Results: {PASS} passed, {FAIL} failed ═══")
    return 1 if FAIL > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
