"""
FILE: process_port_inspector.py
ROLE: Read-only process and port inspector for local-agent operations.
WHAT IT DOES:
  - Reports running processes and listening/established ports when host commands allow
  - Uses platform-specific command fallbacks with short timeouts
  - Avoids mutation; never kills or starts processes
HOW TO USE:
  - python src/tools/process_port_inspector.py metadata
  - python src/tools/process_port_inspector.py run --input-json '{"ports": [3000, 8000]}'
"""

from __future__ import annotations

import csv
import platform
import subprocess
import sys
from io import StringIO
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result


FILE_METADATA = {
    "tool_name": "process_port_inspector",
    "version": "1.0.0",
    "entrypoint": "src/tools/process_port_inspector.py",
    "category": "introspection",
    "summary": "Read-only inspection of relevant running processes and occupied/listening ports with graceful platform fallbacks.",
    "mcp_name": "process_port_inspector",
    "input_schema": {
        "type": "object",
        "properties": {
            "ports": {"type": "array", "items": {"type": "integer"}},
            "process_name_contains": {"type": "array", "items": {"type": "string"}},
            "timeout_seconds": {"type": "number", "default": 5},
            "max_processes": {"type": "integer", "default": 80},
            "max_ports": {"type": "integer", "default": 200},
        },
        "additionalProperties": False,
    },
}


DEFAULT_NAMES = ["python", "node", "npm", "uvicorn", "flask", "django", "vite", "docker", "kubectl"]


def _run(args: list[str], timeout: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}


def _windows_processes(timeout: float, names: list[str], max_processes: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = _run(["tasklist", "/fo", "csv"], timeout)
    if not raw["ok"]:
        return [], {"engine": "tasklist", "ok": False, "error": raw["stderr"][:300]}
    rows = csv.DictReader(StringIO(raw["stdout"]))
    processes = []
    lowered = [name.lower() for name in names]
    for row in rows:
        image = row.get("Image Name", "")
        if lowered and not any(name in image.lower() for name in lowered):
            continue
        processes.append({
            "pid": row.get("PID", ""),
            "name": image,
            "session_name": row.get("Session Name", ""),
            "memory_usage": row.get("Mem Usage", ""),
        })
        if len(processes) >= max_processes:
            break
    return processes, {"engine": "tasklist", "ok": True}


def _posix_processes(timeout: float, names: list[str], max_processes: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw = _run(["ps", "-eo", "pid=,comm=,args="], timeout)
    if not raw["ok"]:
        return [], {"engine": "ps", "ok": False, "error": raw["stderr"][:300]}
    lowered = [name.lower() for name in names]
    processes = []
    for line in raw["stdout"].splitlines():
        text = line.strip()
        if not text:
            continue
        if lowered and not any(name in text.lower() for name in lowered):
            continue
        parts = text.split(None, 2)
        processes.append({
            "pid": parts[0] if len(parts) > 0 else "",
            "name": parts[1] if len(parts) > 1 else "",
            "command": parts[2][:500] if len(parts) > 2 else "",
        })
        if len(processes) >= max_processes:
            break
    return processes, {"engine": "ps", "ok": True}


def _parse_netstat(stdout: str, wanted_ports: set[int]) -> list[dict[str, Any]]:
    rows = []
    for line in stdout.splitlines():
        text = line.strip()
        if not text or not (text.startswith("TCP") or text.startswith("UDP") or text.startswith("tcp") or text.startswith("udp")):
            continue
        parts = text.split()
        if len(parts) < 4:
            continue
        proto = parts[0]
        local = parts[1] if len(parts) > 1 else ""
        state = ""
        pid = ""
        if proto.lower().startswith("tcp"):
            state = parts[3] if len(parts) > 3 else ""
            pid = parts[4] if len(parts) > 4 else ""
        else:
            pid = parts[3] if len(parts) > 3 else ""
        try:
            port = int(local.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        if wanted_ports and port not in wanted_ports:
            continue
        rows.append({"protocol": proto, "local_address": local, "port": port, "state": state, "pid": pid})
    return rows


def _ports(timeout: float, wanted_ports: set[int], max_ports: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    system = platform.system().lower()
    if system == "windows":
        raw = _run(["netstat", "-ano"], timeout)
        engine = "netstat -ano"
    else:
        raw = _run(["ss", "-ltnp"], timeout)
        engine = "ss -ltnp"
        if not raw["ok"]:
            raw = _run(["netstat", "-an"], timeout)
            engine = "netstat -an"
    if not raw["ok"]:
        return [], {"engine": engine, "ok": False, "error": raw["stderr"][:300]}
    rows = _parse_netstat(raw["stdout"], wanted_ports)
    truncated = len(rows) > max_ports
    return rows[:max_ports], {"engine": engine, "ok": True, "truncated": truncated, "total_before_limit": len(rows)}


def run(arguments: dict) -> dict:
    timeout = float(arguments.get("timeout_seconds", 5))
    names = [str(item) for item in arguments.get("process_name_contains", DEFAULT_NAMES)]
    wanted_ports = {int(item) for item in arguments.get("ports", [])}
    max_processes = int(arguments.get("max_processes", 80))
    max_ports = int(arguments.get("max_ports", 200))

    if platform.system().lower() == "windows":
        processes, process_source = _windows_processes(timeout, names, max_processes)
    else:
        processes, process_source = _posix_processes(timeout, names, max_processes)
    ports, port_source = _ports(timeout, wanted_ports, max_ports)

    result = {
        "filters": {
            "ports": sorted(wanted_ports),
            "process_name_contains": names,
        },
        "processes": processes,
        "ports": ports,
        "summary": {
            "process_count": len(processes),
            "port_count": len(ports),
            "process_source": process_source,
            "port_source": port_source,
        },
        "warnings": [
            "Process and port visibility depends on host permissions and available OS commands."
        ],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
