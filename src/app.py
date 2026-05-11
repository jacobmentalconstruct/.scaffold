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
from src.lib.common import detect_sidecar_root, resolve_paths
from src.managers.constraint_manager import ConstraintManager
from src.managers.evidence_manager import EvidenceManager
from src.managers.git_state_manager import GitStateManager
from src.managers.journal_manager import JournalManager
from src.managers.project_index_manager import ProjectIndexManager
from src.managers.tool_registry_manager import ToolRegistryManager
from src.orchestrators.agent_task_orchestrator import AgentTaskOrchestrator
from src.orchestrators.install_orchestrator import InstallOrchestrator
from src.orchestrators.scan_orchestrator import ScanOrchestrator


def boot(sidecar_root: Path | None = None,
         project_root: Path | None = None) -> SidecarState:
    """Wire the sidecar spine and return a fully-bootstrapped SidecarState."""
    sidecar_root = Path(sidecar_root) if sidecar_root else detect_sidecar_root()
    # Development scope per contract §0.10: project_root == sidecar_root.
    project_root = Path(project_root) if project_root else sidecar_root

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
    tool_registry_manager = ToolRegistryManager(store, blob, paths.src / "tools")
    file_scanner = FileScanner()
    install_orch = InstallOrchestrator(store)
    scan_orch = ScanOrchestrator(file_scanner, project_index_manager, blob)
    agent_task_orch = AgentTaskOrchestrator(journal_manager, blob)
    router = Router(
        state, contracts, events, graph, projections,
        journal_manager=journal_manager,
        scan_orchestrator=scan_orch,
    )
    router._tool_registry = tool_registry_manager  # type: ignore[attr-defined]
    router._git_state = git_state_manager  # type: ignore[attr-defined]

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
    state.file_scanner = file_scanner
    state.install_orchestrator = install_orch
    state.scan_orchestrator = scan_orch
    state.agent_task_orchestrator = agent_task_orch
    state.router = router

    # Seed constraints (idempotent) from the binding contract.
    if not paths.contract_file.is_file():
        log.error("contract file not found at %s", paths.contract_file)
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
    router.register("accept_task", agent_task_orch.handle_accept_task, kind="orchestrator")
    router.register("complete_task", agent_task_orch.handle_complete_task, kind="orchestrator")

    # Discover and register tools from src/tools/.
    tool_registry_manager.discover_all()

    # First-boot: dispatch an install envelope if not already installed.
    install_orch.ensure_installed(state)

    # Initial projection refresh so reads return populated rows.
    projections.refresh_all()

    log.info(
        "boot complete: sidecar_id=%s root=%s project=%s schema=%d events=%d tools=%d",
        state.sidecar_id, sidecar_root, project_root,
        store.schema_version(), events.total_count(),
        tool_registry_manager.count(),
    )
    return state


def main(argv: list[str]) -> int:
    if not argv:
        sys.stderr.write(
            "usage: python -m src.app <cli|mcp> [...]\n"
            "  cli <subcommand> [options]   one-shot CLI dispatch\n"
            "  mcp                          MCP server (stdio)\n"
        )
        return 2

    mode = argv[0]
    if mode == "cli":
        state = boot()
        return cli_interface.dispatch(state, argv[1:])
    if mode == "mcp":
        state = boot()
        return mcp_interface.serve_stdio(state)
    sys.stderr.write(f"unknown mode: {mode}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
