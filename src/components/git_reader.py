"""
FILE: src/components/git_reader.py
ROLE: Read-only git observation via subprocess. Used by git_state_manager.
WHAT IT DOES: detect/head/status/tracking — only invokes non-mutating git
              subcommands. Never commits, pushes, rebases, checks out, etc.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from src.lib.logging_setup import get_logger


log = get_logger("components.git_reader")


# Allowlist of git subcommands this module is permitted to invoke.
# Anything else is a programming error.
_ALLOWED_SUBCOMMANDS: frozenset[str] = frozenset({
    "rev-parse", "status", "log", "diff", "branch", "remote",
    "ls-files", "show", "cat-file", "config", "rev-list",
})


_DEFAULT_TIMEOUT_S = 30.0


class GitNotAvailable(RuntimeError):
    """git binary not installed or not on PATH."""


class GitFailure(RuntimeError):
    """git invocation returned a non-zero exit code."""


@dataclass(frozen=True)
class HeadInfo:
    is_repo: bool
    head_sha: str = ""
    branch: str = ""
    detached: bool = False


@dataclass(frozen=True)
class TrackingInfo:
    remote_name: str = ""
    remote_url: str = ""
    ahead: int = 0
    behind: int = 0


@dataclass(frozen=True)
class DirtyPath:
    path: str
    status: str  # 2-char porcelain code (e.g., " M", "??", "A ")


@dataclass(frozen=True)
class StatusInfo:
    clean: bool
    dirty_paths: list[DirtyPath] = field(default_factory=list)


@dataclass(frozen=True)
class GitObservation:
    is_repo: bool
    head: HeadInfo
    tracking: TrackingInfo
    status: StatusInfo


class GitReader:
    def __init__(self, timeout_s: float = _DEFAULT_TIMEOUT_S):
        self._timeout = timeout_s

    def observe(self, project_root: Path) -> GitObservation:
        """One-shot read of current git state. Never raises on missing repo —
        returns is_repo=False instead."""
        root = Path(project_root)
        is_repo = self.is_git_repo(root)
        if not is_repo:
            return GitObservation(
                is_repo=False,
                head=HeadInfo(is_repo=False),
                tracking=TrackingInfo(),
                status=StatusInfo(clean=True),
            )
        head = self._head(root)
        tracking = self._tracking(root)
        status = self._status(root)
        return GitObservation(is_repo=True, head=head, tracking=tracking, status=status)

    def is_git_repo(self, project_root: Path) -> bool:
        rc, _, _ = self._git(project_root, ["rev-parse", "--git-dir"])
        return rc == 0

    # ---- internals -----------------------------------------------------

    def _head(self, root: Path) -> HeadInfo:
        rc, out, _ = self._git(root, ["rev-parse", "HEAD"])
        head_sha = out.strip() if rc == 0 else ""
        rc_b, out_b, _ = self._git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
        branch = out_b.strip() if rc_b == 0 else ""
        detached = (branch == "HEAD") if branch else False
        return HeadInfo(
            is_repo=True,
            head_sha=head_sha,
            branch="" if detached else branch,
            detached=detached,
        )

    def _tracking(self, root: Path) -> TrackingInfo:
        # Default remote (first one listed if any).
        rc, out, _ = self._git(root, ["remote"])
        if rc != 0 or not out.strip():
            return TrackingInfo()
        remote_name = out.splitlines()[0].strip()
        rc_u, out_u, _ = self._git(root, ["remote", "get-url", remote_name])
        remote_url = out_u.strip() if rc_u == 0 else ""
        # Ahead/behind vs upstream. If no upstream set, both stay 0.
        ahead = behind = 0
        rc_a, out_a, _ = self._git(
            root, ["rev-list", "--left-right", "--count", "@{u}...HEAD"]
        )
        if rc_a == 0 and out_a.strip():
            parts = out_a.split()
            if len(parts) == 2:
                try:
                    behind = int(parts[0])
                    ahead = int(parts[1])
                except ValueError:
                    pass
        return TrackingInfo(
            remote_name=remote_name,
            remote_url=remote_url,
            ahead=ahead,
            behind=behind,
        )

    def _status(self, root: Path) -> StatusInfo:
        rc, out, _ = self._git(root, ["status", "--porcelain=v1", "--untracked-files=all"])
        if rc != 0:
            return StatusInfo(clean=True)
        dirty: list[DirtyPath] = []
        for line in out.splitlines():
            if len(line) < 3:
                continue
            code = line[:2]
            path = line[3:]
            # Renames look like "R  oldpath -> newpath" — take the new path.
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            dirty.append(DirtyPath(path=path.strip().strip('"'), status=code))
        return StatusInfo(clean=not dirty, dirty_paths=dirty)

    def _git(self, root: Path, args: list[str]) -> tuple[int, str, str]:
        if not args or args[0] not in _ALLOWED_SUBCOMMANDS:
            raise ValueError(f"git subcommand not in allowlist: {args[:1]}")
        cmd = ["git"] + args
        try:
            cp = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                shell=False,
            )
        except FileNotFoundError as e:
            raise GitNotAvailable("git binary not found on PATH") from e
        except subprocess.TimeoutExpired:
            log.warning("git %s timed out after %ss in %s", args, self._timeout, root)
            return (124, "", "timeout")
        return cp.returncode, cp.stdout, cp.stderr
