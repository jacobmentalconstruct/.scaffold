"""
FILE: src/lib/contract_migration.py
ROLE: Shared contract legacy-reference helpers for the BCC single-source state.
WHAT IT DOES: Defines the canonical contract path, BCC bundle map,
              historical section translation table, repo surface classes, and
              inventory scanning used by migration projections and docs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from src.lib.doc_registry import doc_entries, doc_id_for_relpath, doc_path


PRIMARY_CONTRACT_REL = "contracts/BCC.md"
LEGACY_CONTRACT_REL = "contracts/builder_constraint_contract.md"
TRANSLATION_APPENDIX_REF = "contracts/BCC.md Appendix A"

LEGACY_REFERENCE_TRANSLATIONS = {
    "§D": "BCC §10.8 Park Phase closure rule",
    "contract §D": "BCC §10.8 Park Phase closure rule",
    "§3.1": "BCC §5.10 Spine / envelope / event discipline + §5.13 Governed chat and projection surface rule",
    "chat-over-spine rule": "BCC §5.10 Spine / envelope / event discipline + §5.13 Governed chat and projection surface rule",
    "§0.10": "BCC Contract Use Preamble + §2.4 Contract primacy and doctrine recoverability rule + §5.13 Governed chat and projection surface rule",
    "contracts/builder_constraint_contract.md": "contracts/BCC.md",
}

LEGACY_REFERENCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("path", re.compile(r"contracts[/\\]builder_constraint_contract\.md")),
    ("path", re.compile(r"_docs[/\\]builder_constraint_contract\.md")),
    ("path", re.compile(r"`builder_constraint_contract\.md`")),
    ("section", re.compile(r"contract §D|§D\b")),
    ("section", re.compile(r"§3\.1\b")),
    ("section", re.compile(r"§0\.10\b")),
    ("phrase", re.compile(r"Park Phase Discipline")),
    ("phrase", re.compile(r"chat-over-spine rule")),
    ("phrase", re.compile(r"five artifacts")),
)


@dataclass(frozen=True)
class Bundle:
    bundle_id: str
    title: str
    bcc_sections: tuple[str, ...]
    legacy_refs: tuple[str, ...]
    notes: str = ""


BUNDLE_CATALOG: tuple[Bundle, ...] = (
    Bundle("bundle_1", "Definitions and preamble", ("§0", "Contract Use Preamble", "§2.4"), ("§0.10",)),
    Bundle("bundle_2", "Authority and approval", ("Authority Levels and Approval Scope",), ()),
    Bundle("bundle_3", "Workflow discipline and tranche doctrine", ("Builder Workflow Discipline Amendment", "§10.8"), ("§D",)),
    Bundle("bundle_4", "Documentation, persistence, and builder memory", ("Required Project Documentation", "§10"), ()),
    Bundle("bundle_5", "Boundary and storage rules", ("§1", "§2", "§6.1", "§6.10"), ("1.1", "1.2", "1.4")),
    Bundle("bundle_6", "Tooling and tool contract rules", ("§7",), ("Standard Tool Contract",)),
    Bundle("bundle_7", "Spine, graph, envelope, and dependency discipline", ("§5.10", "§5.11", "§5.12", "§5.13"), ("§3.1", "Pledge.6", "Pledge.7")),
    Bundle("bundle_8", "Quality, reporting, and Park Phase behavior", ("§9", "§10.8"), ("§D", "five artifacts")),
    Bundle("bundle_9", "Prohibited behaviors and pushback", ("§11", "§12"), ()),
    Bundle("bundle_10", "Sandbox, training, and generated contract surfaces", ("§6", "§7", "§8"), ("_docs/builder_constraint_contract.md",)),
)


def primary_contract_path(sidecar_root: Path) -> Path:
    return Path(sidecar_root) / PRIMARY_CONTRACT_REL


def active_contract_path(sidecar_root: Path) -> Path:
    return primary_contract_path(sidecar_root)


def contract_aliases(sidecar_root: Path) -> list[str]:
    return [PRIMARY_CONTRACT_REL]


def classify_surface(rel_path: str) -> tuple[str, bool]:
    rel = rel_path.replace("\\", "/")
    if rel == PRIMARY_CONTRACT_REL:
        return ("active_continuity", False)
    if rel == LEGACY_CONTRACT_REL:
        return ("historical_artifact", True)
    if rel == "README.md":
        return ("active_continuity", False)
    if rel.startswith("_docs/history/") or rel.startswith("_docs/migration/"):
        return ("historical_artifact", True)
    if rel.startswith("_docs/T") or rel.startswith("exports/"):
        return ("historical_artifact", True)
    if rel.startswith("_docs/continuity/LATEST_PARKED_TRANCHE") or rel.startswith("_docs/history/tranches/"):
        return ("historical_artifact", True)
    if rel.startswith(".tools/lib/builtin_templates/") or rel.startswith(".tools/lib/") or rel.startswith(".tools/tools/"):
        return ("generated_template", False)
    if rel.startswith("training_scenarios/") or rel.startswith("workspaces/installed_project_proof/"):
        return ("training_or_proof", False)
    if rel.startswith("src/"):
        return ("runtime_code", False)
    if rel.startswith("config/"):
        return ("config", False)
    return ("project_surface", False)


def iter_inventory_files(sidecar_root: Path) -> list[Path]:
    doc_roots = []
    for entry in doc_entries(sidecar_root):
        doc_roots.append(doc_path(sidecar_root, str(entry["doc_id"])))
        for alias in entry.get("legacy_aliases", []):
            doc_roots.append(Path(sidecar_root) / str(alias))
    roots = [
        Path(sidecar_root) / "contracts",
        Path(sidecar_root) / "src",
        Path(sidecar_root) / "config",
        Path(sidecar_root) / "_docs",
        Path(sidecar_root) / "training_scenarios",
        Path(sidecar_root) / ".tools",
        Path(sidecar_root) / "README.md",
        Path(sidecar_root) / "smoke_test.py",
        *doc_roots,
    ]
    files: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if root.is_file():
            rel = _relative_posix(root, sidecar_root)
            if rel not in seen:
                files.append(root)
                seen.add(rel)
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = _relative_posix(path, sidecar_root)
            if "/__pycache__/" in f"/{rel}/":
                continue
            if rel.startswith("cache/") or rel.startswith("data/") or rel.startswith("logs/") or rel.startswith("snapshots/"):
                continue
            if rel.endswith(".pyc") or rel.endswith(".sqlite3"):
                continue
            if rel not in seen:
                files.append(path)
                seen.add(rel)
    return files


def build_inventory(sidecar_root: Path, store=None) -> dict[str, Any]:
    sidecar_root = Path(sidecar_root)
    refs: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    primary_rel = PRIMARY_CONTRACT_REL
    nodes.append(_node("contract_document", primary_rel, "Binding Builder Constraint Contract", {"active": True}))

    for bundle in BUNDLE_CATALOG:
        nodes.append(_node("contract_bundle", bundle.bundle_id, bundle.title, {
            "bcc_sections": list(bundle.bcc_sections),
            "legacy_refs": list(bundle.legacy_refs),
            "notes": bundle.notes,
        }))
        edges.append(_edge(bundle.bundle_id, "maps_to", primary_rel, {"bcc_sections": list(bundle.bcc_sections)}))

    for path in iter_inventory_files(sidecar_root):
        rel = _relative_posix(path, sidecar_root)
        surface_class, historical = classify_surface(rel)
        registered_doc_id = doc_id_for_relpath(sidecar_root, rel)
        if registered_doc_id is not None:
            surface_class = "active_continuity"
            historical = False
        node_type = "continuity_surface" if surface_class == "active_continuity" else "project_surface"
        nodes.append(_node(node_type, rel, rel, {"surface_class": surface_class, "historical_preservation": historical}))
        text = _safe_read_text(path)
        if not text:
            continue
        found = False
        for ref_kind, pattern in LEGACY_REFERENCE_PATTERNS:
            for match in pattern.finditer(text):
                legacy_ref = match.group(0)
                translated = translate_legacy_ref(legacy_ref)
                status = "mapped" if translated else "unmapped"
                ref_id = _sha256_hex(f"{rel}|{legacy_ref}|{match.start()}".encode("utf-8"))[:20]
                refs.append({
                    "ref_id": f"legacy_ref_{ref_id}",
                    "source_path": rel,
                    "reference_kind": ref_kind,
                    "legacy_ref": legacy_ref,
                    "translated_ref": translated,
                    "translation_status": status,
                    "surface_class": surface_class,
                    "historical_preservation": 1 if historical else 0,
                    "metadata": {"offset": match.start()},
                })
                edges.append(_edge(rel, "mentions", primary_rel, {
                    "legacy_ref": legacy_ref,
                    "translated_ref": translated,
                    "translation_status": status,
                }))
                if translated:
                    bundle_id = bundle_for_ref(legacy_ref)
                    if bundle_id:
                        edges.append(_edge(rel, "maps_to", bundle_id, {"legacy_ref": legacy_ref}))
                else:
                    edges.append(_edge(rel, "requires_translation", primary_rel, {"legacy_ref": legacy_ref}))
                found = True
        if surface_class == "training_or_proof" and ("builder_constraint_contract.md" in text or rel.endswith("builder_constraint_contract.md")):
            edges.append(_edge(rel, "copies_to", primary_rel, {"surface_class": surface_class}))
        elif surface_class == "generated_template" and ("builder_constraint_contract.md" in text or rel.endswith("builder_constraint_contract.md")):
            edges.append(_edge(rel, "generated_from", primary_rel, {"surface_class": surface_class}))
        if not found and surface_class == "active_continuity":
            edges.append(_edge(rel, "verified_by", primary_rel, {"status": "clean"}))

    summary = {
        "active_contract": _relative_posix(active_contract_path(sidecar_root), sidecar_root),
        "compat_contract_present": False,
        "bundle_count": len(BUNDLE_CATALOG),
        "reference_count": len(refs),
        "mapped_reference_count": sum(1 for item in refs if item["translation_status"] == "mapped"),
        "unmapped_reference_count": sum(1 for item in refs if item["translation_status"] != "mapped"),
        "historical_reference_count": sum(1 for item in refs if item["historical_preservation"]),
        "journal_entry_count": _count_rows(store, "journal_entries"),
        "tranche_entry_count": _count_rows(store, "journal_entries", "kind = 'tranche'"),
    }
    return {"nodes": nodes, "edges": edges, "refs": refs, "summary": summary}


def translate_legacy_ref(legacy_ref: str) -> str:
    direct = LEGACY_REFERENCE_TRANSLATIONS.get(legacy_ref)
    if direct:
        return direct
    if "builder_constraint_contract.md" in legacy_ref:
        return PRIMARY_CONTRACT_REL
    if legacy_ref == "Park Phase Discipline":
        return "BCC §10.8 Park Phase closure rule"
    if legacy_ref == "five artifacts":
        return "BCC §10.8 Park Phase closure rule"
    return ""


def bundle_for_ref(legacy_ref: str) -> str:
    if legacy_ref in {"§D", "contract §D", "Park Phase Discipline", "five artifacts"}:
        return "bundle_8"
    if legacy_ref in {"§3.1", "chat-over-spine rule"}:
        return "bundle_7"
    if legacy_ref in {"§0.10"}:
        return "bundle_1"
    if "builder_constraint_contract.md" in legacy_ref:
        return "bundle_10"
    return ""


def _node(node_type: str, node_id: str, title: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "title": title,
        "metadata_json": metadata,
    }


def _edge(subject_id: str, predicate: str, object_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    edge_id = _sha256_hex(f"{subject_id}|{predicate}|{object_id}".encode("utf-8"))[:24]
    return {
        "edge_id": f"mig_{edge_id}",
        "subject_id": subject_id,
        "predicate": predicate,
        "object_id": object_id,
        "metadata_json": metadata,
    }


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _count_rows(store, table: str, where: str = "") -> int:
    if store is None:
        return 0
    try:
        sql = f"SELECT COUNT(*) AS n FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = store.query_one(sql)
        return int(row["n"]) if row else 0
    except Exception:
        return 0


def _relative_posix(path: Path | str, root: Path | str) -> str:
    path_obj = Path(path).resolve()
    root_obj = Path(root).resolve()
    try:
        rel = path_obj.relative_to(root_obj)
    except ValueError:
        return path_obj.name or str(path_obj)
    return rel.as_posix() or "."


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
