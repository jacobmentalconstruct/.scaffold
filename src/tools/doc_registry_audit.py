"""
FILE: src/tools/doc_registry_audit.py
ROLE: Audit canonical documentation registry health and path drift.
WHAT IT DOES: Reports missing canonical docs, alias-backed resolutions,
              root-clutter violations, hardcoded legacy root-doc path hits,
              and registry/file mismatches without mutating project state.
"""

from __future__ import annotations

from pathlib import Path

from src.lib.doc_registry import (
    collection_records,
    doc_entries,
    doc_registry_path,
    doc_status_records,
    root_allowed_entries,
)


FILE_METADATA = {
    "tool_name": "doc_registry_audit",
    "version": "1.0.0",
    "entrypoint": "src/tools/doc_registry_audit.py",
    "category": "introspection",
    "summary": "Audit canonical doc registry health, alias use, and root clutter drift.",
    "mcp_name": "doc_registry_audit",
    "required_authority": "Observe",
    "input_schema": {
        "type": "object",
        "properties": {
            "include_hardcoded_hits": {
                "type": "boolean",
                "default": True,
                "description": "Include raw source hits for legacy root doc path strings.",
            }
        },
        "additionalProperties": False,
    },
}


def run(arguments: dict, state) -> dict:
    sidecar_root = Path(state.sidecar_root)
    include_hits = bool(arguments.get("include_hardcoded_hits", True))
    doc_rows = doc_status_records(sidecar_root)
    collection_rows = collection_records(sidecar_root)
    allowed_root = root_allowed_entries(sidecar_root) | {".gitignore", "smoke_test.py"}

    missing_docs = [row["doc_id"] for row in doc_rows if row["drift_status"] == "missing"]
    alias_backed = [row["doc_id"] for row in doc_rows if row["drift_status"] == "alias"]
    registry_mismatches = [row["doc_id"] for row in doc_rows if row["drift_status"] not in {"ok", "alias"}]
    collection_mismatches = [row["collection_id"] for row in collection_rows if row["drift_status"] != "ok"]

    root_doc_files = []
    root_policy_violations = []
    for path in sidecar_root.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".json"}:
            continue
        root_doc_files.append(path.name)
        if path.name not in allowed_root:
            root_policy_violations.append(path.name)

    hardcoded_hits = _find_hardcoded_hits(sidecar_root) if include_hits else []

    return {
        "status": "ok",
        "tool": FILE_METADATA["tool_name"],
        "input": arguments,
        "result": {
            "registry_path": str(doc_registry_path(sidecar_root).relative_to(sidecar_root)),
            "doc_count": len(doc_rows),
            "collection_count": len(collection_rows),
            "missing_docs": missing_docs,
            "alias_backed_docs": alias_backed,
            "registry_mismatches": registry_mismatches,
            "collection_mismatches": collection_mismatches,
            "root_doc_files": sorted(root_doc_files),
            "root_policy_violations": sorted(root_policy_violations),
            "hardcoded_legacy_root_doc_hits": hardcoded_hits,
        },
    }


def _find_hardcoded_hits(sidecar_root: Path) -> list[dict]:
    needles = sorted(
        {
            alias
            for entry in doc_entries(sidecar_root)
            for alias in entry.get("legacy_aliases", [])
            if "/" not in str(alias)
        }
    )
    search_roots = [
        sidecar_root / "src",
        sidecar_root / ".tools",
        sidecar_root / "config",
        sidecar_root / "contracts",
        sidecar_root / "smoke_test.py",
        sidecar_root / "README.md",
    ]
    hits: list[dict] = []
    for root in search_roots:
        if root.is_file():
            paths = [root]
        elif root.is_dir():
            paths = [path for path in root.rglob("*") if path.is_file()]
        else:
            continue
        for path in paths:
            rel = path.relative_to(sidecar_root).as_posix()
            if rel in {"config/doc_registry.json", "src/lib/doc_registry.py"}:
                continue
            if "/__pycache__/" in f"/{rel}/":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for needle in needles:
                if needle in text:
                    hits.append({"path": rel, "needle": needle})
    return hits
