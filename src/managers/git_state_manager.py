"""
FILE: src/managers/git_state_manager.py
ROLE: Owner of git_observations + git_dirty_paths. Read-only with respect
      to the host project's git state.
WHAT IT DOES (T2.3): handle_observe_git records one observation snapshot.
                     Direct read API for projection builders + the
                     human_dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.components.git_reader import GitNotAvailable, GitReader
from src.lib.common import gen_id, now_iso
from src.lib.logging_setup import get_logger


if TYPE_CHECKING:
    from src.components.sqlite_store import Store
    from src.core.envelope import SidecarEnvelope
    from src.core.state import SidecarState


log = get_logger("managers.git_state")


@dataclass(frozen=True)
class GitObservationRecord:
    observation_id: str
    observed_at: str
    actor_id: str
    is_repo: bool
    branch: str
    head_sha: str
    detached: bool
    dirty_count: int
    ahead: int
    behind: int
    remote: str
    remote_url: str
    event_id: str | None
    dirty_paths: list[tuple[str, str]]


class GitStateManager:
    def __init__(self, store: "Store", git_reader: GitReader):
        self._store = store
        self._git = git_reader

    # ===== envelope handler ============================================

    def handle_observe(self, envelope: "SidecarEnvelope", state: "SidecarState") -> "SidecarEnvelope":
        observation_id = gen_id("gitobs_")
        try:
            obs = self._git.observe(state.project_root)
        except GitNotAvailable:
            log.warning("git not available; recording is_repo=False observation")
            obs = None
        now = now_iso()
        with self._store.transaction():
            if obs is None:
                self._store.execute(
                    "INSERT INTO git_observations(observation_id, observed_at, actor_id, "
                    "is_repo, event_id) VALUES (?, ?, ?, 0, 'PENDING');",
                    (observation_id, now, envelope.actor_id),
                )
            else:
                self._store.execute(
                    """
                    INSERT INTO git_observations(
                        observation_id, observed_at, actor_id, is_repo,
                        branch, head_sha, detached, dirty_count,
                        ahead, behind, remote, remote_url, event_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING');
                    """,
                    (
                        observation_id, now, envelope.actor_id, 1 if obs.is_repo else 0,
                        obs.head.branch, obs.head.head_sha,
                        1 if obs.head.detached else 0,
                        len(obs.status.dirty_paths),
                        obs.tracking.ahead, obs.tracking.behind,
                        obs.tracking.remote_name, obs.tracking.remote_url,
                    ),
                )
                for dirty in obs.status.dirty_paths:
                    self._store.execute(
                        "INSERT OR IGNORE INTO git_dirty_paths(observation_id, path, status) "
                        "VALUES (?, ?, ?);",
                        (observation_id, dirty.path, dirty.status),
                    )

        summary = {
            "observation_id": observation_id,
            "is_repo": obs.is_repo if obs else False,
            "branch": obs.head.branch if obs else "",
            "head_sha": obs.head.head_sha if obs else "",
            "dirty_count": len(obs.status.dirty_paths) if obs else 0,
            "ahead": obs.tracking.ahead if obs else 0,
            "behind": obs.tracking.behind if obs else 0,
            "observed_at": now,
        }
        summary_ref = state.blob_store.put_json(summary)
        log.info("git observation recorded: %s repo=%s branch=%s dirty=%d",
                 observation_id, summary["is_repo"], summary["branch"], summary["dirty_count"])
        return envelope.with_status("completed").with_payload_ref(summary_ref)

    def finalize_observation_event_id(self, sealed_envelope: "SidecarEnvelope") -> None:
        if not sealed_envelope.payload_ref:
            return
        try:
            summary = sealed_envelope.__class__  # placeholder to avoid import cycle
        except Exception:
            return
        # Read summary blob via the state we don't have direct access to here;
        # instead, just update the latest PENDING row for this actor.
        # T2.3 simplification: update the most recently inserted PENDING row.
        self._store.execute(
            "UPDATE git_observations SET event_id = ? "
            "WHERE observation_id = ("
            "  SELECT observation_id FROM git_observations "
            "  WHERE event_id = 'PENDING' "
            "  ORDER BY observed_at DESC LIMIT 1"
            ");",
            (sealed_envelope.event_id,),
        )

    # ===== reads =======================================================

    def latest(self) -> GitObservationRecord | None:
        row = self._store.query_one(
            "SELECT * FROM git_observations ORDER BY observed_at DESC LIMIT 1;"
        )
        if row is None:
            return None
        dirty_rows = self._store.query(
            "SELECT path, status FROM git_dirty_paths WHERE observation_id = ?;",
            (row["observation_id"],),
        )
        return GitObservationRecord(
            observation_id=row["observation_id"],
            observed_at=row["observed_at"],
            actor_id=row["actor_id"],
            is_repo=bool(row["is_repo"]),
            branch=row["branch"] or "",
            head_sha=row["head_sha"] or "",
            detached=bool(row["detached"]) if row["detached"] is not None else False,
            dirty_count=int(row["dirty_count"] or 0),
            ahead=int(row["ahead"] or 0),
            behind=int(row["behind"] or 0),
            remote=row["remote"] or "",
            remote_url=row["remote_url"] or "",
            event_id=row["event_id"],
            dirty_paths=[(r["path"], r["status"]) for r in dirty_rows],
        )

    def count(self) -> int:
        row = self._store.query_one("SELECT COUNT(*) AS n FROM git_observations;")
        return int(row["n"]) if row else 0
