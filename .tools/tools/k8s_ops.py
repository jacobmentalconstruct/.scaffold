"""
FILE: k8s_ops.py
ROLE: Guarded Kubernetes operations wrapper for local-agent sys-ops.
WHAT IT DOES:
  - Reports kubectl context/client availability
  - Validates manifest shape without third-party YAML dependencies
  - Runs guarded kubectl dry-run/apply/status/logs workflows when available
HOW TO USE:
  - python src/tools/k8s_ops.py metadata
  - python src/tools/k8s_ops.py run --input-json '{"action": "validate", "project_root": ".", "manifest": "_v2-pod/k8s/deployment.yaml"}'
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result


FILE_METADATA = {
    "tool_name": "k8s_ops",
    "version": "1.0.0",
    "entrypoint": "src/tools/k8s_ops.py",
    "category": "operations",
    "summary": "Guarded Kubernetes context/validate/dry_run/apply/status/logs/attach_instructions operations scoped to project-root manifests.",
    "mcp_name": "k8s_ops",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["context", "validate", "dry_run", "apply", "status", "logs", "attach_instructions"],
                "default": "context",
            },
            "project_root": {"type": "string", "default": "."},
            "manifest": {"type": "string", "default": "k8s"},
            "resource": {"type": "string", "default": "deploy/devtools-pod"},
            "container": {"type": "string"},
            "namespace": {"type": "string"},
            "tail_lines": {"type": "integer", "default": 120},
            "confirm": {"type": "boolean", "default": False},
            "preview": {"type": "boolean", "default": False},
            "timeout_seconds": {"type": "number", "default": 30},
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


def _kubectl_available() -> dict[str, Any]:
    path = shutil.which("kubectl")
    return {"available": path is not None, "path": path or ""}


def _resolve_under(root: Path, value: str, label: str) -> tuple[Path | None, str]:
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None, f"{label} escapes project_root: {value}"
    return path, ""


def _namespace_args(arguments: dict[str, Any]) -> list[str]:
    namespace = str(arguments.get("namespace") or "")
    return ["--namespace", namespace] if namespace else []


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


def _manifest_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(item for item in path.rglob("*") if item.suffix.lower() in {".yaml", ".yml"})
    return []


def _strip_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _parse_manifest_summary(path: Path) -> list[dict[str, Any]]:
    summaries = []
    for index, doc in enumerate(re.split(r"(?m)^---\s*$", _strip_comments(path.read_text(encoding="utf-8", errors="replace"))), start=1):
        if not doc.strip():
            continue
        api = re.search(r"(?m)^apiVersion:\s*([^\s#]+)", doc)
        kind = re.search(r"(?m)^kind:\s*([^\s#]+)", doc)
        name = re.search(r"(?m)^\s{2}name:\s*([^\s#]+)", doc)
        image = re.search(r"(?m)^\s*image:\s*([^\s#]+)", doc)
        replicas = re.search(r"(?m)^\s*replicas:\s*(\d+)", doc)
        summaries.append({
            "file": str(path),
            "document": index,
            "apiVersion": api.group(1) if api else "",
            "kind": kind.group(1) if kind else "",
            "name": name.group(1) if name else "",
            "image": image.group(1) if image else "",
            "replicas": int(replicas.group(1)) if replicas else None,
            "valid_basic_shape": bool(api and kind and name),
        })
    return summaries


def _context(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    kubectl = _kubectl_available()
    result: dict[str, Any] = {"project_root": str(project_root), "kubectl": kubectl, "commands": {}}
    if kubectl["available"]:
        timeout = float(arguments.get("timeout_seconds", 30))
        result["commands"]["version"] = _run(["kubectl", "version", "--client=true"], project_root, timeout)
        result["commands"]["current_context"] = _run(["kubectl", "config", "current-context"], project_root, timeout)
    else:
        result["warnings"] = ["kubectl command was not found on PATH."]
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


def _validate(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    manifest, error = _resolve_under(project_root, str(arguments.get("manifest", "k8s")), "manifest")
    if error:
        return tool_error(FILE_METADATA["tool_name"], arguments, error)
    assert manifest is not None
    files = _manifest_files(manifest)
    if not files:
        return tool_error(FILE_METADATA["tool_name"], arguments, f"No manifest files found at {manifest}")
    summaries = []
    errors = []
    for path in files:
        try:
            parsed = _parse_manifest_summary(path)
            summaries.extend(parsed)
            errors.extend(f"{path}: missing apiVersion/kind/metadata.name" for item in parsed if not item["valid_basic_shape"])
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    result = {
        "project_root": str(project_root),
        "manifest": str(manifest),
        "file_count": len(files),
        "resources": summaries,
        "valid": not errors and bool(summaries),
        "errors": errors,
        "warnings": ["Validation is a stdlib structural check; use dry_run for kubectl client validation."],
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result, status="ok" if result["valid"] else "error")


def _kubectl_apply_args(arguments: dict[str, Any], project_root: Path, apply: bool) -> tuple[list[str] | None, dict[str, Any] | None]:
    manifest, error = _resolve_under(project_root, str(arguments.get("manifest", "k8s")), "manifest")
    if error:
        return None, tool_error(FILE_METADATA["tool_name"], arguments, error)
    assert manifest is not None
    if not _manifest_files(manifest):
        return None, tool_error(FILE_METADATA["tool_name"], arguments, f"No manifest files found at {manifest}")
    args = ["kubectl", "apply"]
    if not apply:
        args.extend(["--dry-run=client", "--validate=false"])
    args.extend(_namespace_args(arguments))
    args.extend(["-f", str(manifest)])
    return args, None


def _dry_run(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    args, error = _kubectl_apply_args(arguments, project_root, apply=False)
    if error:
        return error
    assert args is not None
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root))
    if not _kubectl_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "kubectl command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 30)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def _apply(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    if arguments.get("confirm") is not True:
        return tool_error(FILE_METADATA["tool_name"], arguments, "apply requires confirm: true")
    args, error = _kubectl_apply_args(arguments, project_root, apply=True)
    if error:
        return error
    assert args is not None
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root))
    if not _kubectl_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "kubectl command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 30)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def _status(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    resource = str(arguments.get("resource", "deploy/devtools-pod"))
    args = ["kubectl", "get", resource, * _namespace_args(arguments), "-o", "wide"]
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root, {"resource": resource}))
    if not _kubectl_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "kubectl command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 30)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "resource": resource,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def _logs(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    resource = str(arguments.get("resource", "deploy/devtools-pod"))
    args = ["kubectl", "logs", resource, * _namespace_args(arguments), "--tail", str(int(arguments.get("tail_lines", 120)))]
    container = str(arguments.get("container") or "")
    if container:
        args.extend(["-c", container])
    if arguments.get("preview"):
        return tool_result(FILE_METADATA["tool_name"], arguments, _preview(args, project_root, {"resource": resource}))
    if not _kubectl_available()["available"]:
        return tool_error(FILE_METADATA["tool_name"], arguments, "kubectl command was not found on PATH")
    run = _run(args, project_root, float(arguments.get("timeout_seconds", 30)))
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "command": args,
        "resource": resource,
        "executed": True,
        "run": run,
    }, status="ok" if run["ok"] else "error")


def _attach_instructions(arguments: dict[str, Any], project_root: Path) -> dict[str, Any]:
    resource = str(arguments.get("resource", "deploy/devtools-pod"))
    namespace = _namespace_args(arguments)
    command = ["kubectl", "attach", "-ti", resource, *namespace]
    return tool_result(FILE_METADATA["tool_name"], arguments, {
        "project_root": str(project_root),
        "resource": resource,
        "command": command,
        "notes": [
            "MCP transport is stdio; attach an interactive client to the pod when a cluster is available.",
            "Use status/logs first to confirm readiness before attaching.",
        ],
    })


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    action = str(arguments.get("action", "context"))
    if action == "context":
        return _context(arguments, project_root)
    if action == "validate":
        return _validate(arguments, project_root)
    if action == "dry_run":
        return _dry_run(arguments, project_root)
    if action == "apply":
        return _apply(arguments, project_root)
    if action == "status":
        return _status(arguments, project_root)
    if action == "logs":
        return _logs(arguments, project_root)
    if action == "attach_instructions":
        return _attach_instructions(arguments, project_root)
    return tool_error(FILE_METADATA["tool_name"], arguments, f"Unknown action: {action}")


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
