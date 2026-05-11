"""
FILE: src/managers/project_index_manager.py
ROLE: Owner of the project_index + scans tables — the sidecar's view of the
      host project.
WHAT IT DOES (T2.2): direct read/write API used by scan_orchestrator
                     (orchestrator → manager is allowed per spine rules).
                     No envelope-routed handlers in T2.2; record_observation
                     and record_scan_summary are direct calls inside the
                     scan workflow. Heavier intents (rescan_path, etc.)
                     land in T2.3+.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.lib.common import gen_id, now_iso, safe_json_dumps
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.file_scanner import ObservedFile
    from src.components.sqlite_store import Store


log = get_logger("managers.project_index")


@dataclass(frozen=True)
class ProjectIndexEntry:
    path: str
    kind: str
    size_bytes: int | None
    content_hash: str | None
    ext: str | None
    mtime: str | None
    last_observed_at: str
    last_observed_event: str | None
    last_observed_scan: str | None
    observe_count: int
    annotation: dict


@dataclass(frozen=True)
class ScanRecord:
    scan_id: str
    project_root: str
    started_at: str
    finished_at: str | None
    file_count: int
    directory_count: int
    added_count: int
    modified_count: int
    removed_count: int
    unchanged_count: int
    actor_id: str
    status: str
    event_id: str | None
    summary_blob_ref: str | None


class ProjectIndexManager:
    def __init__(self, store: "Store"):
        self._store = store

    # ===== scan lifecycle ==============================================

    def begin_scan(self, project_root: str, actor_id: str) -> str:
        scan_id = gen_id("scan_")
        self._store.execute(
            """
            INSERT INTO scans(
                scan_id, project_root, started_at, actor_id, status
            ) VALUES (?, ?, ?, ?, 'in_progress');
            """,
            (scan_id, str(project_root), now_iso(), actor_id),
        )
        log.info("scan begun: %s root=%s actor=%s", scan_id, project_root, actor_id)
        return scan_id

    def finish_scan(
        self,
        scan_id: str,
        *,
        file_count: int,
        directory_count: int,
        added_count: int,
        modified_count: int,
        removed_count: int,
        unchanged_count: int,
        summary_blob_ref: str | None = None,
        status: str = "completed",
    ) -> None:
        self._store.execute(
            """
            UPDATE scans SET
                finished_at = ?,
                file_count = ?,
                directory_count = ?,
                added_count = ?,
                modified_count = ?,
                removed_count = ?,
                unchanged_count = ?,
                status = ?,
                summary_blob_ref = ?
            WHERE scan_id = ?;
            """,
            (
                now_iso(),
                file_count, directory_count,
                added_count, modified_count, removed_count, unchanged_count,
                status, summary_blob_ref, scan_id,
            ),
        )
        log.info(
            "scan finished: %s files=%d dirs=%d added=%d modified=%d removed=%d unchanged=%d",
            scan_id, file_count, directory_count,
            added_count, modified_count, removed_count, unchanged_count,
        )

    def finalize_scan_event_id(self, scan_id: str, event_id: str) -> None:
        """Called by Router post-commit to bind the scan to its event."""
        self._store.execute(
            "UPDATE scans SET event_id = ? WHERE scan_id = ?;",
            (event_id, scan_id),
        )

    # ===== per-file observation ========================================

    def record_observation(
        self,
        observed: "ObservedFile",
        scan_id: str,
        event_id: str | None = None,
    ) -> str:
        """Upsert one row into project_index. Returns: 'added'|'modified'|'unchanged'."""
        existing = self._store.query_one(
            "SELECT content_hash, size_bytes FROM project_index WHERE path = ?;",
            (observed.path,),
        )
        verdict: str
        if existing is None:
            verdict = "added"
            self._store.execute(
                """
                INSERT INTO project_index(
                    path, kind, size_bytes, content_hash, ext, mtime,
                    last_observed_at, last_observed_event, last_observed_scan,
                    observe_count, annotation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, '{}');
                """,
                (
                    observed.path, observed.kind, observed.size_bytes,
                    observed.content_hash, observed.ext, observed.mtime,
                    now_iso(), event_id, scan_id,
                ),
            )
        else:
            if (
                existing["content_hash"] == observed.content_hash
                and int(existing["size_bytes"] or 0) == observed.size_bytes
            ):
                verdict = "unchanged"
            else:
                verdict = "modified"
            self._store.execute(
                """
                UPDATE project_index SET
                    kind = ?,
                    size_bytes = ?,
                    content_hash = ?,
                    ext = ?,
                    mtime = ?,
                    last_observed_at = ?,
                    last_observed_event = COALESCE(?, last_observed_event),
                    last_observed_scan = ?,
                    observe_count = observe_count + 1
                WHERE path = ?;
                """,
                (
                    observed.kind, observed.size_bytes, observed.content_hash,
                    observed.ext, observed.mtime,
                    now_iso(), event_id, scan_id, observed.path,
                ),
            )
        return verdict

    def mark_removed_for_scan(self, scan_id: str, project_root: str) -> int:
        """Identify paths that were in the index but not observed in this scan.

        Returns the count. (Removal marking via deletion is destructive;
        for T2.2 we just count and let the next scan re-observe if the file
        returns. A 'tombstones' table can come later if needed.)
        """
        # For T2.2 we don't actually remove rows. Just count.
        row = self._store.query_one(
            "SELECT COUNT(*) AS n FROM project_index "
            "WHERE last_observed_scan != ? OR last_observed_scan IS NULL;",
            (scan_id,),
        )
        return int(row["n"]) if row else 0

    # ===== reads =======================================================

    def get(self, path: str) -> ProjectIndexEntry | None:
        row = self._store.query_one(
            "SELECT * FROM project_index WHERE path = ?;", (path,)
        )
        return _row_to_entry(row) if row else None

    def query(
        self,
        kind: str | None = None,
        ext: str | None = None,
        limit: int | None = None,
        order: str = "path",
    ) -> list[ProjectIndexEntry]:
        sql = "SELECT * FROM project_index WHERE 1=1"
        params: list = []
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        if ext is not None:
            sql += " AND ext = ?"
            params.append(ext)
        sql += " ORDER BY " + (order if order in ("path", "size_bytes", "last_observed_at") else "path")
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        rows = self._store.query(sql + ";", params)
        return [_row_to_entry(r) for r in rows]

    def count(self, kind: str | None = None) -> int:
        if kind is None:
            row = self._store.query_one("SELECT COUNT(*) AS n FROM project_index;")
        else:
            row = self._store.query_one(
                "SELECT COUNT(*) AS n FROM project_index WHERE kind = ?;",
                (kind,),
            )
        return int(row["n"]) if row else 0

    def latest_scan(self) -> ScanRecord | None:
        row = self._store.query_one(
            "SELECT * FROM scans ORDER BY started_at DESC LIMIT 1;"
        )
        return _row_to_scan(row) if row else None

    def get_scan(self, scan_id: str) -> ScanRecord | None:
        row = self._store.query_one("SELECT * FROM scans WHERE scan_id = ?;", (scan_id,))
        return _row_to_scan(row) if row else None

    def stats(self) -> dict:
        total = self.count()
        files = self.count(kind="file")
        dirs = self.count(kind="directory")
        latest = self.latest_scan()
        return {
            "indexed_path_count": total,
            "file_count": files,
            "directory_count": dirs,
            "latest_scan_id": latest.scan_id if latest else None,
            "latest_scan_at": latest.started_at if latest else None,
            "latest_scan_status": latest.status if latest else None,
        }


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------


def _row_to_entry(row) -> ProjectIndexEntry:
    return ProjectIndexEntry(
        path=row["path"],
        kind=row["kind"],
        size_bytes=int(row["size_bytes"]) if row["size_bytes"] is not None else None,
        content_hash=row["content_hash"],
        ext=row["ext"],
        mtime=row["mtime"],
        last_observed_at=row["last_observed_at"],
        last_observed_event=row["last_observed_event"],
        last_observed_scan=row["last_observed_scan"],
        observe_count=int(row["observe_count"]),
        annotation=json.loads(row["annotation_json"]) if row["annotation_json"] else {},
    )


def _row_to_scan(row) -> ScanRecord:
    return ScanRecord(
        scan_id=row["scan_id"],
        project_root=row["project_root"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        file_count=int(row["file_count"]),
        directory_count=int(row["directory_count"]),
        added_count=int(row["added_count"]),
        modified_count=int(row["modified_count"]),
        removed_count=int(row["removed_count"]),
        unchanged_count=int(row["unchanged_count"]),
        actor_id=row["actor_id"],
        status=row["status"],
        event_id=row["event_id"],
        summary_blob_ref=row["summary_blob_ref"],
    )
