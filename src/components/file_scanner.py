"""
FILE: src/components/file_scanner.py
ROLE: Walks the host project tree yielding ObservedFile records.
WHAT IT DOES: Mechanical worker behind scan_orchestrator. Stdlib-only walk,
              chunked SHA-256 hashing, configurable skip rules (T2.2 uses
              a hard-coded sensible default; full .gitignore parsing is a
              later refactor).
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from src.lib.logging_setup import get_logger


log = get_logger("components.file_scanner")


@dataclass(frozen=True)
class ObservedFile:
    path: str          # POSIX-form relative to project_root
    kind: str          # "file" | "directory" | "symlink"
    size_bytes: int
    content_hash: str  # "" for directories; "TOO_LARGE:<n>" for oversized files
    mtime: str         # ISO 8601 UTC
    ext: str           # file extension lowercase (e.g. ".py"); "" for dirs


class FileScanner:
    # Directory names to skip regardless of where they appear.
    DEFAULT_SKIP_DIRS: frozenset[str] = frozenset({
        ".git", ".github", "__pycache__", ".venv", "venv", "env",
        "node_modules", ".parts", ".idea", ".vscode",
        ".pytest_cache", ".mypy_cache", ".ruff_cache",
        ".claude", "dist", "build", ".tox", ".nox",
        # Sidecar's own runtime folders (when scanning .scaffold/ in dev scope):
        "data", "logs", "cache", "exports", "workspaces", "snapshots",
    })

    # File name patterns to skip (fnmatch-style).
    DEFAULT_SKIP_FILE_PATTERNS: tuple[str, ...] = (
        "*.pyc", "*.pyo", "*.pyd",
        "*.log", "*.log.*",
        ".DS_Store", "Thumbs.db", "desktop.ini",
        "*.db", "*.db-wal", "*.db-shm", "*.db-journal",
        "*.sqlite", "*.sqlite3",
        "*.swp", "*.swo", "*.swn",
        "*.tmp", "*.bak", "*.orig", "*.rej",
    )

    # Files larger than this get a TOO_LARGE marker instead of a hash.
    DEFAULT_MAX_HASH_BYTES = 50 * 1024 * 1024  # 50 MB

    # Hash chunk size.
    _CHUNK = 65536

    def __init__(
        self,
        skip_dirs: Iterable[str] | None = None,
        skip_file_patterns: Iterable[str] | None = None,
        max_hash_bytes: int | None = None,
        include_directories: bool = True,
    ):
        self.skip_dirs = set(skip_dirs) if skip_dirs is not None else set(self.DEFAULT_SKIP_DIRS)
        self.skip_file_patterns = (
            tuple(skip_file_patterns) if skip_file_patterns is not None
            else self.DEFAULT_SKIP_FILE_PATTERNS
        )
        self.max_hash_bytes = max_hash_bytes if max_hash_bytes is not None else self.DEFAULT_MAX_HASH_BYTES
        self.include_directories = include_directories

    def walk(self, project_root: Path) -> Iterable[ObservedFile]:
        """Yield ObservedFile records for every non-skipped path under project_root."""
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise ValueError(f"project_root is not a directory: {root}")

        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # In-place edit to skip subtrees.
            dirnames[:] = sorted(d for d in dirnames if d not in self.skip_dirs)

            current = Path(dirpath)
            rel_dir = current.relative_to(root)

            # Yield the directory itself (skip the root and skipped subtrees).
            if self.include_directories and str(rel_dir) != ".":
                yield self._observed_dir(rel_dir, current)

            for filename in sorted(filenames):
                if self._should_skip_file(filename):
                    continue
                file_path = current / filename
                rel_path = file_path.relative_to(root)
                try:
                    stat = file_path.stat()
                except OSError as e:
                    log.warning("could not stat %s: %s", file_path, e)
                    continue
                kind = "symlink" if file_path.is_symlink() else "file"
                if kind == "file":
                    if stat.st_size <= self.max_hash_bytes:
                        try:
                            content_hash = self._hash_file(file_path)
                        except OSError as e:
                            log.warning("could not hash %s: %s", file_path, e)
                            content_hash = "UNREADABLE"
                    else:
                        content_hash = f"TOO_LARGE:{stat.st_size}"
                else:
                    content_hash = ""
                yield ObservedFile(
                    path=_posix(rel_path),
                    kind=kind,
                    size_bytes=int(stat.st_size),
                    content_hash=content_hash,
                    mtime=_iso_mtime(stat.st_mtime),
                    ext=file_path.suffix.lower(),
                )

    # ---- internals ---------------------------------------------------

    def _should_skip_file(self, filename: str) -> bool:
        return any(fnmatch.fnmatch(filename, p) for p in self.skip_file_patterns)

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(self._CHUNK)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _observed_dir(self, rel_path: Path, abs_path: Path) -> ObservedFile:
        try:
            stat = abs_path.stat()
            mtime = _iso_mtime(stat.st_mtime)
        except OSError:
            mtime = ""
        return ObservedFile(
            path=_posix(rel_path),
            kind="directory",
            size_bytes=0,
            content_hash="",
            mtime=mtime,
            ext="",
        )


def _posix(p: Path) -> str:
    return str(p).replace(os.sep, "/")


def _iso_mtime(epoch_seconds: float) -> str:
    dt = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
