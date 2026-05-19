"""
FILE: src/tools/workspace_boundary_audit.py
ROLE: Audit the project root, sidecar root, and confirm the sidecar's
      runtime folders exist and are contained.
WHAT IT DOES: Returns a structured report: project_root, sidecar_root,
              whether they coincide (dev scope), and the status of each
              required runtime folder. Pure Observe authority — no writes.
"""

from __future__ import annotations

from pathlib import Path

from src.lib.common import public_path, public_root_labels, resolve_paths, under


FILE_METADATA = {
    "tool_name": "workspace_boundary_audit",
    "version": "1.0.0",
    "entrypoint": "src/tools/workspace_boundary_audit.py",
    "category": "introspection",
    "summary": "Audit project root, sidecar root, and runtime folder containment.",
    "mcp_name": "workspace_boundary_audit",
    "required_authority": "Observe",
    "input_schema": {"type": "object", "properties": {}},
}


def run(arguments: dict, state) -> dict:
    paths = resolve_paths(state.sidecar_root)
    sidecar_root = Path(state.sidecar_root)
    project_root = Path(state.project_root)
    project_root_label, sidecar_root_label = public_root_labels(sidecar_root, project_root)
    dev_scope = sidecar_root.resolve() == project_root.resolve()

    folders = {
        "config": paths.config,
        "contracts": paths.contracts,
        "data": paths.data,
        "logs": paths.logs,
        "cache": paths.cache,
        "exports": paths.exports,
        "workspaces": paths.workspaces,
        "snapshots": paths.snapshots,
        "src": paths.src,
        "_docs": paths.docs,
    }
    folder_report = {}
    for name, p in folders.items():
        folder_report[name] = {
            "path": public_path(p, sidecar_root, sidecar_root_label),
            "exists": p.exists(),
            "is_dir": p.is_dir() if p.exists() else False,
            "contained_in_sidecar": under(sidecar_root, p),
        }

    safety_findings: list[str] = []
    if not paths.contract_file.is_file():
        safety_findings.append("contract file missing")
    if not paths.db_file.exists():
        safety_findings.append("data/sidecar.db missing — not yet installed?")
    if not folder_report["data"]["contained_in_sidecar"]:
        safety_findings.append("data/ escapes sidecar root")

    return {
        "status": "ok",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {
            "sidecar_root": sidecar_root_label,
            "project_root": project_root_label,
            "dev_scope": dev_scope,
            "contract_file": public_path(paths.contract_file, sidecar_root, sidecar_root_label),
            "contract_present": paths.contract_file.is_file(),
            "db_file": public_path(paths.db_file, sidecar_root, sidecar_root_label),
            "db_present": paths.db_file.is_file(),
            "folders": folder_report,
            "safety_findings": safety_findings,
            "boundary_invariant": "sidecar writes only inside .scaffold/ unless Apply/Export authority granted",
        },
    }
