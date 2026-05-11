"""
FILE: src/orchestrators/scan_orchestrator.py
ROLE: Coordinates a project file scan. Walks the host project, records each
      observation into project_index, emits ONE scan event summarizing.
WHAT IT DOES (T2.2): handle_scan(envelope, state) → walks via file_scanner,
                     records observations via project_index_manager directly
                     (orchestrator → manager is allowed per spine rules;
                     per-file envelopes would be too granular for T2.2 and
                     violate Envelope Lightness).

                     Heavy/repeated work is bounded by the scanner's skip
                     rules. The single envelope's payload_ref returns a
                     summary blob. Router post-commit hook calls
                     project_index_manager.finalize_scan_event_id().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.envelope import SidecarEnvelope
from src.lib.common import now_iso
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.blob_store import BlobStore
    from src.components.file_scanner import FileScanner
    from src.core.state import SidecarState
    from src.managers.project_index_manager import ProjectIndexManager


log = get_logger("orchestrators.scan")


class ScanOrchestrator:
    def __init__(
        self,
        file_scanner: "FileScanner",
        project_index_manager: "ProjectIndexManager",
        blob_store: "BlobStore",
    ):
        self._scanner = file_scanner
        self._index = project_index_manager
        self._blob = blob_store
        # The Router calls finalize_scan_event_id post-commit; we need to
        # remember which scan_id was created by the most recent handler call
        # so the finalize hook (driven by the sealed envelope's payload_ref)
        # can look it up. We use the response blob for this — no class state.

    def handle_scan(self, envelope: SidecarEnvelope, state: "SidecarState") -> SidecarEnvelope:
        actor = envelope.actor_id
        project_root = state.project_root
        scan_id = self._index.begin_scan(project_root=str(project_root), actor_id=actor)
        log.info("scan_orchestrator: begin scan=%s actor=%s root=%s",
                 scan_id, actor, project_root)

        file_count = 0
        directory_count = 0
        added = 0
        modified = 0
        unchanged = 0
        sample_paths: list[str] = []

        with state.store.transaction():
            for observed in self._scanner.walk(project_root):
                verdict = self._index.record_observation(observed, scan_id=scan_id)
                if observed.kind == "directory":
                    directory_count += 1
                else:
                    file_count += 1
                if verdict == "added":
                    added += 1
                elif verdict == "modified":
                    modified += 1
                else:
                    unchanged += 1
                if len(sample_paths) < 12:
                    sample_paths.append(observed.path)

            removed = 0  # T2.2: removal counting is conservative; see manager.
            summary = {
                "scan_id": scan_id,
                "project_root": str(project_root),
                "file_count": file_count,
                "directory_count": directory_count,
                "added": added,
                "modified": modified,
                "removed": removed,
                "unchanged": unchanged,
                "started_actor": actor,
                "finished_at": now_iso(),
                "sample_paths": sample_paths,
            }
            summary_ref = self._blob.put_json(summary)
            self._index.finish_scan(
                scan_id,
                file_count=file_count,
                directory_count=directory_count,
                added_count=added,
                modified_count=modified,
                removed_count=removed,
                unchanged_count=unchanged,
                summary_blob_ref=summary_ref,
                status="completed",
            )

        log.info(
            "scan_orchestrator: complete scan=%s files=%d dirs=%d added=%d modified=%d unchanged=%d",
            scan_id, file_count, directory_count, added, modified, unchanged,
        )
        return envelope.with_status("completed").with_payload_ref(summary_ref)

    def finalize_scan_event_id(self, sealed_envelope: SidecarEnvelope) -> None:
        """Called by Router after EventStore.append to bind the scan to its event."""
        if not sealed_envelope.payload_ref:
            return
        try:
            summary = self._blob.get_json(sealed_envelope.payload_ref)
        except Exception as e:
            log.error("could not read scan summary blob: %s", e)
            return
        scan_id = summary.get("scan_id")
        if scan_id:
            self._index.finalize_scan_event_id(scan_id, sealed_envelope.event_id)
