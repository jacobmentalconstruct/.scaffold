"""
FILE: src/lib/ui_launcher.py
ROLE: Launch the Tk monitor as a companion process when agent-facing runs start.
WHAT IT DOES: Provides a tiny stdlib-only helper that spawns `python -m src.app ui`
              in a separate process. Used by MCP and local-agent entrypoints so the
              monitor appears by default unless explicitly suppressed.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from src.lib.logging_setup import get_logger


log = get_logger("lib.ui_launcher")


def launch_monitor(sidecar_root: Path) -> bool:
    """Launch a companion Tk monitor window.

    Non-fatal by design: returns False on failure and logs the reason, but does
    not raise. This keeps agent-facing workflows usable in headless contexts when
    the caller intentionally or accidentally leaves auto-monitoring enabled.
    """
    python_exe = _resolve_python_for_ui()
    cmd = [python_exe, "-m", "src.app", "ui"]

    kwargs: dict = {
        "cwd": str(sidecar_root),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "close_fds": True,
    }

    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )

    try:
        subprocess.Popen(cmd, **kwargs)
        log.info("launched companion monitor: cwd=%s cmd=%s", sidecar_root, cmd)
        return True
    except Exception as exc:
        log.warning("failed to launch companion monitor: %s", exc)
        return False


def _resolve_python_for_ui() -> str:
    """Prefer pythonw on Windows so the companion UI doesn't open a spare console."""
    current = Path(sys.executable)
    if os.name == "nt":
        pythonw = current.with_name("pythonw.exe")
        if pythonw.is_file():
            return str(pythonw)
    return str(current)
