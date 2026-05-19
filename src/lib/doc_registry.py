"""
FILE: src/lib/doc_registry.py
ROLE: Canonical documentation registry + resolver for sidecar memory surfaces.
WHAT IT DOES: Resolves stable doc_ids to canonical or legacy-backed paths,
              exposes active continuity docs and historical collections, and
              supports doc-registry-driven cutover away from hardcoded root
              document paths.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DOC_REGISTRY_REL = "config/doc_registry.json"
ROOT_CANONICAL_DOCS = ("README.md", "LICENSE.md")


def doc_registry_path(sidecar_root: Path) -> Path:
    return Path(sidecar_root) / DOC_REGISTRY_REL


def load_registry(sidecar_root: Path) -> dict[str, Any]:
    path = doc_registry_path(sidecar_root)
    return json.loads(path.read_text(encoding="utf-8"))


def doc_entries(sidecar_root: Path) -> list[dict[str, Any]]:
    return list(load_registry(sidecar_root).get("docs", []))


def collection_entries(sidecar_root: Path) -> list[dict[str, Any]]:
    return list(load_registry(sidecar_root).get("collections", []))


def doc_entry(sidecar_root: Path, doc_id: str) -> dict[str, Any]:
    for entry in doc_entries(sidecar_root):
        if entry.get("doc_id") == doc_id:
            return entry
    raise KeyError(f"unknown doc_id: {doc_id}")


def collection_entry(sidecar_root: Path, collection_id: str) -> dict[str, Any]:
    for entry in collection_entries(sidecar_root):
        if entry.get("collection_id") == collection_id:
            return entry
    raise KeyError(f"unknown collection_id: {collection_id}")


def doc_id_for_relpath(sidecar_root: Path, rel_path: str) -> str | None:
    needle = rel_path.replace("\\", "/")
    for entry in doc_entries(sidecar_root):
        if entry.get("canonical_relpath") == needle:
            return str(entry["doc_id"])
        if needle in entry.get("legacy_aliases", []):
            return str(entry["doc_id"])
    return None


def canonical_doc_path(sidecar_root: Path, doc_id: str) -> Path:
    entry = doc_entry(sidecar_root, doc_id)
    return Path(sidecar_root) / str(entry["canonical_relpath"])


def canonical_doc_relpath(sidecar_root: Path, doc_id: str) -> str:
    return str(doc_entry(sidecar_root, doc_id)["canonical_relpath"])


def resolve_doc(sidecar_root: Path, doc_id: str) -> dict[str, Any]:
    entry = doc_entry(sidecar_root, doc_id)
    canonical_rel = str(entry["canonical_relpath"])
    canonical_path = Path(sidecar_root) / canonical_rel
    aliases = [str(item) for item in entry.get("legacy_aliases", [])]
    resolved_path = canonical_path
    resolved_rel = canonical_rel
    exists = canonical_path.is_file()
    if not exists:
        for alias in aliases:
            alias_path = Path(sidecar_root) / alias
            if alias_path.is_file():
                resolved_path = alias_path
                resolved_rel = alias
                exists = True
                break
    return {
        "doc_id": str(entry["doc_id"]),
        "entry": entry,
        "canonical_relpath": canonical_rel,
        "canonical_path": canonical_path,
        "resolved_relpath": resolved_rel,
        "resolved_path": resolved_path,
        "legacy_aliases": aliases,
        "exists": exists,
    }


def doc_path(sidecar_root: Path, doc_id: str) -> Path:
    return Path(resolve_doc(sidecar_root, doc_id)["resolved_path"])


def doc_relpath(sidecar_root: Path, doc_id: str) -> str:
    return str(resolve_doc(sidecar_root, doc_id)["canonical_relpath"])


def doc_exists(sidecar_root: Path, doc_id: str) -> bool:
    return bool(resolve_doc(sidecar_root, doc_id)["exists"])


def read_doc_text(sidecar_root: Path, doc_id: str, *, encoding: str = "utf-8") -> str:
    resolved = resolve_doc(sidecar_root, doc_id)
    if not resolved["exists"]:
        return ""
    return Path(resolved["resolved_path"]).read_text(encoding=encoding)


def doc_ids(sidecar_root: Path) -> list[str]:
    return [str(entry["doc_id"]) for entry in doc_entries(sidecar_root)]


def active_doc_entries(sidecar_root: Path) -> list[dict[str, Any]]:
    return [entry for entry in doc_entries(sidecar_root) if str(entry.get("surface_kind", "")) == "active_continuity"]


def active_doc_ids(sidecar_root: Path) -> list[str]:
    return [str(entry["doc_id"]) for entry in active_doc_entries(sidecar_root)]


def active_doc_relpaths(sidecar_root: Path) -> list[str]:
    return [str(entry["canonical_relpath"]) for entry in active_doc_entries(sidecar_root)]


def active_doc_aliases(sidecar_root: Path) -> list[str]:
    aliases: list[str] = []
    for entry in active_doc_entries(sidecar_root):
        aliases.extend(str(item) for item in entry.get("legacy_aliases", []))
    return aliases


def root_alias_doc_ids(sidecar_root: Path) -> list[str]:
    ids: list[str] = []
    for entry in active_doc_entries(sidecar_root):
        canonical = str(entry["canonical_relpath"])
        aliases = [str(item) for item in entry.get("legacy_aliases", [])]
        if canonical != str(Path(canonical).name) and any("/" not in alias for alias in aliases):
            ids.append(str(entry["doc_id"]))
    return ids


def root_alias_paths(sidecar_root: Path) -> list[str]:
    paths: list[str] = []
    for doc_id in root_alias_doc_ids(sidecar_root):
        entry = doc_entry(sidecar_root, doc_id)
        for alias in entry.get("legacy_aliases", []):
            alias = str(alias)
            if "/" not in alias:
                paths.append(alias)
    return sorted(paths)


def collection_records(sidecar_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in collection_entries(sidecar_root):
        canonical_dir = Path(sidecar_root) / str(entry["canonical_dir"])
        matches = sorted(canonical_dir.glob(str(entry["glob"]))) if canonical_dir.is_dir() else []
        digest_input = "\n".join(
            f"{path.name}:{path.stat().st_size}:{int(path.stat().st_mtime)}"
            for path in matches
        ).encode("utf-8")
        records.append({
            "collection_id": str(entry["collection_id"]),
            "canonical_relpath": str(entry["canonical_dir"]),
            "resolved_relpath": str(entry["canonical_dir"]),
            "temporal_class": str(entry.get("temporal_class", "")),
            "surface_kind": str(entry.get("surface_kind", "")),
            "exists": canonical_dir.is_dir(),
            "hash": hashlib.sha256(digest_input).hexdigest() if matches else "",
            "alias_count": len(entry.get("legacy_dirs", [])),
            "drift_status": "ok" if canonical_dir.is_dir() else "missing",
            "match_count": len(matches),
        })
    return records


def doc_status_records(sidecar_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in doc_entries(sidecar_root):
        resolved = resolve_doc(sidecar_root, str(entry["doc_id"]))
        canonical_path = Path(resolved["canonical_path"])
        resolved_path = Path(resolved["resolved_path"])
        body_hash = ""
        if resolved["exists"] and resolved_path.is_file():
            body_hash = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
        drift_status = "ok"
        if not resolved["exists"]:
            drift_status = "missing"
        elif resolved["resolved_relpath"] != resolved["canonical_relpath"]:
            drift_status = "alias"
        elif not canonical_path.is_file():
            drift_status = "missing"
        records.append({
            "doc_id": str(entry["doc_id"]),
            "canonical_relpath": str(resolved["canonical_relpath"]),
            "resolved_relpath": str(resolved["resolved_relpath"]),
            "temporal_class": str(entry.get("temporal_class", "")),
            "surface_kind": str(entry.get("surface_kind", "")),
            "exists": 1 if resolved["exists"] else 0,
            "hash": body_hash,
            "alias_count": len(resolved["legacy_aliases"]),
            "drift_status": drift_status,
        })
    return records


def root_allowed_entries(sidecar_root: Path) -> set[str]:
    allowed = set(ROOT_CANONICAL_DOCS)
    allowed.update(root_alias_paths(sidecar_root))
    return allowed
