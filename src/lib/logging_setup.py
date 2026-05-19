"""
FILE: src/lib/logging_setup.py
ROLE: Configures the sidecar's logging. Implements the print-prohibition.
WHAT IT DOES: Sets up rotating file handlers under logs/ plus a stderr
              handler at WARNING+. Provides get_logger() helper.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_CONFIGURED = False
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_DEFAULT_BACKUP_COUNT = 5


def configure(
    logs_dir: Path,
    level: str = "INFO",
    stderr_level: str = "WARNING",
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    root = logging.getLogger("sidecar")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.propagate = False

    # Clear any previously attached handlers (re-config safety in tests).
    for h in list(root.handlers):
        root.removeHandler(h)

    # Main rotating file.
    main_handler = logging.handlers.RotatingFileHandler(
        logs_dir / "sidecar.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    main_handler.setFormatter(formatter)
    root.addHandler(main_handler)

    # Stderr handler for dev visibility.
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(getattr(logging, stderr_level.upper(), logging.WARNING))
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not name.startswith("sidecar"):
        name = f"sidecar.{name}"
    return logging.getLogger(name)


def reset_for_tests() -> None:
    """Clear configuration so a test can call configure() fresh."""
    global _CONFIGURED
    _CONFIGURED = False
    root = logging.getLogger("sidecar")
    for h in list(root.handlers):
        root.removeHandler(h)
