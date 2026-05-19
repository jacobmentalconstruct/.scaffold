"""
FILE: src/orchestrators/journal_orchestrator.py
ROLE: Higher-level journal workflows that span more than a single entry write.
WHAT IT DOES (T2.1): basic — exposes a thin wrapper that journal_manager
                     handlers route through when an orchestrator's
                     coordination is needed. Full close_tranche /
                     rollup_decisions / triage_issues / export_journal_bundle
                     workflows are deferred to T4+ (need evidence_manager
                     and multi-step state).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState
    from src.managers.journal_manager import JournalManager


log = get_logger("orchestrators.journal")


class JournalOrchestrator:
    def __init__(self, journal_manager: "JournalManager"):
        self._journal = journal_manager

    # T2.1: orchestrator is a placeholder — single-entry CRUD is handled
    # by journal_manager directly via Router registration. Multi-step
    # workflows (close_tranche, rollup_decisions) land in T4+.

    def handle_close_tranche(self, envelope: "SidecarEnvelope", state: "SidecarState"):
        """Placeholder for T4+ close_tranche workflow."""
        log.warning("close_tranche orchestrator called but not yet implemented (T4+).")
        return envelope.with_status("failed")
