"""
FILE: src/orchestrators/agent_task_orchestrator.py
ROLE: Coordinates an agent task lifecycle (accept_task → work → complete_task).
WHAT IT DOES (T2.3 skeleton): accept_task and complete_task handlers only.
                              The full lifecycle (request_authority_elevation,
                              supersede_task, approval flow) is T4+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.lib.common import gen_id, now_iso
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.blob_store import BlobStore
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState
    from src.managers.journal_manager import JournalManager


log = get_logger("orchestrators.agent_task")


class AgentTaskOrchestrator:
    def __init__(self, journal_manager: "JournalManager", blob_store: "BlobStore"):
        self._journal = journal_manager
        self._blob = blob_store

    def handle_accept_task(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        """Accept a task. Records a journal entry of kind='todo' with status='active'."""
        request = self._blob.get_json(envelope.payload_ref) if envelope.payload_ref else {}
        title = request.get("title", "(untitled task)")
        body = request.get("body", "")
        task_id = gen_id("task_")
        state.active_task = {"task_id": task_id, "title": title, "started_at": now_iso(),
                             "actor_id": envelope.actor_id}
        # Don't write a separate row here for T2.3 — keep state.active_task
        # in memory. T4+ will formalize task persistence.
        log.info("task accepted: %s actor=%s", task_id, envelope.actor_id)
        response = {"task_id": task_id, "title": title, "started_at": state.active_task["started_at"]}
        response_ref = self._blob.put_json(response)
        return envelope.with_status("completed").with_payload_ref(response_ref)

    def handle_complete_task(
        self, envelope: "SidecarEnvelope", state: "SidecarState"
    ) -> "SidecarEnvelope":
        """Complete the active task."""
        request = self._blob.get_json(envelope.payload_ref) if envelope.payload_ref else {}
        if not state.active_task:
            raise RuntimeError("no active task to complete")
        completed_task = dict(state.active_task)
        completed_task["completed_at"] = now_iso()
        completed_task["summary"] = request.get("summary", "")
        state.active_task = None
        log.info("task completed: %s", completed_task.get("task_id"))
        response_ref = self._blob.put_json(completed_task)
        return envelope.with_status("completed").with_payload_ref(response_ref)
