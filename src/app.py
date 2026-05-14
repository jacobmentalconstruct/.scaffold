"""
FILE: src/app.py
ROLE: Sidecar entrypoint. Boots the SidecarApp, wires the spine, dispatches.
WHAT IT DOES (T1): resolves roots, configures logging, opens the SQLite spine,
                   wires state + spine components + ContractAuthority +
                   ConstraintManager, seeds constraints from contract,
                   registers handlers, refreshes projections, dispatches CLI.

USAGE:
    python -m src.app cli ack-contract --actor "human:jacob"
    python -m src.app cli status
    python -m src.app cli version
    python -m src.app cli projection contract_status
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.components.blob_store import BlobStore
from src.components.file_scanner import FileScanner
from src.components.git_reader import GitReader
from src.components.sqlite_store import open_store
from src.core.contracts import ContractAuthority
from src.core.events import EventStore
from src.core.graph import Graph
from src.core.projections import ProjectionManager
from src.core.router import Router
from src.core.state import SidecarState
from src.interfaces import cli_interface, mcp_interface
from src.lib import logging_setup
from src.lib.common import detect_sidecar_root, public_path, public_root_labels, resolve_paths
from src.lib.ui_launcher import launch_monitor
from src.managers.constraint_manager import ConstraintManager
from src.managers.evidence_manager import EvidenceManager
from src.managers.git_state_manager import GitStateManager
from src.managers.journal_manager import JournalManager
from src.managers.project_index_manager import ProjectIndexManager
from src.managers.agent_session_manager import AgentSessionManager
from src.managers.human_approval_manager import HumanApprovalManager
from src.managers.memory_manager import MemoryManager
from src.managers.recovery_manager import RecoveryManager
from src.managers.run_trace_manager import RunTraceManager
from src.managers.training_runway_manager import TrainingRunwayManager
from src.managers.installed_project_proof_manager import InstalledProjectProofManager
from src.managers.tool_registry_manager import ToolRegistryManager
from src.orchestrators.agent_task_orchestrator import AgentTaskOrchestrator
from src.orchestrators.closeout_orchestrator import CloseoutOrchestrator
from src.orchestrators.install_orchestrator import InstallOrchestrator
from src.orchestrators.scan_orchestrator import ScanOrchestrator
from src.managers.tranche_manager import TrancheManager
from src.runtime.local_agent_runtime import LocalAgentRuntime


def boot(sidecar_root: Path | None = None,
         project_root: Path | None = None) -> SidecarState:
    """Wire the sidecar spine and return a fully-bootstrapped SidecarState."""
    sidecar_root = Path(sidecar_root) if sidecar_root else detect_sidecar_root()
    if project_root:
        project_root = Path(project_root)
    elif sidecar_root.name == ".scaffold":
        project_root = sidecar_root.parent
    else:
        # Development scope per contract §0.10: project_root == sidecar_root.
        project_root = sidecar_root

    paths = resolve_paths(sidecar_root)

    # Ensure the runtime folders exist (data/, logs/, etc.).
    for folder in (paths.data, paths.logs, paths.cache, paths.exports,
                   paths.workspaces, paths.snapshots, paths.config):
        folder.mkdir(parents=True, exist_ok=True)

    # Logging.
    logging_setup.configure(paths.logs)
    log = logging_setup.get_logger("app")

    # Storage.
    store = open_store(paths.db_file)
    blob = BlobStore(store)

    # State.
    state = SidecarState.bootstrap(sidecar_root, project_root, store)
    state.blob_store = blob

    # Spine components.
    events = EventStore(store)
    graph = Graph(store)
    constraint_manager = ConstraintManager(store, blob)
    contracts = ContractAuthority(state, store, constraint_manager)
    projections = ProjectionManager(state, store, events, graph)
    journal_manager = JournalManager(store, blob)
    project_index_manager = ProjectIndexManager(store)
    evidence_manager = EvidenceManager(store, blob)
    git_reader = GitReader()
    git_state_manager = GitStateManager(store, git_reader)
    agent_session_manager = AgentSessionManager(store)
    human_approval_manager = HumanApprovalManager(store, blob)
    memory_manager = MemoryManager(store, blob)
    recovery_manager = RecoveryManager()
    run_trace_manager = RunTraceManager(store, recovery_manager)
    tool_registry_manager = ToolRegistryManager(store, blob, paths.src / "tools")
    file_scanner = FileScanner()
    tranche_manager = TrancheManager(store, blob)
    local_agent_runtime = LocalAgentRuntime(state)
    training_runway_manager = TrainingRunwayManager(state)
    installed_project_proof_manager = InstalledProjectProofManager(state)
    install_orch = InstallOrchestrator(store)
    scan_orch = ScanOrchestrator(file_scanner, project_index_manager, blob)
    agent_task_orch = AgentTaskOrchestrator(journal_manager, blob)
    closeout_orch = CloseoutOrchestrator(tranche_manager, journal_manager, blob)
    router = Router(
        state, contracts, events, graph, projections,
        journal_manager=journal_manager,
        scan_orchestrator=scan_orch,
    )
    router._tool_registry = tool_registry_manager  # type: ignore[attr-defined]
    router._git_state = git_state_manager  # type: ignore[attr-defined]
    router._tranche_manager = tranche_manager  # type: ignore[attr-defined]

    # Wire references onto state for handler access.
    state.events = events
    state.graph = graph
    state.constraint_manager = constraint_manager
    state.contract_authority = contracts
    state.projections = projections
    state.journal_manager = journal_manager
    state.project_index_manager = project_index_manager
    state.evidence_manager = evidence_manager
    state.git_state_manager = git_state_manager
    state.tool_registry_manager = tool_registry_manager
    state.agent_session_manager = agent_session_manager
    state.human_approval_manager = human_approval_manager
    state.memory_manager = memory_manager
    state.recovery_manager = recovery_manager
    state.run_trace_manager = run_trace_manager
    state.training_runway_manager = training_runway_manager
    state.installed_project_proof_manager = installed_project_proof_manager
    state.file_scanner = file_scanner
    state.install_orchestrator = install_orch
    state.scan_orchestrator = scan_orch
    state.agent_task_orchestrator = agent_task_orch
    state.tranche_manager = tranche_manager
    state.closeout_orchestrator = closeout_orch
    state.local_agent_runtime = local_agent_runtime
    state.router = router

    # Seed constraints (idempotent) from the binding contract.
    if not paths.contract_file.is_file():
        log.error(
            "contract file not found at %s",
            public_path(paths.contract_file, sidecar_root, "."),
        )
        raise FileNotFoundError(paths.contract_file)
    constraint_manager.seed_from_contract(paths.contract_file)

    # Load the in-force contract record onto state.
    contracts.bootstrap()

    # Register handlers.
    router.register("acknowledge_contract", contracts.handle_acknowledge, kind="manager")
    router.register("create_journal_entry", journal_manager.handle_create, kind="manager")
    router.register("update_journal_entry", journal_manager.handle_update, kind="manager")
    router.register("close_journal_entry", journal_manager.handle_close, kind="manager")
    router.register("archive_journal_entry", journal_manager.handle_archive, kind="manager")
    router.register("install", install_orch.handle_install, kind="orchestrator")
    router.register("scan", scan_orch.handle_scan, kind="orchestrator")
    router.register("attach_evidence", evidence_manager.handle_attach, kind="manager")
    router.register("verify_evidence", evidence_manager.handle_verify, kind="manager")
    router.register("observe_git", git_state_manager.handle_observe, kind="manager")
    router.register("tool_invoked", tool_registry_manager.handle_invoke, kind="manager")
    router.register("request_authority_elevation", human_approval_manager.handle_request, kind="manager")
    router.register("approve_authority_request", human_approval_manager.handle_approve, kind="manager")
    router.register("reject_authority_request", human_approval_manager.handle_reject, kind="manager")
    router.register("accept_task", agent_task_orch.handle_accept_task, kind="orchestrator")
    router.register("complete_task", agent_task_orch.handle_complete_task, kind="orchestrator")
    router.register("declare_tranche", tranche_manager.handle_declare_tranche, kind="manager")
    router.register("update_tranche", tranche_manager.handle_update_tranche, kind="manager")
    router.register("record_decision", tranche_manager.handle_record_decision, kind="manager")
    router.register("smoke_pass", tranche_manager.handle_smoke_pass, kind="manager")
    router.register("request_tranche_review", closeout_orch.handle_request_tranche_review, kind="orchestrator")
    router.register("return_tranche_review", closeout_orch.handle_return_tranche_review, kind="orchestrator")
    router.register("approve_tranche_review", closeout_orch.handle_approve_tranche_review, kind="orchestrator")
    router.register("close_tranche", closeout_orch.handle_close_tranche, kind="orchestrator")

    # Discover and register tools from src/tools/.
    tool_registry_manager.discover_all()

    # First-boot: dispatch an install envelope if not already installed.
    install_orch.ensure_installed(state)

    # Initial projection refresh so reads return populated rows.
    projections.refresh_all()

    # Generate config/toolbox_manifest.json + config/tool_manifest.json.
    # These are derived state (regeneratable from DB) but live in config/ for
    # zero-context agent entry per ARCHITECTURE.md §12.3 / contract §D.
    from src.components.manifest_generator import generate_all as _gen_manifests
    try:
        _gen_manifests(state, paths.config)
    except Exception as e:
        log.error("manifest generation failed (non-fatal): %s", e)

    project_root_label, sidecar_root_label = public_root_labels(sidecar_root, project_root)
    log.info(
        "boot complete: sidecar_id=%s root=%s project=%s schema=%d events=%d tools=%d",
        state.sidecar_id, sidecar_root_label, project_root_label,
        store.schema_version(), events.total_count(),
        tool_registry_manager.count(),
    )
    return state


def main(argv: list[str]) -> int:
    if not argv:
        sys.stderr.write(
            "usage: python -m src.app <cli|mcp|ui> [...]\n"
            "  cli <subcommand> [options]   one-shot CLI dispatch\n"
            "  mcp [--no-ui]                MCP server (stdio)\n"
            "  ui                           Tk monitoring console\n"
        )
        return 2

    mode = argv[0]
    if mode == "cli":
        state = boot()
        return cli_interface.dispatch(state, argv[1:])
    if mode == "mcp":
        state = boot()
        if "--no-ui" not in argv[1:]:
            launch_monitor(state.sidecar_root)
        return mcp_interface.serve_stdio(state)
    if mode == "ui":
        from src.ui import main_window

        state = boot()
        return main_window.run(state)
    sys.stderr.write(f"unknown mode: {mode}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
