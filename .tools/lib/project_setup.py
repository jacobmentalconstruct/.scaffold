from __future__ import annotations

from pathlib import Path
from typing import Any

from lib.contract import acknowledge_contract, get_contract_summary
from lib.journal_store import _connect, initialize_store, parse_tags, resolve_paths, write_entry
from lib.scaffolds import list_templates, seed_templates, unpack_templates


REQUIRED_ROOT_PATHS = [
    "src",
    "src/app.py",
    "src/core",
    "src/ui",
    "README.md",
    "LICENSE.md",
    "requirements.txt",
    "setup_env.bat",
    "run.bat",
    "_docs",
]

REQUIRED_DOC_PATHS = [
    "_docs/BCC.md",
    "_docs/SETUP_DOCTRINE.md",
    "_docs/TODO.md",
]

EQUIVALENT_DOC_GROUPS = {
    "current_state_surface": ["_docs/continuity/WE_ARE_HERE_NOW.md"],
    "handoff_surface": ["_docs/history/DEV_LOG.md", "_docs/continuity/ONBOARDING.md"],
}

RECOMMENDED_CORE_DIRS = [
    "src/core/config",
    "src/core/logging",
    "src/core/coordination",
    "src/core/representation",
    "src/core/persistence",
    "src/core/transformation",
    "src/core/analysis",
    "src/core/execution",
]

HANDSHAKE_READ_ORDER = [
    ".dev-tools/toolbox_manifest.json",
    ".dev-tools/tool_manifest.json",
    "_docs/BCC.md",
    "_docs/SETUP_DOCTRINE.md",
    "_docs/continuity/ONBOARDING.md",
    "_docs/continuity/WE_ARE_HERE_NOW.md",
    "_docs/TODO.md",
]


def _relative_status(project_root: Path, relative_path: str) -> dict[str, Any]:
    path = project_root / relative_path
    return {
        "path": relative_path.replace("\\", "/"),
        "exists": path.exists(),
        "is_dir": path.is_dir() if path.exists() else False,
    }


def _equivalent_group_status(project_root: Path) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for name, options in EQUIVALENT_DOC_GROUPS.items():
        present = [option for option in options if (project_root / option).exists()]
        groups.append({
            "name": name,
            "options": options,
            "present": present,
            "satisfied": bool(present),
        })
    return groups


def _contract_status(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"db_exists": False, "contract_seeded": False, "acknowledged": False}
    with _connect(db_path) as connection:
        return get_contract_summary(connection)


def audit_project_setup(project_root: str | Path, *, sidecar_root: str | Path | None = None) -> dict[str, Any]:
    paths = resolve_paths(project_root=project_root)
    root = Path(paths["project_root"])
    db_path = Path(paths["db_path"])
    sidecar = Path(sidecar_root).resolve() if sidecar_root else root / ".dev-tools"

    required = [_relative_status(root, item) for item in REQUIRED_ROOT_PATHS + REQUIRED_DOC_PATHS]
    missing_required = [item["path"] for item in required if not item["exists"]]
    equivalent_groups = _equivalent_group_status(root)
    recommended_missing = [
        item.replace("\\", "/")
        for item in RECOMMENDED_CORE_DIRS
        if not (root / item).exists()
    ]

    contract_status = _contract_status(db_path)
    ready = not missing_required and all(group["satisfied"] for group in equivalent_groups) and db_path.exists()

    return {
        "project_root": str(root),
        "sidecar_root": str(sidecar),
        "sidecar_present": sidecar.exists(),
        "journal_db_path": str(db_path),
        "journal_db_exists": db_path.exists(),
        "required_items": required,
        "missing_required": missing_required,
        "equivalent_groups": equivalent_groups,
        "recommended_missing": recommended_missing,
        "contract_status": contract_status,
        "handshake_read_order": HANDSHAKE_READ_ORDER,
        "ready": ready,
    }


def apply_project_setup(
    project_root: str | Path,
    *,
    actor_id: str | None = None,
    actor_type: str = "agent",
    overwrite: bool = False,
) -> dict[str, Any]:
    paths = initialize_store(project_root=project_root)
    root = Path(paths["project_root"])

    with _connect(paths["db_path"]) as connection:
        seeded = seed_templates(connection)
        files = unpack_templates(connection, root, overwrite=overwrite)
        available = len(list_templates(connection))
        receipt = None
        if actor_id:
            receipt = acknowledge_contract(connection, actor_id=actor_id, actor_type=actor_type)
        connection.commit()

    write_entry(
        project_root=str(root),
        action="create",
        title="Project setup applied",
        body="Initialized the project journal, unpacked the standard scaffold, and prepared the setup-first doctrine surfaces.",
        kind="setup",
        source="system",
        author="project_setup",
        tags=parse_tags(["setup", "bootstrap", "doctrine"]),
        metadata={
            "templates_seeded": seeded,
            "templates_available": available,
            "files_written": len(files),
            "acknowledged_actor": actor_id or "",
        },
    )

    return {
        "paths": paths,
        "templates_seeded": seeded,
        "templates_available": available,
        "files": files,
        "acknowledgment": receipt,
        "audit": audit_project_setup(root),
    }


def verify_project_setup(project_root: str | Path, *, sidecar_root: str | Path | None = None) -> dict[str, Any]:
    audit = audit_project_setup(project_root, sidecar_root=sidecar_root)
    verification = {
        "passed": audit["ready"] and audit["sidecar_present"],
        "project_root": audit["project_root"],
        "sidecar_present": audit["sidecar_present"],
        "missing_required": audit["missing_required"],
        "unsatisfied_equivalent_groups": [group["name"] for group in audit["equivalent_groups"] if not group["satisfied"]],
        "recommended_missing": audit["recommended_missing"],
        "contract_status": audit["contract_status"],
        "handshake_read_order": audit["handshake_read_order"],
    }
    return verification
