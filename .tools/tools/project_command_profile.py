"""
FILE: project_command_profile.py
ROLE: Read-only command profile detector for local-agent operations.
WHAT IT DOES:
  - Detects declared setup/test/run/build/dev commands from common project files
  - Emits stable command IDs for later guarded workflow tools
  - Adds working-directory, runtime, requirement, and confirmation metadata
  - Avoids executing commands; this is declaration discovery only
HOW TO USE:
  - python src/tools/project_command_profile.py metadata
  - python src/tools/project_command_profile.py run --input-json '{"project_root": "."}'
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # pragma: no cover - Python <3.11 fallback
    tomllib = None

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result


FILE_METADATA = {
    "tool_name": "project_command_profile",
    "version": "1.0.0",
    "entrypoint": "src/tools/project_command_profile.py",
    "category": "introspection",
    "summary": "Read-only detection of declared setup, test, run, build, dev, Docker, and Kubernetes commands with stable command IDs.",
    "mcp_name": "project_command_profile",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "include_inferred": {"type": "boolean", "default": True},
        },
        "additionalProperties": False,
    },
}


SCRIPT_KIND_HINTS = {
    "dev": "dev",
    "start": "run",
    "serve": "dev",
    "test": "test",
    "build": "build",
    "lint": "check",
    "format": "check",
}


def _command(
    command_id: str,
    kind: str,
    label: str,
    argv: list[str],
    source: str,
    declared: bool = True,
    *,
    runtime: str = "",
    working_directory: str = ".",
    requires: list[str] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    mutates = kind in {"setup", "build", "dev", "run", "docker", "kubernetes"}
    return {
        "id": command_id,
        "profile_version": "2.0",
        "kind": kind,
        "label": label,
        "argv": argv,
        "command_line": " ".join(argv),
        "source": source,
        "working_directory": working_directory,
        "declared": declared,
        "mutates": mutates,
        "confirmation_required": mutates,
        "runtime": runtime or _runtime_from_argv(argv),
        "requires": requires or _requirements_for_kind(kind, argv),
        "tags": tags or [],
    }


def _runtime_from_argv(argv: list[str]) -> str:
    if not argv:
        return "unknown"
    first = Path(argv[0]).name.lower()
    if first in {"npm", "npx", "node"}:
        return "node"
    if first in {"python", "python.exe", "py"} or "python" in first:
        return "python"
    if first in {"docker", "docker.exe"}:
        return "docker"
    if first in {"kubectl", "kubectl.exe"}:
        return "kubernetes"
    if first.endswith(".bat") or first in {"cmd", "cmd.exe"}:
        return "windows-shell"
    if first.endswith(".sh") or first in {"bash", "sh"}:
        return "posix-shell"
    return "shell"


def _requirements_for_kind(kind: str, argv: list[str]) -> list[str]:
    runtime = _runtime_from_argv(argv)
    requirements = []
    if runtime == "python":
        requirements.append("python")
    elif runtime == "node":
        requirements.extend(["node", "npm"])
    elif runtime == "docker":
        requirements.append("docker")
    elif runtime == "kubernetes":
        requirements.append("kubectl")
    elif runtime == "windows-shell":
        requirements.append("cmd")
    elif runtime == "posix-shell":
        requirements.append("sh")
    if kind == "setup":
        requirements.append("write_project")
    return requirements


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _package_json_commands(root: Path) -> list[dict[str, Any]]:
    path = root / "package.json"
    data = _load_json(path)
    scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
    commands = []
    if isinstance(scripts, dict):
        for name in sorted(scripts):
            kind = SCRIPT_KIND_HINTS.get(name, "script")
            commands.append(_command(
                f"npm:{name}",
                kind,
                f"npm script {name}",
                ["npm", "run", name],
                "package.json",
                runtime="node",
                requires=["node", "npm", "package.json"],
                tags=["npm-script", name],
            ))
    return commands


def _pyproject_commands(root: Path) -> list[dict[str, Any]]:
    path = root / "pyproject.toml"
    if not path.exists() or tomllib is None:
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return []
    commands = []
    project_scripts = data.get("project", {}).get("scripts", {})
    if isinstance(project_scripts, dict):
        for name in sorted(project_scripts):
            commands.append(_command(
                f"python-script:{name}",
                "run",
                f"Python project script {name}",
                [name],
                "pyproject.toml",
                runtime="python",
                requires=["python", "pyproject.toml"],
                tags=["python-script", name],
            ))
    tool_pytest = data.get("tool", {}).get("pytest")
    if tool_pytest is not None:
        commands.append(_command(
            "python:test:pytest", "test", "pytest",
            [sys.executable, "-m", "pytest"], "pyproject.toml",
            runtime="python", requires=["python", "pytest"], tags=["pytest"],
        ))
    return commands


def _file_commands(root: Path, include_inferred: bool) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for name in ["setup_env.bat", "setup_env.sh"]:
        if (root / name).exists():
            commands.append(_command(f"file:{name}", "setup", name, [str(root / name)], name, tags=["entrypoint", "setup"]))
    for name in ["run.bat", "run.sh"]:
        if (root / name).exists():
            commands.append(_command(f"file:{name}", "run", name, [str(root / name)], name, tags=["entrypoint", "run"]))
    if (root / "src" / "smoke_test.py").exists():
        commands.append(_command(
            "python:smoke", "test", "toolbox smoke test",
            [sys.executable, "src/smoke_test.py"], "src/smoke_test.py",
            runtime="python", requires=["python"], tags=["smoke-test"],
        ))
    if include_inferred and (root / "dev_server.py").exists():
        commands.append(_command(
            "python:dev-server", "dev", "Python dev server",
            [sys.executable, "dev_server.py"], "dev_server.py",
            declared=False, runtime="python", requires=["python"],
            tags=["inferred", "dev-server"],
        ))
    if include_inferred and (root / "requirements.txt").exists():
        commands.append(_command(
            "python:install-requirements", "setup", "install requirements",
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            "requirements.txt", declared=False, runtime="python",
            requires=["python", "pip", "requirements.txt", "write_project"],
            tags=["inferred", "dependency-install"],
        ))
    if (root / "Dockerfile").exists():
        commands.append(_command(
            "docker:build", "docker", "docker build project image",
            ["docker", "build", "-t", f"{root.name}:local", "."], "Dockerfile",
            runtime="docker", requires=["docker", "Dockerfile"], tags=["container"],
        ))
    if (root / "docker-compose.yml").exists() or (root / "compose.yml").exists():
        commands.append(_command(
            "docker:compose-up", "docker", "docker compose up",
            ["docker", "compose", "up"], "compose file",
            runtime="docker", requires=["docker", "compose-file"], tags=["container", "compose"],
        ))
    k8s_dir = root / "k8s"
    if k8s_dir.is_dir() and any(p.suffix.lower() in {".yaml", ".yml"} for p in k8s_dir.rglob("*")):
        commands.append(_command(
            "k8s:validate", "kubernetes", "validate Kubernetes manifests",
            ["kubectl", "apply", "--dry-run=client", "-f", "k8s"], "k8s/",
            runtime="kubernetes", requires=["kubectl", "k8s"], tags=["kubernetes", "dry-run"],
        ))
    return commands


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    include_inferred = bool(arguments.get("include_inferred", True))

    commands = []
    commands.extend(_package_json_commands(project_root))
    commands.extend(_pyproject_commands(project_root))
    commands.extend(_file_commands(project_root, include_inferred))

    by_kind: dict[str, int] = {}
    for command in commands:
        by_kind[command["kind"]] = by_kind.get(command["kind"], 0) + 1

    result = {
        "project_root": str(project_root),
        "profile_version": "2.0",
        "command_count": len(commands),
        "commands": commands,
        "by_kind": by_kind,
        "warnings": [] if commands else ["No declared project commands detected."],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
