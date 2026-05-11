"""
FILE: src/orchestrators/install_orchestrator.py
ROLE: First-boot installer. Records the explicit `install` event.
WHAT IT DOES (T2.2): handles the `install` envelope by emitting a single
                     install event with a summary payload. Idempotent —
                     boot calls ensure_installed() which checks
                     `journal_meta.installed_at` and only dispatches an
                     install envelope on the very first boot.

Most of the heavy lifting (open DB, apply migrations, seed constraints,
load contract) is already done in app.boot(); this orchestrator just
records the semantic milestone "the sidecar is initialized as of T."
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.envelope import SidecarEnvelope
from src.lib.common import now_iso
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.sqlite_store import Store
    from src.core.state import SidecarState


log = get_logger("orchestrators.install")


INSTALLED_AT_KEY = "installed_at"


class InstallOrchestrator:
    def __init__(self, store: "Store"):
        self._store = store

    def handle_install(self, envelope: SidecarEnvelope, state: "SidecarState") -> SidecarEnvelope:
        summary = {
            "sidecar_id": state.sidecar_id,
            "schema_version": self._store.schema_version(),
            "project_root": str(state.project_root),
            "sidecar_root": str(state.sidecar_root),
            "initialized_at": now_iso(),
            "contract_hash": (state.current_contract or {}).get("text_hash"),
        }
        summary_ref = state.blob_store.put_json(summary)
        self._store.set_meta(INSTALLED_AT_KEY, summary["initialized_at"])
        log.info("install recorded: sidecar_id=%s project_root=%s",
                 summary["sidecar_id"], summary["project_root"])
        return envelope.with_status("completed").with_payload_ref(summary_ref)

    def is_installed(self) -> bool:
        return self._store.get_meta(INSTALLED_AT_KEY) is not None

    def ensure_installed(self, state: "SidecarState",
                         actor_id: str = "system") -> SidecarEnvelope | None:
        """Idempotent: dispatch an install envelope if not already installed."""
        if self.is_installed():
            return None
        envelope = SidecarEnvelope.new(
            object_type="sidecar_install",
            actor_id=actor_id,
            operation_intent="install",
        )
        result = state.router.dispatch(envelope)
        if result.status in ("accepted", "completed"):
            log.info("first-boot install dispatched: event_id=%s", result.event_id)
        else:
            log.error("first-boot install failed: status=%s", result.status)
        return result
