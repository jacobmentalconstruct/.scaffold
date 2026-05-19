"""
FILE: local_agent_bootstrap.py
ROLE: Local-agent launch packet generator.
WHAT IT DOES:
  - Aggregates host, workspace, command, dependency, journal, and constraint context
  - Emits a JSON or Markdown packet for a local/podded agent
  - Does not write by default; optional writes go under ignored runtime exports
HOW TO USE:
  - python src/tools/local_agent_bootstrap.py metadata
  - python src/tools/local_agent_bootstrap.py run --input-json '{"project_root": ".", "format": "markdown"}'
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.append(str(Path(__file__).resolve().parents[1]))
from common import ensure_dir, standard_main, tool_error, tool_result, write_json
from tools.dependency_env_check import run as run_dependency_env_check
from tools.git_private_workspace import run as run_git_private_workspace
from tools.host_capability_probe import run as run_host_capability_probe
from tools.journal_query import run as run_journal_query
from tools.project_command_profile import run as run_project_command_profile
from tools.session_evidence_store import run as run_session_evidence_store
from tools.workspace_boundary_audit import run as run_workspace_boundary_audit


FILE_METADATA = {
    "tool_name": "local_agent_bootstrap",
    "version": "1.0.0",
    "entrypoint": "src/tools/local_agent_bootstrap.py",
    "category": "bootstrap",
    "summary": "Aggregate host/workspace/command/dependency/journal/constraint context into a local-agent launch packet.",
    "mcp_name": "local_agent_bootstrap",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_root": {"type": "string", "default": "."},
            "format": {"type": "string", "enum": ["json", "markdown"], "default": "json"},
            "write": {"type": "boolean", "default": False},
            "journal_limit": {"type": "integer", "default": 5},
            "include_markdown": {"type": "boolean", "default": True},
            "include_evidence_shelf": {"type": "boolean", "default": True},
            "evidence_session_id": {"type": "string", "default": "default"},
            "evidence_limit": {"type": "integer", "default": 10},
            "timeout_seconds": {"type": "number", "default": 5},
        },
        "additionalProperties": False,
    },
}


SYS_OPS_TOOLS = [
    "host_capability_probe",
    "workspace_boundary_audit",
    "project_command_profile",
    "dependency_env_check",
    "process_port_inspector",
    "dev_server_manager",
    "docker_ops",
    "k8s_ops",
    "secret_surface_audit",
    "runtime_artifact_cleaner",
    "local_agent_bootstrap",
    "git_private_workspace",
]

CONSTRAINT_DOCS = [
    "CONTRACT.md",
    "_docs/AGENT_GUIDE.md",
    "_docs/SETUP_DOCTRINE.md",
    "_docs/PARKING_WORKFLOW.md",
    "_docs/planning/NORTHSTARS.md",
    "_docs/TODO.md",
    "_docs/continuity/WE_ARE_HERE_NOW.md",
]


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_tool_call(name: str, runner, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        return runner(arguments)
    except Exception as exc:  # pragma: no cover - defensive aggregation guard
        return {"status": "error", "tool": name, "input": arguments, "result": {"message": str(exc)}}


def _read_excerpt(root: Path, rel: str, limit: int = 1200) -> dict[str, Any]:
    path = root / rel
    if not path.exists() or not path.is_file():
        return {"path": rel, "exists": False, "excerpt": ""}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"path": rel, "exists": True, "excerpt": "", "error": str(exc)}
    return {
        "path": rel,
        "exists": True,
        "excerpt": text[:limit],
        "truncated": len(text) > limit,
    }


def _journal_entries(project_root: Path, limit: int) -> dict[str, Any]:
    result = _safe_tool_call(
        "journal_query",
        run_journal_query,
        {"project_root": str(project_root), "limit": limit},
    )
    if result.get("status") != "ok":
        return result
    payload = result.get("result", {})
    entries = payload.get("entries", payload if isinstance(payload, list) else [])
    if not isinstance(entries, list):
        entries = []
    slim_entries = []
    for entry in entries[:limit]:
        if not isinstance(entry, dict):
            continue
        slim_entries.append({
            "entry_uid": entry.get("entry_uid", ""),
            "created_at": entry.get("created_at", ""),
            "status": entry.get("status", ""),
            "title": entry.get("title", ""),
            "tags": entry.get("tags", []),
        })
    return {
        "status": "ok",
        "tool": "journal_query",
        "input": {"project_root": str(project_root), "limit": limit},
        "result": {"entries": slim_entries, "entry_count": len(slim_entries)},
    }


def _tool_manifest_summary(project_root: Path) -> dict[str, Any]:
    path = project_root / "tool_manifest.json"
    if not path.exists():
        return {"exists": False, "tool_count": 0, "sys_ops_tools": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"exists": True, "tool_count": 0, "sys_ops_tools": [], "error": str(exc)}
    tools = data.get("tools", [])
    names = [item.get("tool_name", "") for item in tools if isinstance(item, dict)]
    return {
        "exists": True,
        "tool_count": len(names),
        "sys_ops_tools": [name for name in SYS_OPS_TOOLS if name in names],
        "missing_sys_ops_tools": [name for name in SYS_OPS_TOOLS if name not in names],
    }


def _packet_to_markdown(packet: dict[str, Any]) -> str:
    lines = [
        f"# Local Agent Launch Packet",
        "",
        f"- Project root: `{packet['project_root']}`",
        f"- Generated at: `{packet['generated_at']}`",
        f"- Tool count: `{packet['tool_manifest'].get('tool_count', 0)}`",
        "",
        "## Operating Envelope",
        "",
    ]
    for item in packet["operating_envelope"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Sys-Ops Tools", ""])
    for name in packet["tool_manifest"].get("sys_ops_tools", []):
        lines.append(f"- `{name}`")
    lines.extend(["", "## Commands", ""])
    commands = packet["command_profile"].get("result", {}).get("commands", [])
    if commands:
        for command in commands:
            lines.append(f"- `{command.get('id')}` ({command.get('kind')}): `{command.get('command_line', '')}`")
    else:
        lines.append("- No declared commands detected.")
    lines.extend(["", "## Dependency Warnings", ""])
    warnings = packet["dependency_check"].get("result", {}).get("warnings", [])
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- No dependency readiness warnings reported.")
    lines.extend(["", "## Private Git", ""])
    private_git = packet.get("private_git", {}).get("result", {})
    if private_git:
        lines.append(f"- Initialized: `{private_git.get('initialized')}`")
        lines.append(f"- Branch: `{private_git.get('branch', '')}`")
        lines.append(f"- Project .git exists: `{private_git.get('project_git_exists')}`")
        paths = private_git.get("private_paths", {})
        if paths.get("gitdir"):
            lines.append(f"- Private gitdir: `{paths.get('gitdir')}`")
    else:
        lines.append("- Private Git status unavailable.")
    lines.extend(["", "## Latest Journal Entries", ""])
    entries = packet["journal"].get("result", {}).get("entries", [])
    if entries:
        for entry in entries:
            lines.append(f"- `{entry.get('entry_uid')}` {entry.get('created_at')}: {entry.get('title')}")
    else:
        lines.append("- No journal entries returned.")
    lines.extend(["", "## Evidence Shelf", ""])
    evidence = packet.get("evidence_shelf", {}).get("result", {})
    if evidence:
        lines.append(f"- Session: `{evidence.get('session_id', '')}`")
        lines.append(f"- Items: `{evidence.get('item_count', 0)}`")
        summary = evidence.get("rolling_summary", "")
        if summary:
            lines.append(f"- Summary: {summary}")
        index = evidence.get("item_index", [])
        if index:
            lines.append("")
            for item in index[:10]:
                lines.append(f"- `{item.get('item_id')}` {item.get('kind')}: {item.get('summary')}")
        else:
            lines.append("- No evidence items returned.")
    else:
        lines.append("- No evidence shelf returned.")
    lines.extend(["", "## Constraint Docs", ""])
    for doc in packet["constraints"]:
        status = "present" if doc.get("exists") else "missing"
        lines.append(f"- `{doc['path']}`: {status}")
    lines.append("")
    return "\n".join(lines)


def _write_packet(project_root: Path, packet: dict[str, Any], rendered: str, fmt: str) -> str:
    export_dir = ensure_dir(project_root / ".dev-tools" / "runtime" / "local_agent_bootstrap")
    stamp = _now_stamp()
    if fmt == "markdown":
        path = export_dir / f"local_agent_bootstrap_{stamp}.md"
        path.write_text(rendered, encoding="utf-8")
    else:
        path = export_dir / f"local_agent_bootstrap_{stamp}.json"
        write_json(path, packet)
    return str(path)


def run(arguments: dict) -> dict:
    project_root = Path(arguments.get("project_root", ".")).resolve()
    if not project_root.is_dir():
        return tool_error(FILE_METADATA["tool_name"], arguments, f"Not a directory: {project_root}")

    fmt = str(arguments.get("format", "json"))
    write = bool(arguments.get("write", False))
    journal_limit = max(0, int(arguments.get("journal_limit", 5)))
    evidence_limit = max(0, int(arguments.get("evidence_limit", 10)))
    evidence_session_id = str(arguments.get("evidence_session_id", "default")).strip() or "default"
    timeout = float(arguments.get("timeout_seconds", 5))

    packet: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_root": str(project_root),
        "tool_manifest": _tool_manifest_summary(project_root),
        "host": _safe_tool_call("host_capability_probe", run_host_capability_probe, {"timeout_seconds": timeout}),
        "workspace": _safe_tool_call("workspace_boundary_audit", run_workspace_boundary_audit, {"project_root": str(project_root), "max_depth": 3}),
        "command_profile": _safe_tool_call("project_command_profile", run_project_command_profile, {"project_root": str(project_root)}),
        "dependency_check": _safe_tool_call("dependency_env_check", run_dependency_env_check, {"project_root": str(project_root), "timeout_seconds": timeout}),
        "private_git": _safe_tool_call("git_private_workspace", run_git_private_workspace, {"project_root": str(project_root), "action": "status", "timeout_seconds": timeout}),
        "journal": _journal_entries(project_root, journal_limit),
        "evidence_shelf": _safe_tool_call(
            "session_evidence_store",
            run_session_evidence_store,
            {
                "project_root": str(project_root),
                "action": "shelf",
                "session_id": evidence_session_id,
                "limit": evidence_limit,
            },
        ) if arguments.get("include_evidence_shelf", True) is not False else {"status": "skipped", "result": {"reason": "include_evidence_shelf=false"}},
        "constraints": [_read_excerpt(project_root, rel) for rel in CONSTRAINT_DOCS],
        "operating_envelope": [
            "Inspect before mutating: probe, audit, profile, check dependencies, then operate.",
            "Do not use raw terminal parity for this northstar; use declared command profiles and audited wrappers.",
            "Start/stop dev servers only through dev_server_manager with confirmation.",
            "Docker tag/push and Kubernetes live apply require explicit confirmation.",
            "Audit secret surfaces before packaging, pushing, or exporting.",
            "Use runtime_artifact_cleaner dry-run before deleting generated artifacts.",
            "Use git_private_workspace for agent checkpoints; do not use the user's origin by default.",
            "Write optional bootstrap exports only under ignored runtime paths.",
        ],
    }
    rendered = _packet_to_markdown(packet) if fmt == "markdown" else json.dumps(packet, indent=2)
    result: dict[str, Any] = {
        "format": fmt,
        "write": write,
        "packet": packet,
        "rendered": rendered if bool(arguments.get("include_markdown", True)) or fmt == "markdown" else "",
        "warnings": [
            "Bootstrap packet is an orientation artifact; verify live state before mutating workflows.",
        ],
    }
    if write:
        result["export_path"] = _write_packet(project_root, packet, rendered, fmt)
    return tool_result(FILE_METADATA["tool_name"], arguments, result)


if __name__ == "__main__":
    raise SystemExit(standard_main(FILE_METADATA, run))
