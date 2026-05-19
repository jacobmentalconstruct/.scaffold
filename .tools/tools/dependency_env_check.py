"""
FILE: dependency_env_check.py
ROLE: Read-only dependency and environment readiness checker.
WHAT IT DOES:
  - Inspects Python and Node dependency surfaces without installing anything
  - Reports virtualenv, lockfiles, requirements, package manifests, and tool availability
  - Produces readiness warnings for later guarded operations
HOW TO USE:
  - python src/tools/dependency_env_check.py metadata
  - python src/tools/dependency_env_check.py run --input-json '{"project_root": "."}'
"""

from __future__ import annotations

import json
import shutil
import subprocess
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
    "tool_name": "dependency_env_check",
    "version": "1.0.0",
    "entrypoint": "src/tools/dependency_env_check.py",
    "category": "introspection",
    "summary": "Read-only dependency readiness check for Python and Node projects without installing or modifying anything.",
    "mcp_name": "dependency_env_check",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "check_imports": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional Python module names to import-check in a subprocess.",
            },
            "timeout_seconds": {"type": "number", "default": 5},
        },
        "additionalProperties": False,
    },
}


PYTHON_LOCKFILES = ["requirements.txt", "requirements-dev.txt", "pyproject.toml", "poetry.lock", "Pipfile.lock", "uv.lock"]
NODE_LOCKFILES = ["package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml"]


def _read_requirements(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "entries": [], "entry_count": 0}
    entries = []
    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            entries.append(line)
    except OSError as exc:
        return {"exists": True, "path": str(path), "entries": [], "entry_count": 0, "error": str(exc)}
    return {"exists": True, "path": str(path), "entries": entries[:50], "entry_count": len(entries)}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _pyproject_summary(path: Path) -> dict[str, Any]:
    if not path.exists() or tomllib is None:
        return {"exists": path.exists(), "dependency_count": 0, "optional_dependency_groups": []}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {"exists": True, "dependency_count": 0, "optional_dependency_groups": [], "error": str(exc)}
    project = data.get("project", {})
    deps = project.get("dependencies", [])
    optional = project.get("optional-dependencies", {})
    return {
        "exists": True,
        "dependency_count": len(deps) if isinstance(deps, list) else 0,
        "optional_dependency_groups": sorted(optional.keys()) if isinstance(optional, dict) else [],
        "build_system": bool(data.get("build-system")),
    }


def _command_version(command: str, args: list[str], timeout: float) -> dict[str, Any]:
    path = shutil.which(command)
    result: dict[str, Any] = {"available": path is not None, "path": path or ""}
    if not path:
        return result
    try:
        completed = subprocess.run(
            [path, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip()
        result.update({
            "returncode": completed.returncode,
            "version_text": output.splitlines()[0][:300] if output else "",
        })
    except (OSError, subprocess.TimeoutExpired) as exc:
        result.update({"returncode": -1, "error": str(exc)})
    return result


def _import_check(modules: list[str], timeout: float) -> list[dict[str, Any]]:
    results = []
    for module in modules:
        code = f"import {module}; print('ok')"
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
            results.append({
                "module": module,
                "available": completed.returncode == 0,
                "error": "" if completed.returncode == 0 else (completed.stderr or completed.stdout).strip()[:300],
            })
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({"module": module, "available": False, "error": str(exc)})
    return results


def _node_summary(root: Path, timeout: float) -> dict[str, Any]:
    package_json = root / "package.json"
    data = _load_json(package_json)
    deps = data.get("dependencies", {}) if isinstance(data, dict) else {}
    dev_deps = data.get("devDependencies", {}) if isinstance(data, dict) else {}
    scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
    lockfiles = [{"name": name, "exists": (root / name).exists()} for name in NODE_LOCKFILES]
    return {
        "package_json": {
            "exists": package_json.exists(),
            "dependency_count": len(deps) if isinstance(deps, dict) else 0,
            "dev_dependency_count": len(dev_deps) if isinstance(dev_deps, dict) else 0,
            "script_count": len(scripts) if isinstance(scripts, dict) else 0,
        },
        "node_modules_exists": (root / "node_modules").is_dir(),
        "lockfiles": lockfiles,
        "tools": {
            "node": _command_version("node", ["--version"], timeout),
            "npm": _command_version("npm", ["--version"], timeout),
        },
    }


def _python_summary(root: Path, timeout: float, check_imports: list[str]) -> dict[str, Any]:
    venv_dirs = []
    for name in [".venv", "venv"]:
        path = root / name
        venv_dirs.append({"path": name, "exists": path.is_dir()})
    requirements = [_read_requirements(root / name) for name in ["requirements.txt", "requirements-dev.txt"]]
    lockfiles = [{"name": name, "exists": (root / name).exists()} for name in PYTHON_LOCKFILES]
    return {
        "current_python": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
            "prefix": sys.prefix,
            "base_prefix": getattr(sys, "base_prefix", sys.prefix),
            "inside_virtualenv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        },
        "venv_dirs": venv_dirs,
        "requirements": requirements,
        "pyproject": _pyproject_summary(root / "pyproject.toml"),
        "lockfiles": lockfiles,
        "tools": {
            "python": _command_version("python", ["--version"], timeout),
            "pip": _command_version("pip", ["--version"], timeout),
        },
        "import_checks": _import_check(check_imports, timeout) if check_imports else [],
    }


def _warnings(python_info: dict[str, Any], node_info: dict[str, Any]) -> list[str]:
    warnings = []
    has_python_deps = any(item["exists"] and item["entry_count"] > 0 for item in python_info["requirements"])
    has_python_deps = has_python_deps or python_info["pyproject"].get("dependency_count", 0) > 0
    has_venv = any(item["exists"] for item in python_info["venv_dirs"])
    if has_python_deps and not has_venv and not python_info["current_python"]["inside_virtualenv"]:
        warnings.append("Python dependencies are declared but no project virtualenv was detected.")
    if node_info["package_json"]["exists"] and not node_info["node_modules_exists"]:
        warnings.append("package.json exists but node_modules is absent.")
    if node_info["package_json"]["exists"] and not node_info["tools"]["npm"]["available"]:
        warnings.append("package.json exists but npm is not available on PATH.")
    return warnings


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")
    timeout = float(arguments.get("timeout_seconds", 5))
    check_imports = [str(item) for item in arguments.get("check_imports", [])]

    python_info = _python_summary(project_root, timeout, check_imports)
    node_info = _node_summary(project_root, timeout)
    warnings = _warnings(python_info, node_info)
    result = {
        "project_root": str(project_root),
        "python": python_info,
        "node": node_info,
        "summary": {
            "python_dependency_surface": any(item["exists"] for item in python_info["lockfiles"]),
            "node_dependency_surface": node_info["package_json"]["exists"],
            "warning_count": len(warnings),
            "ready_for_install_free_checks": True,
        },
        "warnings": warnings,
    }
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
