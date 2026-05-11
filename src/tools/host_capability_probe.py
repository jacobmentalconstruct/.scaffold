"""
FILE: src/tools/host_capability_probe.py
ROLE: Probe the host environment — Python version, platform, available
      common tools (git, python3, node, etc.).
WHAT IT DOES: Reads sys/platform info and runs `<tool> --version` for a
              small allowlist of common tools. Pure Observe; no mutation.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys


FILE_METADATA = {
    "tool_name": "host_capability_probe",
    "version": "1.0.0",
    "entrypoint": "src/tools/host_capability_probe.py",
    "category": "introspection",
    "summary": "Probe Python version, platform, and common-tool availability.",
    "mcp_name": "host_capability_probe",
    "required_authority": "Observe",
    "input_schema": {"type": "object", "properties": {}},
}


# Allowlist — only --version invocations against these names. shell=False.
_PROBE_TOOLS = (
    "git", "python", "python3", "pip", "pip3", "node", "npm", "go",
    "cargo", "rustc", "docker", "make", "uv",
)


def run(arguments: dict, state) -> dict:
    tools_present: dict[str, dict] = {}
    for name in _PROBE_TOOLS:
        path = shutil.which(name)
        if path is None:
            tools_present[name] = {"present": False}
            continue
        version = _version_of(path)
        tools_present[name] = {"present": True, "path": path, "version": version}

    return {
        "status": "ok",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {
            "python": {
                "version": sys.version,
                "version_info": list(sys.version_info[:5]),
                "executable": sys.executable,
                "implementation": platform.python_implementation(),
            },
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "node": platform.node(),
            },
            "env": {
                "cwd": os.getcwd(),
                "user": os.environ.get("USERNAME") or os.environ.get("USER", ""),
                "shell": os.environ.get("SHELL") or os.environ.get("COMSPEC", ""),
                "path_count": len(os.environ.get("PATH", "").split(os.pathsep)),
            },
            "tools_present": tools_present,
        },
    }


def _version_of(executable_path: str) -> str:
    try:
        cp = subprocess.run(
            [executable_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5.0,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    out = (cp.stdout or "") + (cp.stderr or "")
    return out.strip().splitlines()[0] if out else ""
