"""
FILE: host_capability_probe.py
ROLE: Read-only host capability probe for local-agent operations.
WHAT IT DOES:
  - Reports OS, Python, shell, and common developer/runtime command availability
  - Captures lightweight version output with short timeouts
  - Avoids mutation; this is an orientation tool only
HOW TO USE:
  - python src/tools/host_capability_probe.py metadata
  - python src/tools/host_capability_probe.py run --input-json "{}"
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_result


FILE_METADATA = {
    "tool_name": "host_capability_probe",
    "version": "1.0.0",
    "entrypoint": "src/tools/host_capability_probe.py",
    "category": "introspection",
    "summary": "Read-only probe of local host capabilities: OS, shell, Python, Git, Docker, kubectl, Node/npm, rg, and browser commands.",
    "mcp_name": "host_capability_probe",
    "input_schema": {
        "type": "object",
        "properties": {
            "commands": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional command names to probe instead of the default set.",
            },
            "timeout_seconds": {
                "type": "number",
                "default": 3,
                "description": "Timeout for each version command.",
            },
        },
        "additionalProperties": False,
    },
}


DEFAULT_COMMANDS = [
    "git", "docker", "kubectl", "node", "npm", "python", "py", "rg",
    "powershell", "pwsh", "cmd", "bash", "sh", "chrome", "msedge",
    "firefox",
]

VERSION_ARGS = {
    "git": ["--version"],
    "docker": ["--version"],
    "kubectl": ["version", "--client=true"],
    "node": ["--version"],
    "npm": ["--version"],
    "python": ["--version"],
    "py": ["--version"],
    "rg": ["--version"],
    "powershell": ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
    "pwsh": ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
    "cmd": ["/c", "ver"],
    "bash": ["--version"],
    "sh": ["--version"],
    "chrome": ["--version"],
    "msedge": ["--version"],
    "firefox": ["--version"],
}


def _run_version(command: str, executable: str, timeout: float) -> dict[str, Any]:
    args = VERSION_ARGS.get(command, ["--version"])
    try:
        completed = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip()
        return {
            "returncode": completed.returncode,
            "version_text": output.splitlines()[0][:300] if output else "",
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "error": f"timed out after {timeout}s"}
    except OSError as exc:
        return {"returncode": -1, "error": str(exc)}


def _probe_command(command: str, timeout: float) -> dict[str, Any]:
    executable = shutil.which(command)
    result: dict[str, Any] = {
        "name": command,
        "available": executable is not None,
        "path": executable or "",
    }
    if executable:
        result.update(_run_version(command, executable, timeout))
    return result


def run(arguments: dict) -> dict:
    commands = arguments.get("commands") or DEFAULT_COMMANDS
    timeout = float(arguments.get("timeout_seconds", 3))

    command_results = [_probe_command(str(command), timeout) for command in commands]
    available = [item["name"] for item in command_results if item["available"]]
    missing = [item["name"] for item in command_results if not item["available"]]

    result = {
        "host": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "cwd": os.getcwd(),
            "home": str(Path.home()),
        },
        "shell": {
            "SHELL": os.environ.get("SHELL", ""),
            "COMSPEC": os.environ.get("COMSPEC", ""),
            "PSModulePath_present": bool(os.environ.get("PSModulePath")),
        },
        "commands": command_results,
        "summary": {
            "available": available,
            "missing": missing,
            "available_count": len(available),
            "missing_count": len(missing),
        },
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
