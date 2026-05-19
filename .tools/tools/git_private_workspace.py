"""Private Git workspace operations for local-agent checkpoints."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import standard_main, tool_error, tool_result
from lib.text_workspace import (
    resolve_project_path,
    resolve_project_root,
    runtime_root,
    safe_relative,
)


FILE_METADATA = {
    "name": "git_private_workspace",
    "tool_name": "git_private_workspace",
    "version": "1.0.0",
    "entrypoint": "src/tools/git_private_workspace.py",
    "category": "version-control",
    "summary": (
        "Manage a private Git history for a chosen project root using an ignored sidecar "
        "gitdir. Supports guarded status/init/add/commit/branch/checkout/pull/push."
    ),
    "mcp_name": "git_private_workspace",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "init", "add", "commit", "branch", "checkout", "pull", "push"],
                "default": "status",
            },
            "project_root": {"type": "string", "description": "Project root to operate on."},
            "confirm": {"type": "boolean", "default": False},
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Pathspecs under project_root for add operations.",
            },
            "allow_all": {
                "type": "boolean",
                "default": False,
                "description": "Allow paths=['.'] for broad add operations.",
            },
            "allow_toolbox": {
                "type": "boolean",
                "default": False,
                "description": "Allow non-runtime .dev-tools paths to be staged.",
            },
            "message": {"type": "string", "description": "Commit message."},
            "branch": {"type": "string", "description": "Branch name for branch/checkout/push/pull."},
            "create": {"type": "boolean", "default": False},
            "remote_name": {"type": "string", "default": "agent"},
            "remote_url": {
                "type": "string",
                "description": "Explicit private remote URL/path for push/pull or init configuration.",
            },
            "allow_origin": {
                "type": "boolean",
                "default": False,
                "description": "Permit using remote_name=origin. Disabled by default.",
            },
            "timeout_seconds": {"type": "number", "default": 30},
        },
        "additionalProperties": False,
    },
}


MUTATING_ACTIONS = {"init", "add", "commit", "checkout", "pull", "push"}
RISKY_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    "credentials.json",
    "secrets.json",
}
RISKY_SUFFIXES = (".pem", ".key", ".pfx", ".p12")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _timeout(arguments: dict[str, Any]) -> int:
    try:
        value = int(arguments.get("timeout_seconds", 30))
    except (TypeError, ValueError):
        return 30
    return max(1, min(value, 120))


def _workspace_paths(project_root: Path) -> dict[str, Path]:
    base = runtime_root(project_root) / "private_git"
    return {
        "base": base,
        "gitdir": base / "repo.git",
        "state": base / "state.json",
        "exclude": base / "exclude",
    }


def _initialized(gitdir: Path) -> bool:
    return (gitdir / "HEAD").exists() and (gitdir / "objects").exists()


def _git_available() -> tuple[bool, str | None]:
    executable = shutil.which("git")
    if executable is None:
        return False, None
    return True, executable


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
    check: bool = False,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": exc.stdout or "",
            "stderr": f"command timed out after {timeout}s",
            "command": command,
        }
    except OSError as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc), "command": command}

    ok = completed.returncode == 0
    if check and not ok:
        ok = False
    return {
        "ok": ok,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": command,
    }


def _git_command(gitdir: Path, worktree: Path, args: list[str]) -> list[str]:
    return ["git", "--git-dir", str(gitdir), "--work-tree", str(worktree), *args]


def _run_git(
    gitdir: Path,
    worktree: Path,
    args: list[str],
    *,
    timeout: int = 30,
) -> dict[str, Any]:
    return _run(_git_command(gitdir, worktree, args), cwd=worktree, timeout=timeout)


def _write_exclude_file(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                ".git/",
                ".dev-tools/runtime/",
                "runtime/private_git/",
                "__pycache__/",
                ".pytest_cache/",
                ".mypy_cache/",
                ".ruff_cache/",
                ".venv/",
                "venv/",
                "node_modules/",
                ".env",
                ".env.*",
                "*.key",
                "*.pem",
                "*.pfx",
                "*.p12",
                "credentials.json",
                "secrets.json",
                "*.log",
                "_logs/",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_branch(branch: str) -> str | None:
    if not branch:
        return "branch is required"
    if not BRANCH_RE.match(branch):
        return "branch may contain only letters, numbers, slash, dash, underscore, and dot"
    if branch.startswith("/") or branch.endswith("/") or ".." in branch or branch.endswith(".lock"):
        return "branch name is unsafe"
    return None


def _validate_remote(remote_name: str, allow_origin: bool) -> str | None:
    if not remote_name:
        return "remote_name is required"
    if not BRANCH_RE.match(remote_name) or "/" in remote_name or ".." in remote_name:
        return "remote_name is unsafe"
    if remote_name == "origin" and not allow_origin:
        return "remote_name=origin is blocked unless allow_origin is true"
    return None


def _is_risky_rel(rel: str) -> bool:
    parts = [part.lower() for part in Path(rel).parts]
    name = parts[-1] if parts else rel.lower()
    if rel == ".":
        return False
    if parts and parts[0] == ".git":
        return True
    if len(parts) >= 3 and parts[0] == ".dev-tools" and parts[1] == "runtime":
        return True
    if name in RISKY_NAMES or name.endswith(RISKY_SUFFIXES):
        return True
    return False


def _normalize_pathspecs(
    project_root: Path,
    paths: Any,
    *,
    allow_all: bool,
    allow_toolbox: bool,
) -> tuple[list[str] | None, str | None]:
    if not isinstance(paths, list) or not paths:
        return None, "paths must be a non-empty array for add"

    pathspecs: list[str] = []
    for raw in paths:
        if not isinstance(raw, str):
            return None, "paths entries must be strings"
        value = raw.strip()
        if value in {"", "."}:
            if not allow_all:
                return None, "paths=['.'] requires allow_all=true"
            pathspecs.append(".")
            continue

        resolved, error = resolve_project_path(
            project_root,
            value,
            allow_toolbox=allow_toolbox,
            label="path",
        )
        if error:
            return None, error
        assert resolved is not None
        rel = safe_relative(resolved, project_root)
        if _is_risky_rel(rel):
            return None, f"path is blocked by private Git safety policy: {rel}"
        pathspecs.append(rel)

    return pathspecs, None


def _current_branch(gitdir: Path, project_root: Path, timeout: int) -> str | None:
    result = _run_git(gitdir, project_root, ["symbolic-ref", "--quiet", "--short", "HEAD"], timeout=timeout)
    if result["ok"] and result["stdout"]:
        return str(result["stdout"]).strip()
    result = _run_git(gitdir, project_root, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=timeout)
    if result["ok"] and result["stdout"]:
        return str(result["stdout"]).strip()
    return None


def _remote_lines(gitdir: Path, project_root: Path, timeout: int) -> list[str]:
    result = _run_git(gitdir, project_root, ["remote", "-v"], timeout=timeout)
    if not result["ok"] or not result["stdout"]:
        return []
    return [line for line in str(result["stdout"]).splitlines() if line.strip()]


def _configure_remote(
    paths: dict[str, Path],
    project_root: Path,
    *,
    remote_name: str,
    remote_url: str | None,
    allow_origin: bool,
    timeout: int,
) -> tuple[bool, str | None]:
    error = _validate_remote(remote_name, allow_origin)
    if error:
        return False, error

    state = _read_state(paths["state"])
    if remote_url:
        _run_git(paths["gitdir"], project_root, ["remote", "remove", remote_name], timeout=timeout)
        added = _run_git(paths["gitdir"], project_root, ["remote", "add", remote_name, remote_url], timeout=timeout)
        if not added["ok"]:
            return False, added["stderr"] or added["stdout"] or "failed to configure private remote"
        state["remote_name"] = remote_name
        state["remote_url"] = remote_url
        _write_state(paths["state"], state)
        return True, None

    remotes = _remote_lines(paths["gitdir"], project_root, timeout)
    if not any(line.startswith(f"{remote_name}\t") for line in remotes):
        return False, "remote_url is required before using this private remote"
    return True, None


def _public_paths(paths: dict[str, Path], project_root: Path) -> dict[str, str]:
    return {
        "runtime_root": safe_relative(paths["base"], project_root),
        "gitdir": safe_relative(paths["gitdir"], project_root),
        "exclude": safe_relative(paths["exclude"], project_root),
        "state": safe_relative(paths["state"], project_root),
    }


def _status(project_root: Path, paths: dict[str, Path], timeout: int) -> dict[str, Any]:
    ok, executable = _git_available()
    result: dict[str, Any] = {
        "project_root": str(project_root),
        "git_available": ok,
        "git_executable": executable,
        "initialized": _initialized(paths["gitdir"]),
        "private_paths": _public_paths(paths, project_root),
        "project_git_exists": (project_root / ".git").exists(),
    }
    if not ok or not result["initialized"]:
        return result

    branch = _current_branch(paths["gitdir"], project_root, timeout)
    status = _run_git(paths["gitdir"], project_root, ["status", "--porcelain=v1", "-b"], timeout=timeout)
    branches = _run_git(paths["gitdir"], project_root, ["branch", "--list"], timeout=timeout)
    result.update(
        {
            "branch": branch,
            "status_ok": status["ok"],
            "porcelain": str(status["stdout"]).splitlines() if status["stdout"] else [],
            "status_error": status["stderr"] if not status["ok"] else "",
            "branches": str(branches["stdout"]).splitlines() if branches["stdout"] else [],
            "remotes": _remote_lines(paths["gitdir"], project_root, timeout),
            "state": _read_state(paths["state"]),
        }
    )
    return result


def run(arguments: dict[str, Any]) -> dict[str, Any]:
    action = str(arguments.get("action", "status")).strip().lower()
    if action not in FILE_METADATA["input_schema"]["properties"]["action"]["enum"]:
        return tool_error(FILE_METADATA["name"], arguments, f"unsupported action: {action}")

    try:
        project_root = resolve_project_root(arguments.get("project_root"))
    except Exception as exc:
        return tool_error(FILE_METADATA["name"], arguments, str(exc))

    timeout = _timeout(arguments)
    paths = _workspace_paths(project_root)

    if action in MUTATING_ACTIONS and arguments.get("confirm") is not True:
        return tool_error(FILE_METADATA["name"], arguments, f"{action} requires confirm=true")

    git_ok, _ = _git_available()
    if not git_ok:
        result = _status(project_root, paths, timeout)
        return tool_result(FILE_METADATA["name"], arguments, result, status="error")

    if action == "status":
        return tool_result(FILE_METADATA["name"], arguments, _status(project_root, paths, timeout))

    if action == "init":
        paths["base"].mkdir(parents=True, exist_ok=True)
        _write_exclude_file(paths["exclude"])
        if not _initialized(paths["gitdir"]):
            initialized = _run(["git", "init", "--bare", str(paths["gitdir"])], timeout=timeout)
            if not initialized["ok"]:
                return tool_result(FILE_METADATA["name"], arguments, initialized, status="error")
        config_runs = [
            _run_git(paths["gitdir"], project_root, ["config", "core.bare", "false"], timeout=timeout),
            _run_git(paths["gitdir"], project_root, ["config", "core.worktree", str(project_root)], timeout=timeout),
            _run_git(paths["gitdir"], project_root, ["config", "core.excludesFile", str(paths["exclude"])], timeout=timeout),
            _run_git(paths["gitdir"], project_root, ["config", "user.name", "dev-tools-agent"], timeout=timeout),
            _run_git(
                paths["gitdir"],
                project_root,
                ["config", "user.email", "dev-tools-agent@example.invalid"],
                timeout=timeout,
            ),
        ]
        failed = next((item for item in config_runs if not item["ok"]), None)
        if failed:
            return tool_result(FILE_METADATA["name"], arguments, failed, status="error")
        if arguments.get("remote_url"):
            ok, error = _configure_remote(
                paths,
                project_root,
                remote_name=str(arguments.get("remote_name", "agent")),
                remote_url=str(arguments["remote_url"]),
                allow_origin=arguments.get("allow_origin") is True,
                timeout=timeout,
            )
            if not ok:
                return tool_error(FILE_METADATA["name"], arguments, error or "failed to configure remote")
        return tool_result(FILE_METADATA["name"], arguments, _status(project_root, paths, timeout))

    if not _initialized(paths["gitdir"]):
        return tool_error(FILE_METADATA["name"], arguments, "private Git workspace is not initialized")

    if action == "add":
        pathspecs, error = _normalize_pathspecs(
            project_root,
            arguments.get("paths"),
            allow_all=arguments.get("allow_all") is True,
            allow_toolbox=arguments.get("allow_toolbox") is True,
        )
        if error:
            return tool_error(FILE_METADATA["name"], arguments, error)
        assert pathspecs is not None
        added = _run_git(paths["gitdir"], project_root, ["add", "--", *pathspecs], timeout=timeout)
        return tool_result(
            FILE_METADATA["name"],
            arguments,
            {"pathspecs": pathspecs, "git": added, "status": _status(project_root, paths, timeout)},
            status="ok" if added["ok"] else "error",
        )

    if action == "commit":
        message = str(arguments.get("message", "")).strip()
        if not message:
            return tool_error(FILE_METADATA["name"], arguments, "commit message is required")
        committed = _run_git(paths["gitdir"], project_root, ["commit", "-m", message], timeout=timeout)
        return tool_result(
            FILE_METADATA["name"],
            arguments,
            {"git": committed, "status": _status(project_root, paths, timeout)},
            status="ok" if committed["ok"] else "error",
        )

    if action == "branch":
        branch = str(arguments.get("branch", "")).strip()
        if not branch:
            listed = _run_git(paths["gitdir"], project_root, ["branch", "--list"], timeout=timeout)
            return tool_result(
                FILE_METADATA["name"],
                arguments,
                {"git": listed, "status": _status(project_root, paths, timeout)},
                status="ok" if listed["ok"] else "error",
            )
        error = _validate_branch(branch)
        if error:
            return tool_error(FILE_METADATA["name"], arguments, error)
        if arguments.get("create") is True:
            if arguments.get("confirm") is not True:
                return tool_error(FILE_METADATA["name"], arguments, "branch create requires confirm=true")
            created = _run_git(paths["gitdir"], project_root, ["branch", branch], timeout=timeout)
            return tool_result(
                FILE_METADATA["name"],
                arguments,
                {"git": created, "status": _status(project_root, paths, timeout)},
                status="ok" if created["ok"] else "error",
            )
        listed = _run_git(paths["gitdir"], project_root, ["branch", "--list", branch], timeout=timeout)
        return tool_result(
            FILE_METADATA["name"],
            arguments,
            {"git": listed, "exists": bool(listed["stdout"]), "status": _status(project_root, paths, timeout)},
            status="ok" if listed["ok"] else "error",
        )

    if action == "checkout":
        branch = str(arguments.get("branch", "")).strip()
        error = _validate_branch(branch)
        if error:
            return tool_error(FILE_METADATA["name"], arguments, error)
        args = ["checkout", "-b", branch] if arguments.get("create") is True else ["checkout", branch]
        checked = _run_git(paths["gitdir"], project_root, args, timeout=timeout)
        return tool_result(
            FILE_METADATA["name"],
            arguments,
            {"git": checked, "status": _status(project_root, paths, timeout)},
            status="ok" if checked["ok"] else "error",
        )

    if action in {"pull", "push"}:
        remote_name = str(arguments.get("remote_name", "agent")).strip()
        remote_url = arguments.get("remote_url")
        ok, error = _configure_remote(
            paths,
            project_root,
            remote_name=remote_name,
            remote_url=str(remote_url) if remote_url else None,
            allow_origin=arguments.get("allow_origin") is True,
            timeout=timeout,
        )
        if not ok:
            return tool_error(FILE_METADATA["name"], arguments, error or "failed to configure remote")

        branch = str(arguments.get("branch") or _current_branch(paths["gitdir"], project_root, timeout) or "").strip()
        error = _validate_branch(branch)
        if error:
            return tool_error(FILE_METADATA["name"], arguments, error)
        if action == "push":
            pushed = _run_git(paths["gitdir"], project_root, ["push", "-u", remote_name, branch], timeout=timeout)
            return tool_result(
                FILE_METADATA["name"],
                arguments,
                {"git": pushed, "status": _status(project_root, paths, timeout)},
                status="ok" if pushed["ok"] else "error",
            )
        pulled = _run_git(paths["gitdir"], project_root, ["pull", "--ff-only", remote_name, branch], timeout=timeout)
        return tool_result(
            FILE_METADATA["name"],
            arguments,
            {"git": pulled, "status": _status(project_root, paths, timeout)},
            status="ok" if pulled["ok"] else "error",
        )

    return tool_error(FILE_METADATA["name"], arguments, f"unsupported action: {action}")


if __name__ == "__main__":
    standard_main(FILE_METADATA, run)
