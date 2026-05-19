"""
FILE: scaffolds.py
ROLE: Project scaffold template management for the vendored authority kit.
WHAT IT DOES: Seeds builtin templates into the DB, lists available templates,
    and unpacks them to disk to create standard project layouts plus the
    discipline/regiment surfaces required for collaborative work.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from common import now_stamp
from lib.journal_store import get_blob, store_blob


BUILTIN_TEMPLATES_DIR = Path(__file__).resolve().parent / "builtin_templates"

# Template definitions — path_pattern is relative to project root.
BUILTIN_TEMPLATES = [
    {"template_id": "README.md", "path_pattern": "README.md", "file_type": "markdown", "description": "Project README"},
    {"template_id": "LICENSE.md", "path_pattern": "LICENSE.md", "file_type": "markdown", "description": "Project license"},
    {"template_id": "requirements.txt", "path_pattern": "requirements.txt", "file_type": "text", "description": "Python dependencies"},
    {"template_id": ".gitignore", "path_pattern": ".gitignore", "file_type": "text", "description": "Git ignore rules"},
    {"template_id": "setup_env.bat", "path_pattern": "setup_env.bat", "file_type": "batch", "description": "Windows environment setup"},
    {"template_id": "setup_env.sh", "path_pattern": "setup_env.sh", "file_type": "shell", "description": "Unix environment setup"},
    {"template_id": "run.bat", "path_pattern": "run.bat", "file_type": "batch", "description": "Windows run script"},
    {"template_id": "run.sh", "path_pattern": "run.sh", "file_type": "shell", "description": "Unix run script"},
    {"template_id": ".dev-tools/README.md", "path_pattern": ".dev-tools/README.md", "file_type": "markdown", "description": "Dev-tools onboarding note"},
    {"template_id": "ANY_NEW_CONVO_READ_THIS_FIRST.md", "path_pattern": "ANY_NEW_CONVO_READ_THIS_FIRST.md", "file_type": "markdown", "description": "Fresh-session onboarding surface"},
    {"template_id": "_docs/ARCHITECTURE.md", "path_pattern": "_docs/reference/ARCHITECTURE.md", "file_type": "markdown", "description": "Architecture overview"},
    {"template_id": "_docs/BCC.md", "path_pattern": "_docs/BCC.md", "file_type": "markdown", "description": "Active builder constraint contract"},
    {"template_id": "_docs/SETUP_DOCTRINE.md", "path_pattern": "_docs/SETUP_DOCTRINE.md", "file_type": "markdown", "description": "Project setup doctrine"},
    {"template_id": "_docs/SHARED_REGISTRY_WORKFLOW.md", "path_pattern": "_docs/SHARED_REGISTRY_WORKFLOW.md", "file_type": "markdown", "description": "Shared-registry workflow doctrine"},
    {"template_id": "_docs/WE_ARE_HERE_NOW.md", "path_pattern": "_docs/continuity/WE_ARE_HERE_NOW.md", "file_type": "markdown", "description": "Current state surface"},
    {"template_id": "_docs/TODO.md", "path_pattern": "_docs/TODO.md", "file_type": "markdown", "description": "Active work ledger"},
    {"template_id": "_docs/DEV_LOG.md", "path_pattern": "_docs/history/DEV_LOG.md", "file_type": "markdown", "description": "Development log"},
    {"template_id": "src/app.py", "path_pattern": "src/app.py", "file_type": "python", "description": "Composition root — lifecycle, wiring, entry point"},
    {"template_id": "src/orchestration/__init__.py", "path_pattern": "src/orchestration/__init__.py", "file_type": "python", "description": "Orchestration package init"},
    {"template_id": "src/core/__init__.py", "path_pattern": "src/core/__init__.py", "file_type": "python", "description": "Core domain package init"},
    {"template_id": "src/core/engine.py", "path_pattern": "src/core/engine.py", "file_type": "python", "description": "Core orchestrator — coordinates domain components, owns no logic itself"},
    {"template_id": "src/managers/__init__.py", "path_pattern": "src/managers/__init__.py", "file_type": "python", "description": "Managers package init"},
    {"template_id": "src/components/__init__.py", "path_pattern": "src/components/__init__.py", "file_type": "python", "description": "Components package init"},
    {"template_id": "src/ui/__init__.py", "path_pattern": "src/ui/__init__.py", "file_type": "python", "description": "UI package init"},
    {"template_id": "src/ui/main_window.py", "path_pattern": "src/ui/main_window.py", "file_type": "python", "description": "UI orchestrator — composes panes, routes events, owns no rendering logic"},
]


def _load_template_content(template_id: str) -> str:
    """Load template content from builtin_templates/ directory, or return a stub."""
    # Map template_id to filename (replace / with _)
    filename = template_id.replace("/", "_")
    tmpl_path = BUILTIN_TEMPLATES_DIR / filename
    if tmpl_path.exists():
        return tmpl_path.read_text(encoding="utf-8")

    # Also try with .tmpl extension
    tmpl_path_ext = BUILTIN_TEMPLATES_DIR / f"{filename}.tmpl"
    if tmpl_path_ext.exists():
        return tmpl_path_ext.read_text(encoding="utf-8")

    # Return a minimal stub
    return f"# {template_id}\n# Placeholder — replace with project-specific content.\n"


def seed_templates(connection: sqlite3.Connection) -> int:
    """Idempotent. Inserts builtin templates into scaffold_templates + blob_store. Returns count."""
    count = 0
    now = now_stamp()
    for tmpl in BUILTIN_TEMPLATES:
        existing = connection.execute(
            "SELECT template_id FROM scaffold_templates WHERE template_id = ?",
            (tmpl["template_id"],),
        ).fetchone()
        if existing:
            continue

        content = _load_template_content(tmpl["template_id"])
        bh = store_blob(connection, content, "text/plain")
        connection.execute(
            "INSERT INTO scaffold_templates(template_id, path_pattern, body_hash, file_type, description, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (tmpl["template_id"], tmpl["path_pattern"], bh, tmpl["file_type"], tmpl["description"], now),
        )
        count += 1
    return count


def list_templates(connection: sqlite3.Connection) -> list[dict]:
    """Return all scaffold template records."""
    rows = connection.execute(
        "SELECT template_id, path_pattern, body_hash, file_type, description, created_at FROM scaffold_templates ORDER BY template_id"
    ).fetchall()
    return [
        {
            "template_id": row["template_id"],
            "path_pattern": row["path_pattern"],
            "body_hash": row["body_hash"],
            "file_type": row["file_type"],
            "description": row["description"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def unpack_templates(
    connection: sqlite3.Connection,
    project_root: Path,
    *,
    overwrite: bool = False,
    template_ids: list[str] | None = None,
) -> list[dict]:
    """
    Write template content to disk. Skips existing files unless overwrite=True.
    Returns list of {path, template_id, status: 'created'|'skipped'|'overwritten'}.
    """
    templates = list_templates(connection)
    if template_ids:
        templates = [t for t in templates if t["template_id"] in template_ids]

    results = []
    for tmpl in templates:
        target_path = project_root / tmpl["path_pattern"]
        if target_path.exists() and not overwrite:
            results.append({"path": str(target_path), "template_id": tmpl["template_id"], "status": "skipped"})
            continue

        content = get_blob(connection, tmpl["body_hash"])
        if content is None:
            results.append({"path": str(target_path), "template_id": tmpl["template_id"], "status": "error_no_blob"})
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        status = "overwritten" if target_path.exists() and overwrite else "created"
        results.append({"path": str(target_path), "template_id": tmpl["template_id"], "status": status})

    return results
