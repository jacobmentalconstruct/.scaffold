from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from common import DEFAULT_IGNORED_DIRS, read_json


RELEASE_PAYLOAD_MANIFEST = "release_payload_manifest.json"


def package_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def load_release_payload_manifest(source_toolbox_root: str | Path | None = None) -> dict[str, Any]:
    toolbox_root = Path(source_toolbox_root).resolve() if source_toolbox_root else package_root_from_here()
    manifest_path = toolbox_root / RELEASE_PAYLOAD_MANIFEST
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing release payload manifest: {manifest_path}")
    manifest = read_json(manifest_path)
    manifest["_manifest_path"] = str(manifest_path)
    manifest["_toolbox_root"] = str(toolbox_root)
    return manifest


def _manifest_items_by_path(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["path"]: item for item in manifest.get("top_level_entries", [])}


def release_payload_inventory(source_toolbox_root: str | Path | None = None) -> dict[str, Any]:
    manifest = load_release_payload_manifest(source_toolbox_root)
    toolbox_root = Path(manifest["_toolbox_root"])
    manifest_items = _manifest_items_by_path(manifest)
    existing_names = {entry.name for entry in toolbox_root.iterdir()}

    inventory: list[dict[str, Any]] = []
    for item in manifest.get("top_level_entries", []):
        path = toolbox_root / item["path"]
        inventory.append({
            "path": item["path"],
            "absolute_path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir(),
            "role": item["role"],
            "install": bool(item.get("install", False)),
            "notes": item.get("notes", ""),
        })

    unclassified = sorted(existing_names - set(manifest_items))
    return {
        "toolbox_root": str(toolbox_root),
        "manifest_path": manifest["_manifest_path"],
        "sidecar_dir_name": manifest.get("sidecar_dir_name", ".dev-tools"),
        "entries": inventory,
        "unclassified_top_level_entries": unclassified,
    }


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if any(part in DEFAULT_IGNORED_DIRS for part in relative_parts):
            continue
        if path.is_dir() and path.name in DEFAULT_IGNORED_DIRS:
            continue
        if path.is_file():
            files.append(path)
    return sorted(files)


def _collect_install_files(toolbox_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for item in manifest.get("top_level_entries", []):
        if not item.get("install", False):
            continue
        source_path = toolbox_root / item["path"]
        if not source_path.exists():
            continue
        if source_path.is_file():
            collected.append({
                "source": source_path,
                "relative_path": Path(item["path"]),
                "role": item["role"],
            })
            continue
        for child in _iter_files(source_path):
            collected.append({
                "source": child,
                "relative_path": child.relative_to(toolbox_root),
                "role": item["role"],
            })
    return collected


def install_sidecar(
    target_project_root: str | Path,
    *,
    source_toolbox_root: str | Path | None = None,
    overwrite: bool = False,
    preview: bool = False,
) -> dict[str, Any]:
    manifest = load_release_payload_manifest(source_toolbox_root)
    toolbox_root = Path(manifest["_toolbox_root"])
    target_root = Path(target_project_root).resolve()
    sidecar_dir = target_root / manifest.get("sidecar_dir_name", ".dev-tools")

    if sidecar_dir == toolbox_root:
        raise ValueError("Refusing to install the sidecar onto itself.")

    files = _collect_install_files(toolbox_root, manifest)
    results: list[dict[str, Any]] = []

    if not preview:
        sidecar_dir.mkdir(parents=True, exist_ok=True)

    for item in files:
        source_path = item["source"]
        target_path = sidecar_dir / item["relative_path"]
        if target_path.exists() and not overwrite:
            results.append({
                "path": str(target_path),
                "relative_path": str(item["relative_path"]).replace("\\", "/"),
                "role": item["role"],
                "status": "skipped",
            })
            continue
        if preview:
            results.append({
                "path": str(target_path),
                "relative_path": str(item["relative_path"]).replace("\\", "/"),
                "role": item["role"],
                "status": "would_create" if not target_path.exists() else "would_overwrite",
            })
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        existed = target_path.exists()
        shutil.copy2(source_path, target_path)
        results.append({
            "path": str(target_path),
            "relative_path": str(item["relative_path"]).replace("\\", "/"),
            "role": item["role"],
            "status": "overwritten" if existed else "created",
        })

    role_summary: dict[str, int] = {}
    for item in files:
        role_summary[item["role"]] = role_summary.get(item["role"], 0) + 1

    skipped_entries = [entry["path"] for entry in manifest.get("top_level_entries", []) if not entry.get("install", False)]
    return {
        "source_toolbox_root": str(toolbox_root),
        "target_project_root": str(target_root),
        "sidecar_dir": str(sidecar_dir),
        "preview": preview,
        "manifest_path": manifest["_manifest_path"],
        "role_summary": role_summary,
        "excluded_top_level_entries": skipped_entries,
        "files": results,
        "next_steps": [
            f'cd "{target_root}"',
            "review .dev-tools/START_HERE.html or OPEN_ME_FIRST.bat",
            "run project-local setup with python .dev-tools/src/tools/project_setup.py",
        ],
    }


def _extract_local_links(html_text: str) -> list[str]:
    links: list[str] = []
    for marker in ('href="', "src='", 'src="', "href='"):
        start = 0
        while True:
            found = html_text.find(marker, start)
            if found == -1:
                break
            value_start = found + len(marker)
            quote = marker[-1]
            value_end = html_text.find(quote, value_start)
            if value_end == -1:
                break
            raw = html_text[value_start:value_end].strip()
            start = value_end + 1
            if not raw or raw.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            links.append(raw)
    return links


def check_onboarding_site(toolbox_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(toolbox_root).resolve() if toolbox_root else package_root_from_here()
    manifest = read_json(root / "onboarding" / "manifest.json")
    required_files = [
        root / "START_HERE.html",
        root / "OPEN_ME_FIRST.bat",
        root / "OPEN_ME_FIRST.command",
        root / "launch_explorer.py",
        root / "assets" / "one-pass_screenshot.png",
        root / "assets" / "continuity_and_loop_screenshot.png",
        root / "onboarding" / "START_HERE.html",
        root / "onboarding" / "assets" / "toolbox.css",
        root / "_docs" / "EXPERIENTIAL_WORKFLOW.md",
    ]
    for page in manifest.get("pages", []):
        required_files.append(root / page["path"])
    for doc in manifest.get("docs", []):
        required_files.append(root / doc["path"])

    missing = sorted(str(path) for path in required_files if not path.exists())
    broken_links: list[dict[str, str]] = []
    stale_refs: list[dict[str, str]] = []
    stale_needles = [
        "_AgenticToolboxBuilderSET",
        "_nGraphMANIFOLD",
        "_AgentToolKIT",
        ".final-tools",
    ]
    html_files = [root / "START_HERE.html"] + list((root / "onboarding").rglob("*.html"))

    for html_path in html_files:
        text = html_path.read_text(encoding="utf-8")
        for link in _extract_local_links(text):
            candidate = (html_path.parent / link).resolve()
            if not candidate.exists():
                broken_links.append({
                    "file": str(html_path),
                    "link": link,
                })
        for needle in stale_needles:
            if needle in text:
                stale_refs.append({
                    "file": str(html_path),
                    "needle": needle,
                })

    docs_to_scan = [
        root / "README.md",
        root / "tool_manifest.json",
        root / "toolbox_manifest.json",
        root / "_docs" / "EXPERIENTIAL_WORKFLOW.md",
    ]
    for doc_path in docs_to_scan:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8", errors="replace")
        for needle in stale_needles:
            if needle in text:
                stale_refs.append({
                    "file": str(doc_path),
                    "needle": needle,
                })

    walkthrough_text = (root / "onboarding" / "START_HERE.html").read_text(encoding="utf-8")
    workflow_centered = "Experiential workflow centered" in walkthrough_text and "The Continuity Packet" in walkthrough_text

    return {
        "toolbox_root": str(root),
        "required_file_count": len(required_files),
        "missing_files": missing,
        "broken_links": broken_links,
        "stale_references": stale_refs,
        "workflow_centered": workflow_centered,
        "passed": not missing and not broken_links and not stale_refs and workflow_centered,
    }
