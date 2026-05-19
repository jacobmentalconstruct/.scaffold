"""
FILE: docker_ops.py
ROLE: Guarded Docker operations wrapper for local-agent sys-ops.
WHAT IT DOES:
  - Reports Docker availability/status
  - Builds and smoke-runs images from contexts inside the project root
  - Reads container logs and gates tag/push behind explicit confirmation
HOW TO USE:
  - python src/tools/docker_ops.py metadata
  - python src/tools/docker_ops.py run --input-json '{"action": "status", "project_root": "."}'
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result


FILE_METADATA = {
    "tool_name": "docker_ops",
    "version": "1.0.0",
    "entrypoint": "src/tools/docker_ops.py",
    "category": "operations",
    "summary": "Guarded Docker status/build/run_smoke/logs/tag/push operations scoped to project-root contexts.",
    "mcp_name": "docker_ops",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "build", "run_smoke", "logs", "tag", "push"],
                "default": "status",
            },
            "project_root": {"type": "string", "default": "."},
            "context": {"type": "string", "default": "."},
            "dockerfile": {"type": "string", "default": "Dockerfile"},
            "image": {"type": "string", "default": "devtools-pod:v2"},
            "source_image": {"type": "string"},
            "target_image": {"type": "string"},
            "container": {"type": "string"},
            "tail_lines": {"type": "integer", "default": 120},
            "confirm": {"type": "boolean", "default": False},
            "preview": {"type": "boolean", "default": False},
            "timeout_seconds": {"type": "number", "default": 60},
        },
        "additionalProperties": False,
    },
}


def _run(args: list[str], cwd: Path, timeout: float) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
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
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(exc)}


def _docker_available() -> dict[str, Any]:
    path = shutil.which("docker")
    return {"available": path is not None, "path": path or ""}


def _resolve_under(root: Path, value: str, label: str) -> tuple[Path | None, str]:
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None, f"{label} escapes project_root: {value}"
    return path, ""


def _preview(args: list[str], cwd: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "command": args,
        "working_directory": str(cwd),
        "preview": True,
        "executed": False,
    }
    if extra:
        payload.update(extra)
    return payload


def _status(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    docker = _docker_available()
    result: dict[str, Any] = {"project_root": str(project_root), "docker": docker, "commands": {}}
    if docker["available"]:
        timeout = float(arguments.get("timeout_seconds", 60))
        result["commands"]["version"] = _run(["docker", "--version"], project_root, timeout)
        result["commands"]["info"] = _run(["docker", "info", "--format", "{{json .ServerVersion}}"], project_root, timeout)
    else:
        result["warnings"] = ["docker command was not found on PATH."]
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


def _build(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    context, error = _resolve_under(project_root, str(arguments.get("context", ".")), "context")
    if error:
        return tool_error(FILE_METADATA["tool_name"], arguments, error)
    assert context is not None
    dockerfile = context / str(arguments.get("dockerfile", "Dockerfile"))
    if not dockerfile.exists():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Dockerfile not found: {dockerfile}")
    image = str(arguments.get("image", "devtools-pod:v2"))
    args = ["docker", "build", "-t", image, "-f", str(dockerfile), str(context)]
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root, {
            "context": str(context),
            "dockerfile": str(dockerfile),
            "image": image,
        }))
    if not _docker_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "docker command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 60)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "context": str(context),
        "dockerfile": str(dockerfile),
        "image": image,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def _run_smoke(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    image = str(arguments.get("image", "devtools-pod:v2"))
    args = ["docker", "run", "--rm", image]
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root, {"image": image}))
    if not _docker_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "docker command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 60)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "image": image,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def _logs(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    container = str(arguments.get("container", ""))
    if not container:
        return tool_error(FILE_METADATA["tool_name"], arguments, "logs requires container")
    tail_lines = int(arguments.get("tail_lines", 120))
    args = ["docker", "logs", "--tail", str(tail_lines), container]
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root, {"container": container}))
    if not _docker_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "docker command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 60)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "container": container,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def _require_confirm(arguments: dict[str, Any], action: str) -> dict[str, Any] | None:
    if arguments.get("confirm") is True:
        return None
    return tool_error(FILE_METADATA["tool_name"], arguments, f"{action} requires confirm: true")


def _tag(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    confirm_error = _require_confirm(arguments, "tag")
    if confirm_error:
        return confirm_error
    source = str(arguments.get("source_image") or arguments.get("image") or "")
    target = str(arguments.get("target_image") or "")
    if not source or not target:
        return tool_error(FILE_METADATA["tool_name"], arguments, "tag requires source_image/image and target_image")
    args = ["docker", "tag", source, target]
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root, {"source_image": source, "target_image": target}))
    if not _docker_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "docker command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 60)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "source_image": source,
        "target_image": target,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def _push(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    confirm_error = _require_confirm(arguments, "push")
    if confirm_error:
        return confirm_error
    image = str(arguments.get("target_image") or arguments.get("image") or "")
    if not image:
        return tool_error(FILE_METADATA["tool_name"], arguments, "push requires image or target_image")
    args = ["docker", "push", image]
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root, {"image": image}))
    if not _docker_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "docker command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 60)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "image": image,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    action = str(arguments.get("action", "status"))
    if action == "status":
        return _status(arguments, project_root)
    if action == "build":
        return _build(arguments, project_root)
    if action == "run_smoke":
        return _run_smoke(arguments, project_root)
    if action == "logs":
        return _logs(arguments, project_root)
    if action == "tag":
        return _tag(arguments, project_root)
    if action == "push":
        return _push(arguments, project_root)
    return tool_error(FILE_METADATA["tool_name"], arguments, f"Unknown action: {action}")


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
