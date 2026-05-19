"""
FILE: dev_server_manager.py
ROLE: Guarded dev-server lifecycle manager for local-agent operations.
WHAT IT DOES:
  - Starts only dev/run commands discovered by project_command_profile
  - Tracks launched processes in gitignored runtime state
  - Tails logs, checks health, reports status, and stops only registered processes
HOW TO USE:
  - python src/tools/dev_server_manager.py metadata
  - python src/tools/dev_server_manager.py run --input-json '{"action": "status", "project_root": "."}'
"""

from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import ensure_dir, standard_main, tool_error, tool_result, write_json
from tools.project_command_profile import run as run_project_command_profile


FILE_METADATA = {
    "tool_name": "dev_server_manager",
    "version": "1.0.0",
    "entrypoint": "src/tools/dev_server_manager.py",
    "category": "operations",
    "summary": "Guarded start/status/stop/restart/tail/health management for declared project dev-server commands.",
    "mcp_name": "dev_server_manager",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "start", "stop", "restart", "tail", "health"],
                "default": "status",
            },
            "project_root": {"type": "string", "default": "."},
            "command_id": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
            "health_url": {"type": "string"},
            "port": {"type": "integer"},
            "tail_lines": {"type": "integer", "default": 80},
            "timeout_seconds": {"type": "number", "default": 5},
        },
        "additionalProperties": False,
    },
}


ALLOWED_KINDS = {"dev", "run"}
RUNTIME_DIR = Path(".dev-tools") / "runtime" / "dev_servers"
STATE_FILE = "servers.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:80]


def _runtime_root(project_root: Path) -> Path:
    return project_root / RUNTIME_DIR


def _state_path(project_root: Path) -> Path:
    return _runtime_root(project_root) / STATE_FILE


def _logs_dir(project_root: Path) -> Path:
    return ensure_dir(_runtime_root(project_root) / "logs")


def _load_state(project_root: Path) -> dict[str, Any]:
    path = _state_path(project_root)
    if not path.exists():
        return {"version": "1.0", "servers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": "1.0", "servers": {}}
    if not isinstance(data, dict):
        return {"version": "1.0", "servers": {}}
    data.setdefault("version", "1.0")
    data.setdefault("servers", {})
    return data


def _save_state(project_root: Path, state: dict[str, Any]) -> None:
    ensure_dir(_runtime_root(project_root))
    write_json(_state_path(project_root), state)


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _profile_commands(project_root: Path) -> list[dict[str, Any]]:
    envelope = run_project_command_profile({"project_root": str(project_root)})
    if envelope.get("status") != "ok":
        return []
    commands = envelope.get("result", {}).get("commands", [])
    return commands if isinstance(commands, list) else []


def _find_command(project_root: Path, command_id: str) -> dict[str, Any] | None:
    for command in _profile_commands(project_root):
        if command.get("id") == command_id:
            return command
    return None


def _registered_entries(project_root: Path) -> list[dict[str, Any]]:
    state = _load_state(project_root)
    entries = []
    changed = False
    for command_id, entry in state.get("servers", {}).items():
        if not isinstance(entry, dict):
            continue
        pid = int(entry.get("pid", 0) or 0)
        alive = _is_process_alive(pid)
        if entry.get("alive") != alive:
            entry["alive"] = alive
            entry["last_checked_at"] = _now()
            changed = True
        item = dict(entry)
        item["command_id"] = command_id
        entries.append(item)
    if changed:
        _save_state(project_root, state)
    return entries


def _require_confirm(arguments: dict[str, Any], action: str) -> dict[str, Any] | None:
    if arguments.get("confirm") is True:
        return None
    return tool_error(FILE_METADATA["tool_name"], arguments, f"{action} requires confirm: true")


def _health_check(url: str, timeout: float) -> dict[str, Any]:
    started = time.time()
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(200)
            return {
                "ok": 200 <= response.status < 500,
                "status_code": response.status,
                "url": url,
                "elapsed_ms": int((time.time() - started) * 1000),
                "body_preview": body.decode("utf-8", errors="replace"),
            }
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return {
            "ok": False,
            "status_code": None,
            "url": url,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": str(exc),
        }


def _tail(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return data[-max(1, lines):]


def _status(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    command_id = arguments.get("command_id")
    entries = _registered_entries(project_root)
    if command_id:
        entries = [entry for entry in entries if entry.get("command_id") == command_id]
    result = {
        "project_root": str(project_root),
        "runtime_state": str(_state_path(project_root)),
        "servers": entries,
        "summary": {
            "registered_count": len(entries),
            "alive_count": sum(1 for entry in entries if entry.get("alive")),
        },
        "warnings": ["Only processes launched and registered by this tool are managed."],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


def _start(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    confirm_error = _require_confirm(arguments, "start")
    if confirm_error:
        return confirm_error
    command_id = str(arguments.get("command_id", ""))
    if not command_id:
        return tool_error(FILE_METADATA["tool_name"], arguments, "start requires command_id")
    command = _find_command(project_root, command_id)
    if not command:
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Unknown command_id: {command_id}")
    if command.get("kind") not in ALLOWED_KINDS:
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Command kind is not allowed for dev servers: {command.get('kind')}")
    argv = [str(part) for part in command.get("argv", [])]
    if not argv:
        return tool_error(FILE_METADATA["tool_name"], arguments, "Profiled command has empty argv")

    state = _load_state(project_root)
    existing = state.get("servers", {}).get(command_id)
    if isinstance(existing, dict) and _is_process_alive(int(existing.get("pid", 0) or 0)):
        return tool_result(FILE_METADATA["tool_name"], arguments, {
            "project_root": str(project_root),
            "command_id": command_id,
            "already_running": True,
            "server": existing,
        })

    working_directory = project_root / str(command.get("working_directory", "."))
    working_directory = working_directory.resolve()
    try:
        working_directory.relative_to(project_root)
    except ValueError:
        return tool_error(FILE_METADATA["tool_name"], arguments, "Profiled working_directory escapes project_root")

    log_path = _logs_dir(project_root) / f"{_safe_id(command_id)}.log"
    log_handle = log_path.open("ab")
    shell = platform.system().lower() == "windows" and Path(argv[0]).suffix.lower() in {".bat", ".cmd"}
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(working_directory),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            shell=shell,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system().lower() == "windows" else 0,
        )
    except (OSError, ValueError) as exc:
        log_handle.close()
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Failed to start command: {exc}")
    log_handle.close()

    entry = {
        "pid": process.pid,
        "alive": True,
        "started_at": _now(),
        "last_checked_at": _now(),
        "command": command,
        "argv": argv,
        "working_directory": str(working_directory),
        "log_path": str(log_path),
        "health_url": arguments.get("health_url", ""),
        "port": arguments.get("port"),
    }
    state.setdefault("servers", {})[command_id] = entry
    _save_state(project_root, state)
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "project_root": str(project_root),
        "command_id": command_id,
        "started": True,
        "server": entry,
    })


def _stop(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    confirm_error = _require_confirm(arguments, "stop")
    if confirm_error:
        return confirm_error
    command_id = str(arguments.get("command_id", ""))
    if not command_id:
        return tool_error(FILE_METADATA["tool_name"], arguments, "stop requires command_id")
    state = _load_state(project_root)
    entry = state.get("servers", {}).get(command_id)
    if not isinstance(entry, dict):
        return tool_error(FILE_METADATA["tool_name"], arguments, f"No registered server for command_id: {command_id}")
    pid = int(entry.get("pid", 0) or 0)
    was_alive = _is_process_alive(pid)
    stop_method = "none"
    if was_alive:
        if platform.system().lower() == "windows":
            completed = subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, check=False)
            stop_method = f"taskkill:{completed.returncode}"
        else:
            os.kill(pid, signal.SIGTERM)
            stop_method = "sigterm"
        deadline = time.time() + float(arguments.get("timeout_seconds", 5))
        while time.time() < deadline and _is_process_alive(pid):
            time.sleep(0.1)
    entry["alive"] = _is_process_alive(pid)
    entry["stopped_at"] = _now()
    entry["last_checked_at"] = _now()
    state["servers"][command_id] = entry
    _save_state(project_root, state)
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "project_root": str(project_root),
        "command_id": command_id,
        "was_alive": was_alive,
        "alive": entry["alive"],
        "stop_method": stop_method,
        "server": entry,
    })


def _tail_action(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    command_id = str(arguments.get("command_id", ""))
    if not command_id:
        return tool_error(FILE_METADATA["tool_name"], arguments, "tail requires command_id")
    state = _load_state(project_root)
    entry = state.get("servers", {}).get(command_id)
    if not isinstance(entry, dict):
        return tool_error(FILE_METADATA["tool_name"], arguments, f"No registered server for command_id: {command_id}")
    log_path = Path(str(entry.get("log_path", "")))
    lines = _tail(log_path, int(arguments.get("tail_lines", 80)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "project_root": str(project_root),
        "command_id": command_id,
        "log_path": str(log_path),
        "line_count": len(lines),
        "lines": lines,
    })


def _health(project_root: Path, arguments: dict[str, Any]) -> dict[str, Any]:
    command_id = str(arguments.get("command_id", ""))
    state = _load_state(project_root)
    entry = state.get("servers", {}).get(command_id) if command_id else None
    url = str(arguments.get("health_url") or (entry or {}).get("health_url") or "")
    if not url and arguments.get("port"):
        url = f"http://127.0.0.1:{int(arguments['port'])}/"
    if not url:
        return tool_error(FILE_METADATA["tool_name"], arguments, "health requires health_url or port")
    check = _health_check(url, float(arguments.get("timeout_seconds", 5)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "project_root": str(project_root),
        "command_id": command_id,
        "health": check,
    }, status="ok" if check["ok"] else "error")


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    action = str(arguments.get("action", "status"))
    if action == "status":
        return _status(project_root, arguments)
    if action == "start":
        return _start(project_root, arguments)
    if action == "stop":
        return _stop(project_root, arguments)
    if action == "restart":
        stop_result = _stop(project_root, {**arguments, "action": "stop"})
        if stop_result.get("status") == "error":
            return stop_result
        return _start(project_root, {**arguments, "action": "start"})
    if action == "tail":
        return _tail_action(project_root, arguments)
    if action == "health":
        return _health(project_root, arguments)
    return tool_error(FILE_METADATA["tool_name"], arguments, f"Unknown action: {action}")


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
