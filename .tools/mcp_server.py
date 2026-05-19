"""
FILE: mcp_server.py
ROLE: MCP stdio server for .dev-tools.
WHAT IT DOES: Exposes builder tools through MCP using the same run(arguments) functions.
HOW TO USE:
  - Start: python src/mcp_server.py
  - Connect as a stdio MCP server from an MCP-capable client.
TOOLS:
  - journal_init, journal_manifest, journal_write, journal_query, journal_export
  - journal_acknowledge, journal_actions, journal_scaffold, journal_pack, journal_snapshot
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.journal_init import FILE_METADATA as INIT_METADATA, run as run_journal_init
from tools.journal_manifest import FILE_METADATA as MANIFEST_METADATA, run as run_journal_manifest
from tools.journal_write import FILE_METADATA as WRITE_METADATA, run as run_journal_write
from tools.journal_query import FILE_METADATA as QUERY_METADATA, run as run_journal_query
from tools.journal_export import FILE_METADATA as EXPORT_METADATA, run as run_journal_export

# Phase 3+ tools — imported when available
try:
    from tools.journal_acknowledge import FILE_METADATA as ACKNOWLEDGE_METADATA, run as run_journal_acknowledge
except ImportError:
    ACKNOWLEDGE_METADATA, run_journal_acknowledge = None, None

try:
    from tools.journal_actions import FILE_METADATA as ACTIONS_METADATA, run as run_journal_actions
except ImportError:
    ACTIONS_METADATA, run_journal_actions = None, None

try:
    from tools.journal_scaffold import FILE_METADATA as SCAFFOLD_METADATA, run as run_journal_scaffold
except ImportError:
    SCAFFOLD_METADATA, run_journal_scaffold = None, None

try:
    from tools.journal_pack import FILE_METADATA as PACK_METADATA, run as run_journal_pack
except ImportError:
    PACK_METADATA, run_journal_pack = None, None

try:
    from tools.journal_snapshot import FILE_METADATA as SNAPSHOT_METADATA, run as run_journal_snapshot
except ImportError:
    SNAPSHOT_METADATA, run_journal_snapshot = None, None

try:
    from tools.sidecar_install import FILE_METADATA as SIDECAR_INSTALL_METADATA, run as run_sidecar_install
except ImportError:
    SIDECAR_INSTALL_METADATA, run_sidecar_install = None, None

try:
    from tools.project_setup import FILE_METADATA as PROJECT_SETUP_METADATA, run as run_project_setup
except ImportError:
    PROJECT_SETUP_METADATA, run_project_setup = None, None

try:
    from tools.onboarding_site_check import FILE_METADATA as ONBOARDING_SITE_CHECK_METADATA, run as run_onboarding_site_check
except ImportError:
    ONBOARDING_SITE_CHECK_METADATA, run_onboarding_site_check = None, None

try:
    from tools.repo_search import FILE_METADATA as REPO_SEARCH_METADATA, run as run_repo_search
except ImportError:
    REPO_SEARCH_METADATA, run_repo_search = None, None

try:
    from tools.host_capability_probe import FILE_METADATA as HOST_CAPABILITY_METADATA, run as run_host_capability_probe
except ImportError:
    HOST_CAPABILITY_METADATA, run_host_capability_probe = None, None

try:
    from tools.workspace_boundary_audit import FILE_METADATA as WORKSPACE_BOUNDARY_METADATA, run as run_workspace_boundary_audit
except ImportError:
    WORKSPACE_BOUNDARY_METADATA, run_workspace_boundary_audit = None, None

try:
    from tools.project_command_profile import FILE_METADATA as PROJECT_COMMAND_METADATA, run as run_project_command_profile
except ImportError:
    PROJECT_COMMAND_METADATA, run_project_command_profile = None, None

try:
    from tools.process_port_inspector import FILE_METADATA as PROCESS_PORT_METADATA, run as run_process_port_inspector
except ImportError:
    PROCESS_PORT_METADATA, run_process_port_inspector = None, None

try:
    from tools.dependency_env_check import FILE_METADATA as DEPENDENCY_ENV_METADATA, run as run_dependency_env_check
except ImportError:
    DEPENDENCY_ENV_METADATA, run_dependency_env_check = None, None

try:
    from tools.dev_server_manager import FILE_METADATA as DEV_SERVER_METADATA, run as run_dev_server_manager
except ImportError:
    DEV_SERVER_METADATA, run_dev_server_manager = None, None

try:
    from tools.docker_ops import FILE_METADATA as DOCKER_OPS_METADATA, run as run_docker_ops
except ImportError:
    DOCKER_OPS_METADATA, run_docker_ops = None, None

try:
    from tools.k8s_ops import FILE_METADATA as K8S_OPS_METADATA, run as run_k8s_ops
except ImportError:
    K8S_OPS_METADATA, run_k8s_ops = None, None

try:
    from tools.secret_surface_audit import FILE_METADATA as SECRET_SURFACE_METADATA, run as run_secret_surface_audit
except ImportError:
    SECRET_SURFACE_METADATA, run_secret_surface_audit = None, None

try:
    from tools.runtime_artifact_cleaner import FILE_METADATA as RUNTIME_CLEANER_METADATA, run as run_runtime_artifact_cleaner
except ImportError:
    RUNTIME_CLEANER_METADATA, run_runtime_artifact_cleaner = None, None

try:
    from tools.local_agent_bootstrap import FILE_METADATA as LOCAL_AGENT_BOOTSTRAP_METADATA, run as run_local_agent_bootstrap
except ImportError:
    LOCAL_AGENT_BOOTSTRAP_METADATA, run_local_agent_bootstrap = None, None

try:
    from tools.local_sidecar_agent import FILE_METADATA as LOCAL_SIDECAR_AGENT_METADATA, run as run_local_sidecar_agent
except ImportError:
    LOCAL_SIDECAR_AGENT_METADATA, run_local_sidecar_agent = None, None

try:
    from tools.session_evidence_store import FILE_METADATA as SESSION_EVIDENCE_METADATA, run as run_session_evidence_store
except ImportError:
    SESSION_EVIDENCE_METADATA, run_session_evidence_store = None, None

try:
    from tools.agent_run_trace import FILE_METADATA as AGENT_RUN_TRACE_METADATA, run as run_agent_run_trace
except ImportError:
    AGENT_RUN_TRACE_METADATA, run_agent_run_trace = None, None

try:
    from tools.teaching_sandbox_harness import FILE_METADATA as TEACHING_SANDBOX_METADATA, run as run_teaching_sandbox_harness
except ImportError:
    TEACHING_SANDBOX_METADATA, run_teaching_sandbox_harness = None, None

try:
    from tools.text_file_reader import FILE_METADATA as TEXT_FILE_READER_METADATA, run as run_text_file_reader
except ImportError:
    TEXT_FILE_READER_METADATA, run_text_file_reader = None, None

try:
    from tools.text_file_writer import FILE_METADATA as TEXT_FILE_WRITER_METADATA, run as run_text_file_writer
except ImportError:
    TEXT_FILE_WRITER_METADATA, run_text_file_writer = None, None

try:
    from tools.directory_scaffold import FILE_METADATA as DIRECTORY_SCAFFOLD_METADATA, run as run_directory_scaffold
except ImportError:
    DIRECTORY_SCAFFOLD_METADATA, run_directory_scaffold = None, None

try:
    from tools.text_file_validator import FILE_METADATA as TEXT_FILE_VALIDATOR_METADATA, run as run_text_file_validator
except ImportError:
    TEXT_FILE_VALIDATOR_METADATA, run_text_file_validator = None, None

try:
    from tools.file_move_guarded import FILE_METADATA as FILE_MOVE_GUARDED_METADATA, run as run_file_move_guarded
except ImportError:
    FILE_MOVE_GUARDED_METADATA, run_file_move_guarded = None, None

try:
    from tools.file_delete_guarded import FILE_METADATA as FILE_DELETE_GUARDED_METADATA, run as run_file_delete_guarded
except ImportError:
    FILE_DELETE_GUARDED_METADATA, run_file_delete_guarded = None, None

try:
    from tools.git_private_workspace import FILE_METADATA as GIT_PRIVATE_WORKSPACE_METADATA, run as run_git_private_workspace
except ImportError:
    GIT_PRIVATE_WORKSPACE_METADATA, run_git_private_workspace = None, None

try:
    from tools.module_decomp_planner import FILE_METADATA as MODULE_DECOMP_METADATA, run as run_module_decomp_planner
except ImportError:
    MODULE_DECOMP_METADATA, run_module_decomp_planner = None, None

try:
    from tools.tokenizing_patcher import FILE_METADATA as TOKENIZING_PATCHER_METADATA, run as run_tokenizing_patcher
except ImportError:
    TOKENIZING_PATCHER_METADATA, run_tokenizing_patcher = None, None

try:
    from tools.domain_boundary_audit import FILE_METADATA as DOMAIN_BOUNDARY_METADATA, run as run_domain_boundary_audit
except ImportError:
    DOMAIN_BOUNDARY_METADATA, run_domain_boundary_audit = None, None

try:
    from tools.scan_blocking_calls import FILE_METADATA as SCAN_BLOCKING_METADATA, run as run_scan_blocking_calls
except ImportError:
    SCAN_BLOCKING_METADATA, run_scan_blocking_calls = None, None

try:
    from tools.sqlite_schema_inspector import FILE_METADATA as SQLITE_INSPECTOR_METADATA, run as run_sqlite_schema_inspector
except ImportError:
    SQLITE_INSPECTOR_METADATA, run_sqlite_schema_inspector = None, None

try:
    from tools.import_graph_mapper import FILE_METADATA as IMPORT_GRAPH_METADATA, run as run_import_graph_mapper
except ImportError:
    IMPORT_GRAPH_METADATA, run_import_graph_mapper = None, None

try:
    from tools.tkinter_widget_tree import FILE_METADATA as TKINTER_TREE_METADATA, run as run_tkinter_widget_tree
except ImportError:
    TKINTER_TREE_METADATA, run_tkinter_widget_tree = None, None

try:
    from tools.file_tree_snapshot import FILE_METADATA as FILE_TREE_METADATA, run as run_file_tree_snapshot
except ImportError:
    FILE_TREE_METADATA, run_file_tree_snapshot = None, None

try:
    from tools.smoke_test_runner import FILE_METADATA as SMOKE_RUNNER_METADATA, run as run_smoke_test_runner
except ImportError:
    SMOKE_RUNNER_METADATA, run_smoke_test_runner = None, None

try:
    from tools.python_complexity_scorer import FILE_METADATA as COMPLEXITY_METADATA, run as run_python_complexity_scorer
except ImportError:
    COMPLEXITY_METADATA, run_python_complexity_scorer = None, None

try:
    from tools.dead_code_finder import FILE_METADATA as DEAD_CODE_METADATA, run as run_dead_code_finder
except ImportError:
    DEAD_CODE_METADATA, run_dead_code_finder = None, None

try:
    from tools.test_scaffold_generator import FILE_METADATA as TEST_SCAFFOLD_METADATA, run as run_test_scaffold_generator
except ImportError:
    TEST_SCAFFOLD_METADATA, run_test_scaffold_generator = None, None

try:
    from tools.schema_diff_tool import FILE_METADATA as SCHEMA_DIFF_METADATA, run as run_schema_diff_tool
except ImportError:
    SCHEMA_DIFF_METADATA, run_schema_diff_tool = None, None

SERVER_INFO = {"name": "dev-tools-toolbox", "version": "2.0.0"}

# Build registry from available tools
TOOL_REGISTRY: dict[str, tuple[dict, callable]] = {}
for meta, runner in [
    (INIT_METADATA, run_journal_init),
    (MANIFEST_METADATA, run_journal_manifest),
    (WRITE_METADATA, run_journal_write),
    (QUERY_METADATA, run_journal_query),
    (EXPORT_METADATA, run_journal_export),
    (ACKNOWLEDGE_METADATA, run_journal_acknowledge),
    (ACTIONS_METADATA, run_journal_actions),
    (SCAFFOLD_METADATA, run_journal_scaffold),
    (PACK_METADATA, run_journal_pack),
    (SNAPSHOT_METADATA, run_journal_snapshot),
    (SIDECAR_INSTALL_METADATA, run_sidecar_install),
    (PROJECT_SETUP_METADATA, run_project_setup),
    (ONBOARDING_SITE_CHECK_METADATA, run_onboarding_site_check),
    (REPO_SEARCH_METADATA, run_repo_search),
    (HOST_CAPABILITY_METADATA, run_host_capability_probe),
    (WORKSPACE_BOUNDARY_METADATA, run_workspace_boundary_audit),
    (PROJECT_COMMAND_METADATA, run_project_command_profile),
    (PROCESS_PORT_METADATA, run_process_port_inspector),
    (DEPENDENCY_ENV_METADATA, run_dependency_env_check),
    (DEV_SERVER_METADATA, run_dev_server_manager),
    (DOCKER_OPS_METADATA, run_docker_ops),
    (K8S_OPS_METADATA, run_k8s_ops),
    (SECRET_SURFACE_METADATA, run_secret_surface_audit),
    (RUNTIME_CLEANER_METADATA, run_runtime_artifact_cleaner),
    (LOCAL_AGENT_BOOTSTRAP_METADATA, run_local_agent_bootstrap),
    (LOCAL_SIDECAR_AGENT_METADATA, run_local_sidecar_agent),
    (SESSION_EVIDENCE_METADATA, run_session_evidence_store),
    (AGENT_RUN_TRACE_METADATA, run_agent_run_trace),
    (TEACHING_SANDBOX_METADATA, run_teaching_sandbox_harness),
    (TEXT_FILE_READER_METADATA, run_text_file_reader),
    (TEXT_FILE_WRITER_METADATA, run_text_file_writer),
    (DIRECTORY_SCAFFOLD_METADATA, run_directory_scaffold),
    (TEXT_FILE_VALIDATOR_METADATA, run_text_file_validator),
    (FILE_MOVE_GUARDED_METADATA, run_file_move_guarded),
    (FILE_DELETE_GUARDED_METADATA, run_file_delete_guarded),
    (GIT_PRIVATE_WORKSPACE_METADATA, run_git_private_workspace),
    (MODULE_DECOMP_METADATA, run_module_decomp_planner),
    (TOKENIZING_PATCHER_METADATA, run_tokenizing_patcher),
    (DOMAIN_BOUNDARY_METADATA, run_domain_boundary_audit),
    (SCAN_BLOCKING_METADATA, run_scan_blocking_calls),
    (SQLITE_INSPECTOR_METADATA, run_sqlite_schema_inspector),
    (IMPORT_GRAPH_METADATA, run_import_graph_mapper),
    (TKINTER_TREE_METADATA, run_tkinter_widget_tree),
    (FILE_TREE_METADATA, run_file_tree_snapshot),
    (SMOKE_RUNNER_METADATA, run_smoke_test_runner),
    (COMPLEXITY_METADATA, run_python_complexity_scorer),
    (DEAD_CODE_METADATA, run_dead_code_finder),
    (TEST_SCAFFOLD_METADATA, run_test_scaffold_generator),
    (SCHEMA_DIFF_METADATA, run_schema_diff_tool),
]:
    if meta is not None and runner is not None:
        TOOL_REGISTRY[meta["mcp_name"]] = (meta, runner)


def _success(result: dict) -> dict:
    return {
        "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        "structuredContent": result,
        "isError": result.get("status") == "error",
    }


def _tool_list() -> list[dict]:
    return [
        {
            "name": metadata["mcp_name"],
            "description": metadata["summary"],
            "inputSchema": metadata["input_schema"],
        }
        for metadata, _ in TOOL_REGISTRY.values()
    ]


def _call_tool(name: str, arguments: dict) -> dict:
    entry = TOOL_REGISTRY.get(name)
    if not entry:
        return _success({"status": "error", "tool": name, "input": arguments, "result": {"message": f"Unknown tool: {name}"}})
    _, runner = entry
    try:
        return _success(runner(arguments))
    except Exception as exc:
        return _success({
            "status": "error", "tool": name, "input": arguments,
            "result": {"message": str(exc), "traceback": traceback.format_exc()},
        })


def _read_content_length_message(first_line: bytes) -> dict | None:
    """Read a Content-Length framed MCP message."""
    headers: dict[str, str] = {}
    line = first_line
    while True:
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        key, _, value = line.decode("utf-8").partition(":")
        headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()

    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        return None
    body = sys.stdin.buffer.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _read_message() -> dict | None:
    """Read one stdin message. Supports Content-Length framing and NDJSON fallback."""
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(b"{"):
            return json.loads(stripped.decode("utf-8"))
        if b"content-length" in stripped.lower():
            return _read_content_length_message(line)
        continue


def _write_message(payload: dict) -> None:
    """Write one NDJSON message to stdout."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(body + b"\n")
    sys.stdout.buffer.flush()


def _handle_request(message: dict) -> dict | None:
    method = message.get("method")
    message_id = message.get("id")
    params = message.get("params", {})

    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": message_id, "result": {}}
    if method == "initialize":
        client_version = params.get("protocolVersion", "2024-11-05")
        return {
            "jsonrpc": "2.0", "id": message_id,
            "result": {
                "protocolVersion": client_version,
                "serverInfo": SERVER_INFO,
                "capabilities": {"tools": {}},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": message_id, "result": {"tools": _tool_list()}}
    if method == "tools/call":
        return {"jsonrpc": "2.0", "id": message_id, "result": _call_tool(params["name"], params.get("arguments", {}))}
    return {
        "jsonrpc": "2.0", "id": message_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    while True:
        message = _read_message()
        if message is None:
            return 0
        response = _handle_request(message)
        if response is not None:
            _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
