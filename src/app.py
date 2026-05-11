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
from src.components.sqlite_store import open_store
from src.core.contracts import ContractAuthority
from src.core.events import EventStore
from src.core.graph import Graph
from src.core.projections import ProjectionManager
from src.core.router import Router
from src.core.state import SidecarState
from src.interfaces import cli_interface
from src.lib import logging_setup
from src.lib.common import detect_sidecar_root, resolve_paths
from src.managers.constraint_manager import ConstraintManager


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
    router = Router(state, contracts, events, graph, projections)

    # Wire references onto state for handler access.
    state.events = events
    state.graph = graph
    state.constraint_manager = constraint_manager
    state.contract_authority = contracts
    state.projections = projections
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

    # Initial projection refresh so reads return populated rows.
    projections.refresh_all()

    log.info(
        "boot complete: sidecar_id=%s root=%s project=%s schema=%d events=%d",
        state.sidecar_id, sidecar_root, project_root,
        store.schema_version(), events.total_count(),
    )
    return state


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "cli":
        sys.stderr.write(
            "usage: python -m src.app cli <subcommand> [options]\n"
            "(T1 only supports the cli mode; ui and mcp land in T2/T3.)\n"
        )
        return 2

    state = boot()
    return cli_interface.dispatch(state, argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
